"""
Scan Auto-Crop Engine — Production-Grade Image Cropper
Refactored from batch_crop_pro.py

5-Tier Fallback Strategy:
  1. Otsu + Morphological Close + RETR_EXTERNAL (primary)
  2. Canny Edge Detection (snow/white photos)
  3. Variance-based Detection (stubborn cases)
  4. Saturation-based Detection (color cast detection)
  5. Gradient Line Scan (physical edge detection)

Core Insight: "Detect the background, not the photo."
"""

import os
import cv2
import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
# Strategy 1: Canny Edge Detection (Fallback for snow/white photos)
# ---------------------------------------------------------------------------
def _canny_edge_crop(img):
    h, w = img.shape[:2]
    image_area = h * w

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    edges = cv2.Canny(blur, 30, 100)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    margin = 10
    dilated[0:margin, :] = 0
    dilated[-margin:, :] = 0
    dilated[:, 0:margin] = 0
    dilated[:, -margin:] = 0

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None, "no_edges"

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)

    if area < 0.1 * image_area:
        return None, "edge_too_small"

    x, y, cw, ch = cv2.boundingRect(largest)

    if (cw * ch) / image_area > 0.95:
        return None, "no_border"

    return img[y:y+ch, x:x+cw], "canny_edge"


# ---------------------------------------------------------------------------
# Strategy 2: Variance-based Detection
# ---------------------------------------------------------------------------
def _variance_based_crop(img):
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    kernel_size = 15
    mean = cv2.blur(gray.astype(np.float32), (kernel_size, kernel_size))
    sqr_mean = cv2.blur((gray.astype(np.float32))**2, (kernel_size, kernel_size))
    variance = sqr_mean - mean**2

    var_mask = (variance > 50).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    var_mask = cv2.morphologyEx(var_mask, cv2.MORPH_CLOSE, kernel)
    var_mask = cv2.morphologyEx(var_mask, cv2.MORPH_OPEN, kernel)

    margin = 10
    var_mask[0:margin, :] = 0
    var_mask[-margin:, :] = 0
    var_mask[:, 0:margin] = 0
    var_mask[:, -margin:] = 0

    coords = cv2.findNonZero(var_mask)
    if coords is None:
        return None, "no_variance"

    x, y, cw, ch = cv2.boundingRect(coords)

    area_ratio = (cw * ch) / (h * w)
    if area_ratio < 0.1 or area_ratio > 0.95:
        return None, "var_invalid"

    return img[y:y+ch, x:x+cw], "variance"


# ---------------------------------------------------------------------------
# Strategy 3: Saturation-based Detection
# ---------------------------------------------------------------------------
def _saturation_based_crop(img):
    h, w = img.shape[:2]

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]

    sat_mask = (saturation > 5).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    sat_mask = cv2.morphologyEx(sat_mask, cv2.MORPH_CLOSE, kernel)
    sat_mask = cv2.morphologyEx(sat_mask, cv2.MORPH_OPEN, kernel)

    margin = 10
    sat_mask[0:margin, :] = 0
    sat_mask[-margin:, :] = 0
    sat_mask[:, 0:margin] = 0
    sat_mask[:, -margin:] = 0

    coords = cv2.findNonZero(sat_mask)
    if coords is None:
        return None, "no_saturation"

    x, y, cw, ch = cv2.boundingRect(coords)

    area_ratio = (cw * ch) / (h * w)
    if area_ratio < 0.1 or area_ratio > 0.95:
        return None, "sat_invalid"

    return img[y:y+ch, x:x+cw], "saturation"


