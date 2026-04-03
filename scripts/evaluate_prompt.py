#!/usr/bin/env python3
"""
Sandbox Tool: Evaluate and compare different Stage C Prompts on Gemini.
Usage: python scripts/evaluate_prompt.py tests/fixtures/chunk-000-phonetics.json config/prompts/stage_c/v1.0_base.yaml config/prompts/stage_c/v1.1_phonetics.yaml
"""
import sys
import json
import yaml
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.config import get_config
from src.common.gateway_client import GatewayClient

def load_prompt(filepath: str) -> dict:
    with open(filepath, 'r') as f:
        return yaml.safe_load(f)

def extract_fixture_data(fixture_path: str) -> tuple:
    with open(fixture_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    emotion = data.get("block_analysis", {}).get("primary_emotion", "Neutral")
    
    # The actual text content is stored in the Stage A output chunk
    import glob
    book_id = data.get("book_id", "Cronache-del-Silicio")
    chunk_id = fixture_path.split("chunk-")[1].split("-")[0]
    
    # Try match by book_id and chunk_id
    pattern = f"data/stage_a/output/{book_id}-chunk-{chunk_id}-*.json"
    stage_a_files = glob.glob(pattern)
    
    text = ""
    if stage_a_files:
        with open(stage_a_files[0], 'r', encoding='utf-8') as fa:
            a_data = json.load(fa)
            text = a_data.get("block_text", "")
    else:
        print(f"DEBUG: No Stage A file found for pattern: {pattern}")
            
    return text, emotion

def run_evaluation(prompt_data: dict, client: GatewayClient, model_name: str, text: str, emotion: str) -> dict:
    print(f"\nEvaluating: {prompt_data.get('description', 'Unknown')}")
    prompt_template = prompt_data.get('prompt_template', '')
    
    prompt = prompt_template.replace("{emotion_description}", emotion).replace("{text_content}", text)
    
    start_time = time.time()
    
    # Using the official ARIA Gateway (Network path)
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    
    print("Calling Google Gemini via ARIA Gateway...")
    response = client.generate_content(
        contents=contents,
        model_id=model_name,
        config={"temperature": 0.7}
    )
    
    elapsed = time.time() - start_time
    
    if response.get("status") == "error":
        print(f"❌ Gateway Error: {response.get('error')}")
        return {"time_s": round(elapsed, 2), "is_valid_json": False, "raw_response": response.get('error'), "parsed_data": None, "tokens": "N/A"}
        
    response_text = response["output"].get("text", "")
    
    # Token usage (Gateway metadata if available)
    tokens_used = response.get("output", {}).get("metadata", {}).get("token_count", "N/A via Gateway")
    
    # Try parsing JSON
    import re
    clean_json = response_text
    if "```json" in clean_json:
        match = re.search(r"```json\s*(.*?)\s*```", clean_json, re.DOTALL)
        if match: clean_json = match.group(1)
        
    try:
        parsed = json.loads(clean_json)
        is_valid = True
    except json.JSONDecodeError as e:
        parsed = None
        is_valid = False
        print(f"❌ JSON Decode Error: {e}")
        
    return {
        "time_s": round(elapsed, 2),
        "tokens": tokens_used,
        "is_valid_json": is_valid,
        "raw_response": response_text[:300] + "..." if not is_valid else "Valid JSON",
        "parsed_data": parsed
    }

def print_comparison(fixture_path: str, prompt_files: list):
    config = get_config()
    model_name = config.google.model_flash_lite
    
    from src.common.redis_client import DiasRedis
    redis_client = DiasRedis(
        host=config.redis.host,
        port=config.redis.port,
        db=config.redis.db,
        decode_responses=config.redis.decode_responses
    )
    
    print("Initializing GatewayClient targeting ARIA via Redis...")
    client = GatewayClient(redis_client)
    
    print(f"Extracting test data from {fixture_path}...")
    text, emotion = extract_fixture_data(fixture_path)
    print(f"Payload Size: {len(text)} characters. Base Emotion: {emotion}")
    
    results = {}
    
    for fw in prompt_files:
        p_data = load_prompt(fw)
        res = run_evaluation(p_data, client, model_name, text, emotion)
        results[fw] = res
        
        print(f"\n--- Results for {fw} ---")
        print(f"Time: {res['time_s']}s")
        print(f"Valid JSON: {res['is_valid_json']}")
        
        # Save to tests/results/
        results_dir = Path("tests/results")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        prompt_name = Path(fw).stem
        fixture_name = Path(fixture_path).stem
        result_file = results_dir / f"result_{prompt_name}_{fixture_name}.json"
        
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
        
        print(f"Full JSON saved to: {result_file}")
        
        if res['parsed_data']:
            print(f"Scenes Generated: {len(res['parsed_data'])}")
            print("Sample Output (Scene 1):")
            print(json.dumps(res['parsed_data'][0], indent=2))
        else:
            print("Raw Response Output:")
            print(res['raw_response'])

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/evaluate_prompt.py <path_to_fixture_json> <prompt_yaml_1> [prompt_yaml_2 ...]")
        sys.exit(1)
    
    fixture = sys.argv[1]
    prompt_files = sys.argv[2:]
    print_comparison(fixture, prompt_files)
