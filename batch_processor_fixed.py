import os
import subprocess
import shutil

def crop_with_imagemagick(base_dir):
    """Use ImageMagick to properly crop images with borders."""
    scan_folder = os.path.join(base_dir, "scan project SRM")
    
    if not os.path.exists(scan_folder):
        print(f"Error: {scan_folder} not found.")
        return

    # Find original subfolders (excluding -Cropped and -Enhanced)
    subfolders = [f.path for f in os.scandir(scan_folder) 
                  if f.is_dir() 
                  and " - Cropped" not in f.name 
                  and " - Enhanced" not in f.name]

    print(f"Found {len(subfolders)} folders to process with ImageMagick.\n")

    for folder in subfolders:
        folder_name = os.path.basename(folder)
        cropped_folder_name = f"{folder_name} - Cropped"
        cropped_path = os.path.join(scan_folder, cropped_folder_name)
        
        # Delete existing cropped folder to redo properly
        if os.path.exists(cropped_path):
            print(f"Removing old cropped folder: {cropped_folder_name}")
            shutil.rmtree(cropped_path)
        
        os.makedirs(cropped_path)
        print(f"Processing: {folder_name} -> {cropped_folder_name}")
        
        # Get all image files
        files = [f for f in os.listdir(folder) 
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'))]
        
        count = 0
        for filename in files:
            input_file = os.path.join(folder, filename)
            output_file = os.path.join(cropped_path, filename)
            
            # ImageMagick command with proper border trimming
            # -fuzz 10% tolerates slight color variations in borders
            # -trim removes the border
            # +repage resets the canvas
            cmd = [
                "magick",
                input_file,
                "-fuzz", "10%",
                "-trim",
                "+repage",
                output_file
            ]
            
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                count += 1
                if count % 20 == 0:
                    print(f"  Processed {count}/{len(files)}...")
            except subprocess.CalledProcessError as e:
                print(f"  Error processing {filename}: {e.stderr.decode()}")
        
        print(f"  DONE: {count} images cropped.\n")

    print("✅ Batch cropping complete using ImageMagick.")

if __name__ == "__main__":
    current_dir = os.getcwd()
    crop_with_imagemagick(current_dir)
