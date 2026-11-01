"""Credits: the balance, the packs, and the PayPal round trip.

    POST /billing/checkout            -> PayPal order, and where to send the buyer
    (buyer approves on paypal.com and is sent back to /billing/return)
    POST /billing/orders/{id}/capture -> takes the money, grants the credits
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from ..billing import credits, webhook as paypal_webhook
from ..billing.braintree_gateway import BraintreeError, get_payments
from ..billing.packs import PACKS
from ..billing.paypal import PayPalError, get_gateway
from ..config import get_settings
from ..schemas.common import SalixModel
from ..store.models import PaymentOrderRow, utcnow
from .deps import OrgId, Session, require_owner

log = logging.getLogger("salix.routers.billing")

router = APIRouter(prefix="/billing", tags=["billing"])
#: Mounted without a session: PayPal is the caller, and the signature is the proof.
webhook_router = APIRouter(prefix="/billing", tags=["billing"])


class BillingState(SalixModel):
    #: Whether uploads currently cost a credit.
    enforced: bool
    #: Whether credits can actually be bought here.
    can_purchase: bool
    #: Purchases run against the labelled stand-in, not PayPal.
    simulated: bool = False
    #: "paypal", "braintree", "simulator", or None when nothing can take payment.
    provider: Optional[str] = None
    #: Whether this person may. Buying is for the team's owner.
    can_buy: bool = True
    environment: str
    balance: int
    call_cost: int = credits.CALL_COST
    packs: list[dict] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)


class BraintreePayRequest(SalixModel):
    pack_id: str
    #: Braintree's single-use stand-in for the card. Card details never come here.
    nonce: str = Field(min_length=1, max_length=512)


class CheckoutRequest(SalixModel):
    pack_id: str


class CheckoutResponse(SalixModel):
    order_id: str
    approve_url: str


class OrderResult(SalixModel):
    order_id: str
    status: str
    credits: int
    balance: int
    detail: str = ""


class ReconcileResult(SalixModel):
    checked: int
    balance: int


def _http_error(exc: PayPalError) -> HTTPException:
    return HTTPException(status_code=502, detail=exc.detail)


@router.get("", response_model=BillingState)
async def state(request: Request, session: Session, org_id: OrgId) -> BillingState:
    settings = get_settings()
    context = getattr(request.state, "auth", None)
    return BillingState(
        can_buy=context is None or context.role == "owner",
        simulated=settings.paypal_simulated,
        provider=settings.payment_provider,
        enforced=settings.billing_enforced,
        can_purchase=settings.payment_provider is not None,
        environment=settings.paypal_mode,
        balance=await credits.balance(session, org_id),
        packs=[p.public() for p in PACKS.values()],
        history=await credits.history(session, org_id),
    )


@router.post("/checkout", response_model=CheckoutResponse, dependencies=[Depends(require_owner)])
async def checkout(
    session: Session, org_id: OrgId, request: CheckoutRequest
) -> CheckoutResponse:
    pack = PACKS.get(request.pack_id)
    if pack is None:
        raise HTTPException(status_code=400, detail=f"No pack {request.pack_id}")

    settings = get_settings()
    # From configuration, never from a request header: this is where PayPal will
    # send somebody's browser straight after they pay.
    base = settings.app_url.rstrip("/")
    try:
        order = await get_gateway(settings).create_order(
            pack,
            org_id=org_id,
            request_id=f"salix-order-{uuid.uuid4().hex}",
            return_url=f"{base}/billing/return",
            cancel_url=f"{base}/billing?cancelled=1",
        )
    except PayPalError as exc:
        raise _http_error(exc)

    session.add(
        PaymentOrderRow(
            id=order.id,
            org_id=org_id,
            pack_id=pack.id,
            credits=pack.credits,
            amount=pack.price,
            currency=pack.currency,
            status=credits.CREATED,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    await session.commit()
    log.info("order %s created for pack %s", order.id, pack.id)
    return CheckoutResponse(order_id=order.id, approve_url=order.approve_url)


_DETAILS = {
    credits.PENDING: (
        "PayPal is still holding this payment. The credits will be added when it "
        "clears; there is nothing you need to do."
    ),
    credits.FAILED: "PayPal declined this payment, and you were not charged.",
    credits.REVIEW: (
        "This payment needs a manual check before the credits can be added. "
        "Quote the order id if you contact support."
    ),
    credits.CREATED: "This payment has not been completed.",
}


@router.post("/orders/{order_id}/capture", response_model=OrderResult)
async def capture(session: Session, org_id: OrgId, order_id: str) -> OrderResult:
    """Called by the return page. Safe to call any number of times.

    Only an order this server created can be captured. An id we have no row for
    never reaches PayPal, so nobody can turn somebody else's payment into credits.
    """
    row = await credits.get_order(session, org_id, order_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No order {order_id}")

    try:
        row = await credits.capture(session, get_gateway(get_settings()), row)
    except PayPalError as exc:
        if exc.code == "INSTRUMENT_DECLINED":
            raise HTTPException(
                status_code=402,
                detail="PayPal declined that payment method. You were not charged.",
            )
        if exc.code == "ORDER_NOT_APPROVED":
            raise HTTPException(
                status_code=409,
                detail="This payment was not approved on PayPal, so nothing was charged.",
            )
        raise _http_error(exc)
    await session.commit()

    return OrderResult(
        order_id=row.id,
        status=row.status,
        credits=row.credits if row.status == credits.COMPLETED else 0,
        balance=await credits.balance(session, org_id),
        detail=_DETAILS.get(row.status, ""),
    )


@router.post("/reconcile", response_model=ReconcileResult)
async def reconcile(session: Session, org_id: OrgId) -> ReconcileResult:
    """Catch up on orders that never came back through the return page."""
    settings = get_settings()
    rows = await credits.unfinished_orders(session, org_id)
    for row in rows:
        try:
            if row.id.startswith(BRAINTREE_PREFIX):
                if settings.braintree_configured:
                    view = await get_payments(settings).find(row.id)
                    if view is not None:
                        await credits.apply_order_state(session, row, view)
            elif settings.paypal_configured:
                await credits.reconcile(session, get_gateway(settings), row)
            await session.commit()
        except (PayPalError, BraintreeError) as exc:
            # One unreadable order must not stop the others, and this runs
            # on page load: the page does not need to fail because of it.
            log.warning("could not reconcile %s: %s", row.id, exc.detail)
    return ReconcileResult(
        checked=len(rows), balance=await credits.balance(session, org_id)
    )


# --------------------------------------------------------------------------
# Braintree
# --------------------------------------------------------------------------

BRAINTREE_PREFIX = "bt_"


@router.post("/braintree/client-token", dependencies=[Depends(require_owner)])
async def braintree_client_token() -> dict:
    """Lets Braintree's own payment form open in the browser."""
    settings = get_settings()
    if not settings.braintree_configured:
        raise HTTPException(status_code=503, detail="Braintree is not configured on this server.")
    try:
        return {"client_token": await get_payments(settings).client_token()}
    except BraintreeError as exc:
        raise HTTPException(status_code=502, detail=exc.detail)


