#!/usr/bin/env python3
import os
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
import re

# --- CONFIGURATION ---
BOOK_ID = "Cronache-del-Silicio"
BASE_DIR = Path("/home/Projects/NH-Mini/sviluppi/dias")
DATA_DIR = BASE_DIR / "data"
STAGE_C_DIR = DATA_DIR / "stage_c" / "output"
STAGE_D_DIR = DATA_DIR / "stage_d" / "output"
TEMP_DIR = BASE_DIR / "temp" / "stitcher_reindexed"
OUTPUT_DIR = DATA_DIR / "milestone_outputs_final"

def ensure_dirs():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def collect_all_scenes() -> List[Dict]:
    """
    Collects every single scene from all Master JSONs in chronological order.
    """
    all_scenes = []
    master_files = sorted(list(STAGE_C_DIR.glob(f"{BOOK_ID}-chunk-*-scenes-*.json")))
    print(f"Loading {len(master_files)} chunk files...")
    
    for mf in master_files:
        try:
            with open(mf, 'r') as f:
                data = json.load(f)
                chunk_scenes = data.get("scenes", [])
                # Ensure chunk_label is passed down if missing
                clabel = data.get("chunk_label")
                for s in chunk_scenes:
                    if "chunk_label" not in s: s["chunk_label"] = clabel
                    all_scenes.append(s)
        except Exception as e:
            print(f"Error reading {mf}: {e}")
            
    print(f"Total scenes collected: {len(all_scenes)}")
    return all_scenes

def partition_by_text(scenes: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Partitions scenes based on 'Capitolo' keyword in text_content.
    """
    partitions = {}
    current_label = "Intro"
    partitions[current_label] = []
    
    chapter_count = 0
    
    # regex for "Capitolo Primo", "Capitolo I", "Capitolo 1", etc.
    # We catch any line starting with "Capitolo" (case insensitive)
    cap_regex = re.compile(r"^Capitolo\s+", re.IGNORECASE)

    for s in scenes:
        text = s.get("text_content", "").strip()
        if cap_regex.match(text):
            chapter_count += 1
            current_label = f"Capitolo_{chapter_count:02d}"
            partitions[current_label] = []
            print(f"Detected {current_label} at scene {s.get('scene_id')} in {s.get('chunk_label')}: {text[:50]}...")
        
        partitions[current_label].append(s)
        
    return partitions

def get_silence(duration_ms: int, temp_dir: Path) -> Path:
    if duration_ms <= 0: return None
    s_file = temp_dir / f"silence_{duration_ms}ms.wav"
    if not s_file.exists():
        duration_sec = duration_ms / 1000.0
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(duration_sec), str(s_file)], stderr=subprocess.DEVNULL, check=True)
    return s_file

def stitch_partition(label: str, scenes: List[Dict]):
    if not scenes: return
    
    print(f"\n--- Stitching {label} ({len(scenes)} scenes) ---")
    partition_temp = TEMP_DIR / label
    partition_temp.mkdir(parents=True, exist_ok=True)
    
    output_file = OUTPUT_DIR / f"{BOOK_ID}-{label}.wav"
    manifest_path = partition_temp / "manifest.txt"
    
    with open(manifest_path, 'w') as f:
        for s in scenes:
            clean_title = s.get("clean_title", BOOK_ID)
            chunk = s.get("chunk_label", "chunk-000")
            sid = s.get("scene_id")
            
            # Local path in Brain cache
            local_wav = STAGE_D_DIR / clean_title / chunk / f"{sid}.wav"
            
            if local_wav.exists():
                f.write(f"file '{local_wav.resolve()}'\n")
                # Add pause
                p_ms = s.get("pause_after_ms", 80) # Default small pause
                if p_ms > 0:
                    sil = get_silence(p_ms, partition_temp)
                    if sil: f.write(f"file '{sil.resolve()}'\n")
            else:
                print(f"⚠️ MISSING: {local_wav}")

    # Run FFmpeg
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest_path),
            "-c", "copy", str(output_file)
        ], check=True, capture_output=True)
        print(f"✅ {label} DONE: {output_file}")
    except subprocess.CalledProcessError:
        print(f"FFmpeg copy failed for {label}. Retrying with encode...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest_path),
            "-ac", "1", "-ar", "44100", str(output_file)
        ], check=True, capture_output=True)
        print(f"✅ {label} DONE (Encoded): {output_file}")

if __name__ == "__main__":
    ensure_dirs()
    all_scenes = collect_all_scenes()
    chapter_map = partition_by_text(all_scenes)
    
    print(f"\nFound {len(chapter_map)} tracks to generate.")
    
    for label, scenes in chapter_map.items():
        stitch_partition(label, scenes)
    
    print("\n📦 RE-INDEXED STITCHING COMPLETE.")
