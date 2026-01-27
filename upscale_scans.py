import os
import subprocess
import shutil
import sys

def prepare_model(models_root):
    """
    Prepares the model folder for Upscayl binary.
    The binary requires the model file to be named 'realesrgan-x4plus' inside the folder provided to -m.
    We will use 'upscayl-lite-4x' as it fits in VRAM on this system.
    """
    source_model_name = "upscayl-lite-4x"
    target_name = "realesrgan-x4plus"
    
    model_dir = os.path.join(models_root, source_model_name)
    if not os.path.exists(model_dir):
        # Fallback: Create directory if it doesn't exist but files are in root
        # This handles the case where setup might have flattened things or we need to look elsewhere
        print(f"Warning: {model_dir} not found. Checking if we need to create it from root models.")
        return None

    # Check for target files (renamed versions)
    dst_bin = os.path.join(model_dir, f"{target_name}.bin")
    dst_param = os.path.join(model_dir, f"{target_name}.param")
    
    if os.path.exists(dst_bin) and os.path.exists(dst_param):
        print(f"Model already prepared in {model_dir}")
        return model_dir

    # Check for source files
    src_bin = os.path.join(model_dir, f"{source_model_name}.bin")
    src_param = os.path.join(model_dir, f"{source_model_name}.param")
    
    if not os.path.exists(src_bin) or not os.path.exists(src_param):
        print(f"Error: Source model files for {source_model_name} not found in {model_dir}")
        return None
    
    if not os.path.exists(dst_bin):
        print(f"Preparing model: Copying to {target_name}.bin")
        shutil.copy2(src_bin, dst_bin)
        
    if not os.path.exists(dst_param):
        print(f"Preparing model: Copying to {target_name}.param")
        shutil.copy2(src_param, dst_param)
        
    return model_dir

def upscale_images():
    base_dir = os.getcwd()
    scan_main_folder = os.path.join(base_dir, "scan project SRM")
    
    tools_dir = os.path.join(base_dir, "tools", "ext")
    upscayl_bin = os.path.join(tools_dir, "upscayl-bin.exe")
    models_root = os.path.join(tools_dir, "models")

    if not os.path.exists(upscayl_bin):
        print(f"Error: upscayl-bin.exe not found at {upscayl_bin}")
        return

    # Prepare logic
    active_model_path = prepare_model(models_root)
    if not active_model_path:
        print("Failed to prepare model. Aborting.")
        return

    # Identify original album folders
    subfolders = [f.path for f in os.scandir(scan_main_folder) 
                  if f.is_dir() 
                  and " - Cropped" not in f.name 
                  and " - Enhanced" not in f.name]

    if not subfolders:
        print("No album folders found to process.")
        return

    print(f"Found {len(subfolders)} album folders.")

    for folder in subfolders:
        folder_name = os.path.basename(folder)
        enhanced_folder_name = f"{folder_name} - Enhanced"
        enhanced_path = os.path.join(scan_main_folder, enhanced_folder_name)

        if not os.path.exists(enhanced_path):
            os.makedirs(enhanced_path)
            print(f"Created: {enhanced_folder_name}")
        
        valid_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff')
        image_files = [f for f in os.listdir(folder) if f.lower().endswith(valid_exts)]
        
        print(f"Processing '{folder_name}' ({len(image_files)} images)...")

        for i, filename in enumerate(image_files):
            input_path = os.path.join(folder, filename)
            
            # Upscayl usually exports PNG.
            name_part = os.path.splitext(filename)[0]
            output_filename = f"{name_part}.png" 
            output_path = os.path.join(enhanced_path, output_filename)

            if os.path.exists(output_path):
                continue
            
            # Use relative path for model if possible to avoid path string issues, 
            # but absolute path is safer if working directory is handled.
            # We will set cwd to tools_dir so binary finds dlls if needed, though mostly static.
            # But we verified pointing to Absolute Path for -m might fail? 
            # No, earlier test 'models/standard_test' was relative.
            
            # Construct relative model path from tools_dir
            rel_model_path = os.path.relpath(active_model_path, tools_dir)
            
            cmd = [
                upscayl_bin,
                "-i", input_path,
                "-o", output_path,
                "-m", rel_model_path,
                "-t", "200" # Tiling to save VRAM
            ]

            try:
                # Run from tools_dir to ensure relative paths work as tested
                result = subprocess.run(cmd, cwd=tools_dir, capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"  Error upscaling {filename}:")
                    print(result.stderr)
                    # Check for VRAM error
                    if "vkAllocateMemory failed" in result.stderr:
                         print("  (VRAM Error - try reducing tile size in script)")
                else:
                    print(f"  [{i+1}/{len(image_files)}] Upscaled: {filename}")
            except Exception as e:
                print(f"  Failed to run binary on {filename}: {e}")

    print("\nAll tasks completed.")

if __name__ == "__main__":
    upscale_images()
