import redis
import json
import time
import uuid

def test_aria_qwen():
    r = redis.Redis(host='192.168.1.120', port=6379, decode_responses=True)
    
    test_id = f"test-{uuid.uuid4().hex[:8]}"
    callback_key = f"dias:callback:test:{test_id}"
    
    # Payload compatible with Stage D -> ARIA flow
    aria_task = {
        "job_id": f"manual-test-{test_id}",
        "client_id": "manual_test_lxc190",
        "model_type": "tts",
        "model_id": "qwen3-tts-1.7b",
        "payload": {
            "text": "Questa è una prova tecnica per verificare che il backend di Aria e il modello Qwen funzionino correttamente dall'ambiente Conda su PC Gaming. La voce selezionata è Luca.",
            "voice_id": "luca",
            "instruct": "Warm Italian male voice, professional audiobook narrator, calm and measured.",
            "temperature": 0.7,
            "top_p": 0.8,
            "output_format": "wav"
        },
        "callback_key": callback_key,
        "timeout_seconds": 300
    }
    
    queue = "gpu:queue:tts:qwen3-tts-1.7b"
    print(f"Pushing test task to {queue}...")
    print(f"Callback key: {callback_key}")
    
    r.lpush(queue, json.dumps(aria_task))
    
    print("Waiting for response (timeout 120s)...")
    # Using blpop since Stage D also uses it for callback keys (which are treated as a list of 1 element)
    result = r.brpop(callback_key, timeout=120)
    
    if result:
        _, data = result
        response = json.loads(data)
        print("\n--- RESPONSE RECEIVED ---")
        print(json.dumps(response, indent=2))
        if response.get("status") == "done":
            print(f"\nSUCCESS! Audio generated at: {response.get('output', {}).get('audio_url')}")
        else:
            print(f"\nFAILED: {response.get('error')}")
    else:
        print("\nTIMEOUT: No response from ARIA.")

if __name__ == "__main__":
    test_aria_qwen()
