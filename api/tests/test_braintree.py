"""Credits bought through Braintree. The gateway object is faked; nothing else is."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio

MP3 = b"\xff\xfb" + b"\x00" * 512


class FakeTransactions:
    def __init__(self):
        self.sales: list[dict] = []
        self.status = "submitted_for_settlement"
        self.amount: Decimal | None = None
        self.currency = "USD"
        self.decline: str | None = None
        self.down = False
        self.spent: set[str] = set()
        self.stored: dict[str, SimpleNamespace] = {}

    def sale(self, params):
        if self.down:
            raise ConnectionError("secret-merchant-detail")
        self.sales.append(params)
        if self.decline:
            return SimpleNamespace(is_success=False, message=self.decline, transaction=None)
        if params["payment_method_nonce"] in self.spent:
            return SimpleNamespace(is_success=False, message="Cannot use a payment_method_nonce more than once.", transaction=None)
        self.spent.add(params["payment_method_nonce"])
        transaction = SimpleNamespace(
            id=f"tx{len(self.sales)}",
            status=self.status,
            amount=self.amount if self.amount is not None else Decimal(params["amount"]),
            currency_iso_code=self.currency,
        )
        self.stored[params["order_id"]] = transaction
        return SimpleNamespace(is_success=True, message="", transaction=transaction)

    def search(self, query):
        wanted = next(iter(self.stored.values()), None)
        return SimpleNamespace(items=[wanted] if wanted else [])


class FakeGateway:
    def __init__(self):
        self.transaction = FakeTransactions()
        self.client_token = SimpleNamespace(generate=lambda: "client-token-123")


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.setenv("SALIX_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    monkeypatch.setenv("SALIX_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("SALIX_PROVIDER_MODE", "mock")
    monkeypatch.setenv("SALIX_BRAINTREE_MERCHANT_ID", "m")
    monkeypatch.setenv("SALIX_BRAINTREE_PUBLIC_KEY", "p")
    monkeypatch.setenv("SALIX_BRAINTREE_PRIVATE_KEY", "s")

    from httpx import ASGITransport, AsyncClient

    from salix.app import create_app
    from salix.billing.braintree_gateway import BraintreePayments, reset_payments
    from salix.config import get_settings
    from salix.providers import build_providers
    from salix.routers.deps import reset_org_cache
    from salix.schemas.org import Org
    from salix.store import db, repo, session_scope

    get_settings.cache_clear()
    await db.dispose()
    await db.init_db()
    reset_org_cache()
    async with session_scope() as session:
        await repo.put_org(session, Org(id="org_b", name="B"))

    fake = FakeGateway()
    reset_payments(BraintreePayments(get_settings(), gateway=fake))
    app = create_app()
    app.state.providers = build_providers(get_settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client, fake

    reset_payments()
    reset_org_cache()
    await db.dispose()
    get_settings.cache_clear()


async def balance(client):
    return (await client.get("/api/billing")).json()["balance"]


async def pay(client, pack="starter", nonce="fake-valid-nonce"):
    return await client.post("/api/billing/braintree/pay", json={"pack_id": pack, "nonce": nonce})


class TestPaying:
    async def test_the_page_is_told_which_provider(self, world):
        client, _ = world
        state = (await client.get("/api/billing")).json()
        assert state["provider"] == "braintree"
        assert state["can_purchase"] is True and state["enforced"] is True and state["simulated"] is False

    async def test_paypal_is_offered_only_when_switched_on(self, world, monkeypatch):
        from salix.config import get_settings

        client, _ = world
        settings = get_settings()
        assert (await client.get("/api/billing")).json()["paypal_wallet"] is False
        monkeypatch.setattr(settings, "braintree_paypal", True)
        assert (await client.get("/api/billing")).json()["paypal_wallet"] is True

    async def test_the_receipt_says_what_was_paid(self, world):
        client, _ = world
        order = (await pay(client)).json()
        assert order["status"] == "completed"
        assert (order["amount"], order["currency"]) == ("10.00", "USD")

    async def test_a_client_token_comes_from_the_server(self, world):
        client, _ = world
        assert (await client.post("/api/billing/braintree/client-token")).json()["client_token"] == "client-token-123"

    async def test_paying_grants_the_pack(self, world):
        client, _ = world
        response = await pay(client)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "completed" and response.json()["credits"] == 5
        assert await balance(client) == 5

    async def test_the_full_paywall(self, world):
        client, _ = world
        upload = lambda: client.post(
            "/api/calls/upload", files={"file": ("a.mp3", MP3, "audio/mpeg")}, data={"salesperson": "Bilal"}
        )
        assert (await upload()).status_code == 402
        await pay(client)
        assert (await upload()).status_code == 202
        assert await balance(client) == 4

    async def test_the_price_comes_from_the_server(self, world):
        client, fake = world
        await pay(client, pack="team")
        assert fake.transaction.sales[0]["amount"] == "40.00"
        assert fake.transaction.sales[0]["options"] == {"submit_for_settlement": True}
        response = await client.post(
            "/api/billing/braintree/pay", json={"pack_id": "team", "nonce": "n", "amount": "0.01"}
        )
        assert response.status_code == 422

    async def test_an_unknown_pack_never_reaches_braintree(self, world):
        client, fake = world
        assert (await pay(client, pack="free")).status_code == 400
        assert not fake.transaction.sales

    async def test_a_decline_grants_nothing_and_says_why(self, world):
        client, fake = world
        fake.transaction.decline = "Processor declined"
        response = await pay(client)
        assert response.status_code == 402 and "Processor declined" in response.json()["detail"]
        assert await balance(client) == 0

    async def test_a_nonce_cannot_buy_twice(self, world):
        client, _ = world
        await pay(client)
        assert (await pay(client)).status_code == 402
        assert await balance(client) == 5

    async def test_the_wrong_amount_goes_to_review(self, world):
        client, fake = world
        fake.transaction.amount = Decimal("0.01")
        assert (await pay(client)).json()["status"] == "review"
        assert await balance(client) == 0

    async def test_the_wrong_currency_goes_to_review(self, world):
        """A sandbox can default to another currency, where 10.00 means something else."""
        client, fake = world
        fake.transaction.currency = "PKR"
        assert (await pay(client)).json()["status"] == "review"
        assert await balance(client) == 0

    @pytest.mark.parametrize("status", ["settled", "settling", "authorized"])
    async def test_every_paid_status_counts(self, world, status):
        client, fake = world
        fake.transaction.status = status
        assert (await pay(client)).json()["status"] == "completed"

    @pytest.mark.parametrize("status", ["failed", "gateway_rejected", "processor_declined"])
    async def test_every_failed_status_grants_nothing(self, world, status):
        client, fake = world
        fake.transaction.status = status
        assert (await pay(client)).json()["status"] == "failed"
        assert await balance(client) == 0

    async def test_braintree_being_down_leaks_nothing(self, world):
        client, fake = world
        fake.transaction.down = True
        response = await pay(client)
        assert response.status_code == 502 and "secret" not in response.text
        assert await balance(client) == 0

    async def test_a_lost_response_is_caught_up_on(self, world):
        """It charged, then this process died before writing it down."""
        from salix.store import session_scope
        from salix.store.models import PaymentOrderRow, utcnow

        client, fake = world
        fake.transaction.sale({"amount": "10.00", "payment_method_nonce": "n", "order_id": "bt_lost"})
        async with session_scope() as session:
            session.add(
                PaymentOrderRow(
                    id="bt_lost", org_id="org_b", pack_id="starter", credits=5, amount="10.00",
                    currency="USD", status="created", created_at=utcnow(), updated_at=utcnow(),
                )
            )
        assert (await client.post("/api/billing/reconcile")).json()["balance"] == 5
        assert (await client.post("/api/billing/reconcile")).json()["balance"] == 5


class TestWhoWins:
    def _s(self, **kw):
        from salix.config import Settings

        return Settings(**kw)

    BT = dict(braintree_merchant_id="m", braintree_public_key="p", braintree_private_key="s")

    def test_nothing_configured(self):
        settings = self._s()
        assert settings.payment_provider is None and settings.billing_enforced is False

    def test_braintree_beats_the_simulator(self):
        settings = self._s(paypal_simulator=True, **self.BT)
        assert settings.payment_provider == "braintree" and settings.paypal_simulated is False

    def test_paypal_keys_win(self):
        settings = self._s(paypal_client_id="a", paypal_client_secret="b", **self.BT)
        assert settings.payment_provider == "paypal"

    def test_simulator_is_the_last_resort(self):
        assert self._s(paypal_simulator=True).payment_provider == "simulator"

    def test_half_the_keys_is_no_keys(self):
        assert self._s(braintree_merchant_id="m").payment_provider is None

    async def test_its_routes_refuse_when_not_configured(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SALIX_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'n.db').as_posix()}")
        monkeypatch.setenv("SALIX_STORAGE_DIR", str(tmp_path / "s"))
        monkeypatch.setenv("SALIX_PROVIDER_MODE", "mock")

        from httpx import ASGITransport, AsyncClient

        from salix.app import create_app
        from salix.config import get_settings
        from salix.routers.deps import reset_org_cache
        from salix.schemas.org import Org
        from salix.store import db, repo, session_scope

        get_settings.cache_clear()
        await db.dispose()
        await db.init_db()
        reset_org_cache()
        async with session_scope() as session:
            await repo.put_org(session, Org(id="o", name="O"))
        try:
            app = create_app()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
                assert (await client.post("/api/billing/braintree/client-token")).status_code == 503
                response = await client.post("/api/billing/braintree/pay", json={"pack_id": "starter", "nonce": "n"})
                assert response.status_code == 503
        finally:
            reset_org_cache()
            await db.dispose()
            get_settings.cache_clear()
