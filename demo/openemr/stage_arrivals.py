"""Put a clinic's morning into OpenEMR, so "running late" is a real number.

**What this is, and what it is not.** Story three's claim is that EKYATRA can
tell a family the clinic is behind *without anybody recording that it is* —
the number is derived from the arrival timestamps a clerk's ordinary work
leaves behind. That derivation is the real thing, in
`adapters/hospital/openemr_db.py`, reading a database nobody wrote for us.

What this script does is stand in for the clerk's morning. At eleven o'clock a
real clinic already has four hours of arrivals behind it; a demo starting from
an empty tracker has none, and a delay cannot accumulate during a six-minute
film. So these are the same rows
`PatientTrackerService::manage_tracker_status()` writes when somebody saves an
appointment as "Arrived" — same table, same columns, same `NOW()` — put there
in advance rather than during the take.

Nothing here touches the delay itself. There is no "minutes behind" column in
OpenEMR to write, which is the entire point: this writes arrivals, and the
system infers the delay. A judge can verify that by changing one arrival time
and watching the figure move.

**Relative to now, deliberately.** An earlier version wrote fixed clock times
and the demo worked only in the late morning — at six in the evening every
appointment was in the past and nothing was waiting; at six in the morning
they were all in the future and the clinic was serenely on time. Both were
correct readings of nonsense data. Everything here is offset from the moment
the script runs, so the clinic is behind whenever anybody looks.

Writes with a privileged account, because seeding is setup and not the system
running. The connector's own account (`saathi_ro`) cannot do any of this, and
that is checked by `tests/test_clinic_flow.py`.

    python demo/openemr/stage_arrivals.py            # say what it would do
    python demo/openemr/stage_arrivals.py --write
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

CONTAINER = "hms-eval-mysql-1"
DATABASE = "openemr"

#: OpenEMR's own status codes. `@` and `~` both carry `toggle_setting_1`
#: (check-in) and both project to FHIR `arrived`; only the database knows
#: which of them a clerk chose, which is why `~` is worth seeding at all.
ARRIVED = "@"
ARRIVED_LATE = "~"
IN_ROOM = "<"


@dataclass(frozen=True)
class Session:
    """One patient's morning, as minutes either side of now.

    Negative is in the past. `in_room_after` is `None` for somebody still
    sitting in the corridor, which is the state that makes a clinic late —
    a patient who has been seen contributes a finished wait, and a patient
    who never arrived contributes nothing at all.
    """

    label: str
    #: How long ago their appointment was meant to start.
    appointment_minutes_ago: int
    #: How long ago they actually turned up.
    arrived_minutes_ago: int
    #: How long ago they were taken in, or None if they are still waiting.
    in_room_minutes_ago: int | None
    late: bool = False


#: A clinic about an hour and a half behind. Two still waiting, one seen — the
#: shape that makes the derived figure meaningful rather than a single
#: patient's bad luck, and the shape the median is there to handle.
MORNING = (
    Session("seen, after a long wait", 150, 158, 55),
    Session("arrived on time, still waiting", 120, 130, None),
    Session("arrived late, still waiting", 90, 85, None, late=True),
)


def sql(statement: str, *, write: bool) -> str:
    """Run one statement, or print it. Returns stdout."""
    if not write:
        print(f"    would run: {' '.join(statement.split())[:150]}")
        return ""
    done = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "mariadb", "-uroot", "-proot", DATABASE, "-N", "-B"],
        input=statement,
        text=True,
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"mariadb refused that: {done.stderr.strip()[:300]}")
    return done.stdout.strip()


def appointments_today(now: datetime, *, write: bool) -> list[tuple[str, str]]:
    """`(eid, pid)` for today's non-recurring, patient-bearing appointments.

    Both filters matter. `manage_tracker_status()` returns early when
    `pc_recurrtype != 0`, so a recurring appointment never gets a tracker row
    however it is saved; and a provider event has no patient, so it never gets
    one either. Seeding against either would produce rows OpenEMR itself
    would not have written.
    """
    rows = sql(
        f"""
        SELECT e.pc_eid, e.pc_pid
        FROM openemr_postcalendar_events e
        JOIN openemr_postcalendar_categories c ON c.pc_catid = e.pc_catid
        WHERE e.pc_eventDate = '{now.date().isoformat()}'
          AND e.pc_pid IS NOT NULL
          AND e.pc_recurrtype = 0
          AND c.pc_cattype = 0
        ORDER BY e.pc_startTime
        """,
        write=True,  # always read, even in a dry run: we report what we found
    )
    found = []
    for line in rows.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] and parts[1] != "NULL":
            found.append((parts[0], parts[1]))
    return found


def stage(now: datetime, *, write: bool) -> int:
    booked = appointments_today(now, write=write)
    if not booked:
        print(
            f"  no non-recurring patient appointments on {now.date()}.\n"
            "  Seed them first: make openemr-seed-write"
        )
        return 1

    # Everybody except the last one. Two reasons, and both matter: a clinic
    # at mid-morning has not seen its whole day yet, so staging every patient
    # as arrived is the unrealistic version; and a family who has *not* turned
    # up is the only one the "the clinic is behind" message can help. Staging
    # all of them left that path with nobody to talk to.
    staging = booked[:-1] if len(booked) > 1 else booked
    still_to_come = booked[len(staging):]
    print(
        f"  {len(booked)} appointment(s) today; staging {min(len(staging), len(MORNING))} "
        f"as arrived, leaving {len(still_to_come)} still to come"
    )

    # Clear only today's tracker, so running this twice does not stack two
    # mornings on top of each other and report a four-hour delay.
    sql(
        f"""
        DELETE e FROM patient_tracker_element e
        JOIN patient_tracker t ON t.id = e.pt_tracker_id
        WHERE t.apptdate = '{now.date().isoformat()}';
        DELETE FROM patient_tracker WHERE apptdate = '{now.date().isoformat()}';
        """,
        write=write,
    )

    for (eid, pid), session in zip(staging, MORNING, strict=False):
        appointment_at = now - timedelta(minutes=session.appointment_minutes_ago)
        arrived_at = now - timedelta(minutes=session.arrived_minutes_ago)

        # The appointment's own time has to agree with the tracker row, or the
        # derived wait is measured against a slot nobody was given.
        sql(
            f"""
            UPDATE openemr_postcalendar_events
            SET pc_startTime = '{appointment_at:%H:%M:%S}',
                pc_endTime = '{(appointment_at + timedelta(minutes=30)):%H:%M:%S}',
                pc_apptstatus = '{ARRIVED_LATE if session.late else ARRIVED}',
                pc_time = NOW()
            WHERE pc_eid = {eid};
            """,
            write=write,
        )

        steps = [(ARRIVED_LATE if session.late else ARRIVED, arrived_at)]
        if session.in_room_minutes_ago is not None:
            steps.append((IN_ROOM, now - timedelta(minutes=session.in_room_minutes_ago)))

        sql(
            f"""
            INSERT INTO patient_tracker
                (date, apptdate, appttime, eid, pid, original_user, encounter, lastseq)
            VALUES (NOW(), '{now.date().isoformat()}', '{appointment_at:%H:%M:%S}',
                    {eid}, {pid}, 'admin', 0, {len(steps)});
            """,
            write=write,
        )
        for seq, (status, at) in enumerate(steps, start=1):
            sql(
                f"""
                INSERT INTO patient_tracker_element
                    (pt_tracker_id, start_datetime, room, status, seq, user)
                SELECT id, '{at:%Y-%m-%d %H:%M:%S}', '', '{status}', {seq}, 'admin'
                FROM patient_tracker
                WHERE apptdate = '{now.date().isoformat()}' AND eid = {eid};
                """,
                write=write,
            )
        waited = session.appointment_minutes_ago - (session.in_room_minutes_ago or 0)
        print(
            f"    appt {eid}: {session.label} — slot {appointment_at:%H:%M}, "
            f"arrived {arrived_at:%H:%M}, {waited} min past their slot"
        )

    if not write:
        print("\n  Nothing was written. Pass --write to do it.")
        return 0

    print("\n  Staged. What EKYATRA now derives from it:")
    _report(now)
    return 0


def _report(now: datetime) -> None:
    """Read it back through the real adapter, not through this script's maths.

    Worth the extra import: a script that printed its own expectation would
    agree with itself no matter what it had actually written.
    """
    sys.path.insert(0, "backend")
    try:
        from saathi.adapters.hospital.openemr_db import OpenEMRDatabase
    except ImportError as exc:
        print(f"    (could not load the adapter to check: {exc})")
        return

    database = OpenEMRDatabase(
        host="127.0.0.1", port=3307, database=DATABASE,
        user="saathi_ro", password="saathi_ro",
    )
    flow = database.clinic_flow(on=now.date())
    if flow is None:
        print(
            "    the read-only account could not reach the database on 127.0.0.1:3307.\n"
            "    Bring it up with demo/openemr/docker-compose.yml, which publishes the port."
        )
        return
    print(f"    {flow.summary()}")
    behind = flow.running_behind()
    if behind is None:
        print("    nothing derived — check the arrival times above")
    else:
        print(f"    a family would be told to leave about {int(behind.total_seconds() // 60)} min later")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="actually write the rows")
    args = parser.parse_args(argv)
    return stage(datetime.now(), write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
