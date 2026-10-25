"""Signing in. Everything here is public by necessity, and says as little as it can."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..ports.identity import LockedOut, Principal
from .access import PrincipalDep
from .deps import ContainerDep

router = APIRouter(prefix="/auth")


def _identity(state: ContainerDep):
    if state.identity is None:
        raise HTTPException(404, "login is off in this world")
    return state.identity


def _session(state: ContainerDep, principal: Principal) -> dict:
    token, expires_in = state.identity.issue_token(principal)
    return {"token": token, "expires_in": expires_in, "principal": _public(principal)}


def _public(principal: Principal) -> dict:
    return {
        "id": principal.id,
        "name": principal.name,
        "role": principal.role.value,
        "patient_ids": list(principal.patient_ids),
    }


@router.get("/config")
async def auth_config(state: ContainerDep) -> dict:
    """Whether an app must ask for a sign-in before it shows anything."""
    return {
        "required": state.identity is not None,
        "provider": state.settings.identity_provider,
    }


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
async def login(state: ContainerDep, body: LoginIn) -> dict:
    identity = _identity(state)
    try:
        principal = identity.login(body.username, body.password)
    except LockedOut as exc:
        raise HTTPException(
            429, str(exc), headers={"retry-after": str(exc.seconds)}
        ) from exc
    if principal is None:
        raise HTTPException(401, "wrong username or password")
    return _session(state, principal)


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=5, max_length=24)


@router.post("/otp/request", status_code=202)
async def otp_request(state: ContainerDep, body: OtpRequestIn) -> dict:
    """Always 202: it must not reveal whether this number is on a family's record."""
    _identity(state).request_otp(body.phone)
    return {"sent": True}


class OtpVerifyIn(BaseModel):
    phone: str = Field(min_length=5, max_length=24)
    code: str = Field(min_length=4, max_length=8)


@router.post("/otp/verify")
async def otp_verify(state: ContainerDep, body: OtpVerifyIn) -> dict:
    principal = _identity(state).verify_otp(body.phone, body.code)
    if principal is None:
        raise HTTPException(401, "that code is wrong or has expired")
    return _session(state, principal)


@router.get("/me")
async def me(principal: PrincipalDep) -> dict:
    if principal is None:
        raise HTTPException(404, "login is off in this world")
    return _public(principal)


@router.post("/stream-ticket")
async def stream_ticket(state: ContainerDep, principal: PrincipalDep) -> dict:
    """A one-minute, one-use ticket to open the event stream with."""
    if principal is None:
        raise HTTPException(404, "login is off in this world")
    return {"ticket": state.identity.issue_stream_ticket(principal)}
