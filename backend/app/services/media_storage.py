from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import boto3
from fastapi import UploadFile

from ..config import get_settings


settings = get_settings()
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredMedia:
    backend: str
    key: str
    filename: str
    content_type: str
    size: int
    sha256: str | None = None


def _safe_filename(value: str) -> str:
    name = Path(value or "upload.bin").name.strip() or "upload.bin"
    name = SAFE_FILENAME_RE.sub("-", name).strip(".-")
    return (name or "upload.bin")[:180]


def _storage_key(workspace_id: str, source_id: str, filename: str) -> str:
    return f"{workspace_id}/{source_id}/{_safe_filename(filename)}"


def _validate_upload(upload: UploadFile) -> int:
    size = int(upload.size or 0)
    max_bytes = max(1, settings.media_max_upload_mb) * 1024 * 1024
    if size > max_bytes:
        raise ValueError(
            f"Upload exceeds the {settings.media_max_upload_mb} MB workspace limit"
        )
    return size


async def _store_local(upload: UploadFile, key: str) -> StoredMedia:
    root = Path(settings.media_local_dir).expanduser().resolve()
    destination = (root / key).resolve()
    if root != destination and root not in destination.parents:
        raise ValueError("Invalid media storage path")

    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    written = 0
    max_bytes = max(1, settings.media_max_upload_mb) * 1024 * 1024

    try:
        with destination.open("wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(
                        f"Upload exceeds the {settings.media_max_upload_mb} MB workspace limit"
                    )
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return StoredMedia(
        backend="local",
        key=key,
        filename=_safe_filename(upload.filename or "upload.bin"),
        content_type=upload.content_type or "application/octet-stream",
        size=written,
        sha256=digest.hexdigest(),
    )


def _s3_client():
    required = {
        "MEDIA_S3_ENDPOINT_URL": settings.media_s3_endpoint_url,
        "MEDIA_S3_BUCKET": settings.media_s3_bucket,
        "MEDIA_S3_ACCESS_KEY_ID": settings.media_s3_access_key_id,
        "MEDIA_S3_SECRET_ACCESS_KEY": settings.media_s3_secret_access_key,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "S3 media storage is not fully configured: " + ", ".join(missing)
        )

    return boto3.client(
        "s3",
        endpoint_url=settings.media_s3_endpoint_url,
        aws_access_key_id=settings.media_s3_access_key_id,
        aws_secret_access_key=settings.media_s3_secret_access_key,
        region_name=settings.media_s3_region or "auto",
    )


async def _store_s3(upload: UploadFile, key: str) -> StoredMedia:
    size = _validate_upload(upload)
    await upload.seek(0)
    client = _s3_client()
    content_type = upload.content_type or "application/octet-stream"

    client.upload_fileobj(
        upload.file,
        settings.media_s3_bucket,
        key,
        ExtraArgs={
            "ContentType": content_type,
            "Metadata": {"original-filename": _safe_filename(upload.filename or "upload.bin")},
        },
    )
    await upload.close()

    return StoredMedia(
        backend="s3",
        key=key,
        filename=_safe_filename(upload.filename or "upload.bin"),
        content_type=content_type,
        size=size,
        sha256=None,
    )


async def store_upload(
    upload: UploadFile,
    *,
    workspace_id: str,
    source_id: str,
) -> StoredMedia:
    backend = settings.media_storage_backend.strip().lower()
    key = _storage_key(workspace_id, source_id, upload.filename or "upload.bin")

    if backend == "local":
        return await _store_local(upload, key)
    if backend in {"s3", "r2"}:
        return await _store_s3(upload, key)
    raise RuntimeError(f"Unsupported MEDIA_STORAGE_BACKEND: {backend}")
