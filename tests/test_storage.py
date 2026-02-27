"""Tests for R2 storage client."""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.storage.r2 import R2StorageClient


@pytest.fixture
def mock_settings():
    """Mock settings with R2 configuration."""
    settings = MagicMock()
    settings.r2_account_id = "test-account-id"
    settings.r2_access_key_id = "test-access-key"
    settings.r2_secret_access_key = "test-secret-key"
    settings.r2_bucket_name = "test-bucket"
    return settings


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 S3 client."""
    with patch("app.storage.r2.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        yield mock_client


@pytest.fixture
def r2_client(mock_settings, mock_boto3_client):
    """R2StorageClient with mocked dependencies."""
    with patch("app.storage.r2.get_settings", return_value=mock_settings):
        client = R2StorageClient()
    return client


def test_r2_client_initialization(mock_settings):
    """Test that R2 client initializes with correct endpoint."""
    with patch("app.storage.r2.get_settings", return_value=mock_settings):
        with patch("app.storage.r2.boto3") as mock_boto3:
            client = R2StorageClient()
            mock_boto3.client.assert_called_once()
            call_kwargs = mock_boto3.client.call_args
            assert call_kwargs[1]["endpoint_url"] == "https://test-account-id.r2.cloudflarestorage.com"
            assert call_kwargs[1]["aws_access_key_id"] == "test-access-key"
            assert call_kwargs[1]["aws_secret_access_key"] == "test-secret-key"


def test_r2_client_custom_params():
    """Test that R2 client accepts custom parameters."""
    with patch("app.storage.r2.get_settings") as mock_get:
        mock_get.return_value = MagicMock(
            r2_account_id="default-id",
            r2_access_key_id="default-key",
            r2_secret_access_key="default-secret",
            r2_bucket_name="default-bucket",
        )
        with patch("app.storage.r2.boto3"):
            client = R2StorageClient(
                account_id="custom-id",
                access_key_id="custom-key",
                secret_access_key="custom-secret",
                bucket_name="custom-bucket",
            )
            assert client.bucket_name == "custom-bucket"


def test_upload_file(r2_client, mock_boto3_client):
    """Test file upload."""
    result = r2_client.upload_file("reports/test/report.pdf", b"fake-pdf-content")

    mock_boto3_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="reports/test/report.pdf",
        Body=b"fake-pdf-content",
        ContentType="application/pdf",
    )
    assert result == "reports/test/report.pdf"


def test_upload_file_custom_content_type(r2_client, mock_boto3_client):
    """Test file upload with custom content type."""
    r2_client.upload_file("data/test.json", b'{"key": "value"}', content_type="application/json")

    mock_boto3_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="data/test.json",
        Body=b'{"key": "value"}',
        ContentType="application/json",
    )


def test_get_signed_url(r2_client, mock_boto3_client):
    """Test pre-signed URL generation."""
    mock_boto3_client.generate_presigned_url.return_value = "https://signed-url.example.com/report.pdf"

    url = r2_client.get_signed_url("reports/test/report.pdf", expires_in=1800)

    mock_boto3_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "reports/test/report.pdf"},
        ExpiresIn=1800,
    )
    assert url == "https://signed-url.example.com/report.pdf"


def test_get_signed_url_default_expiry(r2_client, mock_boto3_client):
    """Test pre-signed URL with default 1-hour expiry."""
    mock_boto3_client.generate_presigned_url.return_value = "https://signed-url.example.com/report.pdf"

    r2_client.get_signed_url("reports/test/report.pdf")

    call_kwargs = mock_boto3_client.generate_presigned_url.call_args
    assert call_kwargs[1]["ExpiresIn"] == 3600


def test_download_file(r2_client, mock_boto3_client):
    """Test file download."""
    mock_body = MagicMock()
    mock_body.read.return_value = b"downloaded-content"
    mock_boto3_client.get_object.return_value = {"Body": mock_body}

    data = r2_client.download_file("reports/test/report.pdf")

    mock_boto3_client.get_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="reports/test/report.pdf",
    )
    assert data == b"downloaded-content"


def test_delete_file(r2_client, mock_boto3_client):
    """Test file deletion."""
    r2_client.delete_file("reports/test/report.pdf")

    mock_boto3_client.delete_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="reports/test/report.pdf",
    )


def test_file_exists_true(r2_client, mock_boto3_client):
    """Test file existence check — file exists."""
    mock_boto3_client.head_object.return_value = {"ContentLength": 1024}

    assert r2_client.file_exists("reports/test/report.pdf") is True


def test_file_exists_false(r2_client, mock_boto3_client):
    """Test file existence check — file does not exist."""
    from botocore.exceptions import ClientError

    mock_boto3_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}},
        "HeadObject",
    )

    assert r2_client.file_exists("reports/test/nonexistent.pdf") is False
