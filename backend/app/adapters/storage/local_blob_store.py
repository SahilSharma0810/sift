"""Local-disk blob store — default for dev/test and small deployments.

Writes `{upload_dir}/{key}`. Reads pass straight through. Serves with
immutable cache headers since content-addressed keys never change for
the same content.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException, status
from starlette.responses import FileResponse, Response


class LocalDiskBlobStore:
    def __init__(self, *, upload_dir: Path) -> None:
        self._upload_dir = upload_dir
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._upload_dir / key

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def put_path(self, key: str, source: Path) -> None:
        target = self._path(key)
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        path = self._path(key)
        if not path.exists():
            raise FileNotFoundError(f"blob not found: {key}")
        yield path

    def serve_response(self, key: str) -> Response:
        path = self._path(key)
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="not found"
            )
        return FileResponse(
            path,
            media_type="application/pdf",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )
