import os
import shutil
from PIL import Image, ImageChops
import numpy as np

def detect_content_bounds(img, threshold=240):
    """
    Detect the content area by finding rows/columns with significant dark content.
    Uses statistical approach: a row/column is "content" if it has enough pixels
    darker than the threshold.
    threshold: pixel intensity below which is considered 'content' (0-255)
    content_percentage: minimum percentage of pixels that must be dark to count as content row/col
    """
    gray = img.convert('L')
    arr = np.array(gray)
    
    # For each row/column, count how many pixels are "content" (darker than threshold)
    # If more than 1% of pixels in a row are content, the row has content
    content_percentage = 0.01  # 1% of pixels must be dark
    
    # For rows: count dark pixels per row
    dark_pixel_count_rows = np.sum(arr < threshold, axis=1)
    min_dark_pixels_row = int(arr.shape[1] * content_percentage)
    row_has_content = dark_pixel_count_rows > min_dark_pixels_row
    
    # For columns: count dark pixels per column  
    dark_pixel_count_cols = np.sum(arr < threshold, axis=0)
    min_dark_pixels_col = int(arr.shape[0] * content_percentage)
    col_has_content = dark_pixel_count_cols > min_dark_pixels_col
    
    # Find the bounds
    rows = np.where(row_has_content)[0]
    cols = np.where(col_has_content)[0]
    
    if len(rows) == 0 or len(cols) == 0:
        return None  # Entire image is white/border
    
    top = rows[0]
    bottom = rows[-1] + 1
    left = cols[0]
    right = cols[-1] + 1
    
    return (left, top, right, bottom)

def smart_crop_image(img, threshold=200):
    """Crop image to content bounds."""
    bbox = detect_content_bounds(img, threshold)
    if bbox:
        # Add small margin to avoid cutting into content
        left, top, right, bottom = bbox
        margin = 5
        left = max(0, left - margin)
        top = max(0, top - margin)
        right = min(img.width, right + margin)
        bottom = min(img.height, bottom + margin)
        
        return img.crop((left, top, right, bottom))
    return img

def batch_crop_improved(base_dir):
    scan_folder = os.path.join(base_dir, "scan project SRM")
    
    if not os.path.exists(scan_folder):
        print(f"Error: {scan_folder} not found.")
        return

    subfolders = [f.path for f in os.scandir(scan_folder) 
                  if f.is_dir() 
                  and " - Cropped" not in f.name 
                  and " - Enhanced" not in f.name]

    print(f"Found {len(subfolders)} folders to process.\n")

    for folder in subfolders:
        folder_name = os.path.basename(folder)
        cropped_folder_name = f"{folder_name} - Cropped"
        cropped_path = os.path.join(scan_folder, cropped_folder_name)
        
        # Delete and recreate
        if os.path.exists(cropped_path):
            print(f"Removing old: {cropped_folder_name}")
            shutil.rmtree(cropped_path)
        
        os.makedirs(cropped_path)
        print(f"Processing: {folder_name}")
        
        files = [f for f in os.listdir(folder) 
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'))]
        
        count = 0
        for filename in files:
            input_file = os.path.join(folder, filename)
            output_file = os.path.join(cropped_path, filename)
            
            try:
                img = Image.open(input_file)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                cropped = smart_crop_image(img, threshold=240)
                cropped.save(output_file, quality=95)
                count += 1
                
                if count % 30 == 0:
                    print(f"  {count}/{len(files)}...")
            except Exception as e:
                print(f"  Error: {filename} - {e}")
        
        print(f"  DONE: {count} images\n")

    print("✅ Cropping complete!")

if __name__ == "__main__":
    current_dir = os.getcwd()
    batch_crop_improved(current_dir)
