import redis
import json
import uuid
import time
import os

# Configurazione Redis (Nodo 120)
REDIS_HOST = '192.168.1.120'
REDIS_PORT = 6379

def test_custom_voice_swap():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    
    job_id = f"test-customvoice-{int(time.time())}"
    callback_key = f"dias:callback:test:{job_id}"
    
    # Payload per Qwen3-TTS CustomVoice (Head-to-Head Test)
    task = {
        "job_id": job_id,
        "client_id": "manual_test_cli",
        "model_type": "tts",
        "model_id": "qwen3-tts-custom",
        "payload": {
            "job_id": job_id,
            "text": "\"Un worm?\" chiese Naila, i suoi occhi che si illuminavano di comprensione. \"Più di un worm. Un 'fiore'. Un codice che, una volta rilasciato, non attaccherà i sistemi, ma vi crescerà dentro, aprendo piccole, sicure porte di accesso anonimo alla rete di Aethelburg. Non ruberemo i dati della gente. Daremo loro un modo per condividere i propri, al sicuro. Lo rilasceremo non su tutta la rete, ma in un solo posto: i 'Giardini' della OSD. Lo pianteremo tra le persone che hanno più bisogno di una voce. I Giardinieri di Dati.\" Liam lo guardò, sbalordito. \"Stai trasformando la più grande rete di sfruttamento della OSD nella base per la nostra rivoluzione.\" \"Esatto,\" disse Kaelen. \"Useremo la loro stessa infrastruttura contro di loro.\"",
            "voice_id": "ryan",
            "language": "Italian",
            "instruct": "Read with natural, fluid rhythm and revolutionary conviction. The tone is strategic and intense, like a conspiratorial whisper, but the pace must remain steady and conversational. Focus on clear, organic delivery.",
            "temperature": 0.7,
            "top_p": 0.9,
            "subtalker_temperature": 0.9,
            "subtalker_top_p": 1.0
        },
        "callback_key": callback_key,
        "timeout_seconds": 600
    }
    
    queue_key = "gpu:queue:tts:qwen3-tts-custom"
    
    print(f"Sottomissione task {job_id} alla coda {queue_key}...")
    r.lpush(queue_key, json.dumps(task))
    
    print(f"In attesa del risultato su {callback_key} (timeout 400s)...")
    result = r.brpop(callback_key, timeout=400)
    
    if result:
        res_data = json.loads(result[1])
        print("\n✅ RISULTATO RICEVUTO:")
        print(json.dumps(res_data, indent=2))
        if res_data.get("status") == "done":
            print(f"\n🎯 URL AUDIO: {res_data.get('output', {}).get('audio_url')}")
        else:
            print(f"\n❌ ERRORE: {res_data.get('error')}")
    else:
        print("\n❌ TIMEOUT: Nessuna risposta da ARIA.")

if __name__ == "__main__":
    test_custom_voice_swap()
