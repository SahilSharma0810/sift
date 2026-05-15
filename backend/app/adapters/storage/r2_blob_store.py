"""Cloudflare R2 blob store via the S3-compatible API (boto3 + s3v4).

R2 endpoint: `https://{account_id}.r2.cloudflarestorage.com`. Egress is
free which is why we use R2 over S3 — every clerk who opens an invoice
ships PDF bytes from R2 directly to the browser via a 5-minute signed
GET URL. FastAPI is only on the path for the initial auth check and
URL signing.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from starlette.responses import RedirectResponse, Response

SIGNED_URL_TTL_SECONDS = 300


class R2BlobStore:
    def __init__(
        self,
        *,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put_path(self, key: str, source: Path) -> None:
        if self.exists(key):
            return
        self._client.upload_file(
            Filename=str(source),
            Bucket=self._bucket,
            Key=key,
            ExtraArgs={"ContentType": "application/pdf"},
        )

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)  # noqa: SIM115
        tmp.close()
        path = Path(tmp.name)
        try:
            self._client.download_file(
                Bucket=self._bucket, Key=key, Filename=str(path)
            )
            yield path
        finally:
            path.unlink(missing_ok=True)

    def serve_response(self, key: str) -> Response:
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=SIGNED_URL_TTL_SECONDS,
        )
        return RedirectResponse(url, status_code=307)
