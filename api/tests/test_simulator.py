"""The labelled stand-in for PayPal: off by default, and never mistaken for the real one."""

from __future__ import annotations

import pytest
import pytest_asyncio

MP3 = b"\xff\xfb" + b"\x00" * 512


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.setenv("SALIX_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    monkeypatch.setenv("SALIX_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("SALIX_PROVIDER_MODE", "mock")
    monkeypatch.setenv("SALIX_PAYPAL_SIMULATOR", "true")
    monkeypatch.setenv("SALIX_APP_URL", "http://app.test")

    from httpx import ASGITransport, AsyncClient

    from salix.app import create_app
    from salix.billing.paypal import reset_gateway
    from salix.config import get_settings
    from salix.providers import build_providers
    from salix.routers.deps import reset_org_cache
    from salix.schemas.org import Org
    from salix.store import db, repo, session_scope

    get_settings.cache_clear()
    reset_gateway()
    await db.dispose()
    await db.init_db()
    reset_org_cache()
    async with session_scope() as session:
        await repo.put_org(session, Org(id="org_s", name="S"))

    app = create_app()
    app.state.providers = build_providers(get_settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://app.test") as client:
        yield client

    reset_gateway()
    reset_org_cache()
    await db.dispose()
    get_settings.cache_clear()


async def buy(client):
    order = (await client.post("/api/billing/checkout", json={"pack_id": "starter"})).json()
    page = await client.get(order["approve_url"].replace("http://app.test", ""))
    assert page.status_code == 200
    approved = await client.get(f"/api/paypal-simulator/approve?token={order['order_id']}")
    assert approved.status_code == 302
    return order, approved


class TestTheFlow:
    async def test_it_says_it_is_simulated(self, world):
        state = (await world.get("/api/billing")).json()
        assert state["simulated"] is True and state["can_purchase"] is True
        order = (await world.post("/api/billing/checkout", json={"pack_id": "starter"})).json()
        page = await world.get(order["approve_url"].replace("http://app.test", ""))
        assert "This is not PayPal" in page.text and "USD 10.00" in page.text

    async def test_buy_then_upload(self, world):
        refused = await world.post(
            "/api/calls/upload", files={"file": ("a.mp3", MP3, "audio/mpeg")}, data={"salesperson": "Bilal"}
        )
        assert refused.status_code == 402

        order, approved = await buy(world)
        assert approved.headers["location"].startswith(f"http://app.test/billing/return?token={order['order_id']}")
        captured = (await world.post(f"/api/billing/orders/{order['order_id']}/capture")).json()
        assert captured["status"] == "completed" and captured["balance"] == 5

        accepted = await world.post(
            "/api/calls/upload", files={"file": ("a.mp3", MP3, "audio/mpeg")}, data={"salesperson": "Bilal"}
        )
        assert accepted.status_code == 202
        assert (await world.get("/api/billing")).json()["balance"] == 4

    async def test_paying_nothing_gets_nothing(self, world):
        order = (await world.post("/api/billing/checkout", json={"pack_id": "starter"})).json()
        response = await world.post(f"/api/billing/orders/{order['order_id']}/capture")
        assert response.status_code == 409
        assert (await world.get("/api/billing")).json()["balance"] == 0

    async def test_capturing_twice_grants_once(self, world):
        order, _ = await buy(world)
        for _ in range(3):
            await world.post(f"/api/billing/orders/{order['order_id']}/capture")
        assert (await world.get("/api/billing")).json()["balance"] == 5

    async def test_an_approved_tab_that_closed_still_settles(self, world):
        await buy(world)
        assert (await world.post("/api/billing/reconcile")).json()["balance"] == 5

    @pytest.mark.parametrize("token", ["<script>alert(1)</script>", "SIM999999", "x\"><img", ""])
    async def test_a_made_up_order_gets_a_404_and_nothing_is_echoed(self, world, token):
        page = await world.get("/api/paypal-simulator", params={"token": token})
        assert page.status_code == 404 and "<script>" not in page.text
        assert (await world.get("/api/paypal-simulator/approve", params={"token": token})).status_code == 404

    async def test_the_real_generated_sdk_is_what_ran(self, world):
        from salix.billing import paypal

        assert (await world.post("/api/billing/checkout", json={"pack_id": "starter"})).status_code == 200
        assert type(paypal._gateway._orders).__module__.startswith("paypalserversdk.")


class TestItCannotBeOnByAccident:
    def test_off_by_default(self):
        from salix.config import Settings

        settings = Settings()
        assert settings.paypal_simulated is False
        assert settings.paypal_configured is False
        assert settings.billing_enforced is False

    def test_real_keys_win(self):
        from salix.config import Settings

        settings = Settings(paypal_simulator=True, paypal_client_id="a", paypal_client_secret="b")
        assert settings.paypal_simulated is False and settings.paypal_configured is True

    def test_never_in_production(self):
        from salix.config import Settings

        settings = Settings(paypal_simulator=True, paypal_environment="production")
        assert settings.paypal_simulated is False and settings.paypal_configured is False

    async def test_its_pages_do_not_exist_when_it_is_off(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SALIX_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'o.db').as_posix()}")
        monkeypatch.setenv("SALIX_STORAGE_DIR", str(tmp_path / "s"))
        monkeypatch.setenv("SALIX_PROVIDER_MODE", "mock")

        from httpx import ASGITransport, AsyncClient

        from salix.app import create_app
        from salix.config import get_settings
        from salix.store import db

        get_settings.cache_clear()
        await db.dispose()
        try:
            app = create_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
                assert (await client.get("/api/paypal-simulator?token=SIM000001")).status_code == 404
                assert (await client.get("/api/paypal-simulator/approve?token=SIM000001")).status_code == 404
        finally:
            await db.dispose()
            get_settings.cache_clear()
