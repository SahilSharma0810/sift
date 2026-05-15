from __future__ import annotations

from pathlib import Path

import pytest
from starlette.responses import FileResponse

from app.adapters.storage.local_blob_store import LocalDiskBlobStore


@pytest.fixture
def store(tmp_path: Path) -> LocalDiskBlobStore:
    return LocalDiskBlobStore(upload_dir=tmp_path)


def _seed(store: LocalDiskBlobStore, key: str, body: bytes, tmp_path: Path) -> None:
    src = tmp_path / "_seed.bin"
    src.write_bytes(body)
    store.put_path(key, src)


class TestLocalDiskBlobStore:
    def test_put_path_writes_under_upload_dir(
        self, store: LocalDiskBlobStore, tmp_path: Path
    ) -> None:
        src = tmp_path / "in.pdf"
        src.write_bytes(b"hello")
        store.put_path("abc.pdf", src)
        assert (tmp_path / "abc.pdf").read_bytes() == b"hello"

    def test_put_path_is_idempotent_skips_when_exists(
        self, store: LocalDiskBlobStore, tmp_path: Path
    ) -> None:
        (tmp_path / "abc.pdf").write_bytes(b"original")
        src = tmp_path / "in.pdf"
        src.write_bytes(b"replacement")
        store.put_path("abc.pdf", src)
        assert (tmp_path / "abc.pdf").read_bytes() == b"original"

    def test_exists_reflects_disk(
        self, store: LocalDiskBlobStore, tmp_path: Path
    ) -> None:
        assert store.exists("nope.pdf") is False
        _seed(store, "yep.pdf", b"x", tmp_path)
        assert store.exists("yep.pdf") is True

    def test_local_path_yields_real_path(
        self, store: LocalDiskBlobStore, tmp_path: Path
    ) -> None:
        _seed(store, "abc.pdf", b"hello", tmp_path)
        with store.local_path("abc.pdf") as p:
            assert p == tmp_path / "abc.pdf"
            assert p.read_bytes() == b"hello"

    def test_serve_response_returns_fileresponse_with_immutable_cache(
        self, store: LocalDiskBlobStore, tmp_path: Path
    ) -> None:
        _seed(store, "abc.pdf", b"hello", tmp_path)
        resp = store.serve_response("abc.pdf")
        assert isinstance(resp, FileResponse)
        assert resp.media_type == "application/pdf"
        assert "max-age=31536000" in resp.headers["cache-control"]
        assert "immutable" in resp.headers["cache-control"]

    def test_serve_response_raises_404_when_missing(
        self, store: LocalDiskBlobStore
    ) -> None:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            store.serve_response("missing.pdf")
        assert exc.value.status_code == 404
