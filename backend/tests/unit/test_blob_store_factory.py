from __future__ import annotations

import pytest

from app.adapters.storage.blob_store import get_blob_store
from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    get_settings.cache_clear()
    get_blob_store.cache_clear()


class TestGetBlobStore:
    def test_returns_local_when_blob_store_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        local_blob_store = pytest.importorskip(
            "app.adapters.storage.local_blob_store",
            reason="LocalDiskBlobStore lands in Task 3",
        )
        monkeypatch.setenv("SIFT_BLOB_STORE", "local")
        store = get_blob_store()
        assert isinstance(store, local_blob_store.LocalDiskBlobStore)

    def test_returns_r2_when_blob_store_r2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        r2_blob_store = pytest.importorskip(
            "app.adapters.storage.r2_blob_store",
            reason="R2BlobStore lands in Task 4",
        )
        monkeypatch.setenv("SIFT_BLOB_STORE", "r2")
        monkeypatch.setenv("SIFT_R2_ACCOUNT_ID", "acct")
        monkeypatch.setenv("SIFT_R2_ACCESS_KEY_ID", "ak")
        monkeypatch.setenv("SIFT_R2_SECRET_ACCESS_KEY", "sk")
        monkeypatch.setenv("SIFT_R2_BUCKET", "b")
        store = get_blob_store()
        assert isinstance(store, r2_blob_store.R2BlobStore)

    def test_unknown_blob_store_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock

        from app.adapters.storage import blob_store as blob_store_module

        fake = MagicMock()
        fake.blob_store = "s3"
        monkeypatch.setattr(blob_store_module, "get_settings", lambda: fake)
        with pytest.raises(ValueError, match="unknown blob_store"):
            get_blob_store()
