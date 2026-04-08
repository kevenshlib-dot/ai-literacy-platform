"""Object storage service — MinIO with local filesystem fallback.

When MinIO is available, files are stored in MinIO.
When MinIO is unavailable (e.g. Docker not running), falls back to local
filesystem at ./storage/ for development convenience.
"""
import io
import os
import uuid
from datetime import timedelta
from pathlib import Path

from app.core.config import settings

# ── Format / MIME / size constants ────────────────────────────────────────────

FORMAT_EXTENSIONS = {
    "pdf": [".pdf"],
    "word": [".doc", ".docx"],
    "markdown": [".md", ".markdown"],
    "html": [".html", ".htm"],
    "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
    "video": [".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm"],
    "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
    "csv": [".csv"],
    "json": [".json"],
}

MIME_TO_FORMAT = {
    "application/pdf": "pdf",
    "application/msword": "word",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
    "text/markdown": "markdown",
    "text/html": "html",
    "text/csv": "csv",
    "application/json": "json",
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
    "image/svg+xml": "image",
    "image/bmp": "image",
    "video/mp4": "video",
    "video/x-msvideo": "video",
    "video/quicktime": "video",
    "video/webm": "video",
    "audio/mpeg": "audio",
    "audio/wav": "audio",
    "audio/flac": "audio",
    "audio/ogg": "audio",
    "audio/aac": "audio",
}

MAX_FILE_SIZES = {
    "pdf": 100 * 1024 * 1024,
    "word": 50 * 1024 * 1024,
    "markdown": 10 * 1024 * 1024,
    "html": 10 * 1024 * 1024,
    "image": 20 * 1024 * 1024,
    "video": 500 * 1024 * 1024,
    "audio": 200 * 1024 * 1024,
    "csv": 50 * 1024 * 1024,
    "json": 50 * 1024 * 1024,
}

# ── Local storage root (fallback when MinIO is unavailable) ───────────────────
LOCAL_STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "storage"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minio_available() -> bool:
    """Quick check if MinIO is reachable."""
    import socket
    host, port = settings.MINIO_HOST, settings.MINIO_PORT
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def get_minio_client():
    from minio import Minio
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )


def ensure_bucket(client, bucket_name: str = None):
    bucket = bucket_name or settings.MINIO_BUCKET
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    return bucket


def detect_format(filename: str, content_type: str = None) -> str:
    if content_type and content_type in MIME_TO_FORMAT:
        return MIME_TO_FORMAT[content_type]
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for fmt, extensions in FORMAT_EXTENSIONS.items():
        if ext in extensions:
            return fmt
    raise ValueError(f"不支持的文件格式: {filename}")


# ── Upload ────────────────────────────────────────────────────────────────────

async def upload_file(
    file_data: bytes,
    filename: str,
    content_type: str,
    user_id: str,
) -> dict:
    """Upload a file — MinIO first, local fallback if MinIO is down."""
    fmt = detect_format(filename, content_type)
    file_size = len(file_data)

    max_size = MAX_FILE_SIZES.get(fmt, 100 * 1024 * 1024)
    if file_size > max_size:
        raise ValueError(
            f"文件大小超过限制: {file_size / 1024 / 1024:.1f}MB > {max_size / 1024 / 1024:.0f}MB"
        )

    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    object_name = f"{user_id}/{fmt}/{uuid.uuid4().hex}.{ext}"
    bucket = settings.MINIO_BUCKET

    if _minio_available():
        client = get_minio_client()
        bucket = ensure_bucket(client)
        client.put_object(
            bucket, object_name, io.BytesIO(file_data),
            length=file_size,
            content_type=content_type or "application/octet-stream",
        )
    else:
        # Local filesystem fallback
        dest = LOCAL_STORAGE_ROOT / bucket / object_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(file_data)

    return {
        "file_path": f"{bucket}/{object_name}",
        "file_size": file_size,
        "format": fmt,
        "object_name": object_name,
        "bucket": bucket,
    }


# ── Download URL ──────────────────────────────────────────────────────────────

def get_presigned_url(file_path: str, expires: int = 3600) -> str:
    parts = file_path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"无效的文件路径: {file_path}")

    bucket, object_name = parts

    if _minio_available():
        client = get_minio_client()
        return client.presigned_get_object(
            bucket, object_name, expires=timedelta(seconds=expires)
        )

    # Local fallback — serve via API route (handled elsewhere or static files)
    local_path = LOCAL_STORAGE_ROOT / bucket / object_name
    if local_path.exists():
        return f"/api/v1/materials/files/{bucket}/{object_name}"
    raise ValueError(f"文件不存在: {file_path}")


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_file(file_path: str):
    parts = file_path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"无效的文件路径: {file_path}")

    bucket, object_name = parts

    if _minio_available():
        client = get_minio_client()
        client.remove_object(bucket, object_name)
    else:
        local_path = LOCAL_STORAGE_ROOT / bucket / object_name
        if local_path.exists():
            local_path.unlink()
