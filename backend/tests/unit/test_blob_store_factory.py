from __future__ import annotations

import pytest

from app.adapters.storage.blob_store import get_blob_store
from app.config import Settings


class TestGetBlobStore:
    def test_returns_local_when_blob_store_local(self) -> None:
        from app.adapters.storage.local_blob_store import LocalDiskBlobStore
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        store = get_blob_store(s)
        assert isinstance(store, LocalDiskBlobStore)

    def test_returns_r2_when_blob_store_r2(self) -> None:
        from app.adapters.storage.r2_blob_store import R2BlobStore
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
            SIFT_BLOB_STORE="r2",
            SIFT_R2_ACCOUNT_ID="acct",
            SIFT_R2_ACCESS_KEY_ID="ak",
            SIFT_R2_SECRET_ACCESS_KEY="sk",
            SIFT_R2_BUCKET="b",
        )
        store = get_blob_store(s)
        assert isinstance(store, R2BlobStore)
