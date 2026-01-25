import os
import shutil
from PIL import Image
import numpy as np

def aggressive_border_crop(img):
    """
    More aggressive cropping - removes rows/columns that are predominantly white/light.
    Uses mean threshold instead of counting individual dark pixels.
    """
    gray = img.convert('L')
    arr = np.array(gray)
    
    # Strategy: A row/column is "border" if its AVERAGE intensity is very high (>245)
    # This means the entire row is mostly white/light gray
    border_threshold = 245
    
    # Calculate mean intensity for each row and column
    row_means = np.mean(arr, axis=1)
    col_means = np.mean(arr, axis=0)
    
    # Find content rows (mean < threshold means row has darker content)
    content_rows = row_means < border_threshold
    content_cols = col_means < border_threshold
    
    # Find bounds
    rows = np.where(content_rows)[0]
    cols = np.where(content_cols)[0]
    
    if len(rows) == 0 or len(cols) == 0:
        # Entire image is white? Return as-is
        return img
    
    top = rows[0]
    bottom = rows[-1] + 1
    left = cols[0]
    right = cols[-1] + 1
    
    # Add small safety margin
    margin = 3
    left = max(0, left - margin)
    top = max(0, top - margin)
    right = min(img.width, right + margin)
    bottom = min(img.height, bottom + margin)
    
    return img.crop((left, top, right, bottom))

def batch_crop_aggressive(base_dir):
    scan_folder = os.path.join(base_dir, "scan project SRM")
    
    if not os.path.exists(scan_folder):
        print(f"Error: {scan_folder} not found.")
        return

    subfolders = [f.path for f in os.scandir(scan_folder) 
                  if f.is_dir() 
                  and " - Cropped" not in f.name 
                  and " - Enhanced" not in f.name]

    print(f"Processing {len(subfolders)} folders with AGGRESSIVE algorithm.\n")

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
        for filename in files:
            input_file = os.path.join(folder, filename)
            output_file = os.path.join(cropped_path, filename)
            
            try:
                img = Image.open(input_file)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                cropped = aggressive_border_crop(img)
                cropped.save(output_file, quality=95)
                count += 1
                
                if count % 30 == 0:
                    print(f"  {count}/{len(files)}...")
            except Exception as e:
                print(f"  Error: {filename} - {e}")
        
        print(f"  DONE: {count} images\n")

    print("✅ AGGRESSIVE cropping complete!")

if __name__ == "__main__":
    current_dir = os.getcwd()
    batch_crop_aggressive(current_dir)
