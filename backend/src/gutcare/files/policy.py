"""Server-side file type, size and integrity validation."""

import warnings
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from gutcare.shared.errors import Problem

MIB = 1024 * 1024
PDF_LIMIT = 20 * MIB
IMAGE_LIMIT = 10 * MIB
MAX_IMAGE_PIXELS = 40_000_000

_ALLOWED = {
    "application/pdf": {".pdf": (b"%PDF-", PDF_LIMIT)},
    "image/jpeg": {".jpg": (b"\xff\xd8\xff", IMAGE_LIMIT), ".jpeg": (b"\xff\xd8\xff", IMAGE_LIMIT)},
    "image/png": {".png": (b"\x89PNG\r\n\x1a\n", IMAGE_LIMIT)},
}


@dataclass(frozen=True, slots=True)
class ValidatedFile:
    content_type: str
    size_bytes: int
    content_sha256: str


def allowed_upload(content_type: str, filename: str, size_bytes: int) -> None:
    normalized_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    extension = PurePath(filename).suffix.lower()
    type_rules = _ALLOWED.get(normalized_type)
    if type_rules is None or extension not in type_rules:
        raise Problem(415, "UNSUPPORTED_MEDIA_TYPE", "Unsupported file type")
    if size_bytes <= 0 or size_bytes > type_rules[extension][1]:
        raise Problem(413, "FILE_SIZE_LIMIT_EXCEEDED", "File size limit exceeded")


def validate_file(content: bytes, declared_type: str, filename: str) -> ValidatedFile:
    allowed_upload(declared_type, filename, len(content))
    normalized_type = declared_type.split(";", maxsplit=1)[0].strip().lower()
    extension = PurePath(filename).suffix.lower()
    magic, _ = _ALLOWED[normalized_type][extension]
    if not content.startswith(magic):
        raise Problem(422, "FILE_CONTENT_MISMATCH", "File content does not match its type")

    try:
        if normalized_type == "application/pdf":
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted or len(reader.pages) == 0:
                raise ValueError("encrypted or empty PDF")
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as image:
                    if image.format != ("JPEG" if normalized_type == "image/jpeg" else "PNG"):
                        raise ValueError("image format mismatch")
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise ValueError("image dimensions exceed limit")
                    image.verify()
                with Image.open(BytesIO(content)) as image:
                    image.load()
    except (Exception, UnidentifiedImageError) as exc:
        raise Problem(422, "FILE_UNREADABLE", "File is damaged, encrypted, or unreadable") from exc

    return ValidatedFile(normalized_type, len(content), sha256(content).hexdigest())
