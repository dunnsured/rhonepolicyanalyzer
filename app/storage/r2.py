"""Cloudflare R2 storage client wrapping boto3 S3-compatible API."""

import logging
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)


class R2StorageClient:
    """Cloudflare R2 object storage client.

    Wraps boto3 S3 client configured for R2's S3-compatible endpoint.
    Provides upload, download, and pre-signed URL generation for
    policy PDFs and generated report PDFs.
    """

    def __init__(
        self,
        account_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ):
        settings = get_settings()
        self._account_id = account_id or settings.r2_account_id
        self._access_key_id = access_key_id or settings.r2_access_key_id
        self._secret_access_key = secret_access_key or settings.r2_secret_access_key
        self._bucket_name = bucket_name or settings.r2_bucket_name

        self._endpoint_url = (
            f"https://{self._account_id}.r2.cloudflarestorage.com"
            if self._account_id
            else None
        )

        self._client = boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
            region_name="auto",
        )

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def upload_file(self, bucket_path: str, file_bytes: bytes, content_type: str = "application/pdf") -> str:
        """Upload a file to R2.

        Args:
            bucket_path: Object key (path) within the bucket.
            file_bytes: Raw file content.
            content_type: MIME type of the file.

        Returns:
            The bucket path of the uploaded object.

        Raises:
            ClientError: If the upload fails.
        """
        logger.info("Uploading %d bytes to r2://%s/%s", len(file_bytes), self._bucket_name, bucket_path)
        self._client.put_object(
            Bucket=self._bucket_name,
            Key=bucket_path,
            Body=file_bytes,
            ContentType=content_type,
        )
        logger.info("Upload complete: %s", bucket_path)
        return bucket_path

    def get_signed_url(self, bucket_path: str, expires_in: int = 3600) -> str:
        """Generate a pre-signed download URL for an object.

        Args:
            bucket_path: Object key within the bucket.
            expires_in: URL expiration time in seconds (default: 1 hour).

        Returns:
            Pre-signed URL string.
        """
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket_name, "Key": bucket_path},
            ExpiresIn=expires_in,
        )
        logger.info("Generated signed URL for %s (expires in %ds)", bucket_path, expires_in)
        return url

    def download_file(self, bucket_path: str) -> bytes:
        """Download a file from R2.

        Args:
            bucket_path: Object key within the bucket.

        Returns:
            Raw file content as bytes.

        Raises:
            ClientError: If the download fails or object doesn't exist.
        """
        logger.info("Downloading r2://%s/%s", self._bucket_name, bucket_path)
        response = self._client.get_object(
            Bucket=self._bucket_name,
            Key=bucket_path,
        )
        data = response["Body"].read()
        logger.info("Downloaded %d bytes from %s", len(data), bucket_path)
        return data

    def delete_file(self, bucket_path: str) -> None:
        """Delete a file from R2.

        Args:
            bucket_path: Object key within the bucket.
        """
        logger.info("Deleting r2://%s/%s", self._bucket_name, bucket_path)
        self._client.delete_object(
            Bucket=self._bucket_name,
            Key=bucket_path,
        )

    def file_exists(self, bucket_path: str) -> bool:
        """Check if a file exists in R2.

        Args:
            bucket_path: Object key within the bucket.

        Returns:
            True if the object exists, False otherwise.
        """
        try:
            self._client.head_object(
                Bucket=self._bucket_name,
                Key=bucket_path,
            )
            return True
        except ClientError:
            return False
