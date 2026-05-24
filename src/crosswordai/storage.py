"""Artifact storage primitives.

The production plan calls for Postgres plus object storage. This module provides
the object-storage-shaped local implementation used by the CLI and tests while
the database and remote object storage adapters are introduced.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from crosswordai.ids import ArtifactId, new_artifact_id, utc_now_iso


class ArtifactExistsError(FileExistsError):
    pass


class ObjectStoreNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: ArtifactId
    media_type: str
    path: Path
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "media_type": self.media_type,
            "path": str(self.path),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class ArtifactSignature:
    artifact_id: str
    content_hash: str
    signature: str
    algorithm: str
    key_id: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ObjectStoreHealth:
    backend: str
    reachable: bool
    bucket: str | None = None
    prefix: str | None = None
    failures: tuple[str, ...] = ()


class ArtifactStore(Protocol):
    def write_json(
        self,
        payload: dict[str, Any],
        *,
        media_type: str = "application/json",
        artifact_id: ArtifactId | None = None,
    ) -> ArtifactRecord:
        ...

    def read_json(self, artifact_id: ArtifactId) -> dict[str, Any]:
        ...

    def write_bytes(
        self,
        payload: bytes,
        *,
        extension: str = ".bin",
        media_type: str = "application/octet-stream",
        artifact_id: ArtifactId | None = None,
    ) -> ArtifactRecord:
        ...

    def read_bytes(self, artifact_id: ArtifactId, *, extension: str = ".bin") -> bytes:
        ...


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write_json(
        self,
        payload: dict[str, Any],
        *,
        media_type: str = "application/json",
        artifact_id: ArtifactId | None = None,
    ) -> ArtifactRecord:
        artifact_id = artifact_id or new_artifact_id()
        path = self._path_for(artifact_id, ".json")
        self._write_bytes(path, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
        return ArtifactRecord(artifact_id, media_type, path, utc_now_iso())

    def read_json(self, artifact_id: ArtifactId) -> dict[str, Any]:
        return json.loads(self._path_for(artifact_id, ".json").read_text(encoding="utf-8"))

    def write_bytes(
        self,
        payload: bytes,
        *,
        extension: str = ".bin",
        media_type: str = "application/octet-stream",
        artifact_id: ArtifactId | None = None,
    ) -> ArtifactRecord:
        artifact_id = artifact_id or new_artifact_id()
        path = self._path_for(artifact_id, extension)
        self._write_bytes(path, payload)
        return ArtifactRecord(artifact_id, media_type, path, utc_now_iso())

    def read_bytes(self, artifact_id: ArtifactId, *, extension: str = ".bin") -> bytes:
        return self._path_for(artifact_id, extension).read_bytes()

    def _path_for(self, artifact_id: ArtifactId, extension: str) -> Path:
        return self.root / f"{artifact_id.value}{extension}"

    def _write_bytes(self, path: Path, payload: bytes) -> None:
        if path.exists():
            raise ArtifactExistsError(f"artifact already exists: {path}")
        path.write_bytes(payload)

    def health_check(self) -> ObjectStoreHealth:
        return ObjectStoreHealth("local", self.root.exists(), prefix=str(self.root))


class S3ArtifactStore:
    """S3/MinIO adapter seam.

    This intentionally fails clearly until boto3 or an S3-compatible client is
    configured. Keeping this seam explicit prevents local code from depending on
    filesystem behavior when production object storage is required.
    """

    def __init__(self, *, bucket: str, prefix: str = "", client: Any | None = None) -> None:
        if client is None:
            try:
                import boto3  # type: ignore[import-not-found]
            except ModuleNotFoundError as exc:
                raise ObjectStoreNotConfiguredError(
                    "S3ArtifactStore requires boto3 and S3/MinIO credentials."
                ) from exc
            client = boto3.client("s3")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = client

    def write_json(
        self,
        payload: dict[str, Any],
        *,
        media_type: str = "application/json",
        artifact_id: ArtifactId | None = None,
    ) -> ArtifactRecord:
        artifact_id = artifact_id or new_artifact_id()
        key = self._key_for(artifact_id, ".json")
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            ContentType=media_type,
        )
        return ArtifactRecord(artifact_id, media_type, Path(f"s3://{self.bucket}/{key}"), utc_now_iso())

    def read_json(self, artifact_id: ArtifactId) -> dict[str, Any]:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key_for(artifact_id, ".json"))
        return json.loads(response["Body"].read().decode("utf-8"))

    def write_bytes(
        self,
        payload: bytes,
        *,
        extension: str = ".bin",
        media_type: str = "application/octet-stream",
        artifact_id: ArtifactId | None = None,
    ) -> ArtifactRecord:
        artifact_id = artifact_id or new_artifact_id()
        key = self._key_for(artifact_id, extension)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=payload, ContentType=media_type)
        return ArtifactRecord(artifact_id, media_type, Path(f"s3://{self.bucket}/{key}"), utc_now_iso())

    def read_bytes(self, artifact_id: ArtifactId, *, extension: str = ".bin") -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key_for(artifact_id, extension))
        return response["Body"].read()

    def health_check(self) -> ObjectStoreHealth:
        try:
            if hasattr(self.client, "head_bucket"):
                self.client.head_bucket(Bucket=self.bucket)
            else:
                self.client.list_objects_v2(Bucket=self.bucket, Prefix=self.prefix, MaxKeys=1)
        except Exception as exc:  # noqa: BLE001 - health checks should report dependency failures.
            return ObjectStoreHealth("s3", False, self.bucket, self.prefix, (str(exc),))
        return ObjectStoreHealth("s3", True, self.bucket, self.prefix)

    def _key_for(self, artifact_id: ArtifactId, extension: str) -> str:
        filename = f"{artifact_id.value}{extension}"
        return f"{self.prefix}/{filename}" if self.prefix else filename


def artifact_content_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sign_artifact(
    *,
    artifact: ArtifactRecord,
    payload: bytes,
    secret_key: str,
    key_id: str = "local-dev",
    algorithm: str = "hmac-sha256",
) -> ArtifactSignature:
    if algorithm != "hmac-sha256":
        raise ValueError(f"unsupported artifact signature algorithm: {algorithm}")
    content_hash = artifact_content_hash(payload)
    signature = hmac.new(secret_key.encode("utf-8"), content_hash.encode("utf-8"), hashlib.sha256).hexdigest()
    return ArtifactSignature(
        artifact_id=str(artifact.artifact_id),
        content_hash=content_hash,
        signature=signature,
        algorithm=algorithm,
        key_id=key_id,
        created_at=utc_now_iso(),
    )


def verify_artifact_signature(*, signature: ArtifactSignature, payload: bytes, secret_key: str) -> bool:
    expected = sign_artifact(
        artifact=ArtifactRecord(ArtifactId(signature.artifact_id), "application/octet-stream", Path(signature.artifact_id), signature.created_at),
        payload=payload,
        secret_key=secret_key,
        key_id=signature.key_id,
        algorithm=signature.algorithm,
    )
    return hmac.compare_digest(signature.content_hash, expected.content_hash) and hmac.compare_digest(
        signature.signature,
        expected.signature,
    )


def signed_export_manifest(
    *,
    artifacts: list[ArtifactRecord],
    payloads: dict[str, bytes],
    secret_key: str,
    key_id: str = "local-dev",
) -> dict[str, Any]:
    signatures = []
    for artifact in artifacts:
        payload = payloads[str(artifact.artifact_id)]
        signatures.append(asdict(sign_artifact(artifact=artifact, payload=payload, secret_key=secret_key, key_id=key_id)))
    return {
        "created_at": utc_now_iso(),
        "algorithm": "hmac-sha256",
        "key_id": key_id,
        "artifacts": signatures,
    }
