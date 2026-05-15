"""Blob storage abstraction — PDFs by content-addressed key.

Two implementations live alongside this protocol: `LocalDiskBlobStore`
(default — used in dev/test/local) and `R2BlobStore` (Cloudflare R2 via
boto3 S3-compatible API, used in production).

Per ADR-0007: callers receive bytes via `serve_response(key)` and never
touch the underlying transport. Extraction code that genuinely needs a
local path uses `local_path(key)` as a context manager — a no-op for
local, a download-to-tempfile for R2.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol, runtime_checkable

from starlette.responses import Response

from app.config import Settings


@runtime_checkable
class BlobStore(Protocol):
    def exists(self, key: str) -> bool: ...
    def put_path(self, key: str, source: Path) -> None: ...
    def local_path(self, key: str) -> AbstractContextManager[Path]: ...
    def serve_response(self, key: str) -> Response: ...


def get_blob_store(settings: Settings) -> BlobStore:
    if settings.blob_store == "local":
        from app.adapters.storage.local_blob_store import LocalDiskBlobStore
        return LocalDiskBlobStore(upload_dir=settings.upload_dir)
    if settings.blob_store == "r2":
        from app.adapters.storage.r2_blob_store import R2BlobStore
        return R2BlobStore(
            account_id=settings.r2_account_id,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            bucket=settings.r2_bucket,
        )
    raise ValueError(f"unknown blob_store: {settings.blob_store!r}")
