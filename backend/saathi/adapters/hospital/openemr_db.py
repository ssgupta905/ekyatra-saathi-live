"""A read-only window onto OpenEMR's own arrival timestamps.

The one thing in this project that reaches past an API and into a database,
and the reason is narrow: the minutes a family waits exist nowhere else. See
`ports/clinic_flow.py` for the full account — in short, `Appointment.status`
flips to `arrived` over FHIR and the time of that flip is not projected, and
"Arrived" and "Arrived late" collapse onto the same FHIR status.

Three properties keep this honest:

**It only ever reads.** Every statement here is a `SELECT`. The connection is
opened read-only where the driver supports it, and the queries are the only
SQL in the module — there is no insert, update or delete to find. Writes
continue to go through the standard API, which is what "OpenEMR unchanged"
means: nothing is added to it and nothing of ours is written into it by hand.

**It reads OpenEMR's semantics rather than guessing them.** Which status codes
mean "arrived" and which mean "gone" are not hardcoded. OpenEMR carries them
as flags on the `apptstat` list — `toggle_setting_1` for check-in,
`toggle_setting_2` for check-out — and its own `collect_checkin()` and
`collect_checkout()` read them the same way. A site that renames a status, or
adds one, keeps working.

**It fails to `None`, never to a number.** An unreachable database, a missing
driver, a schema that does not look like OpenEMR's: all of them produce
`None`, which the Console renders as "arrived" with no delay claimed. The one
outcome that must never happen is a plausible delay with nothing behind it,
because a family rearranges their day around it.

Two preconditions found in OpenEMR's source, both of which the seeder has to
respect or this returns nothing at all:

* `PatientTrackerService::manage_tracker_status()` returns early when
  `pc_recurrtype != 0`, so **a recurring appointment gets no tracker row.**
* A tracker row needs a patient, so provider events never produce one — which
  is fine, and is why leave is read over FHIR instead.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ...ports.clinic_flow import Arrival, ClinicFlow

logger = logging.getLogger(__name__)

#: Which `apptstat` codes mean what, read from OpenEMR's own list rather than
#: assumed. `option_id` is the single-character status stored on an event.
_FLAGS_SQL = """
SELECT option_id, toggle_setting_1 AS is_checkin, toggle_setting_2 AS is_checkout
FROM list_options
WHERE list_id = 'apptstat' AND activity = 1
"""

#: Every status change for one day's sessions, newest irrelevant — the whole
#: ladder is needed, because "arrived then taken in" and "arrived and still
#: waiting" differ only by the presence of a later row.
#:
#: `LENGTH(seq), seq` because `seq` is a varchar in this schema and a plain
#: sort would put 10 before 2.
_TRACKER_SQL = """
SELECT t.eid              AS appointment_ref,
       t.pid              AS patient_ref,
       t.apptdate         AS appt_date,
       t.appttime         AS appt_time,
       e.status           AS status,
       e.start_datetime   AS at
FROM patient_tracker t
JOIN patient_tracker_element e ON e.pt_tracker_id = t.id
WHERE t.apptdate = %s
ORDER BY t.id, LENGTH(e.seq), e.seq
"""

#: "In an exam room" has no flag of its own in `list_options`: it is neither a
#: check-in nor a check-out. These are OpenEMR's shipped codes for it, and a
#: site that invented another one would simply see the wait keep running —
#: which is wrong in the safe direction, towards "still waiting".
_IN_ROOM_CODES = frozenset({"<", "+"})


@dataclass
class OpenEMRDatabase:
    """`ClinicFlowSource` over OpenEMR's MariaDB, read-only."""

    host: str
    database: str
    user: str
    password: str
    port: int = 3306
    #: Matches the rest of this package: a slow database must not hold up a poll.
    timeout: float = 10.0

    name: str = "openemr-db"

    _flags: dict[str, tuple[bool, bool]] | None = None

    # ---------------- the port ----------------

    def clinic_flow(self, *, on: date) -> ClinicFlow | None:
        """One day's arrivals, or None when the database cannot answer.

        Returns `None` rather than an empty `ClinicFlow` on failure, because
        the two mean opposite things: an empty flow is "this clinic saw nobody
        today", and `None` is "we do not know". Reporting the first when the
        second is true would have a Console announce an empty waiting room.
        """
        try:
            flags = self._status_flags()
            rows = self._query(_TRACKER_SQL, (on.isoformat(),))
        except Exception as exc:  # noqa: BLE001 — any failure is the same answer
            logger.warning("openemr-db: cannot read today's arrivals: %s", exc)
            return None

        arrivals = _arrivals_from(rows, flags)
        return ClinicFlow(on=on, observed_at=datetime.now().astimezone(), arrivals=arrivals)

    @property
    def live(self) -> bool:
        """Whether the database answers at all. Used by the Console's banner."""
        try:
            self._query("SELECT 1", ())
        except Exception:  # noqa: BLE001
            return False
        return True

    # ---------------- internals ----------------

    def _status_flags(self) -> dict[str, tuple[bool, bool]]:
        """`option_id -> (is_checkin, is_checkout)`, read once and remembered.

        Cached because it is configuration, not data: a clinic does not
        redefine what "arrived" means during a session, and re-reading it on
        every poll would be a query to learn nothing.
        """
        if self._flags is None:
            self._flags = {
                str(row["option_id"]): (bool(row["is_checkin"]), bool(row["is_checkout"]))
                for row in self._query(_FLAGS_SQL, ())
            }
            if not self._flags:
                raise RuntimeError("list_options has no apptstat entries; this is not OpenEMR")
        return self._flags

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as exc:  # pragma: no cover - a missing extra
            raise RuntimeError(
                "PyMySQL is needed to read OpenEMR's arrival times; "
                "install the 'openemr' extra, or run without it and the "
                "Console will report arrival without a delay"
            ) from exc

        connection = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            cursorclass=DictCursor,
            connect_timeout=self.timeout,
            read_timeout=self.timeout,
            # Belt and braces with the module docstring's claim: even a bug in
            # here cannot write, because the session will not allow it.
            init_command="SET SESSION TRANSACTION READ ONLY",
            autocommit=True,
        )
        try:
            yield connection
        finally:
            connection.close()

    def _query(self, sql: str, params: Sequence[object]) -> list[dict]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            return list(cursor.fetchall())


