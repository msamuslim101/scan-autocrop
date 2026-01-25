import os
import shutil
import cv2
import numpy as np
from PIL import Image

def canny_edge_crop(img):
    """
    Fallback Strategy for Snow/White Photos:
    Uses Canny edge detection to find the physical photo border.
    This works when thresholding fails due to similar intensity.
    """
    h, w = img.shape[:2]
    image_area = h * w
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Canny edge detection - finds physical edges regardless of fill color
    edges = cv2.Canny(blur, 30, 100)
    
    # Dilate to connect broken edges
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edges, kernel, iterations=2)
    
    # Clear edges (same logic as before)
    margin = 10
    dilated[0:margin, :] = 0
    dilated[-margin:, :] = 0
    dilated[:, 0:margin] = 0
    dilated[:, -margin:] = 0
    
    # Find contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None, "no_edges"
    
    # Find largest contour
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    
    if area < 0.1 * image_area:
        return None, "edge_too_small"
    
    x, y, cw, ch = cv2.boundingRect(largest)
    
    # Must remove a meaningful amount (at least 5% from any side)
    if (cw * ch) / image_area > 0.95:
        # Not enough border to remove
        return None, "no_border"
        
    return img[y:y+ch, x:x+cw], "canny_edge"

def variance_based_crop(img):
    """
    Fallback Strategy for stubborn snow photos:
    Uses local variance to detect photo content vs. blank scanner background.
    Scanner background has near-zero variance, photos have texture.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Calculate local variance using a sliding window
    kernel_size = 15
    mean = cv2.blur(gray.astype(np.float32), (kernel_size, kernel_size))
    sqr_mean = cv2.blur((gray.astype(np.float32))**2, (kernel_size, kernel_size))
    variance = sqr_mean - mean**2
    
    # Threshold: anything with variance > 50 is "texture" (i.e., photo content)
    var_mask = (variance > 50).astype(np.uint8) * 255
    
    # Clean up and close small holes
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    var_mask = cv2.morphologyEx(var_mask, cv2.MORPH_CLOSE, kernel)
    var_mask = cv2.morphologyEx(var_mask, cv2.MORPH_OPEN, kernel)
    
    # Clear edges
    margin = 10
    var_mask[0:margin, :] = 0
    var_mask[-margin:, :] = 0
    var_mask[:, 0:margin] = 0
    var_mask[:, -margin:] = 0
    
    # Find bounding box of all texture
    coords = cv2.findNonZero(var_mask)
    if coords is None:
        return None, "no_variance"
    
    x, y, cw, ch = cv2.boundingRect(coords)
    
    # Must be reasonable size
    area_ratio = (cw * ch) / (h * w)
    if area_ratio < 0.1 or area_ratio > 0.95:
        return None, "var_invalid"
    
    return img[y:y+ch, x:x+cw], "variance"

def saturation_based_crop(img):
    """
    Fallback Strategy for snow-on-white photos:
    Scanner background is pure neutral (saturation = 0).
    Real photos (even snow) have slight color casts (saturation > 0).
    """
    h, w = img.shape[:2]
    
    # Convert to HSV and extract saturation channel
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    
    # Any pixel with saturation > 5 is likely photo content
    sat_mask = (saturation > 5).astype(np.uint8) * 255
    
    # Clean up
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    sat_mask = cv2.morphologyEx(sat_mask, cv2.MORPH_CLOSE, kernel)
    sat_mask = cv2.morphologyEx(sat_mask, cv2.MORPH_OPEN, kernel)
    
    # Clear edges
    margin = 10
    sat_mask[0:margin, :] = 0
    sat_mask[-margin:, :] = 0
    sat_mask[:, 0:margin] = 0
    sat_mask[:, -margin:] = 0
    
    # Find bounding box
    coords = cv2.findNonZero(sat_mask)
    if coords is None:
        return None, "no_saturation"
    
    x, y, cw, ch = cv2.boundingRect(coords)
    
    area_ratio = (cw * ch) / (h * w)
    if area_ratio < 0.1 or area_ratio > 0.95:
        return None, "sat_invalid"
    
    return img[y:y+ch, x:x+cw], "saturation"

def gradient_line_scan(img):
    """
    FINAL FALLBACK: Scan from edges inward looking for strong gradient lines.
    The physical photo edge creates a visible line even in snow photos.
    This approach looks for the first row/column with significant gradient changes.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Compute gradient magnitude
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    grad_mag = np.sqrt(sobelx**2 + sobely**2)
    
    # Threshold to find significant edges
    threshold = 20
    edges = (grad_mag > threshold).astype(np.float32)
    
    # Calculate the "edge density" per row and column
    row_density = np.mean(edges, axis=1)
    col_density = np.mean(edges, axis=0)
    
    # Find bounds: first/last rows/cols with significant edge content
    content_threshold = 0.02  # At least 2% of pixels in a row/col must be edges
    
    # Find top: first row with significant edges
    top = 0
    for i in range(h // 2):
        if row_density[i] > content_threshold:
            top = max(0, i - 5)  # Small margin
            break
    
    # Find bottom: last row with significant edges
    bottom = h - 1
    for i in range(h - 1, h // 2, -1):
        if row_density[i] > content_threshold:
            bottom = min(h - 1, i + 5)
            break
    
    # Find left: first column with significant edges
    left = 0
    for i in range(w // 2):
        if col_density[i] > content_threshold:
            left = max(0, i - 5)
            break
    
    # Find right: last column with significant edges
    right = w - 1
    for i in range(w - 1, w // 2, -1):
        if col_density[i] > content_threshold:
            right = min(w - 1, i + 5)
            break
    
    # Check if we found meaningful bounds
    crop_area = (right - left) * (bottom - top)
    original_area = h * w
    
    # Must crop at least 5% but no more than 90% of original
    ratio = crop_area / original_area
    if ratio < 0.1 or ratio > 0.95:
        return None, "grad_invalid"
    
    return img[top:bottom+1, left:right+1], "gradient"



def professional_crop(img):
    """
    Production-grade cropping algorithm:
    1. Grayscale + Blur
    2. Otsu Binarization (Inverse) - isolates background
    3. Morphological Closing - bridges broken borders
    4. RETR_EXTERNAL - ignores interior detail
    5. Highest-area contour + rectangular validation
    6. FALLBACK: Canny edge detection for snow/white photos
    """
    h, w = img.shape[:2]
    image_area = h * w
    
    # Step 1: Preprocessing
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Step 2: Otsu Binarization (Binary Inverse)
    # This turns the photo content WHITE and the background BLACK
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Step 3: Morphological Closing
    # Fills small gaps/noise in the border to ensure a solid contour
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    # NEW: Edge Clearing Logic
    # Scanners often have tiny dark noise at the extreme edges (0-5px).
    # This 'tethers' the photo to the edge, making it the 'largest contour'.
    # We clear the edges of the mask to ensure the photo is a free-floating island.
    margin = 10
    closed[0:margin, :] = 0
    closed[-margin:, :] = 0
    closed[:, 0:margin] = 0
    closed[:, -margin:] = 0
    
    # Step 4: External Contour Detection
    # RETR_EXTERNAL is the critical part - it ignores EVERYTHING inside the photo
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # Step 5: Select Largest Contour
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        
        # Check if this is a valid crop candidate
        if area >= 0.1 * image_area:
            # Step 6: Rectangular Validation & Bounding
            peri = cv2.arcLength(largest, True)
            approx = cv2.approxPolyDP(largest, 0.02 * peri, True)
            
            # If it's roughly rectangular (4 corners), use it. Otherwise use the bounding box.
            if len(approx) == 4:
                x, y, cw, ch = cv2.boundingRect(approx)
                strategy = "pro_rect"
            else:
                x, y, cw, ch = cv2.boundingRect(largest)
                strategy = "pro_contour"
                
            # Check if we are cropping a meaningful amount
            if (cw * ch) / image_area < 0.95:
                return img[y:y+ch, x:x+cw], strategy
    
    # FALLBACK 1: Canny Edge Detection (for snow/white photos)
    result, strategy = canny_edge_crop(img)
    if result is not None:
        return result, strategy
    
    # FALLBACK 2: Variance-based detection (for stubborn cases like Scan_0055)
    result, strategy = variance_based_crop(img)
    if result is not None:
        return result, strategy
    
    # FALLBACK 3: Saturation-based detection (real snow has color cast, scanner bg doesn't)
    result, strategy = saturation_based_crop(img)
    if result is not None:
        return result, strategy
    
    # FALLBACK 4: Gradient line scan (find first row/col with actual edges)
    result, strategy = gradient_line_scan(img)
    if result is not None:
        return result, strategy

    
    return None, "no_crop_needed"




def process_image(input_path, output_path):
    """Applies the professional crop and saves with 100% quality."""
    img = cv2.imread(input_path)
    if img is None:
        return False, "read_error"
        
    try:
        cropped, strategy = professional_crop(img)
        
        if cropped is not None:
            # Convert BGR to RGB for PIL save
            cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
            Image.fromarray(cropped_rgb).save(output_path, quality=100, subsampling=0)
            return True, strategy
        else:
            # Fallback: Save original if no crop found
            cv2.imwrite(output_path, img, [cv2.IMWRITE_JPEG_QUALITY, 100])
            return True, "original"
    except Exception as e:
        # Emergency Fallback: Save original
        cv2.imwrite(output_path, img, [cv2.IMWRITE_JPEG_QUALITY, 100])
        return True, "error_fallback"

def batch_process(base_dir):
    """Iterate through folders and process images."""
    scan_folder = os.path.join(base_dir, "scan project SRM")
    
    subfolders = [f.path for f in os.scandir(scan_folder) 
                  if f.is_dir() 
                  and " - Cropped" not in f.name 
                  and " - Enhanced" not in f.name]
    
    print(f"Starting Professional Cropping Batch...")
    print(f"Algorithm: Otsu + MorphClose + RETR_EXTERNAL\n")
    
    overall_stats = {}
    
    for folder in subfolders:
        folder_name = os.path.basename(folder)
        output_folder = os.path.join(scan_folder, f"{folder_name} - Cropped")
        
        # We overwrite previous "Cropped" attempts for this professional run
        if os.path.exists(output_folder):
            shutil.rmtree(output_folder)
        os.makedirs(output_folder)
        
        print(f"Processing Folder: {folder_name}")
        files = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        
        folder_stats = {}
        for filename in files:
            input_file = os.path.join(folder, filename)
            output_file = os.path.join(output_folder, filename)
            
            success, strategy = process_image(input_file, output_file)
            folder_stats[strategy] = folder_stats.get(strategy, 0) + 1
            overall_stats[strategy] = overall_stats.get(strategy, 0) + 1
            
        # Report folder summary
        print(f"  Done: {len(files)} files.")
        for s, count in folder_stats.items():
            print(f"    - {s}: {count}")
        print()
        
    print("="*40)
    print("FINAL BATCH STATISTICS:")
    total = sum(overall_stats.values())
    for s, count in overall_stats.items():
        print(f"  {s:15}: {count} ({count/total*100:4.1f}%)")
    print("="*40)

if __name__ == "__main__":
    import sys
    # Use current directory or first argument
    path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    batch_process(path)
