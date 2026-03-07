import redis
import json
import uuid
import time
import base64
import os

def test_qwen_direct():
    r = redis.Redis(host='192.168.1.120', port=6379, db=0)
    job_id = f"test_job_{int(time.time())}"
    scene_id = "scene_001"
    queue = "gpu:queue:tts:qwen3-tts-1.7b"
    callback_key = f"dias:callback:stage_d:{job_id}:{scene_id}"
    
    # Testo in stile Luca Ward (Pulp Fiction vibe)
    text_to_speak = "Il cammino dell'uomo timorato è minacciato da ogni parte dalle iniquità degli esseri egoisti. (break) Ma benedetto sia colui che, nel nome della carità e della buona volontà, conduce i deboli attraverso la valle delle tenebre."
    
    payload = {
        "job_id": job_id,
        "client_id": "direct_test",
        "model_type": "tts",
        "model_id": "qwen3-tts-1.7b",
        "payload": {
            "text": text_to_speak,
            "voice_id": "luca",
            "instruct": "Warm Italian narrator voice, professional audiobook narrator, suspenseful and calm pace, cinematic intensity.",
            "temperature": 0.7,
            "top_p": 0.8,
            "output_format": "wav"
        },
        "callback_key": callback_key,
        "timeout_seconds": 300
    }
    
    print(f"[*] Cancello eventuale callback precedente: {callback_key}")
    r.delete(callback_key)
    
    print(f"[*] Sottomissione task TTS ad ARIA sulla coda: {queue}")
    r.lpush(queue, json.dumps(payload))
    
    print(f"[*] In attesa di risultato su {callback_key} (timeout 400s)...")
    print(f"[*] NOTA: il primo avvio potrebbe richiedere 1-2 minuti per caricare il modello da 1.7B in VRAM.")
    
    start = time.time()
    while time.time() - start < 400:
        res = r.brpop(callback_key, timeout=5)
        if res:
            _, data_b = res
            data = json.loads(data_b)
            if data.get("status") == "done":
                audio_url = data.get("output", {}).get("audio_url")
                print(f"\n[+] SUCCESS! Audio generato correttamente 🎉")
                print(f"[+] Audio URL: {audio_url}")
                print(f"[+] Durata restituita: {data.get('output', {}).get('duration_seconds')}s")
                
                # Check HTTP access
                print(f"\n[*] Verificando accessibilità WAV asset server (curl locale)...")
                os.system(f"curl -s -I {audio_url} | grep HTTP")
            else:
                print(f"\n[-] Errore dal backend ARIA: {data.get('error')}")
            return
        
    print("\n[-] Timeout: nessuna risposta dall'Orchestratore.")

if __name__ == "__main__":
    test_qwen_direct()