def _arrivals_from(
    rows: Sequence[dict], flags: dict[str, tuple[bool, bool]]
) -> tuple[Arrival, ...]:
    """Fold the status ladder into one `Arrival` per appointment.

    The table is append-only — one row per status change — so this walks the
    rows in order and keeps the *first* arrival time and the *first* in-room
    time. First rather than last: a patient sent back to the waiting room and
    re-marked arrived has still been waiting since they first turned up, and
    taking the latest row would reset their wait to zero every time a clerk
    touched the record.
    """
    sessions: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        appointment_ref = str(row.get("appointment_ref") or "")
        patient_ref = str(row.get("patient_ref") or "")
        scheduled = _scheduled_at(row)
        at = _as_datetime(row.get("at"))
        status = str(row.get("status") or "")
        if not appointment_ref or scheduled is None or at is None:
            continue

        session = sessions.setdefault(
            (appointment_ref, patient_ref),
            {
                "scheduled_at": scheduled,
                "arrived_at": None,
                "in_room_at": None,
                "departed_at": None,
                "flagged_late": False,
            },
        )

        is_checkin, is_checkout = flags.get(status, (False, False))
        if is_checkin and session["arrived_at"] is None:
            session["arrived_at"] = at
            # "~" is OpenEMR's "Arrived late". Both it and "@" are check-in
            # flags and both project to FHIR `arrived`, so this distinction
            # exists only here.
            session["flagged_late"] = status == "~"
        elif status in _IN_ROOM_CODES and session["in_room_at"] is None:
            session["in_room_at"] = at
        elif is_checkout and session["departed_at"] is None:
            session["departed_at"] = at

    return tuple(
        Arrival(appointment_ref=appointment_ref, patient_ref=patient_ref, **session)
        for (appointment_ref, patient_ref), session in sessions.items()
    )


def _scheduled_at(row: dict) -> datetime | None:
    """`apptdate` + `appttime`, which the schema keeps in separate columns."""
    appt_date, appt_time = row.get("appt_date"), row.get("appt_time")
    if appt_date is None or appt_time is None:
        return None
    try:
        day = appt_date if isinstance(appt_date, date) else date.fromisoformat(str(appt_date))
        moment = datetime.combine(day, datetime.min.time()) + _as_timedelta(appt_time)
    except (TypeError, ValueError):
        return None
    return moment.astimezone()


def _as_datetime(raw: object) -> datetime | None:
    if isinstance(raw, datetime):
        return raw.astimezone() if raw.tzinfo is None else raw
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(str(raw)).astimezone()
    except ValueError:
        return None


def _as_timedelta(raw: object):
    """`appttime` arrives as a `timedelta` from the driver, or as a string."""
    from datetime import timedelta

    if isinstance(raw, timedelta):
        return raw
    parts = str(raw).split(":")
    try:
        hours, minutes, seconds = (int(part) for part in (parts + ["0", "0", "0"])[:3])
    except ValueError as exc:
        raise ValueError(f"unreadable appointment time {raw!r}") from exc
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


__all__ = ["OpenEMRDatabase"]
