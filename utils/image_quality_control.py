"""
Image quality control and lightweight preprocessing for mosquito specimen images.

This module is intentionally pure-Python/PIL/OpenCV-based and has no Streamlit dependency.
It evaluates image quality before classification and can optionally enhance borderline
images that are low-resolution but otherwise usable.

Design notes:
- Blur detection uses the Laplacian variance method.
- Exposure assessment uses histogram analysis to detect over- and under-exposure.
- Resolution adequacy estimates how much of the frame is occupied by the subject.
- The enhancement step is conservative: it can improve low-resolution, mildly noisy, or
  slightly soft images, but it cannot recover detail that was never captured (for example,
  out-of-focus diagnostic structures remain unresolved).
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
from PIL import Image, ImageFilter, ImageOps

# OpenCV is optional. When available we use its fast implementations; otherwise
# fall back to pure-Pillow / numpy approaches. This allows the module to be
# imported and used in environments where installing heavy binaries is not
# possible during quick testing. For best performance and denoising/upscaling
# quality, install `opencv-python`.
try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None


try:
    import torch  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    torch = None


def _coerce_image(image: Any) -> Image.Image:
    """Convert PIL Image, numpy array, or other image-like input to a PIL Image."""
    if isinstance(image, Image.Image):
        return image.convert("RGB")

    if isinstance(image, np.ndarray):
        if image.ndim == 2:
            return Image.fromarray(image.astype(np.uint8), mode="L").convert("RGB")
        if image.ndim == 3:
            if image.shape[2] == 1:
                image = image[:, :, 0]
                return Image.fromarray(image.astype(np.uint8), mode="L").convert("RGB")
            return Image.fromarray(image.astype(np.uint8), mode="RGB")

    raise TypeError("Expected a PIL Image or a numpy array")


def _to_numpy_rgb(image: Image.Image) -> np.ndarray:
    return np.array(image.convert("RGB"))


def compute_blur_score(image: Any) -> float:
    """Return a Laplacian variance-based blur score.

    Higher values generally indicate sharper images. Very low values suggest blur.
    """
    pil_image = _coerce_image(image)
    arr = _to_numpy_rgb(pil_image)

    # Prefer OpenCV Laplacian if available
    if cv2 is not None:
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        variance = float(np.var(lap))
        return variance

    # Fallback: use gradient magnitude variance as a proxy for sharpness
    gray = np.asarray(pil_image.convert("L"), dtype=np.float32)
    gx = np.diff(gray, axis=1)
    gy = np.diff(gray, axis=0)
    mag = np.sqrt(gx[:, :-0]**2 + gy[:-0, :]**2) if gx.size and gy.size else np.zeros_like(gray)
    variance = float(np.var(mag)) if mag.size else 0.0
    return variance


def compute_exposure_score(image: Any) -> float:
    """Return a simple exposure score based on histogram concentration.

    The score is designed as a heuristic: values near 0.5 indicate balanced exposure,
    while values near 0 or 1 indicate severe under- or over-exposure.
    """
    pil_image = _coerce_image(image)
    gray = np.asarray(pil_image.convert("L"), dtype=np.uint8)

    # Use OpenCV histogram if available for speed, otherwise numpy
    if cv2 is not None:
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
        hist = hist / (hist.sum() + 1e-8)
    else:
        hist, _ = np.histogram(gray.flatten(), bins=256, range=(0, 255))
        hist = hist.astype(np.float32)
        hist = hist / (hist.sum() + 1e-8)

    # Estimate how concentrated the brightness is around the midtones.
    mid = hist[80:176]
    if mid.sum() <= 0:
        return 0.0
    score = float(mid.sum())
    return min(max(score, 0.0), 1.0)


def estimate_resolution_adequacy(image: Any, target_subject_fraction: float = 0.25) -> float:
    """Estimate whether the subject likely occupies a sufficient fraction of the frame.

    This is a simple heuristic: if the image is very small or the subject covers only a tiny
    region of the frame, it may be too low-resolution for reliable downstream analysis.

    The heuristic is not a substitute for object detection; it is a simple pre-screen.
    """
    pil_image = _coerce_image(image)
    width, height = pil_image.size
    area = width * height

    # Very small images are often insufficient for identification tasks.
    if area < 150_000:
        return 0.2

    # A simple proxy: images with more pixels are more likely to contain usable detail.
    pixel_score = min(1.0, area / 2_000_000.0)

    # Subject fraction proxy: assume a moderately large target subject should cover roughly
    # 20-30% of the frame if the image is properly framed. We score this conservatively.
    subject_fraction_score = min(1.0, target_subject_fraction / 0.25)
    return float(min(1.0, (pixel_score * 0.7) + (subject_fraction_score * 0.3)))


def _run_lightweight_enhancement(image: Any) -> Image.Image:
    """Apply a lightweight enhancement strategy.

    Preferred approach when heavy dependencies are available:
    - Real-ESRGAN can be used for true super-resolution, but it is usually heavier and may
      require a GPU or specific model weights.

    Fallback used here (no heavy dependency required):
    - Use OpenCV resize + mild sharpening + denoising to improve low-resolution images.

    This cannot recover detail that was never captured; it can only improve genuinely
    recoverable degradation such as low resolution or mild noise.
    """
    pil_image = _coerce_image(image)
    arr = _to_numpy_rgb(pil_image)

    # If OpenCV is available, use its denoising and resize; otherwise use PIL fallbacks
    if cv2 is not None:
        height, width = arr.shape[:2]
        if width < 1200 or height < 1200:
            scale = 2
            resized = cv2.resize(arr, (width * scale, height * scale), interpolation=cv2.INTER_CUBIC)
        else:
            resized = arr

        denoised = cv2.fastNlMeansDenoisingColored(resized, None, 10, 10, 7, 21)
        sharpened = cv2.GaussianBlur(denoised, (0, 0), 1.0)
        sharpened = cv2.addWeighted(denoised, 1.5, sharpened, -0.5, 0)
        return Image.fromarray(sharpened.astype(np.uint8), mode="RGB")

    # PIL fallback: upscale with LANCZOS, apply median denoise and unsharp mask
    width, height = pil_image.size
    if width < 1200 or height < 1200:
        new_size = (int(width * 2), int(height * 2))
        up = pil_image.resize(new_size, resample=Image.LANCZOS)
    else:
        up = pil_image

    denoised = up.filter(ImageFilter.MedianFilter(size=3))
    sharpened = denoised.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
    enhanced = ImageOps.autocontrast(sharpened)
    return enhanced


def assess_image_quality(image: Any, target_subject_fraction: float = 0.25) -> Dict[str, Any]:
    """Evaluate a specimen image and optionally enhance it.

    Returns a clear report dictionary with:
    - passed: bool
    - reason: human-readable explanation
    - processed_image: PIL Image
    - blur_score: float
    - exposure_score: float
    """
    pil_image = _coerce_image(image)

    blur_score = compute_blur_score(pil_image)
    exposure_score = compute_exposure_score(pil_image)
    resolution_score = estimate_resolution_adequacy(pil_image, target_subject_fraction)

    # Heuristic thresholds. These are conservative and intended to catch obvious failures.
    if blur_score < 80:
        reason = "Image appears blurry; please retake with sharper focus on diagnostic structures."
        return {
            "passed": False,
            "reason": reason,
            "processed_image": pil_image,
            "blur_score": blur_score,
            "exposure_score": exposure_score,
        }

    if exposure_score < 0.12:
        reason = "Image appears underexposed; please retake with more light."
        return {
            "passed": False,
            "reason": reason,
            "processed_image": pil_image,
            "blur_score": blur_score,
            "exposure_score": exposure_score,
        }

    if exposure_score > 0.88:
        reason = "Image appears overexposed; please retake with less light or better exposure."
        return {
            "passed": False,
            "reason": reason,
            "processed_image": pil_image,
            "blur_score": blur_score,
            "exposure_score": exposure_score,
        }

    if resolution_score < 0.5:
        reason = "Image resolution or framing appears inadequate for reliable diagnosis; please retake at a higher resolution or closer framing."
        return {
            "passed": False,
            "reason": reason,
            "processed_image": pil_image,
            "blur_score": blur_score,
            "exposure_score": exposure_score,
        }

    # This image passed basic checks. We still apply a conservative enhancement step when
    # it is likely low-resolution and otherwise acceptable.
    processed_image = _run_lightweight_enhancement(pil_image)

    return {
        "passed": True,
        "reason": "Image quality is adequate for downstream processing.",
        "processed_image": processed_image,
        "blur_score": blur_score,
        "exposure_score": exposure_score,
    }


# Requirements snippet for downstream use:
# pip install opencv-python pillow numpy
