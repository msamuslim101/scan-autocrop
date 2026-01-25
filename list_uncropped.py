"""
Script to generate a list of images that were not automatically cropped.
Run this after batch_crop_pro.py to identify files needing manual attention.
"""
import os
from PIL import Image

def find_uncropped_images(base_dir):
    """Find all images where the cropped version is the same size as the original."""
    scan_folder = os.path.join(base_dir, "scan project SRM")
    uncropped_list = []
    
    # Get all original folders
    subfolders = [f.path for f in os.scandir(scan_folder) 
                  if f.is_dir() 
                  and " - Cropped" not in f.name 
                  and " - Enhanced" not in f.name]
    
    for folder in subfolders:
        folder_name = os.path.basename(folder)
        cropped_folder = os.path.join(scan_folder, f"{folder_name} - Cropped")
        
        if not os.path.exists(cropped_folder):
            continue
        
        files = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        
        for filename in files:
            orig_path = os.path.join(folder, filename)
            crop_path = os.path.join(cropped_folder, filename)
            
            try:
                with Image.open(orig_path) as orig:
                    orig_size = orig.size
                with Image.open(crop_path) as crop:
                    crop_size = crop.size
                
                # If sizes are identical, image was not auto-cropped
                if orig_size == crop_size:
                    uncropped_list.append({
                        'folder': folder_name,
                        'filename': filename,
                        'original': orig_path,
                        'cropped': crop_path
                    })
            except Exception as e:
                print(f"Error checking {filename}: {e}")
    
    return uncropped_list

def main():
    base_dir = os.getcwd()
    uncropped = find_uncropped_images(base_dir)
    
    print(f"\n{'='*60}")
    print(f"IMAGES NEEDING MANUAL CROPPING: {len(uncropped)}")
    print(f"{'='*60}\n")
    
    # Group by folder
    by_folder = {}
    for item in uncropped:
        folder = item['folder']
        if folder not in by_folder:
            by_folder[folder] = []
        by_folder[folder].append(item['filename'])
    
    for folder, files in by_folder.items():
        print(f"\n📁 {folder} ({len(files)} files):")
        for f in files:
            print(f"   - {f}")
    
    # Also save to a file for easy reference
    output_file = os.path.join(base_dir, "MANUAL_CROP_LIST.txt")
    with open(output_file, 'w') as f:
        f.write(f"IMAGES NEEDING MANUAL CROPPING: {len(uncropped)}\n")
        f.write("=" * 60 + "\n\n")
        
        for folder, files in by_folder.items():
            f.write(f"\n{folder} ({len(files)} files):\n")
            for filename in files:
                f.write(f"  {filename}\n")
    
    print(f"\n✅ List saved to: {output_file}")

if __name__ == "__main__":
    main()
