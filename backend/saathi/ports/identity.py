"""Who is asking, as the application sees it.

The application never learns how a person proved who they are. Staff arrive with
a username and password today and with an organisation's single sign-on later;
a family arrives with a phone number and a code. Either way the API receives a
`Principal`, and every access rule is written against that, so replacing the
adapter changes nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.enums import Role

STAFF_ROLES = frozenset({Role.NAVIGATOR, Role.DOCTOR, Role.DESK, Role.ADMIN})


@dataclass(frozen=True)
class Principal:
    id: str
    name: str
    role: Role
    #: For a caregiver: the families they may see. Empty for staff, who see all.
    patient_ids: tuple[str, ...] = ()

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    def may_see(self, patient_id: str) -> bool:
        return self.is_staff or patient_id in self.patient_ids


class LockedOut(Exception):
    """Too many wrong attempts; try again after `seconds`."""

    def __init__(self, seconds: int) -> None:
        super().__init__(f"too many attempts; try again in {seconds}s")
        self.seconds = seconds


class EmailSender(Protocol):
    """Delivers a one-time code to an email address."""

    def send(self, email: str, code: str) -> None: ...


class IdentityProvider(Protocol):
    def login(self, username: str, password: str) -> Principal | None:
        """Staff sign-in. None for a wrong name or password; the two look the same."""
        ...

    def request_otp(self, phone: str) -> None:
        """Send a one-time code if this phone belongs to a family. Says nothing either way."""
        ...

    def verify_otp(self, phone: str, code: str) -> Principal | None: ...

    def request_email_otp(self, email: str) -> None:
        """As `request_otp`, for a family that signs in with an email address."""
        ...

    def verify_email_otp(self, email: str, code: str) -> Principal | None: ...

    def issue_token(self, principal: Principal) -> tuple[str, int]:
        """A bearer token and the seconds it stays valid."""
        ...

    def verify_token(self, token: str) -> Principal | None: ...

    def issue_stream_ticket(self, principal: Principal) -> str:
        """A short-lived, single-use stand-in for the token on an event stream.

        A browser's `EventSource` cannot send an Authorization header, and a
        token in a URL ends up in logs. A ticket in the URL is worth nothing a
        minute later.
        """
        ...

    def redeem_stream_ticket(self, ticket: str) -> Principal | None: ...


class OtpSender(Protocol):
    def send(self, phone: str, code: str) -> None: ...
