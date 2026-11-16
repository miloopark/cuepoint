"""S3-compatible object storage (SeaweedFS locally, R2 in production).

The API never proxies audio bytes: the browser PUTs to a presigned URL and the
worker downloads straight from storage."""

from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import settings


def client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    try:
        client().create_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        pass  # already exists / owned


def presign_put(key: str, content_type: str, expires_s: int = 3600) -> str:
    return client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_s,
    )


def presign_get(key: str, expires_s: int = 3600) -> str:
    return client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_s,
    )


def head_size(key: str) -> int | None:
    """Object size in bytes, or None if it doesn't exist."""
    try:
        return int(client().head_object(Bucket=settings.s3_bucket, Key=key)["ContentLength"])
    except (ClientError, BotoCoreError):
        return None


def download_to(key: str, path: str | Path) -> None:
    client().download_file(settings.s3_bucket, key, str(path))
