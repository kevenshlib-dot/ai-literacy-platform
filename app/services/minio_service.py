"""MinIO object storage service for file upload and management."""
import io
import uuid
from datetime import timedelta
from typing import Optional

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

# File format to extension mapping
FORMAT_EXTENSIONS = {
    "pdf": [".pdf"],
    "word": [".doc", ".docx"],
    "epub": [".epub"],
    "markdown": [".md", ".markdown"],
    "html": [".html", ".htm"],
    "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"],
    "video": [".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm"],
    "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
    "csv": [".csv"],
    "json": [".json"],
}

# MIME type to format mapping
MIME_TO_FORMAT = {
    "application/pdf": "pdf",
    "application/msword": "word",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
    "application/epub+zip": "epub",
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

# Max file size per format (in bytes)
MAX_FILE_SIZES = {
    "pdf": 100 * 1024 * 1024,      # 100MB
    "word": 50 * 1024 * 1024,       # 50MB
    "epub": 50 * 1024 * 1024,       # 50MB
    "markdown": 10 * 1024 * 1024,   # 10MB
    "html": 10 * 1024 * 1024,       # 10MB
    "image": 20 * 1024 * 1024,      # 20MB
    "video": 500 * 1024 * 1024,     # 500MB
    "audio": 200 * 1024 * 1024,     # 200MB
    "csv": 50 * 1024 * 1024,        # 50MB
    "json": 50 * 1024 * 1024,       # 50MB
}


def get_minio_client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )


def ensure_bucket(client: Minio, bucket_name: str = None):
    bucket = bucket_name or settings.MINIO_BUCKET
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    return bucket


def detect_format(filename: str, content_type: str = None) -> str:
    """Detect material format from filename extension or MIME type."""
    if content_type and content_type in MIME_TO_FORMAT:
        return MIME_TO_FORMAT[content_type]

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for fmt, extensions in FORMAT_EXTENSIONS.items():
        if ext in extensions:
            return fmt
    raise ValueError(f"不支持的文件格式: {filename}")


async def upload_file(
    file_data: bytes,
    filename: str,
    content_type: str,
    user_id: str,
) -> dict:
    """Upload a file to MinIO and return storage metadata."""
    fmt = detect_format(filename, content_type)
    file_size = len(file_data)

    max_size = MAX_FILE_SIZES.get(fmt, 100 * 1024 * 1024)
    if file_size > max_size:
        raise ValueError(
            f"文件大小超过限制: {file_size / 1024 / 1024:.1f}MB > {max_size / 1024 / 1024:.0f}MB"
        )

    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    object_name = f"{user_id}/{fmt}/{uuid.uuid4().hex}.{ext}"

    client = get_minio_client()
    bucket = ensure_bucket(client)

    client.put_object(
        bucket,
        object_name,
        io.BytesIO(file_data),
        length=file_size,
        content_type=content_type or "application/octet-stream",
    )

    return {
        "file_path": f"{bucket}/{object_name}",
        "file_size": file_size,
        "format": fmt,
        "object_name": object_name,
        "bucket": bucket,
    }


def get_presigned_url(
    file_path: str,
    expires: int = 3600,
    download_filename: Optional[str] = None,
) -> str:
    """Generate a presigned URL for downloading a file."""
    parts = file_path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"无效的文件路径: {file_path}")

    bucket, object_name = parts
    client = get_minio_client()
    response_headers = None
    if download_filename:
        response_headers = {
            "response-content-disposition": f'attachment; filename="{download_filename}"',
        }
    return client.presigned_get_object(
        bucket,
        object_name,
        expires=timedelta(seconds=expires),
        response_headers=response_headers,
    )


def delete_file(file_path: str):
    """Delete a file from MinIO."""
    parts = file_path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"无效的文件路径: {file_path}")

    bucket, object_name = parts
    client = get_minio_client()
    client.remove_object(bucket, object_name)
