from io import BytesIO

import pytest
from PIL import Image

from gutcare.files.policy import allowed_upload, validate_file
from gutcare.shared.errors import Problem


def _jpeg() -> bytes:
    image = Image.new("RGB", (2, 2), (1, 2, 3))
    data = BytesIO()
    image.save(data, format="JPEG")
    return data.getvalue()


def test_valid_jpeg_is_decoded_and_hashed() -> None:
    content = _jpeg()
    result = validate_file(content, "image/jpeg", "record.jpg")
    assert result.size_bytes == len(content)
    assert len(result.content_sha256) == 64


def test_declared_mime_must_match_extension() -> None:
    with pytest.raises(Problem) as error:
        allowed_upload("application/pdf", "record.jpg", 128)
    assert error.value.status == 415


def test_image_must_have_expected_magic_and_decode() -> None:
    with pytest.raises(Problem) as error:
        validate_file(b"not an image", "image/jpeg", "record.jpg")
    assert error.value.status == 422


def test_file_type_specific_size_cap_is_enforced() -> None:
    with pytest.raises(Problem) as error:
        allowed_upload("image/png", "record.png", 10 * 1024 * 1024 + 1)
    assert error.value.status == 413
