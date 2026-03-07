import os
import json
import sys
import time
from pathlib import Path

# Aggiungi src al path per gli import
sys.path.append(str(Path(__file__).parent.parent))

from src.common.redis_client import DiasRedis
from src.common.config import get_config
from src.stages.stage_a_text_ingester import TextIngester
from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.stages.stage_c_scene_director import SceneDirector
from src.stages.stage_d_voice_gen import StageDVoiceGeneratorProxy

def test_pipeline_single_chunk():
    print("=== DIAS E2E Test (Single Chunk) ===")
    
    os.environ["REDIS_HOST"] = "192.168.1.120"
    config = get_config()
    
    # 1. Setup Redis (Mocked pushing to prevent background workers from stealing chunks)
    redis_client = DiasRedis(host="192.168.1.120")
    if not redis_client.health_check():
        print("[!] ERRORE: Redis non raggiungibile su 192.168.1.120")
        return
        
    original_push = redis_client.push_to_queue
    
    # Array per salvare i messaggi intercettati
    stage_a_messages = []
    
    def mock_push_to_queue(queue_name, data):
        stage_a_messages.append(data)
        print(f"[*] Intercettato messaggio in uscita da Stage A per {queue_name} (block_id: {data.get('block_id')})")
        # Non pushiamo sul vero Redis per non far partire l'elaborazione di tutti i 32 blocchi
        
    redis_client.push_to_queue = mock_push_to_queue
    
    # 2. Run Stage A
    pdf_path = "/home/Projects/NH-Mini/sviluppi/dias/docs/Cronache del Silicio 2.0.pdf"
    if not os.path.exists(pdf_path):
        print(f"[!] ERRORE: PDF non trovato in {pdf_path}")
        return
        
    print(f"\n[=>] Esecuzione STAGE A: Ingresso PDF...")
    stage_a = TextIngester()
    # Sovrascriviamo l'istanza interna redis per intercettare il push
    stage_a.redis = redis_client
    
    msg_a = {
        "book_id": "test_cronache",
        "title": "Cronache del Silicio",
        "file_path": pdf_path,
        "original_filename": "Cronache del Silicio 2.0.pdf"
    }
    res_a = stage_a.process(msg_a)
    print(f"[+] Stage A completato: {res_a}")
    
    if not stage_a_messages:
        print("[!] Nessun blocco generato dallo Stage A.")
        return
        
    # Prendiamo solo il primo blocco (chunk)
    first_block_msg = stage_a_messages[0]
    print(f"\n[*] Selezionato il primo chunk (block_id: {first_block_msg.get('block_id')}) per test.")
    
    # 3. Run Stage B sul primo blocco
    stage_b_messages = []
    def mock_push_to_queue_b(queue_name, data):
        if queue_name == "dias_stage_c_queue":
            stage_b_messages.append(data)
            print(f"[*] Intercettato messaggio in uscita da Stage B per Stage C (job_id: {data.get('job_id')})")
    redis_client.push_to_queue = mock_push_to_queue_b
    
    print(f"\n[=>] Esecuzione STAGE B: Analisi Semantica...")
    stage_b = StageBSemanticAnalyzer(redis_client=redis_client)
    res_b = stage_b.process(first_block_msg)
    print(f"[+] Stage B completato.")
    
    if not stage_b_messages:
        print("[!] Nessun messaggio generato dallo Stage B per lo Stage C.")
        return
        
    first_b_msg = stage_b_messages[0]
    # Re-iniettiamo manualmentre book_id e block_id che Stage C si aspetta dentro al payload se non ci fossero
    first_b_msg['book_id'] = first_block_msg.get('book_id')
    first_b_msg['block_id'] = first_block_msg.get('block_id')

    # 4. Run Stage C
    stage_c_messages = []
    def mock_push_to_queue_c(queue_name, data):
        # Stage C pushebbe a 'dias:queue:4:voice_gen' (se passata nel config, internamente potrebbe variare)
        if "dias:queue:4:voice_gen" in queue_name or "stage_d" in queue_name or queue_name == "dias_stage_d_queue":
            stage_c_messages.append(data)
            print(f"[*] Intercettata scena in uscita da Stage C per Stage D (scene_id: {data.get('scene_id')})")
    redis_client.push_to_queue = mock_push_to_queue_c
    
    print(f"\n[=>] Esecuzione STAGE C: Regia Scene (genera script con pause e marker)...")
    stage_c = SceneDirector()
    stage_c.redis = redis_client
    # L'output queue hardcoded nel costruttore di StageC è output_queue="dias:queue:3:scene_director" che in realtà dovrebbe essere la 4 per D,
    # vediamo a dove pusha veramente. Nello script usa la self.output_queue interna definita dal BaseStage. Assicuriamoci che venga intercettata settandola.
    stage_c.output_queue = "dias:queue:4:voice_gen"
    
    # Process Item
    res_c = stage_c.process_item(first_b_msg)
    
    if not res_c or not stage_c_messages:
        print("[!] Fallimento in Stage C o nessuna scena generata.")
        return
        
    first_scene_msg = stage_c_messages[0]
    first_scene_msg["voice_id"] = "luca"
    print(f"\n[*] Selezionata prima scena (scene_id: {first_scene_msg.get('scene_id')}) con voce: luca")
    
    # 5. Run Stage D
    redis_client.push_to_queue = original_push
    print(f"\n[=>] Esecuzione STAGE D: Generazione Voce (ARIA Proxy)...")
    
    # Pulizia preliminare della callback key per sicurezza (come nell'altro test E2E)
    job_id = first_scene_msg.get("job_id")
    scene_id = first_scene_msg.get("scene_id")
    callback_key = f"dias:callback:stage_d:{job_id}:{scene_id}"
    redis_client.client.delete(callback_key)
    
    stage_d = StageDVoiceGeneratorProxy(redis_client=redis_client, config=config)
    start_time = time.time()
    res_d = stage_d.process(first_scene_msg)
    end_time = time.time()
    
    if res_d:
        print("\n[+] SUCCESS! Test E2E Single Chunk completato 🎉")
        print(f"[+] WAV Generato URL: {res_d.get('voice_path')}")
        print(f"[+] Durata: {res_d.get('voice_duration_seconds')}s")
        print(f"[*] Tempo impiegato (compreso chunking TTS pre-sintesi): {end_time - start_time:.2f}s")
        
        # Verifica accessibilità URL
        print(f"\n[*] Verificando accessibilità WAV asset server (curl locale)...")
        os.system(f"curl -s -I {res_d.get('voice_path')} | grep HTTP")
    else:
        print("\n[!] FALLITO in Stage D. Qualcosa e' andato storto lato ARIA o Redis.")


if __name__ == "__main__":
    test_pipeline_single_chunk()
