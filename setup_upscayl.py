import zipfile
import os
import shutil

def setup_upscayl():
    zip_path = r"tools/upscayl-main.zip"
    extract_root = r"tools/ext"
    
    # Target paths in the zip
    # Based on previous check: upscayl-main/resources/win/bin/upscayl-bin.exe
    # We also need models. Usually in upscayl-main/resources/models
    
    bin_zip_path = "upscayl-main/resources/win/bin/upscayl-bin.exe"
    models_zip_dir = "upscayl-main/resources/models"
    
    if not os.path.exists(zip_path):
        print(f"Error: {zip_path} not found.")
        return

    if os.path.exists(extract_root):
        shutil.rmtree(extract_root)
    os.makedirs(extract_root)

    print(f"Opening {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as z:
        # Extract Binary
        try:
            # We want to flatten the structure a bit: tools/ext/upscayl-bin.exe
            source = z.open(bin_zip_path)
            target = open(os.path.join(extract_root, "upscayl-bin.exe"), "wb")
            with source, target:
                shutil.copyfileobj(source, target)
            print(f"Extracted: upscayl-bin.exe")
        except KeyError:
            print(f"Error: Could not find {bin_zip_path} in zip.")
            return

        # Extract Models
        # We look for files starting with the models path
        model_files = [f for f in z.namelist() if f.startswith(models_zip_dir) and not f.endswith("/")]
        
        models_out_dir = os.path.join(extract_root, "models")
        os.makedirs(models_out_dir, exist_ok=True)
        
        count = 0
        for m_file in model_files:
            # simple filename extraction
            fname = os.path.basename(m_file)
            if not fname: continue
            
            source = z.open(m_file)
            target = open(os.path.join(models_out_dir, fname), "wb")
            with source, target:
                shutil.copyfileobj(source, target)
            count += 1
            
        print(f"Extracted {count} model files.")

    print("Setup complete. Tools are in tools/ext/")

if __name__ == "__main__":
    setup_upscayl()
