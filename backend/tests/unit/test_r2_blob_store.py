from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from starlette.responses import RedirectResponse

from app.adapters.storage.r2_blob_store import R2BlobStore


@pytest.fixture
def fake_client() -> MagicMock:
    return MagicMock(name="s3_client")


@pytest.fixture
def store(fake_client: MagicMock) -> R2BlobStore:
    with patch("app.adapters.storage.r2_blob_store.boto3.client", return_value=fake_client):
        return R2BlobStore(
            account_id="acct",
            access_key_id="ak",
            secret_access_key="sk",
            bucket="sift-invoices",
        )


def _not_found_error() -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": "404", "Message": "Not Found"}},
        operation_name="HeadObject",
    )


class TestR2BlobStore:
    def test_exists_true_when_head_object_succeeds(
        self, store: R2BlobStore, fake_client: MagicMock
    ) -> None:
        fake_client.head_object.return_value = {"ContentLength": 123}
        assert store.exists("abc.pdf") is True
        fake_client.head_object.assert_called_once_with(
            Bucket="sift-invoices", Key="abc.pdf"
        )

    def test_exists_false_when_head_object_404s(
        self, store: R2BlobStore, fake_client: MagicMock
    ) -> None:
        fake_client.head_object.side_effect = _not_found_error()
        assert store.exists("nope.pdf") is False

    def test_exists_reraises_non_404_client_errors(
        self, store: R2BlobStore, fake_client: MagicMock
    ) -> None:
        fake_client.head_object.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied"}},
            operation_name="HeadObject",
        )
        with pytest.raises(ClientError):
            store.exists("abc.pdf")

    def test_put_path_uploads_when_missing(
        self, store: R2BlobStore, fake_client: MagicMock, tmp_path: Path
    ) -> None:
        fake_client.head_object.side_effect = _not_found_error()
        src = tmp_path / "in.pdf"
        src.write_bytes(b"hello")
        store.put_path("abc.pdf", src)
        fake_client.upload_file.assert_called_once_with(
            Filename=str(src),
            Bucket="sift-invoices",
            Key="abc.pdf",
            ExtraArgs={"ContentType": "application/pdf"},
        )

    def test_put_path_skips_when_already_present(
        self, store: R2BlobStore, fake_client: MagicMock, tmp_path: Path
    ) -> None:
        fake_client.head_object.return_value = {"ContentLength": 1}
        src = tmp_path / "in.pdf"
        src.write_bytes(b"x")
        store.put_path("abc.pdf", src)
        fake_client.upload_file.assert_not_called()

    def test_local_path_downloads_to_tempfile_and_cleans_up(
        self, store: R2BlobStore, fake_client: MagicMock
    ) -> None:
        def _download(*, Bucket: str, Key: str, Filename: str) -> None:
            Path(Filename).write_bytes(b"downloaded-bytes")
        fake_client.download_file.side_effect = _download

        with store.local_path("abc.pdf") as p:
            assert p.exists()
            assert p.read_bytes() == b"downloaded-bytes"
            cached_path = p

        assert not cached_path.exists()

    def test_serve_response_returns_redirect_to_signed_url(
        self, store: R2BlobStore, fake_client: MagicMock
    ) -> None:
        fake_client.generate_presigned_url.return_value = "https://r2.example/abc.pdf?sig=x"
        resp = store.serve_response("abc.pdf")
        assert isinstance(resp, RedirectResponse)
        assert resp.status_code == 307
        assert resp.headers["location"] == "https://r2.example/abc.pdf?sig=x"
        fake_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "sift-invoices", "Key": "abc.pdf"},
            ExpiresIn=300,
        )
