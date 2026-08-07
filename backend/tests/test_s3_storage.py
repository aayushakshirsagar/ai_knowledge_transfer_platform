import os
import tempfile
from unittest.mock import Mock

from app.storage.s3_storage import S3StorageService


def test_upload_file_returns_key_and_uploads_to_s3() -> None:
    fake_client = Mock()
    service = S3StorageService(bucket_name="test-bucket", client=fake_client)

    with tempfile.NamedTemporaryFile("wb", delete=False) as handle:
        handle.write(b"hello world")
        temp_path = handle.name

    try:
        key = service.upload_file(local_path=temp_path, project_id="project-1", document_id="document-1")
    finally:
        os.unlink(temp_path)

    assert key.startswith("projects/project-1/documents/document-1/")
    fake_client.put_object.assert_called_once()
    assert fake_client.put_object.call_args.kwargs["Bucket"] == "test-bucket"
    assert fake_client.put_object.call_args.kwargs["Key"] == key


def test_get_signed_url_returns_presigned_url() -> None:
    fake_client = Mock()
    fake_client.generate_presigned_url.return_value = "https://signed-url.example"
    service = S3StorageService(bucket_name="test-bucket", client=fake_client)

    url = service.get_signed_url("some/key", expiry_seconds=120)

    assert url == "https://signed-url.example"
    fake_client.generate_presigned_url.assert_called_once_with(
        ClientMethod="get_object",
        Params={"Bucket": "test-bucket", "Key": "some/key"},
        ExpiresIn=120,
    )