# ---------------------------------------------------------------------------
# Strategy 4: Gradient Line Scan (FINAL FALLBACK)
# ---------------------------------------------------------------------------
def _gradient_line_scan(img):
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    grad_mag = np.sqrt(sobelx**2 + sobely**2)

    threshold = 20
    edges = (grad_mag > threshold).astype(np.float32)

    row_density = np.mean(edges, axis=1)
    col_density = np.mean(edges, axis=0)

    content_threshold = 0.02

    top = 0
    for i in range(h // 2):
        if row_density[i] > content_threshold:
            top = max(0, i - 5)
            break

    bottom = h - 1
    for i in range(h - 1, h // 2, -1):
        if row_density[i] > content_threshold:
            bottom = min(h - 1, i + 5)
            break

    left = 0
    for i in range(w // 2):
        if col_density[i] > content_threshold:
            left = max(0, i - 5)
            break

    right = w - 1
    for i in range(w - 1, w // 2, -1):
        if col_density[i] > content_threshold:
            right = min(w - 1, i + 5)
            break

    crop_area = (right - left) * (bottom - top)
    original_area = h * w

    ratio = crop_area / original_area
    if ratio < 0.1 or ratio > 0.95:
        return None, "grad_invalid"

    return img[top:bottom+1, left:right+1], "gradient"


# ---------------------------------------------------------------------------
# Main Crop Engine — 5-Tier Fallback
# ---------------------------------------------------------------------------
def crop_image(img):
    """
    Production-grade cropping with 5-tier fallback.
    
    Returns:
        tuple: (cropped_image_or_None, strategy_name)
    """
    h, w = img.shape[:2]
    image_area = h * w

    # --- TIER 1: Otsu + MorphClose + RETR_EXTERNAL ---
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # Edge clearing — break scanner noise tethering
    margin = 10
    closed[0:margin, :] = 0
    closed[-margin:, :] = 0
    closed[:, 0:margin] = 0
    closed[:, -margin:] = 0

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)

        if area >= 0.1 * image_area:
            peri = cv2.arcLength(largest, True)
            approx = cv2.approxPolyDP(largest, 0.02 * peri, True)

            if len(approx) == 4:
                x, y, cw, ch = cv2.boundingRect(approx)
                strategy = "pro_rect"
            else:
                x, y, cw, ch = cv2.boundingRect(largest)
                strategy = "pro_contour"

            if (cw * ch) / image_area < 0.95:
                return img[y:y+ch, x:x+cw], strategy

    # --- TIER 2: Canny Edge ---
    result, strategy = _canny_edge_crop(img)
    if result is not None:
        return result, strategy

    # --- TIER 3: Variance ---
    result, strategy = _variance_based_crop(img)
    if result is not None:
        return result, strategy

    # --- TIER 4: Saturation ---
    result, strategy = _saturation_based_crop(img)
    if result is not None:
        return result, strategy

    # --- TIER 5: Gradient ---
    result, strategy = _gradient_line_scan(img)
    if result is not None:
        return result, strategy

    return None, "no_crop_needed"


def process_single_image(input_path, output_path):
    """
    Process one image: crop and save at 100% JPEG quality.
    
    Returns:
        dict with keys: success, strategy, original_size, cropped_size, filename
    """
    filename = os.path.basename(input_path)
    img = cv2.imread(input_path)

    if img is None:
        return {
            "success": False,
            "strategy": "read_error",
            "filename": filename,
            "original_size": None,
            "cropped_size": None,
        }

    h, w = img.shape[:2]
    original_size = (w, h)

    try:
        cropped, strategy = crop_image(img)

        if cropped is not None:
            ch, cw = cropped.shape[:2]
            cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
            Image.fromarray(cropped_rgb).save(output_path, quality=100, subsampling=0)
            cropped_size = (cw, ch)
        else:
            # No crop needed — save original
            cv2.imwrite(output_path, img, [cv2.IMWRITE_JPEG_QUALITY, 100])
            cropped_size = original_size
            strategy = "original"

        return {
            "success": True,
            "strategy": strategy,
            "filename": filename,
            "original_size": original_size,
            "cropped_size": cropped_size,
        }

    except Exception:
        # Emergency fallback — save original
        cv2.imwrite(output_path, img, [cv2.IMWRITE_JPEG_QUALITY, 100])
        return {
            "success": True,
            "strategy": "error_fallback",
            "filename": filename,
            "original_size": original_size,
            "cropped_size": original_size,
        }


def batch_process(input_folder, output_folder=None):
    """
    Process all images in a folder.
    
    Args:
        input_folder: Path to folder with scanned images
        output_folder: Path to output (defaults to '{input_folder} - Cropped')
    
    Returns:
        list of result dicts from process_single_image
    """
    if output_folder is None:
        output_folder = input_folder.rstrip("/\\") + " - Cropped"

    os.makedirs(output_folder, exist_ok=True)

    valid_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff')
    files = [f for f in os.listdir(input_folder) if f.lower().endswith(valid_exts)]
    files.sort()

    results = []
    for filename in files:
        input_path = os.path.join(input_folder, filename)
        output_path = os.path.join(output_folder, filename)

        result = process_single_image(input_path, output_path)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python cropper.py <input_folder> [output_folder]")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Processing: {input_dir}")
    results = batch_process(input_dir, output_dir)

    # Statistics
    stats = {}
    for r in results:
        s = r["strategy"]
        stats[s] = stats.get(s, 0) + 1

    total = len(results)
    print(f"\n{'='*50}")
    print(f"BATCH RESULTS: {total} images")
    for s, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {s:15}: {count} ({count/total*100:4.1f}%)")
    print(f"{'='*50}")
