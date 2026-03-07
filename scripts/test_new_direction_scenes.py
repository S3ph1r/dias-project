import sys
import os
import json
import logging
from pathlib import Path

# Aggiungiamo il path src al Python path
sys.path.insert(0, "/home/Projects/NH-Mini/sviluppi/dias")

from src.stages.stage_d_voice_gen import StageDVoiceGeneratorProxy

# Setup logging
logging.basicConfig(level=logging.INFO)

def test_new_direction():
    test_file = "/home/Projects/NH-Mini/sviluppi/dias/scripts/test_new_direction_scenes.json"
    if not os.path.exists(test_file):
        print(f"Error: {test_file} not found.")
        return

    with open(test_file, "r") as f:
        scenes = json.load(f)
    
    stage_d = StageDVoiceGeneratorProxy()
    
    for scene in scenes:
        scene_id = scene.get("scene_id")
        print(f"\n--- 📢 GENERAZIONE AUDIO (NUOVA REGIA): {scene_id} ---")
        
        # Forza voce luca per coerenza test
        scene["voice_id"] = "luca"
        
        print(f"Instruct: {scene.get('qwen3_instruct')}")
        
        result = stage_d.process(scene)
        
        if result:
            print(f"✅ Successo: {scene_id}")
            print(f"   URL: {result.get('output', {}).get('audio_url')}")
        else:
            print(f"❌ Fallimento: {scene_id}")

if __name__ == "__main__":
    test_new_direction()
