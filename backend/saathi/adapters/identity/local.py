"""Local accounts: staff with passwords, families with a phone number and a code.

Good enough to run a pilot on one machine and honest about what it is not: no
password reset, no second factor for staff, and the one-time code is logged
rather than sent, because no SMS provider is wired in. Both are what the OIDC
adapter replaces.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from ...db.tables import UserRow
from ...domain.enums import Role
from ...ports.identity import STAFF_ROLES, EmailSender, LockedOut, OtpSender, Principal
from .email import LogEmailSender

logger = logging.getLogger(__name__)

STAFF_TOKEN_SECONDS = 8 * 3600
CAREGIVER_TOKEN_SECONDS = 7 * 24 * 3600
OTP_SECONDS = 300
OTP_ATTEMPTS = 5
OTP_RESEND_SECONDS = 30
LOCK_AFTER = 5
LOCK_SECONDS = 60
TICKET_SECONDS = 60


class PhoneDirectory(Protocol):
    def families_for(self, phone: str) -> tuple[tuple[str, str], ...]:
        """(patient id, the name to greet them by) for every family this phone is on."""
        ...

    def families_for_email(self, email: str) -> tuple[tuple[str, str], ...]:
        """The same, for an email address (already lower-cased)."""
        ...


class LogOtpSender:
    """Writes the code to the server log. For a developer at a terminal, not a family."""

    def send(self, phone: str, code: str) -> None:
        logger.warning(
            "one-time code for ***%s: %s (no SMS provider is configured)", phone[-4:], code
        )


def normalise_email(email: str) -> str:
    return email.strip().lower()


def digits(phone: str) -> str:
    """The last ten digits: +91 98000 11122, 09800011122 and 9800011122 are one phone."""
    return "".join(c for c in phone if c.isdigit())[-10:]


@dataclass
class _Otp:
    code_hash: str
    expires: float
    attempts: int = 0
    sent_at: float = 0.0


class LocalIdentity:
    def __init__(
        self,
        url: str,
        *,
        secret: str,
        phones: PhoneDirectory,
        sender: OtpSender | None = None,
        email_sender: EmailSender | None = None,
        staff_ttl: int = STAFF_TOKEN_SECONDS,
        caregiver_ttl: int = CAREGIVER_TOKEN_SECONDS,
        now: Callable[[], float] = time.time,
        fixed_codes: dict[str, str] | None = None,
        fixed_email_codes: dict[str, str] | None = None,
    ) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)
        self._secret = secret
        self._phones = phones
        self._sender = sender or LogOtpSender()
        self._email_sender = email_sender or LogEmailSender()
        self._staff_ttl = staff_ttl
        self._caregiver_ttl = caregiver_ttl
        self._now = now
        self._hasher = PasswordHasher()
        # A hash to spend time on when the username does not exist, so a wrong
        # name takes as long to refuse as a wrong password.
        self._decoy = self._hasher.hash(secrets.token_hex(8))
        self._lock = threading.Lock()
        self._failures: dict[str, tuple[int, float]] = {}
        self._otps: dict[str, _Otp] = {}
        #: phone -> a code that never changes. For a demonstration where no SMS
        #: provider exists; the container only fills it in for the one phone named
        #: in configuration, never for a family's own number.
        self._fixed_codes = {digits(phone): code for phone, code in (fixed_codes or {}).items()}
        self._fixed_email_codes = {
            normalise_email(email): code for email, code in (fixed_email_codes or {}).items()
        }
        self._tickets: dict[str, tuple[Principal, float]] = {}

    def close(self) -> None:
        self._engine.dispose()

    # ---------------- accounts ----------------

    def add_user(
        self,
        username: str,
        name: str,
        role: Role,
        password: str,
        *,
        organisation_id: str | None = None,
    ) -> None:
        """A staff account, or a partner account bound to one organisation.

        A partner must name its organisation: an account that answers for
        nobody would see every job or none depending on how the query was
        written, and neither is something to leave to chance.
        """
        if role is Role.PARTNER:
            if not organisation_id:
                raise ValueError("a partner account must say which organisation it answers for")
        elif role not in STAFF_ROLES:
            raise ValueError("accounts with passwords are for staff; families use a phone code")
        if len(password) < 8:
            raise ValueError("a password needs at least 8 characters")
        with self._sessions.begin() as db:
            row = db.scalar(select(UserRow).where(UserRow.username == username.lower()))
            if row is None:
                row = UserRow(id=str(uuid.uuid4()), username=username.lower())
                db.add(row)
            row.name = name
            row.role = role.value
            row.password_hash = self._hasher.hash(password)
            row.active = True
            row.organisation_id = organisation_id if role is Role.PARTNER else None

    def list_users(self) -> list[dict]:
        """Every staff account, without its password hash."""
        with self._sessions() as db:
            return [
                {"id": r.id, "username": r.username, "name": r.name, "role": r.role,
                 "active": r.active, "organisation_id": r.organisation_id}  # fmt: skip
                for r in db.scalars(select(UserRow).order_by(UserRow.username))
            ]

    def update_user(
        self,
        username: str,
        *,
        name: str | None = None,
        role: Role | None = None,
        active: bool | None = None,
        password: str | None = None,
    ) -> dict:
        if role is not None and role is not Role.PARTNER and role not in STAFF_ROLES:
            raise ValueError("accounts with passwords are for staff; families use a phone code")
        if password is not None and len(password) < 8:
            raise ValueError("a password needs at least 8 characters")
        with self._sessions.begin() as db:
            row = db.scalar(select(UserRow).where(UserRow.username == username.lower()))
            if row is None:
                raise LookupError(username)
            if name is not None:
                row.name = name
            if role is not None:
                row.role = role.value
            if active is not None:
                row.active = active
            if password is not None:
                row.password_hash = self._hasher.hash(password)
            return {"id": row.id, "username": row.username, "name": row.name,
                    "role": row.role, "active": row.active,
                    "organisation_id": row.organisation_id}  # fmt: skip

    def has_users(self) -> bool:
        with self._sessions() as db:
            return db.scalar(select(UserRow.id).limit(1)) is not None

    # ---------------- staff ----------------

    def login(self, username: str, password: str) -> Principal | None:
        key = username.strip().lower()
        self._check_not_locked(key)
        with self._sessions() as db:
            row = db.scalar(select(UserRow).where(UserRow.username == key))
        stored = row.password_hash if row is not None and row.active else self._decoy
        try:
            ok = self._hasher.verify(stored, password)
        except (VerificationError, InvalidHashError):
            ok = False
        if not ok or row is None or not row.active:
            self._note_failure(key)
            return None
        with self._lock:
            self._failures.pop(key, None)
        return Principal(
            id=row.id,
            name=row.name,
            role=Role(row.role),
            organisation_id=row.organisation_id,
        )

    def _check_not_locked(self, key: str) -> None:
        with self._lock:
            count, until = self._failures.get(key, (0, 0.0))
        remaining = int(until - self._now())
        if count >= LOCK_AFTER and remaining > 0:
            raise LockedOut(remaining)

    def _note_failure(self, key: str) -> None:
        with self._lock:
            count, _ = self._failures.get(key, (0, 0.0))
            self._failures[key] = (count + 1, self._now() + LOCK_SECONDS)

    # ---------------- families ----------------

    def request_otp(self, phone: str) -> None:
        key = digits(phone)
        if len(key) < 10 or not self._phones.families_for(key):
            return  # say nothing: whether a number is on record is not for a stranger to learn
        with self._lock:
            existing = self._otps.get(key)
            if existing and self._now() - existing.sent_at < OTP_RESEND_SECONDS:
                return
            code = self._fixed_codes.get(key) or f"{secrets.randbelow(10**6):06d}"
            self._otps[key] = _Otp(
                code_hash=self._hash_code(key, code),
                expires=self._now() + OTP_SECONDS,
                sent_at=self._now(),
            )
        self._sender.send(key, code)

    def verify_otp(self, phone: str, code: str) -> Principal | None:
        key = digits(phone)
        with self._lock:
            otp = self._otps.get(key)
            if otp is None or otp.expires < self._now() or otp.attempts >= OTP_ATTEMPTS:
                self._otps.pop(key, None)
                return None
            otp.attempts += 1
            if not hmac.compare_digest(otp.code_hash, self._hash_code(key, code.strip())):
                return None
            del self._otps[key]
        families = self._phones.families_for(key)
        if not families:
            return None
        return Principal(
            id=f"caregiver:{key}",
            name=families[0][1],
            role=Role.CAREGIVER,
            patient_ids=tuple(pid for pid, _ in families),
        )

    # ---------------- families, by email ----------------

    def request_email_otp(self, email: str) -> None:
        key = normalise_email(email)
        if "@" not in key or not self._phones.families_for_email(key):
            return  # say nothing, for the same reason as a phone number
        with self._lock:
            existing = self._otps.get(f"email:{key}")
            if existing and self._now() - existing.sent_at < OTP_RESEND_SECONDS:
                return
            code = self._fixed_email_codes.get(key) or f"{secrets.randbelow(10**6):06d}"
            self._otps[f"email:{key}"] = _Otp(
                code_hash=self._hash_code(f"email:{key}", code),
                expires=self._now() + OTP_SECONDS,
                sent_at=self._now(),
            )
        self._email_sender.send(key, code)

    def verify_email_otp(self, email: str, code: str) -> Principal | None:
        key = normalise_email(email)
        slot = f"email:{key}"
        with self._lock:
            otp = self._otps.get(slot)
            if otp is None or otp.expires < self._now() or otp.attempts >= OTP_ATTEMPTS:
                self._otps.pop(slot, None)
                return None
            otp.attempts += 1
            if not hmac.compare_digest(otp.code_hash, self._hash_code(slot, code.strip())):
                return None
            del self._otps[slot]
        families = self._phones.families_for_email(key)
        if not families:
            return None
        return Principal(
            id=f"caregiver:{slot}",
            name=families[0][1],
            role=Role.CAREGIVER,
            patient_ids=tuple(pid for pid, _ in families),
        )

    def _hash_code(self, phone: str, code: str) -> str:
        message = f"{phone}:{code}".encode()
        return hmac.new(self._secret.encode(), message, hashlib.sha256).hexdigest()

    # ---------------- tokens ----------------

    def issue_token(self, principal: Principal) -> tuple[str, int]:
        ttl = self._staff_ttl if principal.is_staff else self._caregiver_ttl
        issued = int(self._now())
        token = jwt.encode(
            {
                "sub": principal.id,
                "name": principal.name,
                "role": principal.role.value,
                "pids": list(principal.patient_ids),
                # Which organisation a partner answers for. Without it the
                # token says "partner" and nothing else, and every job query
                # has to fail closed — a working account that can see nothing.
                "org": principal.organisation_id,
                "iat": issued,
                "exp": issued + ttl,
            },
            self._secret,
            algorithm="HS256",
        )
        return token, ttl

    def verify_token(self, token: str) -> Principal | None:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                options={"require": ["exp", "sub", "role"]},
                leeway=0,
            )
            # PyJWT checks `exp` against the real clock; honour an injected one too.
            if claims["exp"] < self._now():
                return None
            return Principal(
                id=claims["sub"],
                name=claims.get("name", ""),
                role=Role(claims["role"]),
                patient_ids=tuple(claims.get("pids") or ()),
                organisation_id=claims.get("org"),
            )
        except (jwt.PyJWTError, ValueError):
            return None

    def issue_stream_ticket(self, principal: Principal) -> str:
        ticket = secrets.token_urlsafe(24)
        with self._lock:
            now = self._now()
            self._tickets = {t: v for t, v in self._tickets.items() if v[1] > now}
            self._tickets[ticket] = (principal, now + TICKET_SECONDS)
        return ticket

    def redeem_stream_ticket(self, ticket: str) -> Principal | None:
        with self._lock:
            found = self._tickets.pop(ticket, None)
        if found is None or found[1] < self._now():
            return None
        return found[0]
