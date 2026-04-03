#!/usr/bin/env python3
import os
import json
import subprocess
import argparse
from pathlib import Path

# --- CONFIG ---
BASE_DIR = Path("/home/Projects/NH-Mini/sviluppi/dias")
MASTER_JSON = BASE_DIR / "data" / "projects" / "Cronache-del-Silicio" / "stages" / "stage_c" / "output" / "Cronache-del-Silicio-chunk-000-micro-000-scenes.json"

def get_silence(duration_ms: int, temp_dir: Path) -> Path:
    if duration_ms <= 0: return None
    s_file = temp_dir / f"silence_{duration_ms}ms_24k.wav"
    if not s_file.exists():
        duration_sec = duration_ms / 1000.0
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(duration_sec), str(s_file)], stderr=subprocess.DEVNULL, check=True)
    return s_file

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=str, required=True, help="Folder containing scene wavs")
    parser.add_argument("--out", type=str, required=True, help="Output wav file")
    args = parser.parse_args()

    src_dir = Path(args.src)
    output_file = Path(args.out)
    analysis_dir = output_file.parent

    with open(MASTER_JSON, 'r') as f:
        data = json.load(f)
    
    target_scenes = [
        "chunk-000-micro-000-scene-009", 
        "chunk-000-micro-000-scene-010",
        "chunk-000-micro-000-scene-011",
        "chunk-000-micro-000-scene-012"
    ]
    scenes = [s for s in data["scenes"] if s["scene_id"] in target_scenes]
    
    inputs = []
    for s in scenes:
        scene_file = src_dir / f"Cronache-del-Silicio-{s['scene_id']}.wav"
        if not scene_file.exists():
            print(f"Error: {scene_file} not found")
            continue
        inputs.append(str(scene_file.resolve()))
        
        pause_ms = s.get("pause_after_ms", 0)
        if pause_ms > 0:
            silence = get_silence(pause_ms, analysis_dir)
            inputs.append(str(silence.resolve()))

    if not inputs:
        print("No inputs found!")
        return

    # Build filter_complex string: [0:a][1:a]...concat=n=N:v=0:a=1[outa]
    filter_str = "".join([f"[{i}:a]" for i in range(len(inputs))])
    filter_str += f"concat=n={len(inputs)}:v=0:a=1[outa]"

    cmd = ["ffmpeg", "-y"]
    for inp in inputs:
        cmd.extend(["-i", inp])
    cmd.extend(["-filter_complex", filter_str, "-map", "[outa]", "-ac", "1", "-ar", "24000", str(output_file)])

    print(f"Merging {len(inputs)} segments from {src_dir} into {output_file}...")
    subprocess.run(cmd, check=True)
    print("✅ COMPLETED.")

if __name__ == "__main__":
    run()
