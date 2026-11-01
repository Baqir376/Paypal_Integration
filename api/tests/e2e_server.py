"""The real app, with Google and PayPal stood in for at the network edge.

    python -m uvicorn tests.e2e_server:app --port 8010

For `web/scripts/full_flow.mjs`. Everything inside this process is the production
code: the OAuth checks, Google's token verifier, the APIMatic SDK and the ledger.
Only the far end of each network call is replaced, plus two small pages that play
the part of the Google and PayPal screens a person would click through.

Never importable from the app itself, and it lives under tests/ to keep it that way.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlencode

os.environ.setdefault("SALIX_GOOGLE_CLIENT_ID", "client-123.apps.googleusercontent.com")
os.environ.setdefault("SALIX_GOOGLE_CLIENT_SECRET", "e2e")
os.environ.setdefault("SALIX_PAYPAL_SIMULATOR", "true")
os.environ.setdefault("SALIX_PROVIDER_MODE", "mock")
os.environ.setdefault("SALIX_RATE_LIMIT_ENABLED", "false")

import httpx  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402

from salix.app import create_app  # noqa: E402
from salix.auth import google  # noqa: E402
from salix.config import get_settings  # noqa: E402

from .test_accounts import _CertResponse, signed  # noqa: E402

settings = get_settings()
app = create_app()

#: The nonce Google would have bound into the token, by the code it handed out.
_codes: dict[str, dict] = {}

google.AUTH_URL = f"{settings.app_url.rstrip('/')}/api/e2e/google"
google._google_request = lambda: lambda url, **kw: _CertResponse()


def _token_endpoint(request: httpx.Request) -> httpx.Response:
    form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
    return httpx.Response(200, json={"id_token": signed(_codes[form["code"]])})


google._http = lambda: httpx.AsyncClient(transport=httpx.MockTransport(_token_endpoint))


@app.get("/api/e2e/google", response_class=HTMLResponse)
async def google_screen(redirect_uri: str = "", state: str = "", nonce: str = "") -> str:
    """Stands in for Google's account chooser."""
    rows = "".join(
        f'<p><a href="/api/e2e/google/pick?{urlencode(dict(email=email, name=name, sub=sub, redirect_uri=redirect_uri, state=state, nonce=nonce))}">{name}</a></p>'
        for sub, email, name in (
            ("g-owner", "amna@acme.com", "Amna Khan"),
            ("g-rival", "bilal@rival.com", "Bilal Shah"),
            ("g-sana", "sana@acme.com", "Sana Malik"),
        )
    )
    cancel = f'{redirect_uri}?{urlencode(dict(error="access_denied", state=state))}'
    return f'<!doctype html><title>Fake Google</title><h1>Choose an account</h1>{rows}<p><a href="{cancel}">Cancel</a></p>'


@app.get("/api/e2e/google/pick")
async def google_pick(email: str, name: str, sub: str, redirect_uri: str, state: str, nonce: str) -> RedirectResponse:
    code = f"code-{sub}-{len(_codes)}"
    _codes[code] = {"sub": sub, "email": email, "name": name, "nonce": nonce}
    return RedirectResponse(f"{redirect_uri}?{urlencode(dict(code=code, state=state))}", status_code=302)
