#!/usr/bin/env python3
import os
import json
import requests
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

# --- CONFIGURATION ---
BOOK_ID = "Cronache-del-Silicio"
CHAPTER_ID = "chapter_001" # We'll filter for this
BASE_DIR = Path("/home/Projects/NH-Mini/sviluppi/dias")
DATA_DIR = BASE_DIR / "data"
STAGE_C_DIR = DATA_DIR / "stage_c" / "output"
STAGE_D_DIR = DATA_DIR / "stage_d" / "output"
TEMP_DIR = BASE_DIR / "temp" / "stitcher"
OUTPUT_DIR = DATA_DIR / "milestone_outputs"

# ARIA Asset Server
ARIA_HOST = os.getenv("ARIA_WORKER_IP", "192.168.1.139")
ARIA_PORT = os.getenv("ARIA_WORKER_PORT", "8082")

def ensure_dirs():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def get_all_chapter_scenes() -> Dict[str, List[Dict]]:
    """
    Scans Master JSONs in Stage C and groups scenes by chapter_id.
    """
    chapters = {} # chapter_id -> list of scenes
    # Find all Master JSONs for the book
    master_files = sorted(list(STAGE_C_DIR.glob(f"{BOOK_ID}-chunk-*-scenes.json")))
    
    print(f"Found {len(master_files)} Master JSON files.")
    
    for mf in master_files:
        try:
            with open(mf, 'r') as f:
                data = json.load(f)
                for scene in data.get("scenes", []):
                    c_id = scene.get("chapter_id", "unknown_chapter")
                    if c_id not in chapters:
                        chapters[c_id] = []
                    chapters[c_id].append(scene)
        except:
            continue
    
    print(f"Detected chapters: {list(chapters.keys())}")
    return chapters

def download_asset(url: str, dest_path: Path):
    if dest_path.exists():
        return True
    
    print(f"Downloading: {url} -> {dest_path.name}")
    try:
        response = requests.get(url, timeout=10, stream=True)
        if response.status_code == 200:
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        else:
            print(f"Error {response.status_code} downloading {url}")
            return False
    except Exception as e:
        print(f"Exception downloading {url}: {e}")
        return False

def get_audio_url_from_stage_d(clean_title, chunk_label, scene_id) -> Optional[str]:
    """
    Looks for the Stage D output JSON to find the final remote URL.
    """
    pattern = f"{clean_title}-{chunk_label}-{scene_id}-*.json"
    matches = list(STAGE_D_DIR.glob(pattern))
    if not matches:
        return None
    
    latest = sorted(matches)[-1]
    try:
        with open(latest, 'r') as f:
            data = json.load(f)
            return data.get("voice_path")
    except:
        return None

def stitch_chapter(chapter_id: str, scenes: List[Dict]):
    """
    Merges scenes for a specific chapter.
    """
    downloaded_files = []
    valid_scenes = []
    
    print(f"\n--- Processing {chapter_id} ({len(scenes)} scenes) ---")
    
    # Ensure chapter temp dir to avoid collisions if running parallel (rare here)
    chapter_temp = TEMP_DIR / chapter_id
    chapter_temp.mkdir(parents=True, exist_ok=True)

    for i, scene in enumerate(scenes):
        clean_title = scene.get("clean_title", BOOK_ID)
        chunk_label = scene.get("chunk_label") or "chunk-000"
        scene_id = scene.get("scene_id")
        
        # Check for local file first (DIAS Centrality - RESILIENT STRUCTURE)
        # New: stage_d/output/Cronache-del-Silicio/Cronache-del-Silicio-chunk-000-micro-000-scene-001.wav
        unique_id = f"{clean_title}-{scene_id}"
        local_vocal_path = STAGE_D_DIR / clean_title / f"{unique_id}.wav"
        
        if local_vocal_path.exists():
            print(f"  [LOC] Found: {local_vocal_path.name}")
            downloaded_files.append(local_vocal_path)
            valid_scenes.append(scene)
            continue

        # Fallback to download
        url = get_audio_url_from_stage_d(clean_title, chunk_label, scene_id)
        if not url:
            url = f"http://{ARIA_HOST}:{ARIA_PORT}/{clean_title}-{chunk_label}-{scene_id}.wav"
        
        local_target = chapter_temp / f"{chunk_label}-{scene_id}.wav"
        if download_asset(url, local_target):
            downloaded_files.append(local_target)
            valid_scenes.append(scene)
        else:
            print(f"SKIPPING missing scene {scene_id} in {chunk_label}")

    if not downloaded_files:
        print(f"No assets found for {chapter_id}.")
        return

    output_file = OUTPUT_DIR / f"{BOOK_ID}-{chapter_id}.wav"
    manifest_path = chapter_temp / "manifest.txt"
    
    with open(manifest_path, 'w') as f:
        for i, scene in enumerate(valid_scenes):
            f.write(f"file '{downloaded_files[i].resolve()}'\n")
            # Add pause
            pause_ms = scene.get("pause_after_ms", 0)
            if pause_ms > 0:
                silence_file = get_silence(pause_ms, chapter_temp)
                if silence_file:
                    f.write(f"file '{silence_file.resolve()}'\n")
            
    print(f"Merging {len(downloaded_files)} files into {output_file}...")
    
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest_path),
            "-c", "copy", str(output_file)
        ], check=True, capture_output=True)
        print(f"✅ {chapter_id} COMPLETED: {output_file}")
    except subprocess.CalledProcessError:
        print(f"FFmpeg copy failed for {chapter_id}. Retrying with encode...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest_path),
            "-ac", "1", "-ar", "44100", str(output_file)
        ], check=True, capture_output=True)
        print(f"✅ {chapter_id} COMPLETED (Encoded): {output_file}")

def get_silence(duration_ms: int, temp_dir: Path) -> Path:
    if duration_ms <= 0: return None
    s_file = temp_dir / f"silence_{duration_ms}ms.wav"
    if not s_file.exists():
        duration_sec = duration_ms / 1000.0
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(duration_sec), str(s_file)], stderr=subprocess.DEVNULL, check=True)
    return s_file

if __name__ == "__main__":
    ensure_dirs()
    chapter_map = get_all_chapter_scenes()
    
    for chapter_id, scenes in chapter_map.items():
        stitch_chapter(chapter_id, scenes)
    
    print("\n🎉 ALL CHAPTERS PROCESSED.")
