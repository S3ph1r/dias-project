import redis
import json
import os

def dump_registry():
    try:
        r = redis.Redis(host='192.168.1.120', port=6379, db=0, decode_responses=True)
        registry = r.hgetall('aria:registry:master')
        
        parsed = {}
        for k, v in registry.items():
            try:
                parsed[k] = json.loads(v)
            except:
                parsed[k] = v
                
        output_path = "/home/Projects/NH-Mini/sviluppi/dias/data/sampling/aria_catalog_dump.json"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(parsed, f, indent=2)
        print(f"DONE: {output_path}")
    except Exception as e:
        print(f"FAIL: {e}")

if __name__ == "__main__":
    dump_registry()
