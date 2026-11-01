"""The credit ledger.

One credit analyses one recording. Two tables, deliberately: `credit_ledger` is
the append-only history, with a unique `ref` per event, and `credit_accounts`
holds the running balance so that spending can be a single conditional UPDATE.

Those two properties are what make this safe to retry and safe to race:

* `ref` means a purchase or a refund can only ever land once, however many times
  the return page reloads or the pipeline's failure path runs.
* `balance >= 1` inside the UPDATE means two uploads racing for the last credit
  cannot both win, on SQLite or on Postgres, with no lock held across anything.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..store.models import CreditAccountRow, CreditLedgerRow, PaymentOrderRow, utcnow
from .paypal import OrderView, PayPalGateway

log = logging.getLogger("salix.credits")

CALL_COST = 1

#: Order states.
CREATED = "created"
PENDING = "pending"
COMPLETED = "completed"
FAILED = "failed"
#: The money went back, in PayPal, and the credits with it.
REFUNDED = "refunded"
#: PayPal says it was paid, but not what this order was created for. A person
#: has to look at it, so no credits move on their own.
REVIEW = "review"


class InsufficientCredits(Exception):
    pass


async def _insert_once(session: AsyncSession, row_type: Any, values: dict[str, Any]) -> bool:
    """Insert unless a unique key already exists. True if it was inserted."""
    insert = postgres_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
    result = await session.execute(insert(row_type).values(**values).on_conflict_do_nothing())
    return result.rowcount == 1


async def _post(
    session: AsyncSession, org_id: str, delta: int, reason: str, ref: str
) -> bool:
    """Write one ledger entry. False if this `ref` has already been written."""
    return await _insert_once(
        session,
        CreditLedgerRow,
        {
            "id": f"led_{uuid.uuid4().hex[:16]}",
            "org_id": org_id,
            "delta": delta,
            "reason": reason,
            "ref": ref,
            "created_at": utcnow(),
        },
    )


async def _add(session: AsyncSession, org_id: str, credits: int) -> None:
    await _insert_once(session, CreditAccountRow, {"org_id": org_id, "balance": 0})
    await session.execute(
        update(CreditAccountRow)
        .where(CreditAccountRow.org_id == org_id)
        .values(balance=CreditAccountRow.balance + credits)
    )


async def balance(session: AsyncSession, org_id: str) -> int:
    value = (
        await session.execute(
            select(CreditAccountRow.balance).where(CreditAccountRow.org_id == org_id)
        )
    ).scalar_one_or_none()
    return value or 0


async def history(session: AsyncSession, org_id: str, limit: int = 20) -> list[dict]:
    rows = (
        await session.execute(
            select(CreditLedgerRow)
            .where(CreditLedgerRow.org_id == org_id)
            .order_by(CreditLedgerRow.created_at.desc())
            .limit(limit)
        )
    ).scalars()
    return [
        {
            "id": r.id,
            "delta": r.delta,
            "reason": r.reason,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


async def spend_for_call(session: AsyncSession, org_id: str, call_id: str) -> None:
    """Take the credit for one recording, or raise InsufficientCredits.

    In the caller's transaction, alongside the call row, so a failure anywhere in
    the upload takes the charge back with it.
    """
    result = await session.execute(
        update(CreditAccountRow)
        .where(CreditAccountRow.org_id == org_id, CreditAccountRow.balance >= CALL_COST)
        .values(balance=CreditAccountRow.balance - CALL_COST)
    )
    if result.rowcount != 1:
        raise InsufficientCredits(org_id)
    await _post(session, org_id, -CALL_COST, "call_analysis", f"call:{call_id}")


async def refund_call(session: AsyncSession, call_id: str) -> bool:
    """Return the credit for a call we could not analyse.

    A no-op for a call that was never charged, which is every call on a
    deployment with the paywall off.
    """
    spend = (
        await session.execute(
            select(CreditLedgerRow).where(CreditLedgerRow.ref == f"call:{call_id}")
        )
    ).scalar_one_or_none()
    if spend is None:
        return False
    if not await _post(session, spend.org_id, -spend.delta, "call_refund", f"refund:{call_id}"):
        return False
    await _add(session, spend.org_id, -spend.delta)
    log.info("refunded the credit for %s", call_id)
    return True


def _same_money(a: str, b: str) -> bool:
    try:
        return Decimal(a) == Decimal(b)
    except (InvalidOperation, TypeError):
        return False


async def apply_order_state(
    session: AsyncSession, row: PaymentOrderRow, view: OrderView
) -> PaymentOrderRow:
    """Record what PayPal says happened, and grant credits if it was paid.

    The credits and the amount come from our own row, written when the order was
    created. The only thing taken from PayPal is whether it was paid and for how
    much, and that amount has to match.
    """
    if row.status in (COMPLETED, REFUNDED):
        return row

    if view.capture_status == "COMPLETED":
        row.capture_id = view.capture_id
        if not (_same_money(view.amount, row.amount) and view.currency == row.currency):
            log.error(
                "order %s paid %s %s, expected %s %s; held for review",
                row.id, view.amount, view.currency, row.amount, row.currency,
            )
            row.status = REVIEW
        else:
            if await _post(session, row.org_id, row.credits, "purchase", f"paypal:{row.id}"):
                await _add(session, row.org_id, row.credits)
                log.info("granted %d credits for order %s", row.credits, row.id)
            row.status = COMPLETED
    elif view.capture_status == "PENDING":
        row.status = PENDING
        row.capture_id = view.capture_id
    elif view.capture_status in ("DECLINED", "FAILED") or view.status == "VOIDED":
        row.status = FAILED
    row.updated_at = utcnow()
    return row


async def capture(
    session: AsyncSession, gateway: PayPalGateway, row: PaymentOrderRow
) -> PaymentOrderRow:
    """The buyer came back from PayPal: take the money."""
    if row.status == COMPLETED:
        return row
    return await apply_order_state(session, row, await gateway.capture_order(row.id))


async def reconcile(
    session: AsyncSession, gateway: PayPalGateway, row: PaymentOrderRow
) -> PaymentOrderRow:
    """Bring an unfinished order up to date.

    Covers the buyer who approved and then closed the tab, and the response lost
    between PayPal capturing and this process committing. Either way PayPal has
    the truth, so ask it rather than leave someone paid-for and uncredited.
    """
    view = await gateway.get_order(row.id)
    if view.status == "APPROVED":
        view = await gateway.capture_order(row.id)
    return await apply_order_state(session, row, view)


async def unfinished_orders(
    session: AsyncSession, org_id: str, limit: int = 10
) -> list[PaymentOrderRow]:
    rows = await session.execute(
        select(PaymentOrderRow)
        .where(
            PaymentOrderRow.org_id == org_id,
            PaymentOrderRow.status.in_([CREATED, PENDING]),
        )
        .order_by(PaymentOrderRow.created_at.desc())
        .limit(limit)
    )
    return list(rows.scalars())


async def get_order(
    session: AsyncSession, org_id: str, order_id: str
) -> Optional[PaymentOrderRow]:
    row = await session.get(PaymentOrderRow, order_id)
    return row if row and row.org_id == org_id else None
