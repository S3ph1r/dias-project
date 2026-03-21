#!/usr/bin/env python3
import os
import json
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# --- CONFIGURATION ---
BASE_DIR = Path("/home/Projects/NH-Mini/sviluppi/dias")
STAGE_D_DIR = BASE_DIR / "data" / "stage_d" / "output"

def download_file(url, dest_path):
    if dest_path.exists():
        return False
    
    try:
        response = requests.get(url, timeout=20, stream=True)
        if response.status_code == 200:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
    return False

def sync_assets():
    # Scan all JSONs in stage_d output
    json_files = list(STAGE_D_DIR.glob("*.json"))
    print(f"Found {len(json_files)} scene checkpoints.")
    
    to_download = []
    
    for jf in json_files:
        try:
            with open(jf, 'r') as f:
                data = json.load(f)
                
            voice_path = data.get("voice_path")
            if not voice_path:
                continue
            
            # Extract only the filename from the URL (PC 139 might change path structure)
            filename = voice_path.split("/")[-1]
            corrected_url = f"http://192.168.1.139:8082/{filename}"
            
            clean_title = data.get("clean_title", "unknown")
            chunk_label = data.get("chunk_label", "chunk-000")
            scene_id = data.get("scene_id", "scene-000")
            
            # Target path
            local_path = STAGE_D_DIR / clean_title / chunk_label / f"{scene_id}.wav"
            
            if not local_path.exists():
                to_download.append((corrected_url, local_path))
        except:
            continue

    print(f"Items to download: {len(to_download)}")
    
    # Using ThreadPool for faster concurrent downloads
    success_count = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(download_file, url, path) for url, path in to_download]
        for f in futures:
            if f.result():
                success_count += 1
                if success_count % 50 == 0:
                    print(f"Progress: {success_count}/{len(to_download)}")

    print(f"Sync complete. Downloaded {success_count} files.")

if __name__ == "__main__":
    sync_assets()
