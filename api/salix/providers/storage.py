"""Where uploaded audio lives.

Model Studio's file-transcription API fetches the audio itself, so it needs a
URL it can reach -- a local filesystem path is not something the service can
open. That constraint is what this module exists to handle:

* `LocalStorage` writes to disk and is what local development uses. If
  `SALIX_PUBLIC_BASE_URL` is set (a tunnel, or the deployed host), it can also
  hand back a reachable URL.
* `OSSStorage` uploads to Alibaba Cloud Object Storage and returns a signed
  URL, which is the deployed path.

The upload endpoint does not know which is in use.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..config import Settings
from ..signing import sign

log = logging.getLogger("salix.storage")


@runtime_checkable
class StorageBackend(Protocol):
    name: str

    def put(self, data: bytes, filename: str) -> tuple[str, str]:
        """Store bytes. Returns (local_path_or_key, url_for_the_transcriber)."""
        ...

    @property
    def serves_public_urls(self) -> bool: ...


class LocalStorage:
    """Disk. The default, and all that local development needs."""

    name = "local"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.audio_dir
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def serves_public_urls(self) -> bool:
        return bool(self.settings.public_base_url)

    def put(self, data: bytes, filename: str) -> tuple[str, str]:
        path = self.root / filename
        path.write_bytes(data)
        if self.settings.public_base_url:
            base = self.settings.public_base_url.rstrip("/")
            url = f"{base}/audio/{filename}"
            # Signed when there is a key to sign with, because this URL is
            # handed to somebody else's servers and is the only credential
            # they will have. Unsigned when there is not -- the deployment is
            # open by policy at that point and a signature would prove
            # nothing. Same shape as the OSS branch below.
            if self.settings.api_key:
                expires, sig = sign(self.settings.api_key, filename)
                url = f"{url}?expires={expires}&sig={sig}"
            return str(path), url
        return str(path), str(path)


class OSSStorage:
    """Alibaba Cloud Object Storage.

    Objects are uploaded private and handed to the transcriber as a
    time-limited signed URL, so recordings are never world-readable.
    """

    name = "oss"

    def __init__(self, settings: Settings):
        try:
            import oss2  # type: ignore
        except ImportError as exc:  # pragma: no cover - deployment path
            raise RuntimeError(
                "OSS storage needs the oss2 package: pip install oss2"
            ) from exc

        self.settings = settings
        auth = oss2.Auth(
            settings.oss_access_key_id, settings.oss_access_key_secret
        )
        self.bucket = oss2.Bucket(
            auth, settings.oss_endpoint, settings.oss_bucket
        )
        self.prefix = settings.oss_prefix.strip("/")

    @property
    def serves_public_urls(self) -> bool:
        return True

    def put(self, data: bytes, filename: str) -> tuple[str, str]:
        key = f"{self.prefix}/{filename}" if self.prefix else filename
        self.bucket.put_object(key, data)
        # Long enough for a 12-hour recording to finish transcribing, and no
        # longer than that.
        url = self.bucket.sign_url("GET", key, 60 * 60 * 24, slash_safe=True)
        log.info("uploaded %s to OSS (%d bytes)", key, len(data))
        return key, url


def build_storage(settings: Settings) -> StorageBackend:
    if settings.oss_bucket and settings.oss_access_key_id:
        try:
            return OSSStorage(settings)
        except Exception as exc:  # noqa: BLE001
            log.error("OSS unavailable (%s); falling back to local disk", exc)
    return LocalStorage(settings)
