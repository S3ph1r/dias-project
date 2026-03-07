import sys
import os
import json
import time
import base64
from pathlib import Path
from datetime import datetime

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from src.stages.stage_d_voice_gen import StageDVoiceGeneratorProxy
from src.common.config import get_config

def main():
    print("🚀 DIAS Stage D - Phase 5 Audio Verification")
    print("Testing: Audio Generation for Scenes 0, 1, 2 with Luca voice")
    
    # Setup
    config = get_config()
    stage_d = StageDVoiceGeneratorProxy()
    
    # Path del risultato di Stage C
    input_file = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_c/test_runs/test_phase5_20260305_183348.json")
    
    if not input_file.exists():
        print(f"❌ Stage C test output not found: {input_file}")
        return

    print(f"[*] Loading Stage C scenes from: {input_file.name}")
    with open(input_file, 'r', encoding='utf-8') as f:
        stage_c_result = json.load(f)
    
    scenes = stage_c_result.get("scenes", [])
    if not scenes:
        print("❌ No scenes found in input file.")
        return

    # Selezioniamo solo le prime 3 scene
    test_scenes = scenes[:3]
    print(f"[*] Processing {len(test_scenes)} scenes...")

    output_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_d/test_runs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for i, scene in enumerate(test_scenes):
        scene_id = scene.get("scene_id")
        print(f"\n--- 📢 GENERAZIONE AUDIO: {scene_id} ({scene.get('scene_label')}) ---")
        
        # Override voice to angelo
        scene["voice_id"] = "angelo"
        
        print(f"Instruct: {scene.get('qwen3_instruct')}")
        print(f"Text: {scene.get('text_content')[:100]}...")
        
        start_time = time.time()
        
        # Esegui Stage D (Invia ad ARIA e attende il callback)
        try:
            result = stage_d.process(scene)
            
            if result and result.get("status") == "success":
                duration = time.time() - start_time
                print(f"✅ Success! Audio generated in {duration:.2f}s")
                
                # Salvataggio del WAV
                audio_path = Path(result["audio_path"])
                dest_path = output_dir / f"test_phase5_{timestamp}_{scene_id}.wav"
                
                # Copy the file (it's already saved by stage_d, but let's make a versioned copy in test_runs)
                import shutil
                shutil.copy2(audio_path, dest_path)
                
                print(f"[*] WAV saved to: {dest_path}")
            else:
                print(f"❌ Failed to generate audio for {scene_id}: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            print(f"❌ Error during processing {scene_id}: {e}")

    print("\n" + "="*50)
    print(f"🚀 Audio generation test completed.")
    print(f"Check outputs in: {output_dir}")
    print("="*50)

if __name__ == "__main__":
    main()
