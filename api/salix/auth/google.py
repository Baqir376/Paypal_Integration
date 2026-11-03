"""Sign in with Google, using the authorization code flow on the server.

The browser never sees a Google token. It is sent to Google, comes back with a
one-time code, and this process swaps that code for an ID token using the client
secret. Three values protect the round trip, each against something different:

* `state` ties the callback to the browser that started it, which stops an
  attacker signing a victim into the attacker's account.
* The PKCE verifier means a stolen code is useless without it.
* `nonce` ties the ID token to this attempt, so an old token cannot be replayed.

The ID token's signature, audience, issuer and expiry are checked by Google's own
library rather than by hand. The email is only trusted if Google says it verified
it, because invitations are matched on email.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from ..config import Settings

log = logging.getLogger("salix.auth.google")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TIMEOUT_S = 15.0


class GoogleError(RuntimeError):
    """The sign-in did not complete. Never shown to the user verbatim."""


@dataclass(frozen=True)
class GoogleProfile:
    sub: str
    email: str
    name: str
    picture: str = ""


@dataclass(frozen=True)
class Attempt:
    """What must survive the trip to Google, in the browser's HttpOnly cookie."""

    state: str
    nonce: str
    verifier: str


def new_attempt() -> Attempt:
    return Attempt(
        state=secrets.token_urlsafe(24),
        nonce=secrets.token_urlsafe(24),
        verifier=secrets.token_urlsafe(48),
    )


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def redirect_uri(settings: Settings) -> str:
    return f"{settings.app_url.rstrip('/')}/api/auth/google/callback"


def authorization_url(settings: Settings, attempt: Attempt) -> str:
    return f"{AUTH_URL}?" + urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri(settings),
            "response_type": "code",
            "scope": "openid email profile",
            "state": attempt.state,
            "nonce": attempt.nonce,
            "code_challenge": _challenge(attempt.verifier),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT_S)


def _google_request() -> Any:
    from google.auth.transport.requests import Request

    return Request()


async def exchange_code(settings: Settings, code: str, verifier: str) -> str:
    """Swap the one-time code for an ID token."""
    try:
        async with _http() as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": redirect_uri(settings),
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
            )
    except httpx.HTTPError as exc:
        raise GoogleError(f"token endpoint unreachable: {type(exc).__name__}") from exc

    if response.status_code != 200:
        # The body names the problem and carries no secret; it is what somebody
        # debugging a wrong redirect URI needs to see.
        raise GoogleError(f"token endpoint said {response.status_code}: {response.text[:200]}")
    token = response.json().get("id_token")
    if not token:
        raise GoogleError("token response carried no ID token")
    return token


#: A token is stamped by Google's clock and checked by this one. With no allowance, a
#: machine a second behind rejects a token issued that instant as "used too early".
CLOCK_SKEW_S = 10


async def verify_id_token(settings: Settings, token: str, nonce: str) -> GoogleProfile:
    from google.oauth2 import id_token

    try:
        claims = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            token,
            _google_request(),
            settings.google_client_id,
            clock_skew_in_seconds=CLOCK_SKEW_S,
        )
    except Exception as exc:  # noqa: BLE001
        # The library's own words, which are what tell a clock from a wrong audience.
        raise GoogleError(f"ID token rejected: {type(exc).__name__}: {str(exc)[:160]}") from exc

    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise GoogleError("ID token nonce does not match this attempt")
    if claims.get("email_verified") is not True:
        raise GoogleError("Google has not verified this email address")

    sub, email = claims.get("sub"), claims.get("email")
    if not sub or not email:
        raise GoogleError("ID token is missing the account id or email")

    return GoogleProfile(
        sub=str(sub),
        email=str(email).strip().lower(),
        name=str(claims.get("name") or str(email).split("@")[0])[:200],
        picture=str(claims.get("picture") or "")[:500],
    )


def safe_next(target: Optional[str]) -> str:
    """Where to land afterwards. Same site only, so sign-in cannot be used as an
    open redirect to somewhere that looks like it."""
    if (
        not target
        or not target.startswith("/")
        or target.startswith("//")
        or "\\" in target
        or any(ord(c) < 32 for c in target)
    ):
        return "/console"
    return target
