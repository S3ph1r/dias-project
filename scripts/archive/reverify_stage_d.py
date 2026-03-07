import sys
import os
import json
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from src.common.redis_client import DiasRedis
from src.common.config import get_config
from src.stages.stage_d_voice_gen import StageDVoiceGeneratorProxy

def reverify_stage_d():
    print("=== DIAS Stage D Re-Verification (Luca Voice) ===")
    
    # 1. Load Stage C Output
    scene_path = "/home/Projects/NH-Mini/sviluppi/dias/data/stage_c/output/test_cronache_scene_000_20260305_004055.json"
    with open(scene_path, "r") as f:
        scene_msg = json.load(f)
    
    # Force voice to Luca
    scene_msg["voice_id"] = "luca"
    
    print(f"[*] Loaded scene: {scene_msg.get('scene_id')} (Book: {scene_msg.get('book_id')})")
    print(f"[*] Voice ID: {scene_msg['voice_id']}")
    
    # 2. Setup Stage D Proxy
    os.environ["REDIS_HOST"] = "192.168.1.120"
    config = get_config()
    redis_client = DiasRedis(host="192.168.1.120")
    
    if not redis_client.health_check():
        print("[!] ERROR: Redis not reachable on 192.168.1.120")
        return

    stage_d = StageDVoiceGeneratorProxy(redis_client=redis_client, config=config)
    
    print(f"\n[=>] Executing STAGE D: Sending task to ARIA...")
    res_d = stage_d.process(scene_msg)
    
    if res_d:
        print("\n[+] SUCCESS! Stage D Re-Verification complete 🎉")
        print(f"[+] Audio URL: {res_d.get('voice_path')}")
        print(f"[+] Duration: {res_d.get('voice_duration_seconds')}s")
        
        # Verify access
        print(f"\n[*] Verifying HTTP access...")
        os.system(f"curl -s -I {res_d.get('voice_path')} | grep HTTP")
    else:
        print("\n[!] FAILED: Stage D returned no result.")

if __name__ == "__main__":
    reverify_stage_d()
