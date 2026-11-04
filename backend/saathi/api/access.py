"""Who may call what.

Every rule is written against a `Principal`, never against a body field a caller
filled in. When login is off (the demo, where the stage shows every role at once)
these dependencies let everything through and `principal` is None; handlers that
used to trust a role in the request body still do exactly that in the demo, and
read the principal instead when there is one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from ..domain.enums import Role
from ..ports.identity import STAFF_ROLES, Principal
from .deps import ContainerDep

STAFF = tuple(STAFF_ROLES)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def current_principal(request: Request, state: ContainerDep) -> Principal | None:
    """The signed-in person, None when login is off, 401 when it is on and nobody is."""
    if state.identity is None:
        return None
    token = _bearer(request)
    principal = state.identity.verify_token(token) if token else None
    if principal is None:
        raise HTTPException(
            401, "sign in first", headers={"www-authenticate": "Bearer"}
        )
    return principal


PrincipalDep = Annotated[Principal | None, Depends(current_principal)]


def require(*roles: Role):
    """A dependency allowing only these roles (and everyone, when login is off)."""
    allowed = frozenset(roles)

    def check(principal: PrincipalDep) -> Principal | None:
        if principal is not None and principal.role not in allowed:
            raise HTTPException(403, f"{principal.role.value} may not do this")
        return principal

    #: Read back by the roles page, so what it shows is what is enforced.
    check.allowed = allowed  # type: ignore[attr-defined]
    return Depends(check)


def require_patient(
    patient_id: str, principal: PrincipalDep
) -> Principal | None:
    """Staff, or a caregiver on this family. For routes with `{patient_id}` in the path."""
    ensure_may_see(principal, patient_id)
    return principal


def ensure_may_see(principal: Principal | None, patient_id: str) -> None:
    if principal is not None and not principal.may_see(patient_id):
        # 404 rather than 403: whether another family exists is not theirs to learn.
        raise HTTPException(404, "unknown patient")


#: Staff, or a caregiver looking at their own family.
FamilyOrStaff = Depends(require_patient)
AnyStaff = require(*STAFF)
Desk = require(Role.DESK, Role.ADMIN)
DeskWork = require(Role.DESK, Role.NAVIGATOR, Role.ADMIN)
AdminOnly = require(Role.ADMIN)
Approver = require(Role.NAVIGATOR, Role.DOCTOR)

__all__ = [
    "STAFF",
    "AdminOnly",
    "AnyStaff",
    "Approver",
    "Desk",
    "DeskWork",
    "FamilyOrStaff",
    "PrincipalDep",
    "current_principal",
    "ensure_may_see",
    "require",
]