@router.post("/braintree/pay", response_model=OrderResult, dependencies=[Depends(require_owner)])
async def braintree_pay(session: Session, org_id: OrgId, request: BraintreePayRequest) -> OrderResult:
    settings = get_settings()
    if not settings.braintree_configured:
        raise HTTPException(status_code=503, detail="Braintree is not configured on this server.")
    pack = PACKS.get(request.pack_id)
    if pack is None:
        raise HTTPException(status_code=400, detail=f"No pack {request.pack_id}")

    # Written before the charge, so that a crash between the two leaves something for
    # /reconcile to find rather than a customer who paid and has no record of it.
    row = PaymentOrderRow(
        id=f"{BRAINTREE_PREFIX}{uuid.uuid4().hex[:24]}",
        org_id=org_id,
        pack_id=pack.id,
        credits=pack.credits,
        amount=pack.price,
        currency=pack.currency,
        status=credits.CREATED,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(row)
    await session.commit()

    try:
        view = await get_payments(settings).charge(pack, order_id=row.id, nonce=request.nonce)
    except BraintreeError as exc:
        if exc.declined:
            row.status = credits.FAILED
            await session.commit()
            raise HTTPException(status_code=402, detail=exc.detail)
        # Unknown whether it went through, so it stays open for /reconcile.
        raise HTTPException(status_code=502, detail=exc.detail)

    row = await credits.apply_order_state(session, row, view)
    await session.commit()
    return OrderResult(
        order_id=row.id,
        status=row.status,
        credits=row.credits if row.status == credits.COMPLETED else 0,
        balance=await credits.balance(session, org_id),
        detail=_DETAILS.get(row.status, ""),
    )


@webhook_router.post("/webhook")
async def paypal_event(request: Request, session: Session) -> dict:
    """What PayPal tells us after the buyer has gone: refunds, chargebacks, clearing.

    A 2xx means "do not send this again", so it is returned for anything understood
    or deliberately ignored, and an error only for a delivery that fails its proof.
    """
    settings = get_settings()
    if not settings.paypal_webhook_id:
        raise HTTPException(status_code=503, detail="This server has no PayPal webhook configured.")

    body = await request.body()
    if not await paypal_webhook.signature_is_valid(request.headers, body, settings.paypal_webhook_id):
        raise HTTPException(status_code=400, detail="Signature rejected.")
    try:
        event = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Not JSON.")
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="Not an event.")

    try:
        outcome = await paypal_webhook.handle_event(session, get_gateway(settings), event)
    except PayPalError as exc:
        # Worth a redelivery: PayPal was unreachable from here, for now.
        raise HTTPException(status_code=502, detail=exc.detail)
    await session.commit()
    return {"status": outcome}
