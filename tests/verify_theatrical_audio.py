
import json
import redis
import time
from pathlib import Path

# Configurazione
REDIS_HOST = '192.168.1.120'
REDIS_PORT = 6379
VOICE_QUEUE = 'dias:q:4:voice'
ARIA_QUEUE_PREFIX = 'aria:q:tts:local' # We'll pattern match

def test_theatrical_payload():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    
    # Messaggio di test per Stage D
    test_msg = {
        "job_id": "test-theatrical-001",
        "book_id": "dan-simmons-hyperion",
        "scene_id": "scene-001",
        "text_content": "L'Architetto dei Fantasmi - era finalmente arrivato.",
        "tts_model_id": "qwen3-tts-1.7b",
        "voice_id": "luca"
    }
    
    print(f"🚀 Invio messaggio di test a {VOICE_QUEUE}...")
    r.rpush(VOICE_QUEUE, json.dumps(test_msg))
    
    print("⏳ In attesa di intercettare il payload per ARIA...")
    # Cerchiamo nelle code aria per un po'
    found = False
    for _ in range(10):
        # Cerchiamo code che iniziano con aria:q:tts:local
        keys = r.keys(f"{ARIA_QUEUE_PREFIX}:*")
        for key in keys:
            payload_raw = r.lpop(key)
            if payload_raw:
                payload = json.loads(payload_raw)
                if payload.get("job_id") == "dan-simmons-hyperion-scene-001":
                    print("✅ Intercettato payload per ARIA!")
                    print(json.dumps(payload, indent=4))
                    
                    # Verifiche Payload Leggero (Agnostico)
                    p = payload.get("payload", {})
                    # Path dove DIAS dovrebbe scaricare il file finale
                    local_path = Path("/home/Projects/NH-Mini/sviluppi/dias/data/projects/dan-simmons-hyperion/stages/stage_d/output/dan-simmons-hyperion-scene-001.wav")
                    # Rimuoviamolo se esiste per essere sicuri che il test sia valido
                    if local_path.exists(): local_path.unlink()
                    
                    assert p.get("subtalker_temperature") == 0.75, "Subtalker temp errata!"
                    assert p.get("temperature") == 0.7, "Temperature errata!"
                    assert p.get("voice_ref_text") is None, "voice_ref_text non dovrebbe essere inviato da DIAS (Agnostico)!"
                    assert p.get("voice_ref_audio_path") is None, "voice_ref_audio_path non dovrebbe essere inviato da DIAS (Agnostico)!"
                    
                    print("\n⏳ In attesa del completamento del task e del download locale...")
                    # Diamo tempo allo Stage D di scaricare il file
                    time.sleep(5)
                    if local_path.exists() and local_path.stat().st_size > 1000:
                        print(f"✅ Asset finale scaricato con successo in {local_path}!")
                        print("\n🔥 VERIFICA COMPLETATA CON SUCCESSO! 🔥")
                        found = True
                    else:
                        print(f"❌ Errore: Il file finale non è stato scaricato in {local_path}")
                    break
        if found: break
        time.sleep(1)
    
    if not found:
        print("❌ Fallimento: Payload non intercettato o download fallito entro il timeout.")

if __name__ == "__main__":
    test_theatrical_payload()
