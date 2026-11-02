"""Email and password accounts, and above all: typing an address proves nothing.

Invitations and ownership are matched on address, so the tests that matter most here
are the ones where somebody signs up with an address that belongs to someone else.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from salix.auth import accounts, mailer, passwords
from salix.store import db
from salix.store.models import EmailTokenRow, PasswordRow

from .test_accounts import MP3, sign_in, world  # noqa: F401

GOOD = "correct horse battery"
OTHER = "a different long password"


@pytest.fixture
def inbox(monkeypatch):
    """A mail server that keeps what it is given. Ask for it before `world`."""
    monkeypatch.setenv("SALIX_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SALIX_SMTP_FROM", "salix@test")
    sent = []
    monkeypatch.setattr(mailer, "_send", lambda settings, message: sent.append(message))
    return sent


def link_in(message) -> str:
    return re.search(r"http\S+", message.get_content()).group(0)


def token_in(message) -> str:
    return parse_qs(urlparse(link_in(message)).query)["token"][0]


async def signup(client, email="amna@acme.com", name="Amna Khan", password=GOOD):
    return await client.post("/api/auth/signup", json={"name": name, "email": email, "password": password})


async def me(client):
    return (await client.get("/api/auth/me")).json()["user"]


class TestSignUpAndLogIn:
    async def test_signing_up_signs_you_in_to_a_new_team(self, world):
        _, browser, _ = world
        async with browser() as client:
            response = await signup(client, email="Amna@Acme.com ")
            assert response.status_code == 200, response.text
            user = await me(client)
        assert user["email"] == "amna@acme.com"
        assert user["org_name"] == "Amna's team"
        assert user["role"] == "owner"
        assert user["email_verified"] is False

    async def test_the_session_cookie_is_httponly(self, world):
        _, browser, _ = world
        async with browser() as client:
            cookie = (await signup(client)).headers["set-cookie"]
        assert accounts.SESSION_COOKIE in cookie and "httponly" in cookie.lower()

    async def test_the_password_itself_is_never_stored_or_returned(self, world):
        _, browser, _ = world
        async with browser() as client:
            response = await signup(client)
        assert GOOD not in response.text and "hash" not in response.text
        async with db.session_scope() as session:
            row = (await session.execute(select(PasswordRow))).scalar_one()
        assert GOOD not in row.hash and row.hash.startswith("scrypt$")

    async def test_logging_back_in(self, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            await client.post("/api/auth/logout")
            assert await me(client) is None
            response = await client.post("/api/auth/login", json={"email": "AMNA@acme.com", "password": GOOD})
            assert response.status_code == 200, response.text
            assert (await me(client))["name"] == "Amna Khan"

    @pytest.mark.parametrize(
        "body, words",
        [
            ({"name": "", "email": "a@acme.com", "password": GOOD}, "name"),
            ({"name": "A", "email": "not-an-email", "password": GOOD}, "email"),
            ({"name": "A", "email": "a@acme.com", "password": "short"}, "at least"),
            ({"name": "A", "email": "a@acme.com", "password": "x" * 129}, "at most"),
        ],
    )
    async def test_bad_details_are_explained(self, world, body, words):
        _, browser, _ = world
        async with browser() as client:
            response = await client.post("/api/auth/signup", json=body)
        assert response.status_code == 400
        assert words in response.json()["detail"]

    async def test_a_wrong_password_and_an_unknown_address_look_the_same(self, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            await client.post("/api/auth/logout")
            wrong = await client.post("/api/auth/login", json={"email": "amna@acme.com", "password": OTHER})
            unknown = await client.post("/api/auth/login", json={"email": "nobody@acme.com", "password": OTHER})
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["detail"] == unknown.json()["detail"]
        assert "set-cookie" not in wrong.headers

    async def test_repeated_guessing_locks_the_account_even_for_the_right_password(self, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            await client.post("/api/auth/logout")
            for _ in range(accounts.MAX_FAILURES):
                await client.post("/api/auth/login", json={"email": "amna@acme.com", "password": OTHER})
            response = await client.post("/api/auth/login", json={"email": "amna@acme.com", "password": GOOD})
        assert response.status_code == 401

    async def test_a_right_password_clears_the_count(self, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            for _ in range(accounts.MAX_FAILURES - 1):
                await client.post("/api/auth/login", json={"email": "amna@acme.com", "password": OTHER})
            assert (await client.post("/api/auth/login", json={"email": "amna@acme.com", "password": GOOD})).status_code == 200
            await client.post("/api/auth/login", json={"email": "amna@acme.com", "password": OTHER})
            assert (await client.post("/api/auth/login", json={"email": "amna@acme.com", "password": GOOD})).status_code == 200

    async def test_a_huge_guess_is_refused_without_hashing(self, world, monkeypatch):
        _, browser, _ = world

        async def refuse(*_args):
            raise AssertionError("hashed an oversized password")

        monkeypatch.setattr(passwords, "check_password", refuse)
        async with browser() as client:
            response = await client.post("/api/auth/login", json={"email": "a@acme.com", "password": "x" * 4000})
        assert response.status_code == 401

    async def test_a_stored_hash_with_a_lower_cost_still_checks(self):
        salt = bytes(16)
        stored = f"scrypt$1024$8$1${salt.hex()}${passwords._derive(GOOD, salt, 1024, 8, 1).hex()}"
        assert await passwords.check_password(GOOD, stored)
        assert not await passwords.check_password(OTHER, stored)
        assert not await passwords.check_password(GOOD, "garbage")

    async def test_two_people_see_only_their_own_calls(self, world):
        _, browser, _ = world
        async with browser() as a, browser() as b:
            await signup(a)
            await signup(b, email="bilal@rival.com", name="Bilal Shah")
            call = await a.post(
                "/api/calls/upload",
                files={"file": ("a.mp3", MP3, "audio/mpeg")},
                data={"salesperson": "Zara", "deal_id": ""},
            )
            assert call.status_code == 202, call.text
            assert (await b.get(f"/api/calls/{call.json()['call_id']}")).status_code == 404

    async def test_no_accounts_means_no_password_routes(self, world, monkeypatch):
        from salix.config import get_settings

        app, browser, _ = world
        monkeypatch.setenv("SALIX_AUTH_MODE", "off")
        get_settings.cache_clear()
        async with browser() as client:
            assert (await signup(client)).status_code == 404
            assert (await client.post("/api/auth/login", json={"email": "a@a.co", "password": GOOD})).status_code == 404
        get_settings.cache_clear()


class TestTypingAnAddressProvesNothing:
    async def test_it_cannot_take_an_address_a_google_account_holds(self, world):
        _, browser, fake = world
        async with browser() as owner, browser() as stranger:
            await sign_in(owner, fake, sub="g-a", email="amna@acme.com")
            response = await signup(stranger)
            assert response.status_code == 409
            assert await me(stranger) is None
            login = await stranger.post("/api/auth/login", json={"email": "amna@acme.com", "password": GOOD})
            assert login.status_code == 401

    async def test_it_cannot_be_registered_twice(self, world):
        _, browser, _ = world
        async with browser() as first, browser() as second:
            await signup(first)
            assert (await signup(second, password=OTHER)).status_code == 409
            # And the first person's password still works.
            await first.post("/api/auth/logout")
            assert (await first.post("/api/auth/login", json={"email": "amna@acme.com", "password": GOOD})).status_code == 200

    async def test_it_does_not_claim_an_invitation(self, world):
        _, browser, fake = world
        async with browser() as owner, browser() as stranger:
            await sign_in(owner, fake, sub="g-a", email="owner@acme.com", name="Owner Person")
            team_id = (await me(owner))["org_id"]
            assert (await owner.post("/api/team/invites", json={"email": "sana@acme.com"})).status_code == 201
            await signup(stranger, email="sana@acme.com", name="Not Sana")
            user = await me(stranger)
            assert user["org_id"] != team_id and user["role"] == "owner"
            # The invitation is still there for the real Sana.
            invites = (await owner.get("/api/team")).json()["invites"]
            assert [i["email"] for i in invites] == ["sana@acme.com"]

    async def test_it_does_not_claim_the_deployment_owners_data(self, world):
        from salix.schemas.org import Org
        from salix.store import repo

        _, browser, _ = world
        async with db.session_scope() as session:
            await repo.put_org(session, Org(id="org_existing", name="Existing"))
            await session.commit()
        async with browser() as stranger:
            await signup(stranger, email="founder@acme.com", name="Not Founder")
            assert (await me(stranger))["org_id"] != "org_existing"

    async def test_it_cannot_invite_anyone(self, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            response = await client.post("/api/team/invites", json={"email": "friend@acme.com"})
        assert response.status_code == 403
        assert "Confirm your email" in response.json()["detail"]

    async def test_google_takes_over_an_unproven_account_and_locks_its_maker_out(self, world):
        _, browser, fake = world
        async with browser() as attacker, browser() as owner:
            await signup(attacker, email="amna@acme.com", name="Attacker")
            made = await me(attacker)
            await sign_in(owner, fake, sub="g-a", email="amna@acme.com", name="Amna Khan")
            user = await me(owner)
            assert user["id"] == made["id"] and user["name"] == "Amna Khan"
            assert user["email_verified"] is True
            # The session they already had is over, and the password no longer works.
            assert await me(attacker) is None
            login = await attacker.post("/api/auth/login", json={"email": "amna@acme.com", "password": GOOD})
            assert login.status_code == 401
            # Google still reaches the same account next time.
            await owner.post("/api/auth/logout")
            await sign_in(owner, fake, sub="g-a", email="amna@acme.com", name="Amna Khan")
            assert (await me(owner))["id"] == made["id"]

    async def test_google_proves_an_invited_address_and_joins_the_team(self, world):
        _, browser, fake = world
        async with browser() as owner, browser() as sana:
            await sign_in(owner, fake, sub="g-a", email="owner@acme.com")
            team_id = (await me(owner))["org_id"]
            await owner.post("/api/team/invites", json={"email": "sana@acme.com"})
            await signup(sana, email="sana@acme.com", name="Sana Malik")
            assert (await me(sana))["org_id"] != team_id
            await sign_in(sana, fake, sub="g-s", email="sana@acme.com", name="Sana Malik")
            user = await me(sana)
            assert user["org_id"] == team_id and user["role"] == "member"
            assert (await owner.get("/api/team")).json()["invites"] == []


class TestConfirmingAnAddress:
    async def test_signing_up_sends_a_link_and_the_link_confirms(self, inbox, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            assert len(inbox) == 1 and inbox[0]["To"] == "amna@acme.com"
            assert (await me(client))["email_verified"] is False
            response = await client.get("/api/auth/email/verify", params={"token": token_in(inbox[0])})
            assert response.status_code == 302 and response.headers["location"].endswith("/console")
            assert (await me(client))["email_verified"] is True

    async def test_the_link_does_not_sign_anybody_in(self, inbox, world):
        _, browser, _ = world
        async with browser() as client, browser() as other:
            await signup(client)
            response = await other.get("/api/auth/email/verify", params={"token": token_in(inbox[0])})
            assert accounts.SESSION_COOKIE not in response.headers.get("set-cookie", "")
            assert await me(other) is None

    async def test_a_mail_scanner_opening_it_first_does_no_harm(self, inbox, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            token = token_in(inbox[0])
            for _ in range(2):
                response = await client.get("/api/auth/email/verify", params={"token": token})
                assert response.headers["location"].endswith("/console")

    async def test_a_made_up_link_fails_clearly(self, inbox, world):
        _, browser, _ = world
        async with browser() as client:
            response = await client.get("/api/auth/email/verify", params={"token": "nope"})
        assert response.status_code == 302 and "error=link_expired" in response.headers["location"]

    async def test_a_reset_link_does_not_confirm_and_a_confirm_link_does_not_reset(self, inbox, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            verify = token_in(inbox[0])
            reset = await client.post("/api/auth/password/reset", json={"token": verify, "password": OTHER})
            assert reset.status_code == 400
            await client.post("/api/auth/password/forgot", json={"email": "amna@acme.com"})
            wrong = await client.get("/api/auth/email/verify", params={"token": token_in(inbox[1])})
            assert "error=link_expired" in wrong.headers["location"]

    async def test_confirming_an_invited_address_joins_the_team(self, inbox, world):
        _, browser, fake = world
        async with browser() as owner, browser() as sana:
            await sign_in(owner, fake, sub="g-a", email="owner@acme.com")
            team_id = (await me(owner))["org_id"]
            await owner.post("/api/team/invites", json={"email": "sana@acme.com", })
            inbox.clear()
            await signup(sana, email="sana@acme.com", name="Sana Malik")
            await sana.get("/api/auth/email/verify", params={"token": token_in(inbox[0])})
            user = await me(sana)
            assert user["org_id"] == team_id and user["role"] == "member"

    async def test_confirming_does_not_abandon_calls_already_uploaded(self, inbox, world):
        _, browser, fake = world
        async with browser() as owner, browser() as sana:
            await sign_in(owner, fake, sub="g-a", email="owner@acme.com")
            team_id = (await me(owner))["org_id"]
            await owner.post("/api/team/invites", json={"email": "sana@acme.com"})
            inbox.clear()
            await signup(sana, email="sana@acme.com", name="Sana Malik")
            call = await sana.post(
                "/api/calls/upload",
                files={"file": ("a.mp3", MP3, "audio/mpeg")},
                data={"salesperson": "Zara", "deal_id": ""},
            )
            await sana.get("/api/auth/email/verify", params={"token": token_in(inbox[0])})
            assert (await me(sana))["org_id"] != team_id
            assert (await sana.get(f"/api/calls/{call.json()['call_id']}")).status_code == 200

    async def test_confirming_as_the_named_owner_claims_the_existing_data(self, inbox, world):
        from salix.schemas.org import Org
        from salix.store import repo

        _, browser, _ = world
        async with db.session_scope() as session:
            await repo.put_org(session, Org(id="org_existing", name="Existing"))
            await session.commit()
        async with browser() as founder:
            await signup(founder, email="founder@acme.com", name="Founder")
            await founder.get("/api/auth/email/verify", params={"token": token_in(inbox[0])})
            assert (await me(founder))["org_id"] == "org_existing"

    async def test_a_proven_account_can_invite(self, inbox, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            await client.get("/api/auth/email/verify", params={"token": token_in(inbox[0])})
            assert (await client.post("/api/team/invites", json={"email": "friend@acme.com"})).status_code == 201

    async def test_a_proven_account_keeps_its_password_when_it_links_google(self, inbox, world):
        _, browser, fake = world
        async with browser() as client:
            await signup(client)
            made = await me(client)
            await client.get("/api/auth/email/verify", params={"token": token_in(inbox[0])})
            await sign_in(client, fake, sub="g-a", email="amna@acme.com", name="Amna Khan")
            assert (await me(client))["id"] == made["id"]
            await client.post("/api/auth/logout")
            assert (await client.post("/api/auth/login", json={"email": "amna@acme.com", "password": GOOD})).status_code == 200

    async def test_resending_replaces_the_old_link(self, inbox, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            assert (await client.post("/api/auth/email/resend")).json() == {"sent": True}
            old = await client.get("/api/auth/email/verify", params={"token": token_in(inbox[0])})
            assert "error=link_expired" in old.headers["location"]
            await client.get("/api/auth/email/verify", params={"token": token_in(inbox[1])})
            assert (await me(client))["email_verified"] is True
            assert (await client.post("/api/auth/email/resend")).json() == {"sent": False}
            assert len(inbox) == 2

    async def test_resending_needs_a_session(self, inbox, world):
        _, browser, _ = world
        async with browser() as client:
            assert (await client.post("/api/auth/email/resend")).status_code == 401


class TestForgottenPasswords:
    async def test_without_a_mail_server_it_says_so(self, world):
        _, browser, _ = world
        async with browser() as client:
            assert (await client.get("/api/auth/me")).json()["mail_enabled"] is False
            assert (await client.post("/api/auth/password/forgot", json={"email": "a@acme.com"})).status_code == 409

    async def test_the_answer_does_not_reveal_who_has_an_account(self, inbox, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            inbox.clear()
            known = await client.post("/api/auth/password/forgot", json={"email": "amna@acme.com"})
            unknown = await client.post("/api/auth/password/forgot", json={"email": "nobody@acme.com"})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert [m["To"] for m in inbox] == ["amna@acme.com"]

    async def test_a_reset_changes_the_password_and_signs_out_everywhere_else(self, inbox, world):
        _, browser, _ = world
        async with browser() as stolen, browser() as owner:
            await signup(stolen)
            await owner.post("/api/auth/password/forgot", json={"email": "amna@acme.com"})
            response = await owner.post(
                "/api/auth/password/reset", json={"token": token_in(inbox[-1]), "password": OTHER}
            )
            assert response.status_code == 200, response.text
            assert (await me(owner))["email_verified"] is True
            assert await me(stolen) is None
            assert (await stolen.post("/api/auth/login", json={"email": "amna@acme.com", "password": GOOD})).status_code == 401
            assert (await stolen.post("/api/auth/login", json={"email": "amna@acme.com", "password": OTHER})).status_code == 200

    async def test_the_link_works_once(self, inbox, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            await client.post("/api/auth/password/forgot", json={"email": "amna@acme.com"})
            token = token_in(inbox[-1])
            assert (await client.post("/api/auth/password/reset", json={"token": token, "password": OTHER})).status_code == 200
            assert (await client.post("/api/auth/password/reset", json={"token": token, "password": GOOD})).status_code == 400

    async def test_an_expired_link_is_refused(self, inbox, world):
        from datetime import timedelta

        from salix.store.models import utcnow

        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            await client.post("/api/auth/password/forgot", json={"email": "amna@acme.com"})
            token = token_in(inbox[-1])
            async with db.session_scope() as session:
                for row in (await session.execute(select(EmailTokenRow))).scalars():
                    row.expires_at = utcnow() - timedelta(minutes=1)
                await session.commit()
            assert (await client.post("/api/auth/password/reset", json={"token": token, "password": OTHER})).status_code == 400

    async def test_a_weak_new_password_does_not_burn_the_link(self, inbox, world):
        _, browser, _ = world
        async with browser() as client:
            await signup(client)
            await client.post("/api/auth/password/forgot", json={"email": "amna@acme.com"})
            token = token_in(inbox[-1])
            assert (await client.post("/api/auth/password/reset", json={"token": token, "password": "short"})).status_code == 400
            assert (await client.post("/api/auth/password/reset", json={"token": token, "password": OTHER})).status_code == 200

    async def test_a_google_account_can_gain_a_password_through_its_mailbox(self, inbox, world):
        _, browser, fake = world
        async with browser() as client:
            await sign_in(client, fake, sub="g-a", email="amna@acme.com")
            made = await me(client)
            await client.post("/api/auth/logout")
            await client.post("/api/auth/password/forgot", json={"email": "amna@acme.com"})
            await client.post("/api/auth/password/reset", json={"token": token_in(inbox[-1]), "password": OTHER})
            await client.post("/api/auth/logout")
            assert (await client.post("/api/auth/login", json={"email": "amna@acme.com", "password": OTHER})).status_code == 200
            assert (await me(client))["id"] == made["id"]


class TestRemovedPeople:
    async def test_a_removed_member_cannot_log_back_in_to_the_team(self, inbox, world):
        _, browser, fake = world
        async with browser() as owner, browser() as sana:
            await sign_in(owner, fake, sub="g-a", email="owner@acme.com")
            team_id = (await me(owner))["org_id"]
            await owner.post("/api/team/invites", json={"email": "sana@acme.com"})
            inbox.clear()
            await signup(sana, email="sana@acme.com", name="Sana Malik")
            await sana.get("/api/auth/email/verify", params={"token": token_in(inbox[0])})
            user = await me(sana)
            assert user["org_id"] == team_id
            assert (await owner.delete(f"/api/team/members/{user['id']}")).status_code == 204
            assert await me(sana) is None
            login = await sana.post("/api/auth/login", json={"email": "sana@acme.com", "password": GOOD})
            assert login.status_code == 401
