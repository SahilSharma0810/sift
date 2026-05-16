from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


class TestBlobStoreSettings:
    def test_defaults_to_local(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.blob_store == "local"

    def test_r2_requires_all_four_fields(self) -> None:
        with pytest.raises(ValidationError, match="r2_account_id"):
            Settings(
                _env_file=None,  # type: ignore[call-arg]
                SIFT_BLOB_STORE="r2",
                SIFT_R2_ACCESS_KEY_ID="ak",
                SIFT_R2_SECRET_ACCESS_KEY="sk",
                SIFT_R2_BUCKET="b",
            )

    def test_r2_accepts_all_four_fields(self) -> None:
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
            SIFT_BLOB_STORE="r2",
            SIFT_R2_ACCOUNT_ID="acct",
            SIFT_R2_ACCESS_KEY_ID="ak",
            SIFT_R2_SECRET_ACCESS_KEY="sk",
            SIFT_R2_BUCKET="b",
        )
        assert s.blob_store == "r2"
        assert s.r2_account_id == "acct"
        assert s.r2_access_key_id == "ak"
        assert s.r2_secret_access_key == "sk"
        assert s.r2_bucket == "b"
