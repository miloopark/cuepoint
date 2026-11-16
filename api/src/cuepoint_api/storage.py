"""Object storage, in two modes.

- "s3": SeaweedFS locally (or any S3 endpoint) via boto3 with presigned URLs.
- "blob": Vercel Blob public store — the browser uploads via the Blob client
  SDK (token minted by the web project), and an audio key is the blob's full
  public URL, fetched here with plain HTTPS.

Either way the API never proxies audio bytes."""

from pathlib import Path

import boto3
import urllib3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import settings

_http = urllib3.PoolManager()


def _blob_mode() -> bool:
    return settings.storage_backend == "blob"


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
    if _blob_mode():
        return  # blob stores are provisioned, not created at runtime
    try:
        client().create_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        pass  # already exists / owned


def presign_put(key: str, content_type: str, expires_s: int = 3600) -> str:
    if _blob_mode():
        raise RuntimeError("blob mode: uploads go browser → Blob via the web project's token route")
    return client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_s,
    )


def presign_get(key: str, expires_s: int = 3600) -> str:
    if _blob_mode():
        return key  # the key IS the (unguessable) public blob URL
    return client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_s,
    )


def head_size(key: str) -> int | None:
    """Object size in bytes, or None if it doesn't exist."""
    if _blob_mode():
        try:
            r = _http.request("HEAD", key, timeout=urllib3.Timeout(total=10))
            if r.status != 200:
                return None
            length = r.headers.get("Content-Length")
            return int(length) if length else None
        except Exception:  # noqa: BLE001 — unreachable store reads as absent object
            return None
    try:
        return int(client().head_object(Bucket=settings.s3_bucket, Key=key)["ContentLength"])
    except (ClientError, BotoCoreError):
        return None


def download_bytes(key: str) -> bytes:
    """Fetch an object fully into memory — workers have no usable /tmp (the
    Python runtime's dependencies fill it) but plenty of headroom for audio."""
    if _blob_mode():
        r = _http.request("GET", key, timeout=urllib3.Timeout(total=300))
        if r.status != 200:
            raise RuntimeError(f"blob fetch failed with status {r.status}")
        return r.data
    body = client().get_object(Bucket=settings.s3_bucket, Key=key)["Body"]
    try:
        return body.read()
    finally:
        body.close()


def download_to(key: str, path: str | Path) -> None:
    if _blob_mode():
        with _http.request("GET", key, preload_content=False, timeout=urllib3.Timeout(total=300)) as r:
            if r.status != 200:
                raise RuntimeError(f"blob fetch failed with status {r.status}")
            with open(path, "wb") as f:
                f.writelines(r.stream(1 << 20))
        return
    client().download_file(settings.s3_bucket, key, str(path))
