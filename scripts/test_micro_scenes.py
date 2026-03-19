import json
import redis
import os
import time
from pathlib import Path

# Configurazione
REDIS_HOST = "192.168.1.120"
REDIS_PORT = 6379
VOICE_QUEUE = "dias:queue:4:voice"
PROJECT_ID = "Cronache-del-Silicio"
CHUNK_LABEL = "chunk-000"
VOICE_ID = "luca"
TTS_MODEL_ID = "qwen3-tts-1.7b"
NUM_SCENES = 10

# Directory degli output di Stage C
BASE_DIR = Path(__file__).resolve().parent.parent
STAGE_C_OUTPUT = BASE_DIR / "data" / "stage_c" / "output"

def run_test():
    print(f"🚀 Avvio test Micro-Scele su {PROJECT_ID} ({CHUNK_LABEL})")
    print(f"   Voice: {VOICE_ID} | Backend: {TTS_MODEL_ID}")
    
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    
    # PULIZIA REGISTRO: Rimuove lo stato "COMPLETED" per permettere il re-test
    registry_key = f"dias:registry:{PROJECT_ID}"
    print(f"🧹 Pulizia registro per {PROJECT_ID} (scene 0-9)...")
    for i in range(NUM_SCENES):
        scene_id = f"scene-{i:03d}"
        r.hdel(registry_key, scene_id)
    
    # Trova i file delle scene
    # Pattern: Cronache-del-Silicio-chunk-000-scene-00[0-9]-*.json
    scenes_files = sorted(list(STAGE_C_OUTPUT.glob(f"{PROJECT_ID}-{CHUNK_LABEL}-scene-00[0-9]-*.json")))
    
    if not scenes_files:
        print(f"❌ Nessun file trovato in {STAGE_C_OUTPUT}")
        return

    print(f"📦 Trovate {len(scenes_files)} micro-scene. Invio le prime {NUM_SCENES}...")

    for i, file_path in enumerate(scenes_files[:NUM_SCENES]):
        with open(file_path, 'r', encoding='utf-8') as f:
            scene_data = json.load(f)
        
        # Override per il test
        scene_data["voice_id"] = VOICE_ID
        scene_data["tts_model_id"] = TTS_MODEL_ID
        
        # Pulizia metadati vecchi per evitare confusione
        if "dialogue_notes" in scene_data:
            scene_data["dialogue_notes"] = f"TEST: {VOICE_ID} custom voice"

        print(f"   [{i}] Pushing {file_path.name} to {VOICE_QUEUE}...")
        r.lpush(VOICE_QUEUE, json.dumps(scene_data, ensure_ascii=False))
        
    print(f"✅ Fatto. {min(len(scenes_files), NUM_SCENES)} task inviati a Redis.")
    print(f"Monitora l'Orchestrator di ARIA e il log di Qwen3 server sul PC Gaming.")

if __name__ == "__main__":
    run_test()
