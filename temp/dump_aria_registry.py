import redis
import json
import os

try:
    r = redis.Redis(host='192.168.1.120', port=6379, db=0, decode_responses=True)
    registry = r.hgetall('aria:registry:master')
    
    # Pre-processing for better readability (parse JSON values if they are strings)
    parsed_registry = {}
    for k, v in registry.items():
        try:
            parsed_registry[k] = json.loads(v)
        except:
            parsed_registry[k] = v
            
    output_path = "/home/Projects/NH-Mini/sviluppi/dias/temp/aria_registry_dump.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(parsed_registry, f, indent=2)
    
    print(f"SUCCESS: Registry dumped to {output_path}")
except Exception as e:
    print(f"ERROR: {e}")
