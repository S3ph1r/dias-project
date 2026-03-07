import os
import json
import sys
import time
from pathlib import Path

# Aggiungi src al path per gli import
sys.path.append(str(Path(__file__).parent.parent))

from src.stages.stage_d_voice_gen import StageDVoiceGeneratorProxy
from src.common.redis_client import DiasRedis
from src.common.config import get_config

def test_e2e_stage_d():
    print("=== DIAS to ARIA End-to-End Test (Stage D) ===")
    
    # 1. Carica dati Stage C
    stage_c_path = "/home/Projects/NH-Mini/sviluppi/dias/data/stage_c/output/surgical_20260302_025345_scene_000_20260302_044218.json"
    print(f"[*] Caricamento dati Stage C da: {stage_c_path}")
    with open(stage_c_path, "r", encoding="utf-8") as f:
        message = json.load(f)
    
    # 2. Configura Redis per LXC 190 -> LXC 120
    os.environ["REDIS_HOST"] = "192.168.1.120"
    config = get_config()
    redis_client = DiasRedis(host="192.168.1.120")
    
    if not redis_client.health_check():
        print("[!] ERRORE: Redis non raggiungibile su 192.168.1.120")
        return

    # 3. Inizializza Stage D
    # Passiamo il redis_client già configurato
    stage_d = StageDVoiceGeneratorProxy(redis_client=redis_client, config=config)
    
    # 4. Processa il messaggio (QUESTO INVIA AD ARIA E ASPETTA)
    print(f"[*] Elaborazione scena '{message.get('scene_id')}'...")
    print(f"[*] Testo: {message.get('text_content')[:100]}...")
    
    # PULIZIA PREVENTIVA: Elimina eventuali vecchi messaggi di callback per evitare di leggere risultati obsoleti
    job_id = message.get("job_id")
    scene_id = message.get("scene_id")
    callback_key = f"dias:callback:stage_d:{job_id}:{scene_id}"
    redis_client.client.delete(callback_key)
    print(f"[*] Callback key '{callback_key}' pulita.")
    
    start_time = time.time()
    result = stage_d.process(message)
    end_time = time.time()
    
    if result:
        print("\n[+] SUCCESS! Stage D completato.")
        print(f"[+] Output WAV URL: {result.get('voice_path')}")
        print(f"[+] Durata audio: {result.get('voice_duration_seconds')}s")
        print(f"[*] Tempo di elaborazione (proxy): {end_time - start_time:.2f}s")
        
        # Verifica accessibilità URL
        print(f"[*] Verificando accessibilità URL via curl...")
        os.system(f"curl -I {result.get('voice_path')}")
    else:
        print("\n[!] FALLITO: Lo Stage D non ha restituito risultati.")

if __name__ == "__main__":
    test_e2e_stage_d()
