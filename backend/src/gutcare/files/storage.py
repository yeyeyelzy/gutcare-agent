"""Private S3 compatible storage adapter."""

from io import BytesIO
from typing import Protocol, cast

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]


class ObjectStorage(Protocol):
    def put_object(self, bucket: str, key: str, body: bytes, content_type: str) -> None: ...

    def head_object(self, bucket: str, key: str) -> tuple[int, str]: ...

    def read_object(self, bucket: str, key: str) -> bytes: ...

    def read_object_limited(self, bucket: str, key: str, limit: int) -> bytes: ...

    def delete_object(self, bucket: str, key: str) -> None: ...

    def list_object_versions(self, bucket: str, prefix: str) -> list[tuple[str, str | None]]: ...

    def delete_object_version(self, bucket: str, key: str, version_id: str | None) -> None: ...


class S3ObjectStorage:
    """MinIO/S3 storage using only server-side credentials."""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def put_object(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=bucket,
            Key=key,
            Body=BytesIO(body),
            ContentLength=len(body),
            ContentType=content_type,
        )

    def head_object(self, bucket: str, key: str) -> tuple[int, str]:
        response = self._client.head_object(Bucket=bucket, Key=key)
        return int(response["ContentLength"]), str(response.get("ContentType", ""))

    def read_object(self, bucket: str, key: str) -> bytes:
        response = self._client.get_object(Bucket=bucket, Key=key)
        try:
            return cast(bytes, response["Body"].read())
        finally:
            response["Body"].close()

    def read_object_limited(self, bucket: str, key: str, limit: int) -> bytes:
        response = self._client.get_object(Bucket=bucket, Key=key)
        try:
            # Read one byte past the limit so a changed/lying Content-Length cannot
            # cause an unbounded allocation after the preceding HEAD request.
            return cast(bytes, response["Body"].read(limit + 1))
        finally:
            response["Body"].close()

    def delete_object(self, bucket: str, key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=key)

    def list_object_versions(self, bucket: str, prefix: str) -> list[tuple[str, str | None]]:
        paginator = self._client.get_paginator("list_object_versions")
        found: list[tuple[str, str | None]] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Versions", []):
                raw_version = str(item["VersionId"])
                found.append((str(item["Key"]), None if raw_version == "null" else raw_version))
            for item in page.get("DeleteMarkers", []):
                raw_version = str(item["VersionId"])
                found.append((str(item["Key"]), None if raw_version == "null" else raw_version))
        return found

    def delete_object_version(self, bucket: str, key: str, version_id: str | None) -> None:
        params: dict[str, str] = {"Bucket": bucket, "Key": key}
        if version_id is not None:
            params["VersionId"] = version_id
        self._client.delete_object(**params)
