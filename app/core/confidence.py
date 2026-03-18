"""
CV Confidence Scorer — Rates crop quality 0-100.

Analyzes 5 signals to determine how confident the CV engine is about a crop:
  1. Contour area ratio (is the crop 85-99% of original?)
  2. Aspect ratio match (standard photo ratios: 4:3, 3:2, 16:9, 1:1)
  3. Edge sharpness (gradient magnitude at crop boundary)
  4. Background uniformity (is the removed border flat/uniform?)
  5. Contour count (single dominant contour = unambiguous)

Used by the main crop engine to route images into confidence tiers.
"""

import cv2
import numpy as np


# Standard photo aspect ratios (width/height, both orientations)
STANDARD_RATIOS = [
    4 / 3, 3 / 4,
    3 / 2, 2 / 3,
    16 / 9, 9 / 16,
    5 / 4, 4 / 5,
    1.0,
]
RATIO_TOLERANCE = 0.12  # ±12% match window


def _score_area_ratio(original_img, cropped_img):
    """
    Score based on how much area the crop retains.
    Sweet spot: 85-99% of original (clear border removal).
    Too aggressive (<70%) or too conservative (>99.5%) = low confidence.
    """
    orig_h, orig_w = original_img.shape[:2]
    crop_h, crop_w = cropped_img.shape[:2]

    ratio = (crop_w * crop_h) / (orig_w * orig_h)

    if 0.85 <= ratio <= 0.99:
        return 30  # Perfect sweet spot
    elif 0.75 <= ratio < 0.85:
        return 20  # Moderate removal, still plausible
    elif 0.70 <= ratio < 0.75:
        return 10  # Aggressive, lower confidence
    elif ratio > 0.99:
        return 15  # Almost no change, probably fine but trivial
    else:
        return 0   # Very aggressive, suspicious


def _score_aspect_ratio(cropped_img):
    """
    Score based on whether the crop matches standard photo aspect ratios.
    Standard ratios suggest a well-detected photo boundary.
    """
    h, w = cropped_img.shape[:2]
    if h == 0:
        return 0

    crop_ratio = w / h

    for target in STANDARD_RATIOS:
        if abs(crop_ratio - target) / target <= RATIO_TOLERANCE:
            return 20

    # Not a standard ratio, but might still be valid
    return 8


def _score_edge_sharpness(original_img, crop_box):
    """
    Score based on gradient magnitude at the crop boundary.
    Sharp edges = clear physical photo border = high confidence.
    Weak edges = unclear boundary = low confidence.
    """
    x, y, w, h = crop_box
    gray = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY)
    orig_h, orig_w = gray.shape[:2]

    # Sample gradient along each crop edge (3px band)
    band = 3
    gradients = []

    # Top edge
    if y > band:
        top_band = gray[max(0, y - band):y + band, x:x + w]
        if top_band.size > 0:
            grad = np.mean(np.abs(np.diff(top_band.astype(np.float32), axis=0)))
            gradients.append(grad)

    # Bottom edge
    if y + h < orig_h - band:
        bot_band = gray[y + h - band:min(orig_h, y + h + band), x:x + w]
        if bot_band.size > 0:
            grad = np.mean(np.abs(np.diff(bot_band.astype(np.float32), axis=0)))
            gradients.append(grad)

    # Left edge
    if x > band:
        left_band = gray[y:y + h, max(0, x - band):x + band]
        if left_band.size > 0:
            grad = np.mean(np.abs(np.diff(left_band.astype(np.float32), axis=1)))
            gradients.append(grad)

    # Right edge
    if x + w < orig_w - band:
        right_band = gray[y:y + h, x + w - band:min(orig_w, x + w + band)]
        if right_band.size > 0:
            grad = np.mean(np.abs(np.diff(right_band.astype(np.float32), axis=1)))
            gradients.append(grad)

    if not gradients:
        return 5

    avg_gradient = np.mean(gradients)

    # Higher gradient = sharper edge = higher confidence
    if avg_gradient > 15:
        return 20
    elif avg_gradient > 8:
        return 14
    elif avg_gradient > 3:
        return 8
    else:
        return 3


def _score_background_uniformity(original_img, crop_box):
    """
    Score based on how uniform the removed border region is.
    Uniform border = scanner bed = high confidence.
    Textured border = might be photo content = low confidence.
    """
    x, y, w, h = crop_box
    orig_h, orig_w = original_img.shape[:2]
    gray = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # Collect pixels from the border regions (outside the crop box)
    border_pixels = []

    # Top border
    if y > 5:
        border_pixels.append(gray[0:y, :].flatten())
    # Bottom border
    if y + h < orig_h - 5:
        border_pixels.append(gray[y + h:orig_h, :].flatten())
    # Left border
    if x > 5:
        border_pixels.append(gray[y:y + h, 0:x].flatten())
    # Right border
    if x + w < orig_w - 5:
        border_pixels.append(gray[y:y + h, x + w:orig_w].flatten())

    if not border_pixels:
        return 5

    all_border = np.concatenate(border_pixels)
    if all_border.size < 100:
        return 5

    variance = np.var(all_border)

    # Low variance = uniform background = scanner bed
    if variance < 200:
        return 15  # Very uniform
    elif variance < 800:
        return 10  # Mostly uniform
    elif variance < 2000:
        return 5   # Some texture
    else:
        return 0   # Highly textured -- suspicious


def _score_contour_count(contour_count):
    """
    Score based on the number of contours found.
    Single dominant contour = clear, unambiguous detection.
    Multiple = confusion about photo boundaries.
    """
    if contour_count == 1:
        return 15
    elif contour_count == 2:
        return 10
    elif contour_count <= 4:
        return 5
    else:
        return 0


def compute_confidence(original_img, cropped_img, crop_box, contour_count=1):
    """
    Compute a 0-100 confidence score for a proposed crop.

    Args:
        original_img: Original BGR image (numpy array)
        cropped_img: Proposed cropped BGR image (numpy array)
        crop_box: Tuple (x, y, w, h) of the crop region in original image
        contour_count: Number of significant contours detected

    Returns:
        int: Confidence score 0-100
    """
    if cropped_img is None or crop_box is None:
        return 0

    score = 0
    score += _score_area_ratio(original_img, cropped_img)
    score += _score_aspect_ratio(cropped_img)
    score += _score_edge_sharpness(original_img, crop_box)
    score += _score_background_uniformity(original_img, crop_box)
    score += _score_contour_count(contour_count)

    return min(100, max(0, score))
