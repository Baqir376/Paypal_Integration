# -*- coding: utf-8 -*-
"""Put your keys in .env without pasting them into a chat, then prove they work.

    python api/scripts/setup_credentials.py            # asks, saves, then checks
    python api/scripts/setup_credentials.py --check    # only checks what is saved

Run it in your own terminal. Secrets are typed with the echo off and go only into
.env, which is gitignored. Press Enter to keep whatever is there already.

Each check makes one real request, and none of them moves money: PayPal is asked to
create an order that nobody ever approves.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ENV = ROOT / ".env"
sys.path.insert(0, str(ROOT / "api"))

SECTIONS = [
    (
        "Google sign-in",
        """\
1. Open https://console.cloud.google.com/apis/credentials and create or pick a project.
2. If asked, configure the consent screen: External, with your email as a test user.
3. Create credentials > OAuth client ID > Web application.
4. Under "Authorized redirect URIs" add exactly:
       {app_url}/api/auth/google/callback""",
        [
            ("SALIX_GOOGLE_CLIENT_ID", "Client ID", False),
            ("SALIX_GOOGLE_CLIENT_SECRET", "Client secret", True),
            ("SALIX_OWNER_EMAIL", "Your Google email (claims the existing data)", False),
        ],
    ),
    (
        "PayPal sandbox",
        """\
1. Open https://developer.paypal.com/dashboard/applications/sandbox and log in.
2. Create App (type: Merchant). Copy the Client ID and show the Secret.
3. Sandbox buyer accounts for test payments are under Testing Tools > Sandbox Accounts.""",
        [
            ("SALIX_PAYPAL_CLIENT_ID", "Client ID", False),
            ("SALIX_PAYPAL_CLIENT_SECRET", "Secret", True),
        ],
    ),
    (
        "Braintree sandbox (PayPal's gateway; needs no PayPal account)",
        """\
1. Apply at https://apply.braintreegateway.com/signup/sandbox with your real details.
2. Confirm the email, then log in at https://sandbox.braintreegateway.com/login
3. Gear icon > API > API Keys: Generate New API Key, click View for the private key.
   The merchant ID is at gear icon > Business.""",
        [
            ("SALIX_BRAINTREE_MERCHANT_ID", "Merchant ID", False),
            ("SALIX_BRAINTREE_PUBLIC_KEY", "Public key", False),
            ("SALIX_BRAINTREE_PRIVATE_KEY", "Private key", True),
        ],
    ),
    (
        "PayPal webhook (optional; needs a public HTTPS address)",
        """\
PayPal cannot reach localhost, so this only applies once deployed or tunnelled.
1. In your app's settings, under Sandbox Webhooks, click Add Webhook.
2. URL: https://<your domain>/api/billing/webhook
3. Tick: Payment capture completed, denied, refunded, reversed. Copy the Webhook ID.""",
        [("SALIX_PAYPAL_WEBHOOK_ID", "Webhook ID", False)],
    ),
    (
        "Backup AI provider (optional, recommended)",
        """\
Your Gemini key already fails over between models. A second company also covers a
Gemini-wide outage. Groq's key is at https://console.groq.com/keys""",
        [("SALIX_LLM_BACKUP_API_KEY", "Groq API key", True)],
    ),
    (
        "Invitation email (optional)",
        """\
Any SMTP provider. For Gmail, make an App Password at
https://myaccount.google.com/apppasswords and use host smtp.gmail.com.""",
        [
            ("SALIX_SMTP_HOST", "SMTP host", False),
            ("SALIX_SMTP_USER", "SMTP username", False),
            ("SALIX_SMTP_PASSWORD", "SMTP password", True),
            ("SALIX_SMTP_FROM", "Send from (e.g. Salix <you@gmail.com>)", False),
        ],
    ),
]

#: Set alongside a backup key, so that the key alone is enough.
GROQ_DEFAULTS = {
    "SALIX_LLM_BACKUP_BASE_URL": "https://api.groq.com/openai/v1",
    "SALIX_LLM_BACKUP_MODELS": "openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b",
}


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            match = re.match(r"\s*([A-Z0-9_]+)\s*=(.*)$", line)
            if match:
                values[match.group(1)] = match.group(2).strip()
    return values


