"""
Pre-Commit Crop Validators — Catch data loss BEFORE saving.

Three independent validators that inspect a proposed crop:
  1. Edge Pixel Analysis: checks if border pixels have texture (= content, not border)
  2. Histogram Comparison: compares color distribution of border vs. kept region
  3. Face Detection Guard: rejects crops that cut into detected faces

Each validator returns (is_safe, reason).
validate_crop() runs all three and returns a combined verdict.
"""

import cv2
import numpy as np
import os


# ---------------------------------------------------------------------------
# Thresholds (tunable)
# ---------------------------------------------------------------------------
EDGE_VARIANCE_THRESHOLD = 500       # Border variance above this = content, not scanner bed
HISTOGRAM_CORRELATION_MIN = 0.70    # Border vs content correlation above this = too similar
FACE_MARGIN_PX = 10                 # Extra px around face box for safety


# ---------------------------------------------------------------------------
# 1. Edge Pixel Analysis
# ---------------------------------------------------------------------------
def _validate_edge_pixels(original_img, crop_box):
    """
    Check if the border region being removed looks like content or scanner bed.
    High variance in border = we might be cutting into the photo.

    Returns: (is_safe: bool, reason: str)
    """
    x, y, w, h = crop_box
    orig_h, orig_w = original_img.shape[:2]
    gray = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    variances = []

    # Measure variance of each border strip (the parts being removed)
    # Top border
    if y > 5:
        top_strip = gray[0:y, x:x + w]
        if top_strip.size > 50:
            variances.append(np.var(top_strip))

    # Bottom border
    if y + h < orig_h - 5:
        bot_strip = gray[y + h:orig_h, x:x + w]
        if bot_strip.size > 50:
            variances.append(np.var(bot_strip))

    # Left border
    if x > 5:
        left_strip = gray[y:y + h, 0:x]
        if left_strip.size > 50:
            variances.append(np.var(left_strip))

    # Right border
    if x + w < orig_w - 5:
        right_strip = gray[y:y + h, x + w:orig_w]
        if right_strip.size > 50:
            variances.append(np.var(right_strip))

    if not variances:
        # No significant border being removed
        return True, "no_border_removal"

    max_variance = max(variances)

    if max_variance > EDGE_VARIANCE_THRESHOLD:
        return False, "border_has_content"

    return True, "border_is_uniform"


# ---------------------------------------------------------------------------
# 2. Histogram Comparison
# ---------------------------------------------------------------------------
def _validate_histogram(original_img, crop_box):
    """
    Compare color histograms of border region vs. kept content.
    If they look too similar, the border might actually be part of the photo.

    Returns: (is_safe: bool, reason: str)
    """
    x, y, w, h = crop_box
    orig_h, orig_w = original_img.shape[:2]

    # Extract kept region and border region
    kept = original_img[y:y + h, x:x + w]

    # Build border mask (everything outside crop box)
    border_mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
    border_mask[:, :] = 255
    border_mask[y:y + h, x:x + w] = 0

    # Count border pixels
    border_pixel_count = np.count_nonzero(border_mask)
    if border_pixel_count < 500:
        # Border too small to analyze meaningfully
        return True, "border_too_small"

    # Convert to HSV for better color comparison
    hsv_full = cv2.cvtColor(original_img, cv2.COLOR_BGR2HSV)
    hsv_kept = cv2.cvtColor(kept, cv2.COLOR_BGR2HSV)

    # Compute histograms
    hist_border = cv2.calcHist(
        [hsv_full], [0, 1], border_mask,
        [30, 32], [0, 180, 0, 256]
    )
    cv2.normalize(hist_border, hist_border)

    hist_kept = cv2.calcHist(
        [hsv_kept], [0, 1], None,
        [30, 32], [0, 180, 0, 256]
    )
    cv2.normalize(hist_kept, hist_kept)

    # Compare using correlation (1.0 = identical)
    correlation = cv2.compareHist(hist_border, hist_kept, cv2.HISTCMP_CORREL)

    if correlation > HISTOGRAM_CORRELATION_MIN:
        return False, "border_matches_content"

    return True, "border_differs_from_content"


