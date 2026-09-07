# -*- coding: utf-8 -*-
"""Time-limited URLs for files served off local disk.

`/audio` is not under `/api`, so the shared key never applied to it -- which
meant the recordings, the most confidential thing in the system, were the one
thing served with no credential at all. Anyone holding a filename could fetch
somebody's sales call.

The obvious fix is to require the key, and it does not work. In live mode
Model Studio fetches the audio *itself*, from its own servers, with nothing of
ours to present. Requiring a header would close the hole and break
transcription in the same change.

So: the same answer OSS already gives. A URL carries its own proof, and that
proof expires. The transcriber can fetch what it was handed and nothing else,
for as long as the job needs and no longer.

Keyed by `SALIX_API_KEY`, which means signatures are only meaningful when a key
is configured. Without one the deployment is open by policy anyway, and
pretending otherwise here would be theatre.
"""

from __future__ import annotations

import hashlib
import hmac
import time

#: Long enough for a twelve-hour recording to finish transcribing, and no
#: longer. OSS uses the same window for the same reason.
DEFAULT_TTL = 60 * 60 * 24


def _digest(secret: str, name: str, expires: int) -> str:
    # The name is in the message, so a signature for one recording cannot be
    # replayed against another.
    message = f"{name}:{expires}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:32]


def sign(secret: str, name: str, ttl: int = DEFAULT_TTL) -> tuple[int, str]:
    """Return `(expires, signature)` for a filename."""
    expires = int(time.time()) + ttl
    return expires, _digest(secret, name, expires)


def verify(secret: str, name: str, expires: str | int | None, signature: str | None) -> bool:
    """Is this signature good for this name, right now?

    Returns False rather than raising for every malformed input: this runs on
    a request path, and the caller's only question is whether to serve.
    """
    if not secret or not signature or expires is None:
        return False
    try:
        expires_at = int(expires)
    except (TypeError, ValueError):
        return False

    if expires_at < time.time():
        return False

    return hmac.compare_digest(signature, _digest(secret, name, expires_at))
