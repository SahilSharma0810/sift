from __future__ import annotations

import pytest

from app.adapters.storage.blob_store import get_blob_store
from app.config import Settings


class TestGetBlobStore:
    def test_returns_local_when_blob_store_local(self) -> None:
        local_blob_store = pytest.importorskip(
            "app.adapters.storage.local_blob_store",
            reason="LocalDiskBlobStore lands in Task 3",
        )
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        store = get_blob_store(s)
        assert isinstance(store, local_blob_store.LocalDiskBlobStore)

    def test_returns_r2_when_blob_store_r2(self) -> None:
        r2_blob_store = pytest.importorskip(
            "app.adapters.storage.r2_blob_store",
            reason="R2BlobStore lands in Task 4",
        )
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
            SIFT_BLOB_STORE="r2",
            SIFT_R2_ACCOUNT_ID="acct",
            SIFT_R2_ACCESS_KEY_ID="ak",
            SIFT_R2_SECRET_ACCESS_KEY="sk",
            SIFT_R2_BUCKET="b",
        )
        store = get_blob_store(s)
        assert isinstance(store, r2_blob_store.R2BlobStore)

    def test_unknown_blob_store_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        monkeypatch.setattr(s, "blob_store", "s3")
        with pytest.raises(ValueError, match="unknown blob_store"):
            get_blob_store(s)
