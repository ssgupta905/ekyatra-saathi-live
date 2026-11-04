"""Sending a one-time code by email.

Brevo is called over HTTPS, not SMTP: Render's free web services cannot reach the
SMTP ports, and an API call needs no mail server of ours. A failure is logged and
swallowed. Whether an address is on a family's record is not for a stranger to
learn, and a request that errored for known addresses only would tell them.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class LogEmailSender:
    """Writes the code to the server log. For a developer, or when no provider is set."""

    def send(self, email: str, code: str) -> None:
        logger.warning(
            "one-time code for %s: %s (no email provider is configured)", mask(email), code
        )


class BrevoEmailSender:
    def __init__(
        self,
        api_key: str,
        sender_email: str,
        sender_name: str = "Saathi",
        *,
        validity_minutes: int = 5,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._from = {"email": sender_email, "name": sender_name}
        self._minutes = validity_minutes
        self._client = client or httpx.Client(timeout=10.0)

    def send(self, email: str, code: str) -> None:
        body = {
            "sender": self._from,
            "to": [{"email": email}],
            "subject": f"Your Saathi sign-in code: {code}",
            "textContent": (
                f"Your Saathi sign-in code is {code}.\n\n"
                f"It works for {self._minutes} minutes. "
                "If you did not ask for it, you can ignore this email."
            ),
        }
        try:
            response = self._client.post(
                BREVO_URL,
                json=body,
                headers={"api-key": self._api_key, "accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            logger.error("could not reach the email provider for %s: %s", mask(email), exc)
            return
        if response.status_code >= 300:
            logger.error(
                "the email provider refused the code for %s: %s %s",
                mask(email),
                response.status_code,
                response.text[:200],
            )


def mask(email: str) -> str:
    """j***@gmail.com: enough to recognise in a log, not enough to harvest."""
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"
