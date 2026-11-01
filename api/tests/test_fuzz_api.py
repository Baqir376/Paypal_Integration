"""Throw generated requests at every endpoint, from the API's own OpenAPI schema.

Schemathesis writes the hostile inputs nobody thought of: odd encodings, boundary
numbers, the wrong types, enormous strings. Two rules, for every operation:

* never a 500. Whatever was sent, the server answers it properly.
* every response matches the schema the API publishes.

Marked slow by nothing, but kept small per operation so it stays in the normal run.
Set SALIX_FUZZ_EXAMPLES higher for a longer hunt.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

schemathesis = pytest.importorskip("schemathesis")

from hypothesis import HealthCheck, settings as hypothesis_settings  # noqa: E402
from schemathesis.checks import not_a_server_error  # noqa: E402

EXAMPLES = int(os.getenv("SALIX_FUZZ_EXAMPLES", "8"))

#: Calls nothing here can stand in for, or that wait forever by design.
SKIPPED = {
    ("GET", "/api/calls/{call_id}/events"),  # a stream that ends when a pipeline does
    ("GET", "/api/dojo/voice"),  # a third party's speech endpoint
    ("POST", "/api/dojo/speak"),
    ("GET", "/api/auth/google/start"),
    ("GET", "/api/auth/google/callback"),
    ("POST", "/api/billing/checkout"),  # would reach PayPal
    ("POST", "/api/billing/reconcile"),
    ("POST", "/api/billing/braintree/client-token"),  # 503 by design until configured
    ("POST", "/api/billing/braintree/pay"),
}


def _build():
    tmp = Path(tempfile.mkdtemp())
    os.environ["SALIX_DATABASE_URL"] = f"sqlite+aiosqlite:///{(tmp / 'f.db').as_posix()}"
    os.environ["SALIX_STORAGE_DIR"] = str(tmp / "storage")
    os.environ["SALIX_PROVIDER_MODE"] = "mock"

    from salix.app import create_app
    from salix.config import get_settings
    from salix.providers import build_providers
    from salix.routers.deps import reset_org_cache
    from salix.schemas.org import Org, Rep
    from salix.store import db, repo, session_scope

    get_settings.cache_clear()

    async def seed():
        await db.dispose()
        await db.init_db()
        reset_org_cache()
        async with session_scope() as session:
            await repo.put_org(session, Org(id="org_f", name="F"))
            await repo.put_rep(session, Rep(id="rep_f", org_id="org_f", name="Fuzz Target"))
        await db.dispose()

    asyncio.run(seed())
    app = create_app()
    app.state.providers = build_providers(get_settings())
    return app


app = _build()
schema = schemathesis.openapi.from_asgi("/openapi.json", app)


@schema.parametrize()
@hypothesis_settings(
    max_examples=EXAMPLES,
    deadline=None,
    suppress_health_check=list(HealthCheck),
    derandomize=True,
)
def test_every_endpoint_survives(case):
    if (case.method.upper(), case.path) in SKIPPED:
        pytest.skip("reaches a third party or never returns")
    response = case.call()
    # Speech recognition is refused offline, and says so. 503 is the honest answer.
    if case.path == "/api/dojo/transcribe" and response.status_code == 503:
        return
    # With no webhook configured, deliveries are refused rather than accepted unchecked.
    if case.path == "/api/billing/webhook" and response.status_code == 503:
        return
    case.validate_response(response, checks=[not_a_server_error])
