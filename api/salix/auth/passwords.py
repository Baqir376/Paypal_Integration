"""Hashing passwords, with scrypt from the standard library.

The cost is written into each hash, so it can be raised later without locking out
anyone whose password was stored at the old one. Hashing is slow on purpose, so it
runs off the event loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets

# OWASP's scrypt setting for about 32 MiB of memory per guess.
N, R, P = 2**15, 8, 3
MAX_MEMORY = 64 * 1024 * 1024

MIN_LENGTH = 10
#: The cost of hashing grows with the input, so a stranger cannot choose it freely.
MAX_LENGTH = 128


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=MAX_MEMORY, dklen=32)


def _hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${N}${R}${P}${salt.hex()}${_derive(password, salt, N, R, P).hex()}"


def _matches(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _derive(password, bytes.fromhex(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, OverflowError):
        return False


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hash, password)


async def check_password(password: str, stored: str) -> bool:
    return await asyncio.to_thread(_matches, password, stored)


_decoy = _hash(secrets.token_urlsafe(16))


async def waste_a_check(password: str) -> None:
    """Takes as long as a real check, so timing cannot reveal which addresses have accounts."""
    await check_password(password, _decoy)