# ---------------------------------------------------------------------------
# 3. Face Detection Guard
# ---------------------------------------------------------------------------
# Use OpenCV's built-in Haar cascade (ships with opencv-python)
_face_cascade = None


def _get_face_cascade():
    """Lazy-load the face cascade classifier."""
    global _face_cascade
    if _face_cascade is None:
        cascade_path = os.path.join(
            cv2.data.haarcascades,
            "haarcascade_frontalface_default.xml"
        )
        _face_cascade = cv2.CascadeClassifier(cascade_path)
    return _face_cascade


def _validate_faces(original_img, crop_box):
    """
    Detect faces in the original image. If any face would be partially
    cut by the proposed crop, reject it.

    Returns: (is_safe: bool, reason: str, face_count: int)
    """
    x, y, w, h = crop_box
    gray = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY)
    orig_h, orig_w = gray.shape[:2]

    cascade = _get_face_cascade()

    # Detect faces (scale down large images for speed)
    scale = 1.0
    detect_img = gray
    if max(orig_h, orig_w) > 2000:
        scale = 1000 / max(orig_h, orig_w)
        detect_img = cv2.resize(gray, None, fx=scale, fy=scale)

    faces = cascade.detectMultiScale(
        detect_img,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(20, 20),
    )

    if len(faces) == 0:
        return True, "no_faces_detected", 0

    # Scale face coordinates back to original size
    face_count = len(faces)
    for (fx, fy, fw, fh) in faces:
        # Scale back
        fx = int(fx / scale)
        fy = int(fy / scale)
        fw = int(fw / scale)
        fh = int(fh / scale)

        # Add safety margin around face
        fx_start = fx - FACE_MARGIN_PX
        fy_start = fy - FACE_MARGIN_PX
        fx_end = fx + fw + FACE_MARGIN_PX
        fy_end = fy + fh + FACE_MARGIN_PX

        # Check if any part of the face (with margin) falls outside the crop box
        face_cut = False
        if fx_start < x:  # Face extends past left crop edge
            face_cut = True
        if fy_start < y:  # Face extends past top crop edge
            face_cut = True
        if fx_end > x + w:  # Face extends past right crop edge
            face_cut = True
        if fy_end > y + h:  # Face extends past bottom crop edge
            face_cut = True

        if face_cut:
            return False, "face_would_be_cut", face_count

    return True, "faces_inside_crop", face_count


# ---------------------------------------------------------------------------
# Combined Validator
# ---------------------------------------------------------------------------
def validate_crop(original_img, cropped_img, crop_box):
    """
    Run all validators on a proposed crop.

    Args:
        original_img: Original BGR image (numpy array)
        cropped_img: Proposed cropped BGR image (numpy array)
        crop_box: Tuple (x, y, w, h) of the crop in original coordinates

    Returns:
        tuple: (is_safe, reason, details_dict)
            is_safe: True if all validators pass
            reason: Human-readable reason for rejection (or "all_clear")
            details_dict: Per-validator results for logging/display
    """
    if cropped_img is None or crop_box is None:
        return True, "no_crop_proposed", {}

    details = {}

    # 1. Edge pixel analysis
    edge_safe, edge_reason = _validate_edge_pixels(original_img, crop_box)
    details["edge_pixels"] = {"passed": edge_safe, "reason": edge_reason}

    # 2. Histogram comparison
    hist_safe, hist_reason = _validate_histogram(original_img, crop_box)
    details["histogram"] = {"passed": hist_safe, "reason": hist_reason}

    # 3. Face detection
    face_safe, face_reason, face_count = _validate_faces(original_img, crop_box)
    details["face_detection"] = {
        "passed": face_safe,
        "reason": face_reason,
        "faces_found": face_count,
    }

    # Overall verdict: ALL must pass
    if not face_safe:
        return False, face_reason, details
    if not edge_safe:
        return False, edge_reason, details
    if not hist_safe:
        return False, hist_reason, details

    return True, "all_clear", details
