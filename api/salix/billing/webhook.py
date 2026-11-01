"""PayPal webhooks: what happens to a payment after the buyer has left.

Refunds and chargebacks are issued in PayPal, and nothing tells this app otherwise.

Signatures are checked here rather than by asking PayPal, using the method PayPal
documents for it: the signed message is `transmission id|time|webhook id|crc32 of
the raw body`, checked with PayPal's certificate. That needs the body exactly as
received, which is what this has, and it is why the alternative of posting the event
back was not used: PayPal warns that any reformatting of the JSON breaks that check.

The certificate's address comes from the request, so it is only fetched from
paypal.com over HTTPS. Otherwise anybody could sign with their own certificate, and
this server could be pointed at any address they liked.
"""

from __future__ import annotations

import base64
import logging
import math
import zlib
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..store.models import CreditLedgerRow, PaymentOrderRow, utcnow
from . import credits

log = logging.getLogger("salix.billing.webhook")

COMPLETED = "PAYMENT.CAPTURE.COMPLETED"
CLAWED_BACK = ("PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED")
SETTLED_OTHERWISE = ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED")

_certs: dict[str, x509.Certificate] = {}


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0)


def _trusted_cert_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "paypal.com" or host.endswith(".paypal.com"))


async def _certificate(url: str) -> x509.Certificate:
    if url not in _certs:
        async with _http() as client:
            response = await client.get(url)
        response.raise_for_status()
        _certs[url] = x509.load_pem_x509_certificate(response.content)
    return _certs[url]


async def signature_is_valid(headers: Mapping[str, str], body: bytes, webhook_id: str) -> bool:
    """Did PayPal send exactly this body to this webhook?"""
    transmission = headers.get("paypal-transmission-id", "")
    sent_at = headers.get("paypal-transmission-time", "")
    signature = headers.get("paypal-transmission-sig", "")
    cert_url = headers.get("paypal-cert-url", "")
    if not (transmission and sent_at and signature and cert_url):
        return False
    if not _trusted_cert_url(cert_url):
        log.warning("webhook named a certificate outside paypal.com")
        return False

    message = f"{transmission}|{sent_at}|{webhook_id}|{zlib.crc32(body)}".encode()
    try:
        certificate = await _certificate(cert_url)
        certificate.public_key().verify(
            base64.b64decode(signature), message, padding.PKCS1v15(), hashes.SHA256()
        )
    except (InvalidSignature, ValueError, TypeError, httpx.HTTPError) as exc:
        log.warning("webhook signature rejected: %s", type(exc).__name__)
        return False
    return True


def _capture_id(event_type: str, resource: dict[str, Any]) -> str:
    """Which capture this is about. A refund's own id is the refund's, and it points
    at its capture through an `up` link."""
    for link in resource.get("links") or []:
        href = link.get("href") or ""
        if link.get("rel") == "up" and "/captures/" in href:
            return href.rstrip("/").rsplit("/", 1)[-1]
    return str(resource.get("id") or "")


async def _claw_back(session: AsyncSession, event_type: str, resource: dict[str, Any]) -> str:
    capture_id = _capture_id(event_type, resource)
    row = (
        await session.execute(
            select(PaymentOrderRow).where(PaymentOrderRow.capture_id == capture_id)
        )
    ).scalar_one_or_none()
    if row is None:
        # Not one of ours, or a test event. A non-2xx would only make PayPal retry.
        log.info("%s for unknown capture %s", event_type, capture_id)
        return "unknown capture"

    event_ref = str(resource.get("id") or capture_id)
    prefix = f"paypal-refund:{row.id}:"
    taken_back = -(
        await session.execute(
            select(func.coalesce(func.sum(CreditLedgerRow.delta), 0)).where(
                CreditLedgerRow.ref.like(f"{prefix}%")
            )
        )
    ).scalar_one()

    # A partial refund takes back its share of the pack, rounded up, and refunds in
    # total can never take back more than the pack gave.
    try:
        refunded = Decimal(str((resource.get("amount") or {}).get("value")))
        share = refunded / Decimal(row.amount)
    except (InvalidOperation, ZeroDivisionError):
        share = Decimal(1)
    owed = min(math.ceil(row.credits * min(share, Decimal(1))), row.credits - taken_back)
    if owed <= 0:
        return "nothing left to take back"

    # The balance is allowed to go below zero: those credits may already be spent,
    # and owing them is what stops refund-and-keep from being free.
    if await credits._post(session, row.org_id, -owed, "paypal_refund", f"{prefix}{event_ref}"):
        await credits._add(session, row.org_id, -owed)
        log.info("took back %d credits for order %s (%s)", owed, row.id, event_type)
    if taken_back + owed >= row.credits:
        row.status = credits.REFUNDED
    row.updated_at = utcnow()
    return "credits taken back"


async def handle_event(session: AsyncSession, gateway: Any, event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "")
    resource = event.get("resource") or {}

    if event_type in CLAWED_BACK:
        return await _claw_back(session, event_type, resource)

    if event_type == COMPLETED or event_type in SETTLED_OTHERWISE:
        # The event only says something changed. What happened is read from PayPal,
        # through the same path as every other settlement.
        order_id: Optional[str] = (
            (resource.get("supplementary_data") or {}).get("related_ids") or {}
        ).get("order_id")
        row = await session.get(PaymentOrderRow, order_id) if order_id else None
        if row is None:
            return "unknown order"
        await credits.reconcile(session, gateway, row)
        return f"order is {row.status}"

    return "ignored"
