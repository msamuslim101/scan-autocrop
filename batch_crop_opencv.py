import os
import shutil
import cv2
import numpy as np
from PIL import Image

def contour_crop(img):
    """Strategy 1: Contour detection - finds photo rectangle via edge detection."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    # Lower Canny thresholds to detect softer edges
    edges = cv2.Canny(blurred, 30, 100)
    
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    
    h, w = img.shape[:2]
    total_area = h * w
    
    for contour in contours[:10]:
        x, y, cw, ch = cv2.boundingRect(contour)
        area_ratio = (cw * ch) / total_area
        aspect_ratio = cw / ch if ch > 0 else 0
        
        # More relaxed constraints: 5% minimum area, 99.5% maximum
        if 0.05 < area_ratio < 0.995 and 0.2 < aspect_ratio < 5.0:
            return img[y:y+ch, x:x+cw], "contour"
    
    return None, None

def adaptive_threshold_crop(img):
    """Strategy 2: Adaptive thresholding with morphology."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY_INV, 11, 2)
    
    kernel = np.ones((5, 5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    
    coords = cv2.findNonZero(binary)
    if coords is not None:
        x, y, w, h = cv2.boundingRect(coords)
        area_ratio = (w * h) / (img.shape[0] * img.shape[1])
        
        if 0.15 < area_ratio < 0.98:
            return img[y:y+h, x:x+w], "adaptive"
    
    return None, None

def mean_based_crop(img):
    """Strategy 3: Mean-based threshold (learned from previous tests)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(float)
    
    row_means = np.mean(gray, axis=1)
    col_means = np.mean(gray, axis=0)
    
    # Increased threshold to catch more near-white borders
    content_rows = row_means < 248
    content_cols = col_means < 248
    
    rows = np.where(content_rows)[0]
    cols = np.where(content_cols)[0]
    
    if len(rows) > 0 and len(cols) > 0:
        top, bottom = rows[0], rows[-1] + 1
        left, right = cols[0], cols[-1] + 1
        
        area_ratio = ((right-left) * (bottom-top)) / (img.shape[0] * img.shape[1])
        if 0.05 < area_ratio < 0.995:
            return img[top:bottom, left:right], "mean"
    
    return None, None

def smart_crop_opencv(input_path, output_path):
    """Apply multi-strategy cropping with fallbacks."""
    img = cv2.imread(input_path)
    if img is None:
        return False, "read_error"
    
    # Try strategies in order
    result, strategy = contour_crop(img)
    
    if result is None:
        result, strategy = adaptive_threshold_crop(img)
    
    if result is None:
        result, strategy = mean_based_crop(img)
    
    if result is None:
        # Fallback: use original
        result = img
        strategy = "original"
    
    # Convert to RGB and save with 100% quality
    result_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
    Image.fromarray(result_rgb).save(output_path, quality=100, subsampling=0)
    
    return True, strategy

def batch_crop_opencv(base_dir):
    """Process all folders with OpenCV multi-strategy approach."""
    scan_folder = os.path.join(base_dir, "scan project SRM")
    
    if not os.path.exists(scan_folder):
        print(f"Error: {scan_folder} not found.")
        return
    
    subfolders = [f.path for f in os.scandir(scan_folder) 
                  if f.is_dir() 
                  and " - Cropped" not in f.name 
                  and " - Enhanced" not in f.name]
    
    print(f"Processing {len(subfolders)} folders with OpenCV multi-strategy.\n")
    
    strategy_stats = {"contour": 0, "adaptive": 0, "mean": 0, "original": 0}
    
    for folder in subfolders:
        folder_name = os.path.basename(folder)
        cropped_folder_name = f"{folder_name} - Cropped"
        cropped_path = os.path.join(scan_folder, cropped_folder_name)
        
        # Delete and recreate
        if os.path.exists(cropped_path):
            shutil.rmtree(cropped_path)
        os.makedirs(cropped_path)
        
        print(f"Processing: {folder_name}")
        
        files = [f for f in os.listdir(folder) 
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'))]
        
        count = 0
        folder_stats = {"contour": 0, "adaptive": 0, "mean": 0, "original": 0}
        
        for filename in files:
            input_file = os.path.join(folder, filename)
            output_file = os.path.join(cropped_path, filename)
            
            success, strategy = smart_crop_opencv(input_file, output_file)
            if success:
                count += 1
                folder_stats[strategy] += 1
                strategy_stats[strategy] += 1
                
                if count % 30 == 0:
                    print(f"  {count}/{len(files)}...")
        
        # Report per folder
        print(f"  DONE: {count} images")
        print(f"    Contour: {folder_stats['contour']}, Adaptive: {folder_stats['adaptive']}, " +
              f"Mean: {folder_stats['mean']}, Original: {folder_stats['original']}\n")
    
    # Overall statistics
    total = sum(strategy_stats.values())
    print("="*60)
    print("OVERALL STATISTICS:")
    print(f"Total: {total}")
    print(f"  Contour detection: {strategy_stats['contour']} ({strategy_stats['contour']/total*100:.1f}%)")
    print(f"  Adaptive threshold: {strategy_stats['adaptive']} ({strategy_stats['adaptive']/total*100:.1f}%)")
    print(f"  Mean-based: {strategy_stats['mean']} ({strategy_stats['mean']/total*100:.1f}%)")
    print(f"  Original (unchanged): {strategy_stats['original']} ({strategy_stats['original']/total*100:.1f}%)")
    print(f"\nCropped successfully: {total - strategy_stats['original']} ({(total-strategy_stats['original'])/total*100:.1f}%)")
    print("="*60)

if __name__ == "__main__":
    current_dir = os.getcwd()
    batch_crop_opencv(current_dir)
