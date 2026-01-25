import os
import shutil
import cv2
import numpy as np
from PIL import Image

def find_content_bbox(gray_img, white_threshold=248):
    """
    Find bounding box by scanning from edges INWARD until hitting non-white content.
    This prevents cropping into photo content.
    """
    h, w = gray_img.shape
    
    # Start from edges and scan inward
    # Top edge: scan down
    top = 0
    for i in range(h):
        if np.mean(gray_img[i, :]) < white_threshold:
            top = i
            break
    
    # Bottom edge: scan up
    bottom = h
    for i in range(h-1, -1, -1):
        if np.mean(gray_img[i, :]) < white_threshold:
            bottom = i + 1
            break
    
    # Left edge: scan right
    left = 0
    for i in range(w):
        if np.mean(gray_img[:, i]) < white_threshold:
            left = i
            break
    
    # Right edge: scan left
    right = w
    for i in range(w-1, -1, -1):
        if np.mean(gray_img[:, i]) < white_threshold:
            right = i + 1
            break
    
    return left, top, right, bottom

def safe_border_crop(img_path):
    """
    Safely crop white borders by scanning from edges inward.
    NEVER crops into photo content.
    """
    img = cv2.imread(img_path)
    if img is None:
        return None, "read_error"
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Try multiple thresholds to find borders
    for threshold in [252, 248, 245, 242]:
        left, top, right, bottom = find_content_bbox(gray, threshold)
        
        h, w = img.shape[:2]
        cropped_area = (right - left) * (bottom - top)
        original_area = h * w
        area_ratio = cropped_area / original_area
        
        # Must remove at least 2% but not more than 95%
        if 0.05 < area_ratio < 0.98:
            cropped = img[top:bottom, left:right]
            return cropped, f"border_trim_{threshold}"
    
    # If no suitable crop found, return original
    return img, "original"

def batch_crop_safe(base_dir):
    """Safe border cropping - NEVER damages photo content."""
    scan_folder = os.path.join(base_dir, "scan project SRM")
    
    if not os.path.exists(scan_folder):
        print(f"Error: {scan_folder} not found.")
        return
    
    subfolders = [f.path for f in os.scandir(scan_folder) 
                  if f.is_dir() 
                  and " - Cropped" not in f.name 
                  and " - Enhanced" not in f.name]
    
    print(f"Processing {len(subfolders)} folders with SAFE border trimming.\n")
    
    total_cropped = 0
    total_original = 0
    
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
        
        cropped_count = 0
        original_count = 0
        
        for filename in files:
            input_file = os.path.join(folder, filename)
            output_file = os.path.join(cropped_path, filename)
            
            result, strategy = safe_border_crop(input_file)
            if result is not None:
                # Convert to RGB and save with 100% quality
                result_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
                Image.fromarray(result_rgb).save(output_file, quality=100, subsampling=0)
                
                if strategy == "original":
                    original_count += 1
                else:
                    cropped_count += 1
                
                if (cropped_count + original_count) % 30 == 0:
                    print(f"  {cropped_count + original_count}/{len(files)}...")
        
        total_cropped += cropped_count
        total_original += original_count
        
        print(f"  DONE: Cropped: {cropped_count}, Original: {original_count}\n")
    
    total = total_cropped + total_original
    print("="*60)
    print("OVERALL STATISTICS:")
    print(f"Total: {total}")
    print(f"  Cropped successfully: {total_cropped} ({total_cropped/total*100:.1f}%)")
    print(f"  Original (unchanged): {total_original} ({total_original/total*100:.1f}%)")
    print("="*60)

if __name__ == "__main__":
    current_dir = os.getcwd()
    batch_crop_safe(current_dir)
