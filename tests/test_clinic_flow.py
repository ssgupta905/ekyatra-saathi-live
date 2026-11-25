"""How far behind a clinic is running, derived from timestamps nobody typed.

Nobody at a hospital marks the clinic as late — there is no such field. What
exists is an append-only log of appointment status changes, written as a side
effect of the ordinary calendar save a clerk already performs. The delay is an
inference over that log, and these tests pin the four ways the inference can
be quietly wrong:

* resetting a patient's wait when a clerk touches their record twice;
* counting a patient who never arrived as having waited no time, which drags a
  late clinic towards "on time" with every no-show;
* letting one unusual four-hour wait become the number a dozen families are
  told;
* and reporting a delay when the database could not be read at all.

The rows in `REAL_ROWS` came out of a running OpenEMR 8.6 after marking three
patients arrived through the calendar, so the shapes here — a `date` object, a
`timedelta` for the time of day, single-character statuses — are the driver's,
not ones chosen to be convenient.
"""

from __future__ import annotations

import ast
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from saathi.adapters.hospital.openemr_db import OpenEMRDatabase, _arrivals_from
from saathi.ports.clinic_flow import Arrival, ClinicFlow, ClinicFlowSource

#: OpenEMR's own flags, as read from `list_options` on a live instance.
FLAGS: dict[str, tuple[bool, bool]] = {
    "-": (False, False), "*": (False, False), "+": (False, False),
    "x": (False, False), "?": (False, False),
    "@": (True, False),   # Arrived
    "~": (True, False),   # Arrived late
    "!": (False, True),   # Left without visit
    "<": (False, False),  # In exam room — neither check-in nor check-out
    ">": (False, True),   # Checked out
}

#: A clinic running late: three booked, three arrived, one seen.
REAL_ROWS = [
    {"appointment_ref": "41", "patient_ref": "3", "appt_date": date(2026, 11, 25),
     "appt_time": timedelta(hours=9), "status": "@", "at": datetime(2026, 11, 25, 8, 52)},
    {"appointment_ref": "41", "patient_ref": "3", "appt_date": date(2026, 11, 25),
     "appt_time": timedelta(hours=9), "status": "<", "at": datetime(2026, 11, 25, 10, 35)},
    {"appointment_ref": "42", "patient_ref": "1", "appt_date": date(2026, 11, 25),
     "appt_time": timedelta(hours=9, minutes=30), "status": "@",
     "at": datetime(2026, 11, 25, 9, 20)},
    {"appointment_ref": "43", "patient_ref": "2", "appt_date": date(2026, 11, 25),
     "appt_time": timedelta(hours=10), "status": "~", "at": datetime(2026, 11, 25, 10, 5)},
]

NOON_ISH = datetime(2026, 11, 25, 11, 30).astimezone()


def _flow(rows=REAL_ROWS, *, observed_at=NOON_ISH) -> ClinicFlow:
    return ClinicFlow(
        on=date(2026, 11, 25),
        observed_at=observed_at,
        arrivals=_arrivals_from(rows, FLAGS),
    )


