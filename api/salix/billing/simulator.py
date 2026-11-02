"""A stand-in for PayPal's sandbox, for developers who cannot get into it.

PayPal accounts cannot be opened from every country, and the sandbox needs one. This
lets the whole purchase flow run anyway: the APIMatic SDK builds and sends its real
requests, and this answers them where PayPal's servers would, on the SDK's own HTTP
session. Nothing leaves the machine and no PayPal account is involved.

It proves this app's side of the integration. It does not prove PayPal would accept
it, and it hands out credits for free, so three rules keep it honest:

* It is off unless asked for by name.
* Real PayPal keys always win, so adding them is all it takes to switch over.
* It never runs with the environment set to production.

The pages say "simulated" wherever a person could otherwise believe they paid.
"""

from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from requests.adapters import HTTPAdapter

from ..config import Settings, get_settings

ROUTE = "/paypal-simulator"
_ORDER_PATH = re.compile(r"/v2/checkout/orders/([A-Z0-9]+)(/capture)?")
_ORDER_ID = re.compile(r"[A-Z0-9]{1,36}")

router = APIRouter(tags=["paypal-simulator"])


class SimulatedPayPal(HTTPAdapter):
    """Answers the Orders v2 calls the SDK makes, in PayPal's shapes."""

    def __init__(self, settings: Settings):
        super().__init__()
        self.app_url = settings.app_url.rstrip("/")
        self.orders: dict[str, dict[str, Any]] = {}

    def _respond(self, request: Any, status: int, body: dict) -> requests.Response:
        response = requests.Response()
        response.status_code = status
        response.raw = BytesIO(json.dumps(body).encode())
        response.headers["Content-Type"] = "application/json"
        response.url = request.url
        response.request = request
        return response

    def _refuse(self, request: Any, status: int, issue: str) -> requests.Response:
        return self._respond(
            request,
            status,
            {"name": "SIMULATED", "message": issue, "debug_id": "simulated", "details": [{"issue": issue}]},
        )

    def _body(self, order: dict[str, Any]) -> dict:
        unit = order["unit"]
        out: dict[str, Any] = {"id": order["id"], "status": order["status"]}
        if order["status"] == "PAYER_ACTION_REQUIRED":
            out["links"] = [
                {
                    "href": f"{self.app_url}/api{ROUTE}?token={order['id']}",
                    "rel": "payer-action",
                    "method": "GET",
                }
            ]
        if order["status"] == "COMPLETED":
            out["purchase_units"] = [
                {
                    "reference_id": unit["reference_id"],
                    "payments": {
                        "captures": [
                            {"id": f"SIMCAP{order['id']}", "status": "COMPLETED", "amount": unit["amount"]}
                        ]
                    },
                }
            ]
        return out

    def send(self, request: Any, **kwargs: Any) -> requests.Response:
        path = request.path_url.split("?")[0]
        if path == "/v1/oauth2/token":
            return self._respond(
                request, 200, {"access_token": "simulated", "token_type": "Bearer", "expires_in": 3600}
            )

        if path == "/v2/checkout/orders" and request.method == "POST":
            order_id = f"SIM{len(self.orders) + 1:06d}"
            self.orders[order_id] = {
                "id": order_id,
                "status": "PAYER_ACTION_REQUIRED",
                "unit": json.loads(request.body)["purchase_units"][0],
            }
            return self._respond(request, 200, self._body(self.orders[order_id]))

        match = _ORDER_PATH.fullmatch(path)
        order = self.orders.get(match.group(1)) if match else None
        if order is None:
            return self._refuse(request, 404, "RESOURCE_NOT_FOUND")
        if not match.group(2):
            return self._respond(request, 200, self._body(order))
        if order["status"] == "PAYER_ACTION_REQUIRED":
            return self._refuse(request, 422, "ORDER_NOT_APPROVED")
        if order["status"] == "COMPLETED":
            return self._refuse(request, 422, "ORDER_ALREADY_CAPTURED")
        order["status"] = "COMPLETED"
        return self._respond(request, 200, self._body(order))


_active: SimulatedPayPal | None = None


def http_client(settings: Settings) -> requests.Session:
    """The session the SDK is given, so its requests land here."""
    global _active
    _active = SimulatedPayPal(settings)
    session = requests.Session()
    session.mount("https://", _active)
    return session


def _order_or_404(token: str) -> dict[str, Any]:
    order = _active.orders.get(token) if _active and _ORDER_ID.fullmatch(token) else None
    if order is None:
        raise HTTPException(status_code=404, detail="No such simulated order.")
    return order


@router.get(ROUTE, response_class=HTMLResponse)
async def checkout_page(token: str) -> str:
    """Plays the part of PayPal's approval page, and says that it is doing so."""
    order = _order_or_404(token)
    amount = order["unit"]["amount"]
    # Only values this server produced, checked above or taken from its own pack table.
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Simulated PayPal checkout</title>
<style>*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:20px;font:15px system-ui,sans-serif;color:#f4f5f0;
background:radial-gradient(60vmax 60vmax at 20% 10%,#3f4f14,transparent),radial-gradient(60vmax 60vmax at 90% 80%,#123f3b,transparent),#06080a}}
main{{width:min(400px,100%);padding:30px 28px;border-radius:24px;background:rgb(255 255 255 / .07);backdrop-filter:blur(24px);
box-shadow:inset 0 0 0 1px rgb(255 255 255 / .16),0 30px 80px -24px #000;animation:pop .55s cubic-bezier(.2,1.5,.4,1) both}}
@keyframes pop{{from{{opacity:0;transform:scale(.8) translateY(20px)}}}}
.tag{{margin:0 0 20px;padding:10px 12px;border-radius:11px;font-size:13px;line-height:1.45;background:rgb(255 196 57 / .13);box-shadow:inset 0 0 0 1px rgb(255 196 57 / .45)}}
h1{{margin:0;font-size:34px;font-weight:600;letter-spacing:-.01em}}
.order{{margin:6px 0 22px;font:12px ui-monospace,monospace;opacity:.72}}
a{{display:block;padding:13px;margin-top:10px;border-radius:13px;text-align:center;text-decoration:none;color:#f4f5f0;box-shadow:inset 0 0 0 1px rgb(255 255 255 / .2);transition:transform .2s,background .2s}}
a:hover{{transform:translateY(-1px);background:rgb(255 255 255 / .08)}}
a.pay{{font-weight:650;color:#15190a;background:#d4f55a;box-shadow:none}}a.pay:hover{{background:#dcfa6c}}
@media (prefers-reduced-motion:reduce){{main{{animation:none}}a{{transition:none}}}}</style></head><body><main>
<p class="tag"><b>Simulated checkout. This is not PayPal.</b> No account is used and no money moves.</p>
<h1>Pay {amount['currency_code']} {amount['value']}</h1>
<p class="order">Order {token}, created with APIMatic's PayPal Server SDK</p>
<a class="pay" href="/api{ROUTE}/approve?token={token}">Approve simulated payment</a>
<a href="{get_settings().app_url.rstrip('/')}/billing?cancelled=1">Cancel and return</a>
</main></body></html>"""


@router.get(f"{ROUTE}/approve")
async def approve(token: str) -> RedirectResponse:
    order = _order_or_404(token)
    if order["status"] == "PAYER_ACTION_REQUIRED":
        order["status"] = "APPROVED"
    return RedirectResponse(
        f"{get_settings().app_url.rstrip('/')}/billing/return?token={token}&PayerID=SIMULATED",
        status_code=302,
    )
