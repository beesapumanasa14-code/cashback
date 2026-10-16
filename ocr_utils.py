"""Local-only image validation and OCR helpers."""

from io import BytesIO

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_FORMATS = {"PNG", "JPEG"}


class OCRUnavailableError(RuntimeError):
    """OCR is not configured on this computer."""


def validate_image(data: bytes) -> str:
    """Validate image size and actual image content; return its detected format."""
    if not data:
        raise ValueError("The uploaded image is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be 5 MB or smaller.")
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        raise OCRUnavailableError("Image preview and validation require Pillow. Install the project requirements.") from None
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError):
        raise ValueError("The uploaded file is not a valid PNG or JPEG image.") from None
    if image_format not in ALLOWED_FORMATS:
        raise ValueError("Only PNG and JPEG screenshots are supported.")
    return image_format


def extract_text(data: bytes) -> str:
    """Run Tesseract OCR locally on a validated image."""
    validate_image(data)
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise OCRUnavailableError(
            "OCR needs Pillow and pytesseract. Install requirements, then install Tesseract OCR for Windows "
            "and add its installation folder to PATH. Manual text entry is still available."
        ) from None
    try:
        with Image.open(BytesIO(data)) as image:
            return pytesseract.image_to_string(image).strip()
    except pytesseract.pytesseract.TesseractNotFoundError:
        raise OCRUnavailableError(
            "Tesseract OCR is not installed or is missing from PATH. On Windows, install Tesseract OCR, "
            "restart your terminal, and continue with manual text entry in the meantime."
        ) from None
