import sys
import os
import json
import time
import uuid
from pathlib import Path
from datetime import datetime

# Add root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.stages.stage_d_voice_gen import StageDVoiceGeneratorProxy
from src.common.config import get_config

def main():
    print("🚀 DIAS V1.3 Shadow Test - Audio Generation")
    
    # Setup
    config = get_config()
    proxy = StageDVoiceGeneratorProxy()
    
    # Path del risultato di Stage C (V1.3 Balanced)
    input_file = Path("tests/results/result_v1.3_balanced_chunk-000-sub.json")
    
    if not input_file.exists():
        print(f"❌ V1.3 JSON not found: {input_file}")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    scenes = data.get("parsed_data", [])
    if not scenes:
        print("❌ No scenes found in input file.")
        return

    print(f"[*] Processing {len(scenes)} scenes with 'luca' voice...")
    
    book_id = "Cronache-del-Silicio-V1.3"
    job_id = str(uuid.uuid4())[:8]
    
    results = []

    for i, scene in enumerate(scenes):
        # Prepare message for Proxy
        msg = {
            "job_id": job_id,
            "book_id": book_id,
            "scene_id": f"v1.3-{i:03d}",
            "scene_label": scene.get("scene_label", "No Label"),
            "text_content": scene.get("clean_text"),
            "qwen3_instruct": scene.get("qwen3_instruct"),
            "voice_id": "luca",
            "chunk_label": "shadow-test"
        }
        
        print(f"\n--- 📢 GENERATION: {msg['scene_id']} | {msg['scene_label']} ---")
        print(f"Text: {msg['text_content'][:60]}...")
        
        start_time = time.time()
        try:
            res = proxy.process(msg)
            if res and res.get("voice_status") == "completed":
                duration = time.time() - start_time
                audio_path = res.get("voice_path")
                print(f"✅ Success! Audio: {audio_path} ({duration:.2f}s)")
                results.append(audio_path)
            else:
                print(f"❌ Failed: {res.get('error') if res else 'No result'}")
        except Exception as e:
            print(f"❌ Exception: {e}")

    print("\n" + "="*50)
    print(f"✅ Shadow Test Completed. Generated {len(results)}/{len(scenes)} WAVs.")
    if results:
        print(f"Sample WAV: {results[0]}")
    print("="*50)

if __name__ == "__main__":
    main()
