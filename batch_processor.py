import os
import sys
from PIL import Image, ImageChops

def is_border(pixel, bg_pixel, fuzz=10):
    """Checks if a pixel is within the fuzz tolerance of the background color."""
    return (abs(pixel[0] - bg_pixel[0]) <= fuzz and
            abs(pixel[1] - bg_pixel[1]) <= fuzz and
            abs(pixel[2] - bg_pixel[2]) <= fuzz)

def smart_crop(img, fuzz=50):
    """
    Detects borders and crops the image.
    Strategy:
    1. Sample the top-left pixel as the background color.
    2. Create a solid background image of that color.
    3. Find difference between original and background.
    4. Threshold the difference to strictly identify non-background content.
    5. Get bounding box of the non-background content.
    """
    bg_color = img.getpixel((0, 0))
    
    # Create a background image with the sampled color
    bg = Image.new(img.mode, img.size, bg_color)
    
    # Calculate difference
    diff = ImageChops.difference(img, bg)
    
    # Apply a threshold to ignore minor noise (fuzz factor equivalent)
    # Convert to grayscale to simplify thresholding
    diff_gray = diff.convert('L')
    
    # Filter: pixels < fuzz are becoming 0 (black), others 255 (white)
    # This creates a mask of "Content" vs "Background"
    mask = diff_gray.point(lambda x: 255 if x > fuzz else 0)
    
    bbox = mask.getbbox()
    
    if bbox:
        # Check if the crop is significant enough to be real content.
        # If bbox is almost the same size as original, we might preserve it or crop it.
        # But we ensure we return exactly one crop.
        return img.crop(bbox)
        
    return img # Return original if no distinct border found

def process_folders(base_dir):
    # Fixed subfolders as per user context
    scan_folder = os.path.join(base_dir, "scan project SRM")
    
    if not os.path.exists(scan_folder):
        print(f"Error: Base folder '{scan_folder}' not found.")
        return

    # Filter for directories only and ignore '... - Cropped' or '... - Enhanced' to avoid recursion loops if run multiple times
    subfolders = [f.path for f in os.scandir(scan_folder) 
                  if f.is_dir() 
                  and " - Cropped" not in f.name 
                  and " - Enhanced" not in f.name]
    
    if not subfolders:
         print(f"No original subfolders found in {scan_folder} (excluding Cropped/Enhanced).")
         return

    print(f"Found {len(subfolders)} subfolders to process.")

    for folder in subfolders:
        folder_name = os.path.basename(folder)
        
        # Define parallel output paths
        cropped_folder_name = f"{folder_name} - Cropped"
        enhanced_folder_name = f"{folder_name} - Enhanced"
        
        cropped_path = os.path.join(scan_folder, cropped_folder_name)
        enhanced_path = os.path.join(scan_folder, enhanced_folder_name)
        
        # Create directories
        if not os.path.exists(cropped_path):
            os.makedirs(cropped_path)
            print(f"Created folder: {cropped_folder_name}")
            
        if not os.path.exists(enhanced_path):
            os.makedirs(enhanced_path)
            print(f"Created folder: {enhanced_folder_name}")

        # Process Images
        print(f"Processing folder: {folder_name}...")
        
        files = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'))]
        
        count = 0
        for filename in files:
            input_file = os.path.join(folder, filename)
            output_file = os.path.join(cropped_path, filename)
            
            # Skip if output already exists
            if os.path.exists(output_file):
                continue
                
            try:
                with Image.open(input_file) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                        
                    cropped_img = smart_crop(img)
                    cropped_img.save(output_file, quality=95)
                    count += 1
            except Exception as e:
                print(f"  Error processing {filename}: {e}")
                
        print(f"  Processed {count} images in {folder_name}")

    print("\nBatch Processing Complete.")

if __name__ == "__main__":
    current_dir = os.getcwd()
    process_folders(current_dir)
