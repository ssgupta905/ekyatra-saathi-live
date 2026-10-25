"""Sign-in through an organisation's identity provider (Keycloak, Cognito, Auth0).

Not built. It exists so the choice is a setting rather than a rewrite: selecting
it fails at startup with a message, instead of quietly falling back to local
accounts on a deployment that believed it had single sign-on.

What it would do: redirect staff to the provider, verify the returned ID token
against the provider's published keys, and map its role claim to `Role`.
Families would keep the phone-code route, which no organisation provider offers.
"""

from __future__ import annotations


class OidcIdentity:
    def __init__(self, *_: object, **__: object) -> None:
        raise NotImplementedError(
            "SAATHI_IDENTITY_PROVIDER=oidc is not implemented yet; use 'local'"
        )
