import os
import subprocess
import sys

def enhance_folders(base_dir):
    scan_folder = os.path.join(base_dir, "scan project SRM")
    
    # Path to the extracted tools
    ext_tools_dir = os.path.join(base_dir, "tools", "ext")
    executable_path = os.path.join(ext_tools_dir, "upscayl-bin.exe")
    models_path = os.path.join(ext_tools_dir, "models")
    
    if not os.path.exists(executable_path):
        print(f"Error: Enhancement tool not found at: {executable_path}")
        print("Please run setup_upscayl.py to extract the tools first.")
        return

    if not os.path.exists(scan_folder):
        print(f"Error: Base folder '{scan_folder}' not found.")
        return

    # Find Cropped folders
    subfolders = [f.path for f in os.scandir(scan_folder) 
                  if f.is_dir() and f.name.endswith(" - Cropped")]

    if not subfolders:
         print(f"No '- Cropped' folders found in {scan_folder}. Run batch_processor.py first.")
         return

    print(f"Found {len(subfolders)} folders to enhance.")

    for crop_folder in subfolders:
        folder_name = os.path.basename(crop_folder)
        base_name = folder_name.rsplit(" - Cropped", 1)[0]
        enhanced_folder_name = f"{base_name} - Enhanced"
        enhanced_path = os.path.join(scan_folder, enhanced_folder_name)
        
        # Ensure output exists
        if not os.path.exists(enhanced_path):
            os.makedirs(enhanced_path)
            print(f"Created/Verified folder: {enhanced_folder_name}")

        print(f"Enhancing: {folder_name} -> {enhanced_folder_name}")
        
        # Construct Command
        # usage: upscayl-bin.exe -i input -o output -n modelname -m modelpath
        cmd = [
            executable_path,
            "-i", crop_folder,
            "-o", enhanced_path,
            "-n", "realesrgan-x4plus",
            "-m", models_path,
            "-s", "4",
            "-f", "jpg"
        ]
        
        # print(f"DEBUG Command: {' '.join(cmd)}")
        
        try:
            subprocess.run(cmd, check=True)
            print(f"Done enhancing {folder_name}.\n")
        except subprocess.CalledProcessError as e:
            print(f"Error running upscaler: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    current_dir = os.getcwd()
    enhance_folders(current_dir)
