# How APIMatic is used

Two APIMatic tools are part of this project.

## 1. The generated SDK

Every PayPal Orders call goes through `paypal-server-sdk`, which APIMatic generates
from PayPal's API definition. The only file that imports it is
[`api/salix/billing/paypal.py`](../api/salix/billing/paypal.py).

### It has run against PayPal's real sandbox

On 2026-11-03 two real purchases went through this code, with PayPal sandbox keys. This
is the one recorded in the demo video:

| Step | Evidence |
| :-- | :-- |
| `orders.create_order` in `paypal.py` | Order `4GM35893VB994222R`, returned with a `payer-action` link to `sandbox.paypal.com` |
| A sandbox buyer approved it on PayPal's own page | Returned to `/billing/return` |
| `orders.capture_order` in `paypal.py` | Capture `4M2861976M379154E`, USD 40.00, `COMPLETED`, read back from PayPal's API |
| Salix's ledger | 25 credits granted, once |

The earlier order was `9H555343TH507360E`, captured as `9YY25602CS4125354`, also USD 40.00.

Sandbox only: no real money moved. To check it yourself with your own sandbox keys,
follow the Quickstart, set `SALIX_PAYPAL_CLIENT_ID` and `SALIX_PAYPAL_CLIENT_SECRET`, and
buy a pack using a sandbox **Personal** account. The order then appears under Event Logs
in PayPal's developer dashboard. To see the SDK itself:

```
pip show paypal-server-sdk                     # 2.4.0
grep -n "paypalserversdk" api/salix/billing/paypal.py
```

## 2. The Context Plugin

The ContextMatic plugin was installed in an AI coding assistant and used to review that file
against the current SDK, through `/integrate-context-matic`, on 2026-11-02. The
integration was already written by then, so this was a review and not the original
build.

### What it found, and what changed

| Finding | Source | Change |
| :-- | :-- | :-- |
| The SDK reports endpoint errors through `result.is_error()` as well as by raising. The code only handled exceptions, so an error result read as an empty order, and a failed capture could look like "not completed" | `ask`, `endpoint_search` samples, then confirmed in the installed package | `_call` now checks `is_error()` and raises `PayPalError` |
| The sample reads the error code from `ErrorException.name` | `ask` | A code in `name` already worked as the fallback after `details[].issue`. Now covered by a test |
| The client retried nothing, because `max_retries` defaults to 0. The plugin's answer on this errored, so this came from reading the SDK's own configuration | Installed package | `max_retries=2`, which the SDK applies to GET and PUT only. Capture stays safe through its request id |

### What it confirmed, with no change needed

- `experience_context` under `payment_source.paypal` is the current place for
  `return_url` and `cancel_url`. `application_context` is marked deprecated.
- `paypal_request_id` is the idempotency key, and retries must reuse the same value.
- `capture_order`, `create_order` and their parameters match the code.
- `ORDER_ALREADY_CAPTURED`, `ORDER_NOT_APPROVED` and `INSTRUMENT_DECLINED` are the
  cases worth handling apart.

### Limits of this review

- The `ask` tool returned errors on 4 of its 5 calls, including the questions about
  retries and the approval link. `endpoint_search` and `model_search` worked.
- The docs the plugin returned name the `rel:approve` link. The code also accepts
  `payer-action`, which comes from general knowledge of PayPal's API and was not
  confirmed by the plugin, so both are handled and tested.
- At the time of this review the code had only run in tests, against a stand-in at the
  HTTP layer. It has since run against PayPal's real sandbox: see above.

## An SDK and docs portal for Salix's own API

The steps above are about calling PayPal. Salix's own API also has a client, generated with
the APIMatic CLI (`@apimatic/cli` 2.0.0) from [`openapi.json`](openapi.json).

```
cd api && python scripts/export_openapi.py          # writes docs/openapi.json
cp docs/openapi.json portal-source/src/spec/        # copy it into the portal project
cd portal-source
apimatic api validate
apimatic portal serve                               # the docs portal, locally
apimatic sdk generate -l python                     # writes sdk/python, which is not committed
```

### Generating it is not the same as it working

APIMatic scored the improved description 100/100 for SDK generation, but the first SDK
generated from it failed when it was run. Three problems showed up, and all were fixed in
the description (`api/scripts/export_openapi.py`):

| Problem | What it did | Fix |
|---|---|---|
| The upload forms were named schemas with a file field | The Python SDK crashed on import | Put each form on its operation |
| `anyOf` with `null` lost the null | The SDK refused `user: null` when signed out | Written as `oneOf` |
| `/api/auth/me` was marked as needing no credentials | The SDK did not send the session, so everyone looked signed out | Made the session optional there |

The final SDK then passed 17 checks against a running server: signing up and in, a wrong
password, requests with no session, unknown records, checkout and capture, adding a
salesperson, uploading a recording, and logging out. That run used the local PayPal stand-in,
and that test script is not in this repository.

### Limits

- The API score is 72 out of 100, measured before these three fixes. Most of the remaining
  warnings are for missing example values.
- Only the Python SDK has been generated and tested, and not every route was called.
- Neither the SDK nor the portal is published, and the description still points at `localhost`.

