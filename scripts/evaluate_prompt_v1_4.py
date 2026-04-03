#!/usr/bin/env python3
"""
Test V1.4 Contextual Prompt — Single Chunk
==========================================
Legge Stage A + Stage B per chunk-000 di Cronache-del-Silicio,
chiama Stage C con il nuovo prompt V1.4, salva il JSON delle scene
in tests/results/ e stampa un confronto con V1.3 per le scene 006-008.

USO:
    cd /home/Projects/NH-Mini/sviluppi/dias
    python3 scripts/evaluate_prompt_v1_4.py
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.config import get_config
# from src.stages.stage_c_scene_director import StageCSceneDirector  <-- removed broken import

# ── Input files ────────────────────────────────────────────────────────
STAGE_A_FILE = Path("data/stage_a/output/Test-Phonetics-V1-chunk-000-sub.json")

# Stage B output per Cronache-del-Silicio chunk-000
STAGE_B_FILE = Path("data/stage_b/output/Cronache-del-Silicio-chunk-000-20260315_090906.json")

# V1.3 result to compare against
V1_3_FILE = Path("tests/results/result_v1.3_balanced_chunk-000-sub.json")

OUTPUT_DIR = Path("tests/results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

COMPARE_SCENES = [5, 6, 7]  # 0-indexed → scena 006, 007, 008


def main():
    print("=" * 60)
    print("🎬 DIAS Stage C — Prompt V1.4 Evaluation")
    print(f"   Config: dias.yaml → stage_c_prompt_path")
    print("=" * 60)

    # Load Stage A
    if not STAGE_A_FILE.exists():
        print(f"❌ Stage A file not found: {STAGE_A_FILE}")
        sys.exit(1)
    with open(STAGE_A_FILE, "r", encoding="utf-8") as f:
        stage_a = json.load(f)

    text_content = stage_a.get("block_text", "")
    block_id = stage_a.get("block_id", "block_sub_000")
    book_id = "Test-Phonetics-V1.4"

    # Load Stage B
    macro_analysis = {}
    if STAGE_B_FILE.exists():
        with open(STAGE_B_FILE, "r", encoding="utf-8") as f:
            macro_analysis = json.load(f)
        print(f"✅ Stage B loaded: {len(macro_analysis.get('narrative_markers', []))} markers, "
              f"{len(macro_analysis.get('entities', []))} entities")
    else:
        print(f"⚠️  Stage B not found at {STAGE_B_FILE} — context will be minimal")

    # Pull emotion from Stage B
    block_analysis = macro_analysis.get("block_analysis", {})
    primary_emotion = block_analysis.get("primary_emotion", "neutro")
    print(f"   Primary emotion: {primary_emotion}")
    print(f"   Prompt path: {get_config().stage_c_prompt_path}")
    print()

    # Init Stage C director and call annotate_text_for_qwen3 directly
    config = get_config()
    from src.common.redis_client import DiasRedis
    redis = DiasRedis(
        host=config.redis.host,
        port=config.redis.port,
        db=config.redis.db,
        decode_responses=config.redis.decode_responses
    )
    from src.common.gateway_client import GatewayClient
    gateway = GatewayClient(redis_client=redis)

    from src.stages.stage_c_scene_director import TextDirector
    import logging
    logger = logging.getLogger("v1.4_test")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    director = TextDirector(gemini_client=gateway, config=config, logger=logger)

    print("⏳ Calling Gemini with V1.4 prompt...")
    t0 = time.time()
    scenes = director.annotate_text_for_qwen3(
        text_content=text_content,
        emotion=primary_emotion,
        emotion_description=primary_emotion,
        book_id=book_id,
        block_id=block_id,
        macro_analysis=macro_analysis,
    )
    elapsed = time.time() - t0
    print(f"✅ {len(scenes)} scenes generated in {elapsed:.1f}s")
    print()

    # Save full result
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = OUTPUT_DIR / f"result_v1.4_contextual_chunk-000-sub_{timestamp}.json"
    result = {"prompt_version": "1.4", "scenes_count": len(scenes), "parsed_data": scenes}
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"💾 Saved: {out_file}")
    print()

    # Load V1.3 for comparison
    v1_3_scenes = []
    if V1_3_FILE.exists():
        with open(V1_3_FILE, "r", encoding="utf-8") as f:
            v13 = json.load(f)
        v1_3_scenes = v13.get("parsed_data", [])

    # Print comparison for key scenes
    print("=" * 60)
    print("📊 CONFRONTO V1.3 vs V1.4 — Scene 006, 007, 008")
    print("=" * 60)
    for idx in COMPARE_SCENES:
        v14_scene = scenes[idx] if idx < len(scenes) else None
        v13_scene = v1_3_scenes[idx] if idx < len(v1_3_scenes) else None

        print(f"\n── Scena {idx:03d} ──")
        if v14_scene:
            print(f"  [V1.4] label    : {v14_scene.get('scene_label','')}")
            print(f"  [V1.4] text     : {v14_scene.get('clean_text','')[:80]}...")
            print(f"  [V1.4] instruct : {v14_scene.get('qwen3_instruct','')}")
        if v13_scene:
            print(f"  [V1.3] label    : {v13_scene.get('scene_label','')}")
            print(f"  [V1.3] instruct : {v13_scene.get('qwen3_instruct','')}")

    print()
    print("=" * 60)
    print("✅ Test completed. Review the instruct quality above.")
    print(f"   Full result: {out_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