class TestReadingTheLadder:
    def test_arrival_in_room_and_waiting_are_distinguished(self) -> None:
        flow = _flow()
        by_ref = {a.appointment_ref: a for a in flow.arrivals}

        assert by_ref["41"].in_room_at == datetime(2026, 11, 25, 10, 35).astimezone()
        assert not by_ref["41"].is_waiting
        assert by_ref["42"].is_waiting
        assert by_ref["43"].is_waiting
        assert len(flow.waiting) == 2
        assert len(flow.seen) == 1

    def test_arrived_late_is_captured(self) -> None:
        """FHIR maps "Arrived" and "Arrived late" onto the same status.

        The distinction exists only in the database, so if it is not read here
        it does not exist anywhere.
        """
        by_ref = {a.appointment_ref: a for a in _flow().arrivals}
        assert by_ref["43"].flagged_late
        assert not by_ref["42"].flagged_late

    def test_a_second_arrival_row_does_not_reset_the_wait(self) -> None:
        """A patient sent back to the waiting room has still been waiting.

        Taking the latest check-in row would zero their wait every time a
        clerk touched the record — and a clinic that looks on time because
        staff are busy is the exact opposite of useful.
        """
        rows = [
            *REAL_ROWS,
            {"appointment_ref": "42", "patient_ref": "1", "appt_date": date(2026, 11, 25),
             "appt_time": timedelta(hours=9, minutes=30), "status": "@",
             "at": datetime(2026, 11, 25, 11, 25)},
        ]
        by_ref = {a.appointment_ref: a for a in _flow(rows).arrivals}
        assert by_ref["42"].arrived_at == datetime(2026, 11, 25, 9, 20).astimezone()

    def test_in_exam_room_is_read_without_a_flag_of_its_own(self) -> None:
        """`<` is neither a check-in nor a check-out in `list_options`."""
        assert FLAGS["<"] == (False, False)
        by_ref = {a.appointment_ref: a for a in _flow().arrivals}
        assert by_ref["41"].in_room_at is not None

    def test_a_checkout_ends_the_wait(self) -> None:
        rows = [
            *REAL_ROWS,
            {"appointment_ref": "42", "patient_ref": "1", "appt_date": date(2026, 11, 25),
             "appt_time": timedelta(hours=9, minutes=30), "status": ">",
             "at": datetime(2026, 11, 25, 11, 0)},
        ]
        by_ref = {a.appointment_ref: a for a in _flow(rows).arrivals}
        assert not by_ref["42"].is_waiting

    def test_unreadable_rows_are_skipped_not_guessed(self) -> None:
        rows = [{"appointment_ref": "", "patient_ref": "9", "appt_date": None,
                 "appt_time": None, "status": "@", "at": None}]
        assert _arrivals_from(rows, FLAGS) == ()


