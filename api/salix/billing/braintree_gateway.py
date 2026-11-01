"""Braintree, PayPal's card and wallet gateway.

Here because PayPal does not open accounts everywhere, but Braintree's sandbox can be
applied for from Pakistan with a name, a company and an email address, and the
hackathon's rules count it as part of the PayPal platform.

The flow differs from PayPal Orders in one way that matters. The browser never sends
card details here: Braintree's own form turns them into a single-use nonce, and this
process spends the nonce. The price still comes from the server's pack table, and the
outcome goes through the same `apply_order_state` as every other payment, so the
amount check and the once-only ledger are shared.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from ..config import Settings
from .packs import Pack
from .paypal import OrderView

log = logging.getLogger("salix.braintree")

#: Braintree statuses meaning the money is being taken.
_PAID = frozenset({"authorized", "submitted_for_settlement", "settling", "settlement_pending", "settled"})
_FAILED = frozenset({"failed", "gateway_rejected", "processor_declined", "settlement_declined", "voided"})


class BraintreeError(RuntimeError):
    def __init__(self, detail: str, *, declined: bool = False):
        super().__init__(detail)
        self.detail = detail
        self.declined = declined


def _view(order_id: str, transaction: Any) -> OrderView:
    status = str(transaction.status)
    return OrderView(
        id=order_id,
        status=status.upper(),
        capture_id=str(transaction.id),
        capture_status="COMPLETED" if status in _PAID else "FAILED" if status in _FAILED else "PENDING",
        amount=str(transaction.amount),
        currency=str(transaction.currency_iso_code),
    )


class BraintreePayments:
    def __init__(self, settings: Settings, *, gateway: Any = None):
        self._gateway = gateway or self._connect(settings)

    @staticmethod
    def _connect(settings: Settings) -> Any:
        import braintree

        return braintree.BraintreeGateway(
            braintree.Configuration(
                environment=(
                    braintree.Environment.Production
                    if settings.paypal_mode == "production"
                    else braintree.Environment.Sandbox
                ),
                merchant_id=settings.braintree_merchant_id,
                public_key=settings.braintree_public_key,
                private_key=settings.braintree_private_key,
            )
        )

    async def _call(self, method: Any, *args: Any) -> Any:
        try:
            return await asyncio.to_thread(method, *args)
        except Exception as exc:  # noqa: BLE001
            # The SDK's errors can quote the request, so only the type is passed on.
            log.warning("braintree call failed: %s", type(exc).__name__)
            raise BraintreeError("Braintree could not be reached.") from exc

    async def client_token(self) -> str:
        return await self._call(self._gateway.client_token.generate)

    async def charge(self, pack: Pack, *, order_id: str, nonce: str) -> OrderView:
        result = await self._call(
            self._gateway.transaction.sale,
            {
                "amount": pack.price,
                "payment_method_nonce": nonce,
                "order_id": order_id,
                "options": {"submit_for_settlement": True},
            },
        )
        if result.is_success:
            return _view(order_id, result.transaction)
        log.info("braintree refused order %s", order_id)
        raise BraintreeError(str(result.message or "The payment was declined."), declined=True)

    async def find(self, order_id: str) -> Optional[OrderView]:
        """What happened to an order whose response never made it back."""
        import braintree

        found = await self._call(
            self._gateway.transaction.search, braintree.TransactionSearch.order_id == order_id
        )
        for transaction in found.items:
            return _view(order_id, transaction)
        return None


_payments: Optional[BraintreePayments] = None


def get_payments(settings: Settings) -> BraintreePayments:
    global _payments
    if not settings.braintree_configured:
        raise BraintreeError("Braintree is not configured on this server.")
    if _payments is None:
        _payments = BraintreePayments(settings)
    return _payments


def reset_payments(payments: Optional[BraintreePayments] = None) -> None:
    global _payments
    _payments = payments
