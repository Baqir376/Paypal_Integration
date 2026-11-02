"""Sign-in, sessions, and above all: one team can never see another's data.

Google's side is stood in for at the network edge only. ID tokens are really signed
with a key made here, and really verified by Google's own library against that
key's certificate, so a forged, expired or wrong-audience token fails the same way
it would in production.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt, jwt

CLIENT_ID = "client-123.apps.googleusercontent.com"
MP3 = b"\xff\xfb" + b"\x00" * 512

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_pem = _key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption(),
)
_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
_now = dt.datetime.now(dt.timezone.utc)
_cert = (
    x509.CertificateBuilder()
    .subject_name(_name)
    .issuer_name(_name)
    .public_key(_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(_now - dt.timedelta(days=1))
    .not_valid_after(_now + dt.timedelta(days=1))
    .sign(_key, hashes.SHA256())
)
CERTS = json.dumps({"k1": _cert.public_bytes(serialization.Encoding.PEM).decode()}).encode()


def signed(claims: dict, *, signer_pem: bytes = _pem) -> str:
    now = int(time.time())
    payload = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "iat": now,
        "exp": now + 600,
        "email_verified": True,
        **claims,
    }
    return jwt.encode(crypt.RSASigner.from_string(signer_pem, "k1"), payload).decode()


class FakeGoogle:
    """The token endpoint. Decides what ID token the next exchange gets."""

    def __init__(self):
        self.next_claims: dict = {}
        self.next_token: str | None = None
        self.posted: list[dict] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.posted.append(form)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "invalid_grant"})
        return httpx.Response(200, json={"id_token": self.next_token or signed(self.next_claims)})


class _CertResponse:
    status = 200
    data = CERTS
    headers: dict = {}


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    monkeypatch.setenv("SALIX_DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    monkeypatch.setenv("SALIX_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("SALIX_GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("SALIX_GOOGLE_CLIENT_SECRET", "shh")
    monkeypatch.setenv("SALIX_APP_URL", "http://app.test")
    monkeypatch.setenv("SALIX_PROVIDER_MODE", "mock")
    monkeypatch.setenv("SALIX_OWNER_EMAIL", "founder@acme.com")

    from httpx import ASGITransport, AsyncClient

    from salix.app import create_app
    from salix.auth import google
    from salix.config import get_settings
    from salix.providers import build_providers
    from salix.routers.deps import reset_org_cache
    from salix.store import db

    get_settings.cache_clear()
    await db.dispose()
    await db.init_db()
    reset_org_cache()

    fake = FakeGoogle()
    monkeypatch.setattr(
        google,
        "_http",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)),
    )
    monkeypatch.setattr(google, "_google_request", lambda: lambda url, **kw: _CertResponse())

    app = create_app()
    app.state.providers = build_providers(get_settings())

    def browser() -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://app.test")

    yield app, browser, fake

    reset_org_cache()
    await db.dispose()
    get_settings.cache_clear()


async def sign_in(browser, fake, sub="g-1", email="a@acme.com", name="Amna Khan", **claims):
    """The whole round trip, as a browser does it."""
    start = await browser.get("/api/auth/google/start", params={"next": claims.pop("next", "/console")})
    assert start.status_code == 302, start.text
    query = parse_qs(urlparse(start.headers["location"]).query)
    fake.next_token = None
    fake.next_claims = {"sub": sub, "email": email, "name": name, "nonce": query["nonce"][0], **claims}
    return await browser.get(
        "/api/auth/google/callback", params={"code": "c0de", "state": query["state"][0]}
    )


@pytest_asyncio.fixture
async def two_teams(world):
    app, browser, fake = world
    a, b = browser(), browser()
    await sign_in(a, fake, sub="g-a", email="a@acme.com", name="Amna Khan")
    await sign_in(b, fake, sub="g-b", email="b@rival.com", name="Bilal Shah")
    response = await a.post(
        "/api/calls/upload",
        files={"file": ("a.mp3", MP3, "audio/mpeg")},
        data={"salesperson": "Zara", "deal_id": ""},
    )
    assert response.status_code == 202, response.text
    yield a, b, response.json(), app
    await a.aclose()
    await b.aclose()


class TestSignIn:
    async def test_start_sends_a_complete_request_to_google(self, world):
        _, browser, _ = world
        async with browser() as client:
            response = await client.get("/api/auth/google/start")
        target = urlparse(response.headers["location"])
        query = parse_qs(target.query)
        assert target.netloc == "accounts.google.com"
        assert query["client_id"] == [CLIENT_ID]
        assert query["redirect_uri"] == ["http://app.test/api/auth/google/callback"]
        assert query["code_challenge_method"] == ["S256"]
        assert set(query["scope"][0].split()) == {"openid", "email", "profile"}
        assert query["state"] and query["nonce"] and query["code_challenge"]

    async def test_the_attempt_cookie_is_httponly(self, world):
        _, browser, _ = world
        async with browser() as client:
            response = await client.get("/api/auth/google/start")
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie

    async def test_a_full_sign_in(self, world):
        _, browser, fake = world
        async with browser() as client:
            response = await sign_in(client, fake)
            assert response.status_code == 302
            assert response.headers["location"] == "http://app.test/console"
            me = (await client.get("/api/auth/me")).json()
        assert me["user"]["email"] == "a@acme.com"
        assert me["user"]["role"] == "owner"
        assert me["user"]["org_name"] == "Amna's team"

    async def test_the_verifier_reaches_google_and_the_secret_is_sent(self, world):
        _, browser, fake = world
        async with browser() as client:
            await sign_in(client, fake)
        form = fake.posted[-1]
        assert form["code_verifier"] and form["client_secret"] == "shh"
        assert form["grant_type"] == "authorization_code"

    async def test_the_session_cookie_is_httponly_and_not_the_stored_value(self, world):
        from sqlalchemy import select

        from salix.store import session_scope
        from salix.store.models import SessionRow

        _, browser, fake = world
        async with browser() as client:
            response = await sign_in(client, fake)
            cookies = response.headers.get_list("set-cookie")
            session_cookie = next(c for c in cookies if c.startswith("salix_session="))
            assert "HttpOnly" in session_cookie
            token = session_cookie.split(";")[0].split("=", 1)[1]
        async with session_scope() as session:
            rows = list((await session.execute(select(SessionRow))).scalars())
        assert len(rows) == 1 and rows[0].token_hash != token and token not in rows[0].token_hash

    async def test_secure_cookie_on_https(self, world, monkeypatch):
        from salix.config import get_settings

        _, browser, fake = world
        monkeypatch.setattr(get_settings(), "app_url", "https://app.test")
        async with browser() as client:
            response = await client.get("/api/auth/google/start")
        assert "Secure" in response.headers["set-cookie"]

    async def test_signing_in_again_is_the_same_person_with_a_fresh_profile(self, world):
        _, browser, fake = world
        async with browser() as first:
            await sign_in(first, fake, name="Amna Khan")
            one = (await first.get("/api/auth/me")).json()["user"]
        async with browser() as second:
            await sign_in(second, fake, name="Amna K", email="new@acme.com")
            two = (await second.get("/api/auth/me")).json()["user"]
        assert one["id"] == two["id"] and one["org_id"] == two["org_id"]
        assert two["name"] == "Amna K" and two["email"] == "new@acme.com"

    async def test_logout_ends_the_session_on_the_server(self, world):
        _, browser, fake = world
        async with browser() as client:
            await sign_in(client, fake)
            token = client.cookies.get("salix_session")
            assert (await client.post("/api/auth/logout")).status_code == 204
            assert (await client.get("/api/auth/me")).json()["user"] is None
        async with browser() as thief:
            thief.cookies.set("salix_session", token)
            assert (await thief.get("/api/reps")).status_code == 401

    async def test_an_expired_session_is_refused(self, world):
        from sqlalchemy import update

        from salix.store import session_scope
        from salix.store.models import SessionRow, utcnow

        _, browser, fake = world
        async with browser() as client:
            await sign_in(client, fake)
            async with session_scope() as session:
                await session.execute(
                    update(SessionRow).values(expires_at=utcnow() - dt.timedelta(minutes=1))
                )
            assert (await client.get("/api/reps")).status_code == 401

    async def test_a_made_up_cookie_is_refused(self, world):
        _, browser, _ = world
        async with browser() as client:
            client.cookies.set("salix_session", "nonsense")
            assert (await client.get("/api/reps")).status_code == 401


class TestForgery:
    """Each ends at the login page with no session."""

    async def _attempt(self, client, fake):
        start = await client.get("/api/auth/google/start")
        return parse_qs(urlparse(start.headers["location"]).query)

    async def _refused(self, client, response, reason):
        assert response.status_code == 302
        assert response.headers["location"] == f"http://app.test/login?error={reason}"
        assert "salix_session" not in client.cookies

    async def test_wrong_state(self, world):
        _, browser, fake = world
        async with browser() as client:
            await self._attempt(client, fake)
            response = await client.get("/api/auth/google/callback", params={"code": "c", "state": "evil"})
            await self._refused(client, response, "expired")
        assert not fake.posted, "nothing should reach Google on a bad state"

    async def test_no_attempt_cookie_at_all(self, world):
        _, browser, fake = world
        async with browser() as client:
            response = await client.get("/api/auth/google/callback", params={"code": "c", "state": "s"})
            await self._refused(client, response, "expired")

    async def test_a_tampered_attempt_cookie(self, world):
        _, browser, fake = world
        async with browser() as client:
            client.cookies.set("salix_oauth", "{not json")
            response = await client.get("/api/auth/google/callback", params={"code": "c", "state": "s"})
            await self._refused(client, response, "expired")

    async def test_user_pressed_cancel(self, world):
        _, browser, _ = world
        async with browser() as client:
            response = await client.get("/api/auth/google/callback", params={"error": "access_denied"})
            await self._refused(client, response, "cancelled")

    @pytest.mark.parametrize(
        "claims",
        [
            {"aud": "someone-elses-app"},
            {"iss": "https://evil.example"},
            {"exp": 1000, "iat": 900},
            {"email_verified": False},
            {"nonce": "a-different-attempt"},
        ],
        ids=["audience", "issuer", "expired", "unverified-email", "nonce"],
    )
    async def test_a_bad_id_token(self, world, claims):
        _, browser, fake = world
        async with browser() as client:
            query = await self._attempt(client, fake)
            base = {"sub": "g", "email": "x@x.com", "name": "X", "nonce": query["nonce"][0]}
            fake.next_token = signed({**base, **claims})
            response = await client.get(
                "/api/auth/google/callback", params={"code": "c", "state": query["state"][0]}
            )
            await self._refused(client, response, "failed")

    async def test_a_token_signed_with_the_wrong_key(self, world):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        _, browser, fake = world
        async with browser() as client:
            query = await self._attempt(client, fake)
            fake.next_token = signed(
                {"sub": "g", "email": "x@x.com", "nonce": query["nonce"][0]}, signer_pem=other
            )
            response = await client.get(
                "/api/auth/google/callback", params={"code": "c", "state": query["state"][0]}
            )
            await self._refused(client, response, "failed")

    async def test_google_refusing_the_code(self, world):
        _, browser, fake = world
        async with browser() as client:
            query = await self._attempt(client, fake)
            fake.status = 400
            response = await client.get(
                "/api/auth/google/callback", params={"code": "c", "state": query["state"][0]}
            )
            await self._refused(client, response, "failed")

    @pytest.mark.parametrize(
        "target",
        ["https://evil.example", "//evil.example", "/\\evil.example", "evil", "", "/ok\r\nSet-Cookie: x"],
    )
    def test_next_cannot_leave_the_site(self, target):
        from salix.auth.google import safe_next

        assert safe_next(target) == "/console"

    def test_next_can_go_somewhere_on_the_site(self):
        from salix.auth.google import safe_next

        assert safe_next("/reps/rep_1?x=1") == "/reps/rep_1?x=1"


class TestEveryRouteIsGuarded:
    """Walks the app, so a route added next year is checked without anyone asking."""

    PUBLIC = {
        "/api/health", "/api/ready", "/api/auth/me", "/api/auth/google/start",
        "/api/auth/google/callback", "/api/auth/logout",
        # How somebody without a session gets one.
        "/api/auth/signup", "/api/auth/login", "/api/auth/password/forgot",
        "/api/auth/password/reset", "/api/auth/email/verify",
        # PayPal is the caller. Refused without a valid signature: see test_hardening.
        "/api/billing/webhook",
    }

    async def test_nothing_answers_without_a_session(self, world):
        from fastapi.routing import APIRoute

        app, browser, _ = world
        checked = 0
        async with browser() as client:
            for route in app.routes:
                if not isinstance(route, APIRoute) or not route.path.startswith("/api"):
                    continue
                if route.path in self.PUBLIC:
                    continue
                path = route.path.replace("{", "").replace("}", "")
                for method in route.methods - {"HEAD", "OPTIONS"}:
                    response = await client.request(method, path)
                    assert response.status_code == 401, f"{method} {route.path} -> {response.status_code}"
                    checked += 1
        assert checked > 30, f"only walked {checked} routes"

    async def test_recordings_need_a_session_too(self, two_teams, world):
        _, browser, _ = world
        _, _, body, _ = two_teams
        async with browser() as stranger:
            response = await stranger.get(f"/audio/{body['call_id']}.mp3")
        assert response.status_code == 404

    async def test_health_says_nothing_about_anyones_data(self, two_teams, world):
        _, browser, _ = world
        async with browser() as stranger:
            health = (await stranger.get("/api/health")).json()
        assert health["calls"] == 0 and health["plays"] == 0 and health["moments"] == 0


class TestOneTeamCannotSeeAnother:
    async def test_bs_lists_are_empty(self, two_teams):
        _, b, _, _ = two_teams
        for path in ("/api/calls", "/api/reps", "/api/plays", "/api/deals", "/api/reports", "/api/dojo/sessions"):
            response = await b.get(path)
            assert response.status_code == 200, path
            assert response.json() == [], f"{path} leaked {response.json()}"
        assert (await b.get("/api/search", params={"q": "price objection"})).json() == []
        assert (await b.get("/api/reports/latest")).json() is None

    async def test_as_data_is_really_there(self, two_teams):
        a, _, body, _ = two_teams
        assert len((await a.get("/api/calls")).json()) == 1
        assert (await a.get(f"/api/calls/{body['call_id']}")).status_code == 200
        assert (await a.get(f"/api/reps/{body['rep_id']}")).status_code == 200
        assert (await a.get(f"/audio/{body['call_id']}.mp3")).content == MP3

    @pytest.mark.parametrize(
        "method,template",
        [
            ("get", "/api/calls/{call}"),
            ("get", "/api/calls/{call}/timeline"),
            ("get", "/api/calls/{call}/events"),
            ("get", "/audio/{call}.mp3"),
            ("get", "/api/reps/{rep}"),
            ("post", "/api/reps/{rep}/coach"),
            ("post", "/api/reps/{rep}/restore"),
            ("delete", "/api/reps/{rep}"),
        ],
    )
    async def test_guessing_an_id_gets_nothing(self, two_teams, method, template):
        a, b, body, _ = two_teams
        path = template.format(call=body["call_id"], rep=body["rep_id"])
        response = await getattr(b, method)(path)
        assert response.status_code == 404, f"{path} -> {response.status_code}"
        assert (await a.get(f"/api/reps/{body['rep_id']}")).status_code == 200

    async def test_a_rep_cannot_be_edited_across_teams(self, two_teams):
        a, b, body, _ = two_teams
        response = await b.patch(f"/api/reps/{body['rep_id']}", json={"name": "Hacked"})
        assert response.status_code == 404
        assert (await a.get(f"/api/reps/{body['rep_id']}")).json()["snapshot"]["rep"]["name"] == "Zara"

    async def test_uploading_onto_another_teams_rep(self, two_teams):
        _, b, body, _ = two_teams
        response = await b.post(
            "/api/calls/upload",
            files={"file": ("a.mp3", MP3, "audio/mpeg")},
            data={"rep_id": body["rep_id"]},
        )
        assert response.status_code == 400

    async def test_a_dojo_session_cannot_be_started_for_another_teams_rep(self, two_teams):
        _, b, body, _ = two_teams
        response = await b.post("/api/dojo/start", json={"rep_id": body["rep_id"]})
        assert response.status_code == 404
        response = await b.post("/api/roleplay/start", json={"rep_id": body["rep_id"]})
        assert response.status_code == 404

    async def test_a_session_cannot_be_overwritten_across_teams(self, two_teams):
        """The session travels with the request, so its id is chosen by the client."""
        a, b, body, _ = two_teams
        started = (await a.post("/api/dojo/start", json={"rep_id": body["rep_id"]})).json()["session"]
        started["turns"] = [{"index": 0, "speaker": "rep", "text": "Hello there, how are you?", "start_ms": 0, "end_ms": 1000}]
        assert (await a.post("/api/dojo/end", json={"session": started})).status_code == 200

        await b.post("/api/reps", json={"name": "Mine"})
        mine = (await b.get("/api/reps")).json()[0]["rep"]["id"]
        attack = {**started, "rep_id": mine, "scenario": "overwritten"}
        assert (await b.post("/api/dojo/end", json={"session": attack})).status_code == 404
        kept = (await a.get("/api/dojo/sessions")).json()
        assert kept[0]["scenario"] != "overwritten"

    async def test_a_dojo_turn_cannot_use_another_teams_rep(self, two_teams):
        a, b, body, _ = two_teams
        started = (await a.post("/api/dojo/start", json={"rep_id": body["rep_id"]})).json()["session"]
        response = await b.post("/api/dojo/turn", json={"session": started, "text": "hello"})
        assert response.status_code == 404

    async def test_credits_are_per_team(self, two_teams):
        from salix.billing import credits
        from salix.store import session_scope

        a, b, _, _ = two_teams
        org_a = (await a.get("/api/auth/me")).json()["user"]["org_id"]
        async with session_scope() as session:
            await credits._add(session, org_a, 7)
        assert (await a.get("/api/billing")).json()["balance"] == 7
        assert (await b.get("/api/billing")).json()["balance"] == 0

    async def test_a_payment_cannot_be_captured_across_teams(self, two_teams):
        from salix.store import session_scope
        from salix.store.models import PaymentOrderRow, utcnow

        a, b, _, _ = two_teams
        org_a = (await a.get("/api/auth/me")).json()["user"]["org_id"]
        async with session_scope() as session:
            session.add(
                PaymentOrderRow(
                    id="ORDERA", org_id=org_a, pack_id="starter", credits=5, amount="10.00",
                    currency="USD", status="created", created_at=utcnow(), updated_at=utcnow(),
                )
            )
        assert (await b.post("/api/billing/orders/ORDERA/capture")).status_code == 404

    @pytest.mark.parametrize("name", ["..%2f..%2fsecret.txt", "a/b.mp3", "CON", "x.mp3.exe.json.more"])
    async def test_recording_names_cannot_escape(self, two_teams, name):
        a, _, _, _ = two_teams
        assert (await a.get(f"/audio/{name}")).status_code == 404


class TestInvites:
    async def test_an_invited_person_joins_the_team(self, world):
        _, browser, fake = world
        async with browser() as owner, browser() as invited:
            await sign_in(owner, fake, sub="g-owner", email="boss@acme.com")
            assert (await owner.post("/api/reps", json={"name": "Sana"})).status_code == 201
            rep = (await owner.get("/api/reps")).json()[0]["rep"]["id"]
            response = await owner.post("/api/team/invites", json={"email": " Sana@Acme.com ", "rep_id": rep})
            assert response.status_code == 201

            await sign_in(invited, fake, sub="g-sana", email="sana@acme.com", name="Sana")
            me = (await invited.get("/api/auth/me")).json()["user"]
            owner_me = (await owner.get("/api/auth/me")).json()["user"]
            assert me["org_id"] == owner_me["org_id"]
            assert me["role"] == "member"
            assert me["rep_id"] == rep
            # The same team, so the same data.
            assert (await invited.get(f"/api/reps/{rep}")).status_code == 200

            team = (await owner.get("/api/team")).json()
            assert sorted(m["email"] for m in team["members"]) == ["boss@acme.com", "sana@acme.com"]
            assert team["invites"] == []

    async def test_an_uninvited_person_gets_their_own_team(self, world):
        _, browser, fake = world
        async with browser() as one, browser() as two:
            await sign_in(one, fake, sub="1", email="one@a.com")
            await sign_in(two, fake, sub="2", email="two@b.com")
            first = (await one.get("/api/auth/me")).json()["user"]
            second = (await two.get("/api/auth/me")).json()["user"]
        assert first["org_id"] != second["org_id"]
        assert second["role"] == "owner"

    async def test_only_the_owner_can_manage(self, world):
        _, browser, fake = world
        async with browser() as owner, browser() as member:
            await sign_in(owner, fake, sub="o", email="o@a.com")
            await owner.post("/api/team/invites", json={"email": "m@a.com"})
            await sign_in(member, fake, sub="m", email="m@a.com")
            owner_id = (await owner.get("/api/auth/me")).json()["user"]["id"]

            assert (await member.post("/api/team/invites", json={"email": "x@a.com"})).status_code == 403
            assert (await member.delete(f"/api/team/members/{owner_id}")).status_code == 403
            assert (await member.patch("/api/team/org", json={"name": "Mine"})).status_code == 403
            assert (await member.get("/api/team")).json()["can_manage"] is False

    async def test_removing_a_member_ends_their_session(self, world):
        _, browser, fake = world
        async with browser() as owner, browser() as member:
            await sign_in(owner, fake, sub="o", email="o@a.com")
            await owner.post("/api/team/invites", json={"email": "m@a.com"})
            await sign_in(member, fake, sub="m", email="m@a.com")
            member_id = (await member.get("/api/auth/me")).json()["user"]["id"]
            assert (await owner.delete(f"/api/team/members/{member_id}")).status_code == 204
            assert (await member.get("/api/reps")).status_code == 401

    async def test_an_owner_cannot_remove_themselves(self, world):
        _, browser, fake = world
        async with browser() as owner:
            await sign_in(owner, fake)
            me = (await owner.get("/api/auth/me")).json()["user"]["id"]
            assert (await owner.delete(f"/api/team/members/{me}")).status_code == 409

    async def test_a_duplicate_invite_and_a_bad_email(self, world):
        _, browser, fake = world
        async with browser() as owner:
            await sign_in(owner, fake)
            assert (await owner.post("/api/team/invites", json={"email": "m@a.com"})).status_code == 201
            assert (await owner.post("/api/team/invites", json={"email": "M@A.com"})).status_code == 409
            assert (await owner.post("/api/team/invites", json={"email": "nope"})).status_code == 422
            assert (await owner.post("/api/team/invites", json={"email": "a@acme.com"})).status_code == 409

    async def test_an_invite_cannot_point_at_another_teams_rep(self, two_teams):
        _, b, body, _ = two_teams
        response = await b.post("/api/team/invites", json={"email": "x@y.com", "rep_id": body["rep_id"]})
        assert response.status_code == 400

    async def test_invites_cannot_be_cancelled_across_teams(self, two_teams):
        a, b, _, _ = two_teams
        made = (await a.post("/api/team/invites", json={"email": "x@y.com"})).json()
        assert (await b.delete(f"/api/team/invites/{made['id']}")).status_code == 404


class TestExistingData:
    async def test_the_named_owner_claims_it(self, world):
        from salix.schemas.org import Org
        from salix.store import repo, session_scope

        _, browser, fake = world
        async with session_scope() as session:
            await repo.put_org(session, Org(id="org_old", name="Old data"))
        async with browser() as client:
            await sign_in(client, fake, sub="f", email="founder@acme.com", name="F")
            me = (await client.get("/api/auth/me")).json()["user"]
        assert me["org_id"] == "org_old" and me["role"] == "owner"

    async def test_a_stranger_signing_in_first_does_not(self, world):
        from salix.schemas.org import Org
        from salix.store import repo, session_scope

        _, browser, fake = world
        async with session_scope() as session:
            await repo.put_org(session, Org(id="org_old", name="Old data"))
        async with browser() as client:
            await sign_in(client, fake, sub="s", email="stranger@else.com", name="S")
            me = (await client.get("/api/auth/me")).json()["user"]
        assert me["org_id"] != "org_old"


class TestModes:
    def test_auto_requires_sign_in_only_with_google_configured(self):
        from salix.config import Settings

        assert Settings(auth_mode="auto").auth_required is False
        assert Settings(auth_mode="auto", google_client_id="a", google_client_secret="b").auth_required is True

    def test_off_is_off(self):
        from salix.config import Settings

        assert Settings(auth_mode="off", google_client_id="a", google_client_secret="b").auth_required is False

    @pytest.mark.parametrize("mode", ["on", "ON", "yes", "typo"])
    def test_anything_else_requires_it(self, mode):
        from salix.config import Settings

        assert Settings(auth_mode=mode).auth_required is True
