"""Image preprocessing pipeline for OCR.
Validates file format and size, computes SHA-256 hash, and generates
preprocessed variants (grayscale denoised and adaptive threshold).
"""
import hashlib
from pathlib import Path
import cv2
import numpy as np

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def preprocess(image_bytes: bytes, filename: str) -> dict:
    """Preprocess image bytes for OCR extraction.
    Validates file extension and size limit.
    Computes SHA-256 hash.
    Generates grayscale denoised and adaptive threshold variants.

    Returns:
    {
        "image_hash": str,
        "variants": {
            "gray": np.ndarray,
            "thresh": np.ndarray
        }
    }
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Invalid file extension '{ext}'. Only PNG, JPG, and JPEG are supported.")

    if len(image_bytes) > MAX_FILE_SIZE:
        raise ValueError(f"File size ({len(image_bytes)} bytes) exceeds the 5 MB maximum limit.")

    # SHA-256 of raw bytes
    image_hash = hashlib.sha256(image_bytes).hexdigest()

    # Decode bytes with OpenCV
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image: file bytes are corrupt or not a valid image.")

    h, w = img.shape[:2]
    # Upscale 2x if width < 1000 px for improved OCR character resolution
    if w < 1000:
        img = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Denoise using non-local means denoising
    denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

    # Adaptive threshold
    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )

    return {
        "image_hash": image_hash,
        "variants": {
            "gray": denoised,
            "thresh": thresh,
        },
    }

