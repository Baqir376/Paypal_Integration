# How APIMatic is used

Two APIMatic tools are part of this project.

## 1. The generated SDK

Every PayPal Orders call goes through `paypal-server-sdk`, which APIMatic generates
from PayPal's API definition. The only file that imports it is
[`api/salix/billing/paypal.py`](../api/salix/billing/paypal.py).

## 2. The Context Plugin

The ContextMatic plugin was installed in Claude Code and used to review that file
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
- None of this has run against PayPal's real sandbox, because PayPal does not open
  accounts in Pakistan, where this was built. It runs in tests against a stand-in at
  the HTTP layer. Add PayPal sandbox keys to `.env` and it is used automatically.
