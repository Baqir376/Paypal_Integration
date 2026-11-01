"""The credit paywall, from checkout to analysis.

Nothing below the HTTP layer is faked. These run the real APIMatic-generated SDK
against a stand-in for PayPal mounted on its `requests` session, so OAuth, the
JSON it puts on the wire and the parsing of what comes back are all exercised.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from io import BytesIO

import pytest
import pytest_asyncio
import requests
from requests.adapters import HTTPAdapter

BASE = "https://api-m.sandbox.paypal.com"
MP3 = b"\xff\xfb" + b"\x00" * 512


class FakePayPal(HTTPAdapter):
    """Enough of PayPal's Orders v2 to run the whole round trip."""

    def __init__(self):
        super().__init__()
        self.orders: dict[str, dict] = {}
        self.requests: list[requests.PreparedRequest] = []
        self.captures = 0
        self.down = False
        self.next_capture_error: tuple[int, str] | None = None
        self.paid_amount: str | None = None
        self.capture_status = "COMPLETED"
        self.next_capture_raw: tuple[int, dict] | None = None
        self.approve_rel = "payer-action"

    def _respond(self, request, status: int, body: dict) -> requests.Response:
        response = requests.Response()
        response.status_code = status
        response.raw = BytesIO(json.dumps(body).encode())
        response.headers["Content-Type"] = "application/json"
        response.url = request.url
        response.request = request
        return response

    def _order(self, order: dict) -> dict:
        unit = order["body"]["purchase_units"][0]
        out = {"id": order["id"], "status": order["status"]}
        if order["status"] == "PAYER_ACTION_REQUIRED":
            out["links"] = [
                {"href": f"{BASE}/v2/checkout/orders/{order['id']}", "rel": "self", "method": "GET"},
                {
                    "href": f"https://www.sandbox.paypal.com/checkoutnow?token={order['id']}",
                    "rel": self.approve_rel,
                    "method": "GET",
                },
            ]
        if order.get("captured"):
            out["purchase_units"] = [
                {
                    "reference_id": unit["reference_id"],
                    "payments": {
                        "captures": [
                            {
                                "id": f"CAP-{order['id']}",
                                "status": self.capture_status,
                                "amount": {
                                    "currency_code": unit["amount"]["currency_code"],
                                    "value": self.paid_amount or unit["amount"]["value"],
                                },
                            }
                        ]
                    },
                }
            ]
        return out

    def _error(self, request, status: int, issue: str) -> requests.Response:
        return self._respond(
            request,
            status,
            {
                "name": "UNPROCESSABLE_ENTITY",
                "message": "refused",
                "debug_id": "dbg123",
                "details": [{"issue": issue, "description": issue}],
            },
        )

    def send(self, request, **kwargs):
        self.requests.append(request)
        if self.down:
            raise requests.ConnectionError("no route to PayPal")

        path = request.path_url.split("?")[0]
        if path == "/v1/oauth2/token":
            return self._respond(
                request,
                200,
                {"access_token": "tok", "token_type": "Bearer", "expires_in": 3600},
            )

        assert request.headers.get("Authorization") == "Bearer tok", "order call without OAuth"

        if path == "/v2/checkout/orders" and request.method == "POST":
            order_id = f"ORDER{len(self.orders) + 1}"
            self.orders[order_id] = {
                "id": order_id,
                "status": "PAYER_ACTION_REQUIRED",
                "body": json.loads(request.body),
                "request_id": request.headers.get("PayPal-Request-Id"),
            }
            return self._respond(request, 200, self._order(self.orders[order_id]))

        match = re.fullmatch(r"/v2/checkout/orders/([A-Z0-9]+)(/capture)?", path)
        assert match, f"unexpected call {request.method} {path}"
        order = self.orders.get(match.group(1))
        if order is None:
            return self._error(request, 404, "RESOURCE_NOT_FOUND")

        if not match.group(2):
            return self._respond(request, 200, self._order(order))

        self.captures += 1
        order["capture_request_id"] = request.headers.get("PayPal-Request-Id")
        if self.next_capture_raw:
            status, body = self.next_capture_raw
            self.next_capture_raw = None
            return self._respond(request, status, body)
        if self.next_capture_error:
            status, issue = self.next_capture_error
            self.next_capture_error = None
            return self._error(request, status, issue)
        if order["status"] == "PAYER_ACTION_REQUIRED":
            return self._error(request, 422, "ORDER_NOT_APPROVED")
        if order.get("captured"):
            return self._error(request, 422, "ORDER_ALREADY_CAPTURED")
        order["status"] = "COMPLETED"
        order["captured"] = True
        return self._respond(request, 200, self._order(order))

    def approve(self, order_id: str) -> None:
        self.orders[order_id]["status"] = "APPROVED"


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.setenv("SALIX_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    monkeypatch.setenv("SALIX_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("SALIX_PAYPAL_CLIENT_ID", "client")
    monkeypatch.setenv("SALIX_PAYPAL_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SALIX_APP_URL", "https://app.example.com/")
    monkeypatch.setenv("SALIX_PROVIDER_MODE", "mock")

    from httpx import ASGITransport, AsyncClient

    from salix.app import create_app
    from salix.billing.paypal import PayPalGateway, reset_gateway
    from salix.config import get_settings
    from salix.providers import build_providers
    from salix.routers.deps import reset_org_cache
    from salix.schemas.org import Org, Rep
    from salix.store import db, repo, session_scope

    get_settings.cache_clear()
    await db.dispose()
    await db.init_db()
    reset_org_cache()
    async with session_scope() as session:
        await repo.put_org(session, Org(id="org_t", name="T"))
        await repo.put_rep(session, Rep(id="rep_t", org_id="org_t", name="Sana Malik"))

    fake = FakePayPal()
    http = requests.Session()
    http.mount("https://", fake)
    reset_gateway(PayPalGateway(get_settings(), http_client=http))

    app = create_app()
    app.state.providers = build_providers(get_settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, fake

    reset_gateway()
    reset_org_cache()
    await db.dispose()
    get_settings.cache_clear()


async def balance(client) -> int:
    return (await client.get("/api/billing")).json()["balance"]


async def buy(client, fake, pack="starter") -> str:
    order = (await client.post("/api/billing/checkout", json={"pack_id": pack})).json()
    fake.approve(order["order_id"])
    response = await client.post(f"/api/billing/orders/{order['order_id']}/capture")
    assert response.status_code == 200, response.text
    return order["order_id"]


async def upload(client, name="Sana"):
    return await client.post(
        "/api/calls/upload",
        files={"file": ("a.mp3", MP3, "audio/mpeg")},
        data={"salesperson": name},
    )


class TestCheckout:
    async def test_the_order_on_the_wire_is_what_paypal_expects(self, world):
        client, fake = world
        response = await client.post("/api/billing/checkout", json={"pack_id": "team"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["approve_url"].startswith("https://www.sandbox.paypal.com/checkoutnow")

        sent = fake.orders[body["order_id"]]["body"]
        assert sent["intent"] == "CAPTURE"
        assert sent["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "40.00"}
        context = sent["payment_source"]["paypal"]["experience_context"]
        assert context["return_url"] == "https://app.example.com/billing/return"
        assert context["cancel_url"] == "https://app.example.com/billing?cancelled=1"
        assert context["shipping_preference"] == "NO_SHIPPING"
        assert fake.orders[body["order_id"]]["request_id"]

    async def test_it_talks_to_the_sandbox(self, world):
        client, fake = world
        await client.post("/api/billing/checkout", json={"pack_id": "starter"})
        assert all(r.url.startswith(BASE) for r in fake.requests)

    async def test_an_unknown_pack_is_refused(self, world):
        client, fake = world
        response = await client.post("/api/billing/checkout", json={"pack_id": "free"})
        assert response.status_code == 400
        assert not fake.orders

    async def test_the_browser_cannot_name_a_price(self, world):
        client, fake = world
        response = await client.post(
            "/api/billing/checkout", json={"pack_id": "team", "price": "0.01"}
        )
        assert response.status_code == 422
        assert not fake.orders

    async def test_paypal_being_down_is_a_502_with_no_order_recorded(self, world):
        client, fake = world
        fake.down = True
        response = await client.post("/api/billing/checkout", json={"pack_id": "starter"})
        assert response.status_code == 502
        assert "client" not in response.text and "secret" not in response.text
        fake.down = False
        assert (await client.post("/api/billing/reconcile")).json()["checked"] == 0


class TestCapture:
    async def test_paying_grants_the_pack(self, world):
        client, fake = world
        assert await balance(client) == 0
        await buy(client, fake)
        assert await balance(client) == 5

    async def test_a_reloaded_return_page_grants_once(self, world):
        client, fake = world
        order_id = await buy(client, fake)
        for _ in range(3):
            response = await client.post(f"/api/billing/orders/{order_id}/capture")
            assert response.status_code == 200
        assert await balance(client) == 5
        assert fake.captures == 1

    async def test_racing_captures_grant_once(self, world):
        client, fake = world
        order = (await client.post("/api/billing/checkout", json={"pack_id": "starter"})).json()
        fake.approve(order["order_id"])
        await asyncio.gather(
            *(client.post(f"/api/billing/orders/{order['order_id']}/capture") for _ in range(5))
        )
        assert await balance(client) == 5

    async def test_the_capture_request_id_is_stable(self, world):
        """So PayPal itself treats a retried capture as the same one."""
        client, fake = world
        order_id = await buy(client, fake)
        assert fake.orders[order_id]["capture_request_id"] == f"salix-capture-{order_id}"

    async def test_an_order_this_server_did_not_create_is_refused(self, world):
        client, fake = world
        response = await client.post("/api/billing/orders/SOMEONEELSES/capture")
        assert response.status_code == 404
        assert fake.captures == 0
        assert await balance(client) == 0

    async def test_an_unapproved_order_grants_nothing(self, world):
        client, fake = world
        order = (await client.post("/api/billing/checkout", json={"pack_id": "starter"})).json()
        response = await client.post(f"/api/billing/orders/{order['order_id']}/capture")
        assert response.status_code == 409
        assert await balance(client) == 0

    async def test_a_declined_card_grants_nothing(self, world):
        client, fake = world
        order = (await client.post("/api/billing/checkout", json={"pack_id": "starter"})).json()
        fake.approve(order["order_id"])
        fake.next_capture_error = (422, "INSTRUMENT_DECLINED")
        response = await client.post(f"/api/billing/orders/{order['order_id']}/capture")
        assert response.status_code == 402
        assert await balance(client) == 0

    async def test_a_capture_whose_response_was_lost_still_grants(self, world):
        """PayPal took the money and we never heard. The retry is told it is
        already captured, and has to read the order rather than fail."""
        client, fake = world
        order = (await client.post("/api/billing/checkout", json={"pack_id": "starter"})).json()
        fake.orders[order["order_id"]]["status"] = "COMPLETED"
        fake.orders[order["order_id"]]["captured"] = True
        response = await client.post(f"/api/billing/orders/{order['order_id']}/capture")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert await balance(client) == 5

    async def test_the_wrong_amount_grants_nothing(self, world):
        client, fake = world
        fake.paid_amount = "0.01"
        order = (await client.post("/api/billing/checkout", json={"pack_id": "floor"})).json()
        fake.approve(order["order_id"])
        response = await client.post(f"/api/billing/orders/{order['order_id']}/capture")
        assert response.json()["status"] == "review"
        assert await balance(client) == 0

    async def test_a_pending_capture_grants_nothing_until_it_clears(self, world):
        client, fake = world
        fake.capture_status = "PENDING"
        order = (await client.post("/api/billing/checkout", json={"pack_id": "starter"})).json()
        fake.approve(order["order_id"])
        response = await client.post(f"/api/billing/orders/{order['order_id']}/capture")
        assert response.json()["status"] == "pending"
        assert await balance(client) == 0

        fake.capture_status = "COMPLETED"
        await client.post("/api/billing/reconcile")
        assert await balance(client) == 5


class TestFromTheContextPluginReview:
    """Found by reviewing paypal.py with APIMatic's plugin. See docs/APIMATIC.md."""

    async def _ready(self, client, fake):
        order = (await client.post("/api/billing/checkout", json={"pack_id": "starter"})).json()["order_id"]
        fake.approve(order)
        return order

    @pytest.mark.parametrize("status", [429, 503])
    async def test_a_failed_capture_is_an_error_and_not_an_empty_order(self, world, status):
        client, fake = world
        order = await self._ready(client, fake)
        fake.next_capture_raw = (status, {"message": "try later"})
        response = await client.post(f"/api/billing/orders/{order}/capture")
        assert response.status_code == 502, response.text
        assert await balance(client) == 0

    async def test_it_can_be_retried_after_a_failed_capture(self, world):
        client, fake = world
        order = await self._ready(client, fake)
        fake.next_capture_raw = (503, {"message": "try later"})
        await client.post(f"/api/billing/orders/{order}/capture")
        assert (await client.post(f"/api/billing/orders/{order}/capture")).json()["status"] == "completed"
        assert await balance(client) == 5

    async def test_an_error_code_in_name_alone_is_understood(self, world):
        """The shape in the plugin's sample, with no `details`."""
        client, fake = world
        order = await self._ready(client, fake)
        fake.next_capture_raw = (422, {"name": "INSTRUMENT_DECLINED", "message": "declined", "debug_id": "d"})
        response = await client.post(f"/api/billing/orders/{order}/capture")
        assert response.status_code == 402
        assert await balance(client) == 0

    async def test_the_approve_link_works_as_well_as_payer_action(self, world):
        client, fake = world
        fake.approve_rel = "approve"
        order = (await client.post("/api/billing/checkout", json={"pack_id": "starter"})).json()
        assert order["approve_url"].startswith("https://www.sandbox.paypal.com/checkoutnow")

    def test_retries_are_on(self, world):
        from salix.billing import paypal

        assert paypal.MAX_RETRIES > 0


class TestReconcile:
    async def test_approving_then_closing_the_tab_still_grants(self, world):
        client, fake = world
        order = (await client.post("/api/billing/checkout", json={"pack_id": "starter"})).json()
        fake.approve(order["order_id"])
        body = (await client.post("/api/billing/reconcile")).json()
        assert body == {"checked": 1, "balance": 5}

    async def test_an_abandoned_order_stays_unpaid(self, world):
        client, fake = world
        await client.post("/api/billing/checkout", json={"pack_id": "starter"})
        assert (await client.post("/api/billing/reconcile")).json()["balance"] == 0
        assert fake.captures == 0

    async def test_paypal_being_down_does_not_break_the_page(self, world):
        client, fake = world
        await client.post("/api/billing/checkout", json={"pack_id": "starter"})
        fake.down = True
        assert (await client.post("/api/billing/reconcile")).status_code == 200


class TestPaywall:
    async def test_no_credits_no_upload(self, world):
        client, _ = world
        response = await upload(client)
        assert response.status_code == 402
        assert "credits" in response.json()["detail"]
        assert (await client.get("/api/calls")).json() == []

    async def test_a_refused_upload_does_not_add_the_salesperson(self, world):
        client, _ = world
        await upload(client, "Brand New Person")
        names = [r["rep"]["name"] for r in (await client.get("/api/reps")).json()]
        assert "Brand New Person" not in names

    async def test_the_whole_flow(self, world):
        """Refused, buys credits, uploads, gets a score and a coaching plan."""
        client, fake = world
        assert (await upload(client)).status_code == 402
        await buy(client, fake)

        response = await upload(client)
        assert response.status_code == 202, response.text
        assert await balance(client) == 4

        detail = (await client.get(f"/api/calls/{response.json()['call_id']}")).json()
        assert detail["call"]["status"] == "ready"
        assert detail["scorecard"]["overall"] > 0
        profile = (await client.get("/api/reps/rep_t")).json()
        assert profile["coaching_plan"] is not None

    async def test_credits_run_out(self, world):
        client, fake = world
        await buy(client, fake)
        statuses = [(await upload(client)).status_code for _ in range(6)]
        assert statuses == [202] * 5 + [402]
        assert await balance(client) == 0

    async def test_racing_for_the_last_credit_only_one_wins(self, tmp_path, world):
        from salix.billing import credits
        from salix.store import session_scope

        client, fake = world
        await buy(client, fake)

        async def attempt(i):
            try:
                async with session_scope() as session:
                    await credits.spend_for_call(session, "org_t", f"call_{i}")
                return True
            except credits.InsufficientCredits:
                return False

        results = await asyncio.gather(*(attempt(i) for i in range(12)))
        assert sum(results) == 5
        assert await balance(client) == 0

    async def test_a_failed_transcription_refunds(self, world):
        client, fake = world
        await buy(client, fake)

        class Broken:
            name = "broken"

            async def transcribe(self, *args, **kwargs):
                raise RuntimeError("no such audio")

        client._transport.app.state.providers.asr = Broken()
        response = await upload(client)
        assert response.status_code == 202
        detail = (await client.get(f"/api/calls/{response.json()['call_id']}")).json()
        assert detail["call"]["status"] == "failed"
        assert await balance(client) == 5

        ledger = (await client.get("/api/billing")).json()["history"]
        assert sorted(e["reason"] for e in ledger) == ["call_analysis", "call_refund", "purchase"]

    async def test_a_failed_reading_of_the_call_refunds(self, world):
        client, fake = world
        await buy(client, fake)
        from salix.agents.anatomist import Anatomist

        async def boom(*args, **kwargs):
            raise RuntimeError("model down")

        original = Anatomist.run
        Anatomist.run = boom
        try:
            response = await upload(client)
        finally:
            Anatomist.run = original
        assert response.status_code == 202
        assert await balance(client) == 5

    async def test_a_refund_only_ever_happens_once(self, world):
        from salix.billing import credits
        from salix.store import session_scope

        client, fake = world
        await buy(client, fake)
        response = await upload(client)
        call_id = response.json()["call_id"]
        for _ in range(3):
            async with session_scope() as session:
                await credits.refund_call(session, call_id)
        assert await balance(client) == 5

    async def test_a_restart_refunds_calls_it_interrupted(self, world):
        from datetime import datetime, timezone

        from salix.app import lifespan
        from salix.billing import credits
        from salix.schemas.call import Call, CallStatus
        from salix.store import repo, session_scope

        client, fake = world
        await buy(client, fake)
        async with session_scope() as session:
            await repo.put_call(
                session,
                Call(
                    id="call_stuck", org_id="org_t", rep_id="rep_t", title="t", account="a",
                    occurred_at=datetime.now(timezone.utc), status=CallStatus.ANALYZING,
                ),
            )
            await credits.spend_for_call(session, "org_t", "call_stuck")
        assert await balance(client) == 4

        app = client._transport.app
        from salix.routers.deps import reset_org_cache

        async with lifespan(app):
            reset_org_cache()
            async with session_scope() as session:
                assert await credits.balance(session, "org_t") == 5


class TestModes:
    def test_auto_charges_only_when_paypal_is_configured(self):
        from salix.config import Settings

        assert Settings(billing_mode="auto").billing_enforced is False
        assert (
            Settings(
                billing_mode="auto", paypal_client_id="a", paypal_client_secret="b"
            ).billing_enforced
            is True
        )

    def test_off_means_free_even_with_paypal(self):
        from salix.config import Settings

        assert (
            Settings(
                billing_mode="off", paypal_client_id="a", paypal_client_secret="b"
            ).billing_enforced
            is False
        )

    @pytest.mark.parametrize("mode", ["on", "ON", "yes", "enforce"])
    def test_anything_else_charges(self, mode):
        from salix.config import Settings

        assert Settings(billing_mode=mode).billing_enforced is True

    @pytest.mark.parametrize("value", ["", "sandbox", "live", "prod", "Sandbox"])
    def test_only_the_exact_word_reaches_real_money(self, value):
        from salix.config import Settings

        assert Settings(paypal_environment=value).paypal_mode == "sandbox"

    def test_production_is_production(self):
        from salix.config import Settings

        assert Settings(paypal_environment="production").paypal_mode == "production"

    async def test_on_without_paypal_says_so_rather_than_crashing(self, world):
        from salix.billing.paypal import PayPalError, get_gateway, reset_gateway
        from salix.config import Settings

        reset_gateway()
        with pytest.raises(PayPalError, match="not configured"):
            get_gateway(Settings(paypal_client_id=None, paypal_client_secret=None))

    def test_the_sdk_is_the_generated_one(self):
        import paypalserversdk.paypal_serversdk_client as module

        with open(module.__file__, encoding="utf-8") as source:
            assert "generated by APIMATIC" in source.read(200)


def test_no_secret_is_in_the_example_env():
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    with open(os.path.join(root, ".env.example"), encoding="utf-8") as env:
        text = env.read()
    assert re.search(r"^SALIX_PAYPAL_CLIENT_ID=$", text, re.M)
    assert re.search(r"^SALIX_PAYPAL_CLIENT_SECRET=$", text, re.M)
    assert re.search(r"^SALIX_PAYPAL_ENVIRONMENT=sandbox$", text, re.M)