def write_env(updates: dict[str, str]) -> None:
    """Change only these keys, leaving every other line and comment as it was."""
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    remaining = dict(updates)
    for i, line in enumerate(lines):
        match = re.match(r"\s*([A-Z0-9_]+)\s*=", line)
        if match and match.group(1) in remaining:
            lines[i] = f"{match.group(1)}={remaining.pop(match.group(1))}"
    lines += [f"{key}={value}" for key, value in remaining.items()]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ask() -> None:
    current = read_env()
    app_url = current.get("SALIX_APP_URL") or "http://localhost:3000"
    updates: dict[str, str] = {}
    for title, help_text, fields in SECTIONS:
        print(f"\n=== {title}\n{help_text.format(app_url=app_url)}\n")
        for key, label, secret in fields:
            state = "saved" if current.get(key) else "not set"
            prompt = f"{label} [{state}, Enter to keep]: "
            value = (getpass.getpass(prompt) if secret else input(prompt)).strip()
            if value:
                updates[key] = value
    if updates.get("SALIX_LLM_BACKUP_API_KEY"):
        for key, value in GROQ_DEFAULTS.items():
            if not current.get(key):
                updates[key] = value
    if updates:
        write_env(updates)
        print(f"\nSaved {len(updates)} value(s) to .env")


def report(name: str, ok: bool | None, detail: str = "") -> None:
    mark = {True: "ok  ", False: "FAIL", None: "--  "}[ok]
    print(f"  {mark} {name}{f': {detail}' if detail else ''}")


async def check_google(settings) -> None:
    if not settings.google_configured:
        return report("Google sign-in", None, "not set")
    import httpx

    from salix.auth.google import TOKEN_URL, redirect_uri

    # A made-up code. Google says invalid_grant for a real client, invalid_client
    # for a wrong one, and nothing else about this client can be checked from here.
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "code": "salix-setup-check",
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri(settings),
                "grant_type": "authorization_code",
            },
        )
    error = response.json().get("error", "")
    if error == "invalid_grant":
        report("Google sign-in", True, f"client accepted; redirect URI must be {redirect_uri(settings)}")
    else:
        report("Google sign-in", False, f"Google said {error or response.status_code}")


async def check_paypal(settings) -> None:
    if settings.paypal_simulated:
        return report("PayPal", None, "SIMULATED: no keys, so nothing here reaches PayPal")
    if not settings.paypal_configured:
        return report("PayPal", None, "not set")
    from salix.billing.packs import PACKS
    from salix.billing.paypal import PayPalError, PayPalGateway

    try:
        order = await PayPalGateway(settings).create_order(
            PACKS["starter"],
            org_id="setup-check",
            request_id=f"salix-check-{uuid.uuid4().hex}",
            return_url=f"{settings.app_url.rstrip('/')}/billing/return",
            cancel_url=f"{settings.app_url.rstrip('/')}/billing",
        )
        report("PayPal", True, f"{settings.paypal_mode}: created unapproved order {order.id}")
    except PayPalError as exc:
        report("PayPal", False, exc.detail)
    report(
        "PayPal webhook",
        True if settings.paypal_webhook_id else None,
        "id saved; deliveries need a public address" if settings.paypal_webhook_id else "not set",
    )


async def check_braintree(settings) -> None:
    if not settings.braintree_configured:
        return report("Braintree", None, "not set")
    from salix.billing.braintree_gateway import BraintreeError, BraintreePayments

    try:
        await BraintreePayments(settings).client_token()
        report("Braintree", True, f"{settings.paypal_mode}: keys accepted")
    except BraintreeError as exc:
        report("Braintree", False, exc.detail)


async def check_llm(settings) -> None:
    if not settings.llm_key:
        return report("AI reasoning", None, "not set")
    from salix.providers.failover import build_routes

    for route in build_routes(settings):
        try:
            answer = await route.llm.complete(system="Reply with one word.", user="Say ok.", max_tokens=400)
            report(f"AI route {route.label}", bool(answer.strip()))
        except Exception as exc:  # noqa: BLE001
            report(f"AI route {route.label}", False, str(exc)[:120])


async def check_mail(settings) -> None:
    if not settings.mail_configured:
        return report("Invitation email", None, "not set")
    import smtplib

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
        report("Invitation email", True, "logged in; nothing sent")
    except (smtplib.SMTPException, OSError) as exc:
        report("Invitation email", False, type(exc).__name__)


async def check() -> None:
    from salix.config import Settings

    settings = Settings()
    print("\nChecking...")
    await check_google(settings)
    await check_paypal(settings)
    await check_braintree(settings)
    await check_llm(settings)
    await check_mail(settings)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="only check what is saved")
    args = parser.parse_args()
    if not args.check:
        ask()
    asyncio.run(check())


if __name__ == "__main__":
    main()