class TestTheDelay:
    def test_the_clinic_is_measured_as_behind(self) -> None:
        """95 minutes, from the live instance. This is story three's number."""
        behind = _flow().running_behind()
        assert behind is not None
        assert int(behind.total_seconds() // 60) == 95

    def test_a_patient_who_never_arrived_does_not_count_as_waiting_nothing(self) -> None:
        """Otherwise every no-show drags a late clinic towards "on time"."""
        never_came = Arrival(
            appointment_ref="99", patient_ref="7",
            scheduled_at=datetime(2026, 11, 25, 9, 0).astimezone(),
        )
        assert never_came.waited(NOON_ISH) is None
        assert never_came.waited_past_appointment(NOON_ISH) is None

        flow = ClinicFlow(
            on=date(2026, 11, 25), observed_at=NOON_ISH,
            arrivals=(*_flow().arrivals, never_came),
        )
        assert flow.running_behind() == _flow().running_behind()

    def test_one_unusual_wait_does_not_become_everybody_s_number(self) -> None:
        """The median is why. One patient who waited all day is not the clinic."""
        outlier = Arrival(
            appointment_ref="98", patient_ref="8",
            scheduled_at=datetime(2026, 11, 25, 6, 0).astimezone(),
            arrived_at=datetime(2026, 11, 25, 6, 0).astimezone(),
        )
        flow = ClinicFlow(
            on=date(2026, 11, 25), observed_at=NOON_ISH,
            arrivals=(*_flow().arrivals, outlier),
        )
        behind = flow.running_behind()
        assert behind is not None
        assert behind < timedelta(hours=2), "a mean would have been dragged to ~2h45"

    def test_an_early_arrival_does_not_make_the_clinic_look_late(self) -> None:
        """Sitting there since dawn by choice is not the clinic's delay."""
        early = Arrival(
            appointment_ref="97", patient_ref="6",
            scheduled_at=datetime(2026, 11, 25, 11, 0).astimezone(),
            arrived_at=datetime(2026, 11, 25, 7, 0).astimezone(),
            in_room_at=datetime(2026, 11, 25, 11, 5).astimezone(),
        )
        assert early.waited(NOON_ISH) == timedelta(hours=4, minutes=5)
        assert early.waited_past_appointment(NOON_ISH) == timedelta(minutes=5)

    def test_nobody_arrived_yet_is_not_on_time(self) -> None:
        """There is no such thing as a clinic zero minutes behind at dawn."""
        flow = ClinicFlow(on=date(2026, 11, 25), observed_at=NOON_ISH, arrivals=())
        assert flow.running_behind() is None
        assert not flow.is_behind_by(timedelta(minutes=1))
        assert "nobody has arrived" in flow.summary()

    def test_a_small_delay_is_not_worth_a_message(self) -> None:
        """Messaging about eight minutes trains a family to ignore messages."""
        slight = Arrival(
            appointment_ref="96", patient_ref="5",
            scheduled_at=datetime(2026, 11, 25, 11, 0).astimezone(),
            arrived_at=datetime(2026, 11, 25, 11, 0).astimezone(),
            in_room_at=datetime(2026, 11, 25, 11, 8).astimezone(),
        )
        flow = ClinicFlow(on=date(2026, 11, 25), observed_at=NOON_ISH, arrivals=(slight,))
        assert not flow.is_behind_by(timedelta(minutes=45))
        assert flow.is_behind_by(timedelta(minutes=5))


class TestFailingHonestly:
    def test_an_unreachable_database_reports_nothing_not_zero(self) -> None:
        """`None` and an empty flow mean opposite things.

        An empty flow is "this clinic saw nobody today". `None` is "we do not
        know". Reporting the first when the second is true would have a
        Console announce an empty waiting room.
        """
        unreachable = OpenEMRDatabase(
            host="127.0.0.1", port=1, database="openemr", user="u", password="p", timeout=0.2
        )
        assert unreachable.clinic_flow(on=date(2026, 11, 25)) is None
        assert unreachable.live is False

    def test_the_adapter_satisfies_the_optional_port(self) -> None:
        bare = OpenEMRDatabase.__new__(OpenEMRDatabase)
        assert isinstance(bare, ClinicFlowSource)


class TestItOnlyEverReads:
    """A structural check, because the claim is in the module's docstring.

    Cheap to assert and the kind of thing that erodes: somebody needs one
    small write, adds it here because the connection is to hand, and
    "OpenEMR unchanged" quietly stops being true.
    """

    def test_every_sql_string_in_the_module_is_a_select(self) -> None:
        # Parsed rather than grepped: the module's own docstring contains the
        # words "insert, update or delete", and a substring search over the
        # file reports that as a violation of the thing it is describing.
        source = Path("backend/saathi/adapters/hospital/openemr_db.py").read_text()
        tree = ast.parse(source)
        statements = [
            node.value.strip()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.strip().upper().startswith(("SELECT", "INSERT", "UPDATE",
                                                       "DELETE", "REPLACE", "TRUNCATE",
                                                       "ALTER", "DROP", "CREATE"))
        ]
        assert statements, "no SQL found — this test would pass vacuously"
        for statement in statements:
            assert statement.upper().startswith("SELECT"), (
                f"a read-only adapter must only SELECT: {statement[:60]!r}"
            )

    def test_the_session_is_opened_read_only(self) -> None:
        source = Path("backend/saathi/adapters/hospital/openemr_db.py").read_text()
        assert "SET SESSION TRANSACTION READ ONLY" in source


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (timedelta(hours=9, minutes=30), timedelta(hours=9, minutes=30)),
        ("09:30:00", timedelta(hours=9, minutes=30)),
        ("14:05:09", timedelta(hours=14, minutes=5, seconds=9)),
    ],
)
def test_appointment_times_arrive_in_two_shapes(raw: object, expected: timedelta) -> None:
    """The driver hands back a `timedelta`; a dump hands back a string."""
    from saathi.adapters.hospital.openemr_db import _as_timedelta

    assert _as_timedelta(raw) == expected
