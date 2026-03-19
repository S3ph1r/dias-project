#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.redis_factory import get_redis_client

def push_single_scene(scene_file_path: str):
    path = Path(scene_file_path)
    if not path.exists():
        print(f"Error: File {scene_file_path} not found.")
        return

    try:
        with open(path, 'r', encoding='utf-8') as f:
            scene_data = json.load(f)
        
        # Force real Redis for E2E testing
        os.environ["MOCK_SERVICES"] = "false"
        redis_client = get_redis_client()
        queue_name = "dias:queue:4:voice"
        
        redis_client.push_to_queue(queue_name, scene_data)
        print(f"Successfully pushed {path.name} to {queue_name}")
        print("Now start Stage D Voice Generator on LXC 201 to process it.")
        
    except Exception as e:
        print(f"Failed to push scene: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/test_single_scene.py <path_to_scene_json>")
        sys.exit(1)
    
    push_single_scene(sys.argv[1])
