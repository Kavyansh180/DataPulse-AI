import logging
import uuid
import re
from typing import Optional
from urllib.parse import urlparse

from app.core.config import get_settings
from app.api.errors import APIError

logger = logging.getLogger("datapulse.s3")
settings = get_settings()


class S3Service:
    """Service handling Amazon S3 storage operations for ingested CSV datasets."""

    @staticmethod
    def is_configured() -> bool:
        """Check if an S3 bucket name is configured."""
        return bool(settings.S3_BUCKET_NAME and settings.S3_BUCKET_NAME.strip())

    @classmethod
    def get_client(cls):
        """Initialize and return a boto3 S3 client using the configured region and credentials."""
        try:
            import boto3
        except ImportError:
            raise APIError(
                status_code=500,
                message="boto3 is not installed in the runtime environment.",
                code="DEPENDENCY_MISSING",
            )

        client_kwargs = {
            "region_name": settings.AWS_REGION,
        }
        if settings.S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

        return boto3.client("s3", **client_kwargs)

    @classmethod
    def generate_safe_object_key(cls, dataset_id: int, original_filename: str) -> str:
        """Generate a collision-resistant, path-traversal-safe S3 object key.

        The original filename is sanitized and truncated for human readability in S3 consoles,
        but unique identification is guaranteed via a UUID4 hex prefix.
        """
        # Strip directories to prevent path traversal
        clean_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", original_filename.split("/")[-1].split("\\")[-1])
        if not clean_name.lower().endswith(".csv"):
            clean_name = f"{clean_name}.csv"

        unique_id = uuid.uuid4().hex
        return f"datasets/{dataset_id}/{unique_id}_{clean_name}"

    @classmethod
    def upload_file_bytes(
        cls,
        file_bytes: bytes,
        object_key: str,
        content_type: str = "text/csv",
    ) -> str:
        """Upload in-memory file bytes to Amazon S3.

        Returns:
            The canonical S3 URI: s3://<bucket>/<object_key>
        Raises:
            APIError if S3 bucket configuration is missing or AWS rejects the upload.
        """
        if not cls.is_configured():
            raise APIError(
                status_code=503,
                message=(
                    "Amazon S3 storage is not configured. "
                    "Please set S3_BUCKET_NAME in your environment configuration."
                ),
                code="S3_NOT_CONFIGURED",
            )

        client = cls.get_client()
        bucket = settings.S3_BUCKET_NAME

        try:
            client.put_object(
                Bucket=bucket,
                Key=object_key,
                Body=file_bytes,
                ContentType=content_type,
            )
            s3_uri = f"s3://{bucket}/{object_key}"
            logger.info(f"Successfully uploaded {len(file_bytes)} bytes to {s3_uri}")
            return s3_uri
        except Exception as exc:
            logger.error(f"S3 upload error to bucket '{bucket}', key '{object_key}': {exc}")
            raise APIError(
                status_code=502,
                message=f"Failed to store file in Amazon S3: {str(exc)}",
                code="S3_UPLOAD_FAILED",
            )

    @classmethod
    def download_file_bytes(cls, storage_uri_or_key: str) -> bytes:
        """Download file bytes given an S3 URI (s3://bucket/key) or direct object key.

        Raises:
            APIError if download fails or S3 is unreachable.
        """
        if storage_uri_or_key.startswith("s3://"):
            parsed = urlparse(storage_uri_or_key)
            bucket = parsed.netloc
            key = parsed.path.lstrip("/")
        else:
            if not cls.is_configured():
                raise APIError(
                    status_code=503,
                    message="S3_BUCKET_NAME is required to resolve relative S3 object keys.",
                    code="S3_NOT_CONFIGURED",
                )
            bucket = settings.S3_BUCKET_NAME
            key = storage_uri_or_key

        client = cls.get_client()
        try:
            response = client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:
            logger.error(f"S3 download failed for s3://{bucket}/{key}: {exc}")
            raise APIError(
                status_code=502,
                message=f"Failed to retrieve file from S3: {str(exc)}",
                code="S3_DOWNLOAD_FAILED",
            )
