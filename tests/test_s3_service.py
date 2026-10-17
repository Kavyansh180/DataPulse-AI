import pytest
from unittest.mock import patch, MagicMock
from app.services.s3_service import S3Service
from app.api.errors import APIError
from app.core.config import get_settings


def test_generate_safe_object_key():
    """Verify safe S3 object key generation prevents path traversal."""
    unsafe_filename = "../../secrets/../../malicious_file.csv"
    key = S3Service.generate_safe_object_key(dataset_id=42, original_filename=unsafe_filename)

    assert key.startswith("datasets/42/")
    assert ".." not in key
    assert "/" not in key.replace("datasets/42/", "")
    assert key.endswith(".csv")


def test_s3_not_configured_raises_error():
    """Verify attempting S3 upload without S3_BUCKET_NAME raises 503 S3_NOT_CONFIGURED."""
    settings = get_settings()
    with patch.object(settings, "S3_BUCKET_NAME", None):
        with pytest.raises(APIError) as exc_info:
            S3Service.upload_file_bytes(b"col1,col2\n1,2\n", "datasets/1/test.csv")
        assert exc_info.value.status_code == 503
        assert exc_info.value.code == "S3_NOT_CONFIGURED"


def test_s3_upload_success_mocked():
    """Verify successful upload returns canonical s3:// URI when S3 client succeeds."""
    mock_boto_client = MagicMock()
    mock_boto_client.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

    settings = get_settings()
    with patch.object(settings, "S3_BUCKET_NAME", "datapulse-test-bucket"):
        with patch.object(S3Service, "get_client", return_value=mock_boto_client):
            uri = S3Service.upload_file_bytes(
                file_bytes=b"id,name\n1,test\n",
                object_key="datasets/10/test.csv",
            )
            assert uri == "s3://datapulse-test-bucket/datasets/10/test.csv"
            mock_boto_client.put_object.assert_called_once_with(
                Bucket="datapulse-test-bucket",
                Key="datasets/10/test.csv",
                Body=b"id,name\n1,test\n",
                ContentType="text/csv",
            )


def test_s3_upload_failure_mocked():
    """Verify S3 upload error raises 502 S3_UPLOAD_FAILED without exposing internal secrets."""
    mock_boto_client = MagicMock()
    mock_boto_client.put_object.side_effect = Exception("AWS Access Denied (Simulated)")

    settings = get_settings()
    with patch.object(settings, "S3_BUCKET_NAME", "datapulse-test-bucket"):
        with patch.object(S3Service, "get_client", return_value=mock_boto_client):
            with pytest.raises(APIError) as exc_info:
                S3Service.upload_file_bytes(b"id,val\n1,2", "datasets/5/fail.csv")
            assert exc_info.value.status_code == 502
            assert exc_info.value.code == "S3_UPLOAD_FAILED"


def test_s3_download_success_mocked():
    """Verify successful download returns raw bytes."""
    mock_body = MagicMock()
    mock_body.read.return_value = b"id,val\n10,20\n"

    mock_boto_client = MagicMock()
    mock_boto_client.get_object.return_value = {"Body": mock_body}

    settings = get_settings()
    with patch.object(settings, "S3_BUCKET_NAME", "my-bucket"):
        with patch.object(S3Service, "get_client", return_value=mock_boto_client):
            data = S3Service.download_file_bytes("s3://my-bucket/datasets/1/data.csv")
            assert data == b"id,val\n10,20\n"
            mock_boto_client.get_object.assert_called_once_with(
                Bucket="my-bucket",
                Key="datasets/1/data.csv",
            )
