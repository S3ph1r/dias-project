import redis
import json

def check_registry():
    try:
        # Nodo ARIA Redis
        r = redis.Redis(host='192.168.1.120', port=6379, decode_responses=True)
        reg_raw = r.get('aria:registry:master')
        if not reg_raw:
            print("Registro 'aria:registry:master' non trovato su Redis.")
            return

        reg = json.loads(reg_raw)
        assets = reg.get('assets', {})
        
        counts = {k: len(assets.get(k, {})) for k in ['pad', 'amb', 'sfx', 'sting', 'voices']}
        
        print("--- Riepilogo Asset nel Registro ARIA ---")
        print(json.dumps(counts, indent=2))
        
        print("\n--- Esempi canonical_id per categoria ---")
        for cat in ['pad', 'amb', 'sfx', 'sting']:
            items = assets.get(cat, {})
            print(f"\n[{cat.upper()}] ({len(items)} asset):")
            if items:
                # Mostra i primi 10 canonical_id
                for cid in list(items.keys())[:10]:
                    tags = items[cid].get('tags', [])
                    print(f"  - {cid} | tags: {tags}")
            else:
                print("  (Nessun asset in questa categoria)")

    except Exception as e:
        print(f"Errore durante l'interrogazione di Redis: {e}")

if __name__ == '__main__':
    check_registry()
