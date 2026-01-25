import os
from PIL import Image

def analyze_all_crops(base_dir):
    scan_folder = os.path.join(base_dir, "scan project SRM")
    
    folders = [
        ("Album no.2 - Grey", "Album no.2 - Grey - Cropped"),
        ("multi", "multi - Cropped"),
        ("Navy Blue album", "Navy Blue album - Cropped"),
        ("royal Green album", "royal Green album - Cropped")
    ]
    
    total_analyzed = 0
    total_cropped = 0
    total_uncropped = 0
    
    for orig_name, crop_name in folders:
        orig_path = os.path.join(scan_folder, orig_name)
        crop_path = os.path.join(scan_folder, crop_name)
        
        files = [f for f in os.listdir(orig_path) if f.lower().endswith('.jpg')]
        
        cropped_count = 0
        uncropped_count = 0
        uncropped_files = []
        
        for filename in files:
            orig_file = os.path.join(orig_path, filename)
            crop_file = os.path.join(crop_path, filename)
            
            try:
                orig_img = Image.open(orig_file)
                crop_img = Image.open(crop_file)
                
                if orig_img.size == crop_img.size:
                    uncropped_count += 1
                    if len(uncropped_files) < 10:  # Store first 10 examples
                        uncropped_files.append(filename)
                else:
                    cropped_count += 1
            except:
                pass
        
        total = len(files)
        crop_success_rate = (cropped_count / total * 100) if total > 0 else 0
        
        print(f"\n{orig_name}:")
        print(f"  Total: {total}")
        print(f"  Successfully cropped: {cropped_count} ({crop_success_rate:.1f}%)")
        print(f"  Failed (unchanged): {uncropped_count}")
        if uncropped_files:
            print(f"  Examples of failures: {', '.join(uncropped_files[:5])}")
        
        total_analyzed += total
        total_cropped += cropped_count
        total_uncropped += uncropped_count
    
    print(f"\n{'='*50}")
    print(f"OVERALL STATISTICS:")
    print(f"Total images: {total_analyzed}")
    print(f"Successfully cropped: {total_cropped} ({total_cropped/total_analyzed*100:.1f}%)")
    print(f"Failed/unchanged: {total_uncropped} ({total_uncropped/total_analyzed*100:.1f}%)")
    print(f"{'='*50}")

if __name__ == "__main__":
    current_dir = os.getcwd()
    analyze_all_crops(current_dir)
