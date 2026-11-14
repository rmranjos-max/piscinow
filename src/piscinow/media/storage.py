import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

_KEY = re.compile(r"[a-z0-9_-]+(/[a-z0-9_.-]+)+")
_PREFIX = re.compile(r"[a-z0-9_-]+(/[a-z0-9_-]+)*")


class StorageError(RuntimeError):
    """The file could not be stored or removed. Never carries credentials or provider details."""


def new_key(prefix: str) -> str:
    """A random object key. The uploader's file name is never part of it."""
    if not _PREFIX.fullmatch(prefix or ""):
        raise ValueError("invalid media prefix")
    return f"{prefix}/{uuid.uuid4().hex}.jpg"


def _safe(key: str) -> bool:
    return bool(key) and ".." not in key and "\\" not in key and not key.startswith("/") and bool(_KEY.fullmatch(key))


class MediaStorage(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def url(self, key: str) -> str: ...


class MemoryMediaStorage(MediaStorage):
    """For tests: keeps the files in a dict."""

    def __init__(self):
        self.files: dict[str, bytes] = {}

    def save(self, key: str, data: bytes, content_type: str) -> None:
        if not _safe(key):
            raise ValueError("invalid media key")
        self.files[key] = data

    def delete(self, key: str) -> None:
        self.files.pop(key, None)

    def url(self, key: str) -> str:
        return f"/midia/{key}"


class LocalMediaStorage(MediaStorage):
    """For development: files on disk, served by the app itself at /midia/."""

    def __init__(self, root: str | Path):
        self._root = Path(root)

    def path_for(self, key: str) -> Path | None:
        """The file for a key, or None when the key could point outside the folder."""
        if not _safe(key):
            return None
        path = (self._root / key).resolve()
        return path if path.is_relative_to(self._root.resolve()) else None

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self.path_for(key)
        if path is None:
            raise ValueError("invalid media key")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        path = self.path_for(key)
        if path is not None:
            path.unlink(missing_ok=True)

    def url(self, key: str) -> str:
        return f"/midia/{key}"


class S3MediaStorage(MediaStorage):
    """Any S3-compatible bucket. Objects are public catalog photos, served from `public_base_url`."""

    def __init__(self, *, client, bucket: str, public_base_url: str):
        self._client = client
        self._bucket = bucket
        self._base = public_base_url.rstrip("/")

    def save(self, key: str, data: bytes, content_type: str) -> None:
        if not _safe(key):
            raise ValueError("invalid media key")
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
            )
        except Exception as exc:  # the provider's error may hold request details; keep it out of the message
            raise StorageError("Não foi possível guardar a foto agora. Tente novamente.") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise StorageError("Não foi possível remover a foto agora. Tente novamente.") from exc

    def url(self, key: str) -> str:
        return f"{self._base}/{key}"


def build_media_storage(
    *, kind: str, local_dir: str = "var/media", s3_endpoint_url: str | None = None, s3_bucket: str | None = None,
    s3_access_key_id: str | None = None, s3_secret_access_key: str | None = None, s3_region: str = "auto",
    public_base_url: str | None = None,
) -> MediaStorage:
    if kind == "local":
        return LocalMediaStorage(local_dir)
    if kind == "s3":
        missing = [
            name for name, value in {
                "PISCINOW_S3_ENDPOINT_URL": s3_endpoint_url, "PISCINOW_S3_BUCKET": s3_bucket,
                "PISCINOW_S3_ACCESS_KEY_ID": s3_access_key_id, "PISCINOW_S3_SECRET_ACCESS_KEY": s3_secret_access_key,
                "PISCINOW_MEDIA_PUBLIC_BASE_URL": public_base_url,
            }.items() if not value
        ]
        if missing:
            raise ValueError("media_storage=s3 requires " + ", ".join(missing))
        import boto3  # imported here so development and tests do not need the dependency loaded

        client = boto3.client(
            "s3", endpoint_url=s3_endpoint_url, aws_access_key_id=s3_access_key_id,
            aws_secret_access_key=s3_secret_access_key, region_name=s3_region,
        )
        return S3MediaStorage(client=client, bucket=s3_bucket, public_base_url=public_base_url)
    raise ValueError(f"unknown media_storage: {kind}")
