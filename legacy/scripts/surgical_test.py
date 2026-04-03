#!/usr/bin/env python3
import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.stages.stage_a_text_ingester import TextIngester
from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.stages.stage_c_scene_director import SceneDirector
from src.stages.stage_d_voice_gen import StageDVoiceGeneratorProxy
from src.common.config import get_config
from src.common.redis_factory import get_redis_client
from src.common.persistence import DiasPersistence

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("dias_surgical")

class SurgicalOrchestrator:
    def __init__(self, book_id=None):
        # Load config and auto-detect Redis host (Dynamic)
        self.config = get_config()
        
        # Override mock services for surgical tests
        os.environ["MOCK_SERVICES"] = "false"
        
        self.redis = get_redis_client()
        self.persistence = DiasPersistence()
        self.book_id = book_id or f"surgical_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"🔧 Orchestrator initialized. Redis: {self.config.redis.host}, Project: {self.book_id}")
        
    def reset_queues(self):
        """Clean all DIAS and GPU queues in Redis."""
        logger.info("🧹 Flushing Redis Queues...")
        # MockRedis is the client directly, DiasRedis is a wrapper with .client
        raw_redis = self.redis.client if hasattr(self.redis, 'client') else self.redis
        
        queues = [
            "dias:queue:0:upload",
            "dias:queue:1:ingestion",
            "dias:queue:2:macro_analysis",
            "dias:queue:2:semantic_analysis",
            "dias:queue:3:scene_director",
            "dias:queue:4:voice_gen",
            "dias:queue:5:music_gen",
            "dias_stage_c_queue", 
            "gpu:queue:tts:fish-s1-mini"
        ]
        
        for q in queues:
            try:
                # Use raw_redis to access standard Redis methods
                count = raw_redis.llen(q) if raw_redis.exists(q) else 0
                if count > 0:
                    raw_redis.delete(q)
                    logger.info(f"  - Cleared {q} ({count} items)")
                else:
                    logger.info(f"  - {q} is already empty")
            except Exception as e:
                logger.warning(f"  - Could not clear {q}: {e}")
                
        # Also clear callbacks
        try:
            callbacks = raw_redis.keys("dias:callback:*")
            if callbacks:
                raw_redis.delete(*callbacks)
                logger.info(f"  - Cleared {len(callbacks)} callbacks")
        except Exception as e:
            logger.warning(f"  - Could not clear callbacks: {e}")

    def run_stage_a(self, pdf_path):
        """Process PDF and produce ALL chunks to disk (Stage A)."""
        logger.info(f"🚀 Phase A: Ingesting {pdf_path}")
        ingester = TextIngester(self.redis, self.config)
        
        # We process the PDF and keep all blocks on disk
        # Use PDF filename as title
        pdf_name = Path(pdf_path).stem
        blocks = ingester.process_book_file(pdf_path, self.book_id, {"title": pdf_name})
        
        if blocks:
            logger.info(f"✅ Phase A Complete. {len(blocks)} blocks saved.")
            logger.info(f"💡 NOTE: Per risparmiare API Google, processeremo solo il blocco 0 negli step successivi.")
            return blocks
        return []

    def run_stage_b(self, block_index=0):
        """Run Semantic Analysis on a SINGLE block (Stage B)."""
        logger.info(f"🚀 Phase B: Analyzing block index {block_index} for {self.book_id}")
        
        # Try to load the block from persistence
        block = self.persistence.load_stage_output("a", self.book_id)
        # Find the file that has "block_index": block_index and "book_id": self.book_id
        target_file = None
        for file in Path(self.persistence.base_path / "stage_a" / "output").glob("*.json"):
            with open(file, 'r') as f:
                try:
                    data = json.load(f)
                    if data.get("block_index") == block_index and data.get("book_id") == self.book_id:
                        target_file = file
                        block_data = data
                        break
                except Exception:
                    continue
        
        if not target_file:
            logger.error(f"❌ No block found for logical index {block_index}")
            return None
            
        logger.info(f"  - Loading block index {block_index} from {target_file.name}")
            
        analyzer = StageBSemanticAnalyzer(self.redis)
        # Prepare input for Stage B
        b_input = {
            "book_id": self.book_id,
            "block_id": block_data.get("block_id"),
            "text": block_data.get("block_text")
        }
        
        result = analyzer.process(b_input)
        if result and result.get("status") == "success":
            logger.info(f"✅ Phase B Complete. Analysis saved to data/stage_b/output/")
            return result
        return None

    def run_stage_c(self, b_result_file=None):
        """Run Scene Direction on a SINGLE analysis (Stage C)."""
        logger.info(f"🚀 Phase C: Directing scenes...")
        
        if b_result_file:
            with open(b_result_file, 'r') as f:
                b_result = json.load(f)
        else:
            # Load latest from B
            b_result = self.persistence.load_stage_output("b", self.book_id)
            
        if not b_result:
            logger.error("❌ No Stage B input found.")
            return None
            
        # Initialize director with a real analyzer client for Gemini
        analyzer = StageBSemanticAnalyzer(self.redis)
        director = SceneDirector(gemini_client=analyzer.gemini_client)
        
        c_result = director.process(b_result)
        if c_result and ("status" in c_result):
            logger.info(f"✅ Phase C Complete. {c_result.get('scenes_count')} scenes saved.")
            return c_result
        return None

    def run_stage_d(self, scene_index=0):
        """Run Voice Generation on a SINGLE scene via ARIA (Stage D)."""
        logger.info(f"🚀 Phase D: Generating Voice via ARIA for scene {scene_index}")
        
        # Stage C results are now saved as individual scene files (surgical_BOOKID_scene_000_...)
        pattern = f"{self.book_id}_scene_{scene_index:03d}_*.json"
        stage_c_path = self.persistence.base_path / "stage_c" / "output"
        files = sorted(list(stage_c_path.glob(pattern)))
        
        if not files:
            logger.error(f"❌ No Stage C scene file found for index {scene_index} (pattern: {pattern})")
            return None
            
        target_file = files[-1] # Pick latest
        logger.info(f"  - Loading scene from {target_file.name}")
        
        with open(target_file, 'r') as f:
            target_scene = json.load(f)
        proxy = StageDVoiceGeneratorProxy(self.redis, self.config)
        
        result = proxy.process(target_scene)
        if result:
            logger.info(f"🎉 SUCCESS! Audio generated: {result.get('voice_path')}")
            return result
        return None

def main():
    parser = argparse.ArgumentParser(description="DIAS Surgical Orchestrator - Precision Testing")
    parser.add_argument("--reset", action="store_true", help="Flush Redis queues and clear callbacks")
    parser.add_argument("--step", choices=["A", "B", "C", "D"], help="Run specific stage")
    parser.add_argument("--book-id", help="Existing book ID to continue from")
    parser.add_argument("--pdf", help="PDF path for Step A")
    parser.add_argument("--index", type=int, default=0, help="Chunk/Scene index for steps B, D")
    
    args = parser.parse_args()
    orch = SurgicalOrchestrator(args.book_id)
    
    if args.reset:
        orch.reset_queues()
        
    if args.step == "A":
        if not args.pdf:
            print("Error: --pdf required for step A")
            return
        orch.run_stage_a(args.pdf)
        print(f"\n👉 CONTAGIO! Book ID generato: {orch.book_id}")
        print(f"Usa questo book_id per gli step successivi: --book-id {orch.book_id}")
        
    elif args.step == "B":
        if not args.book_id:
            print("Error: --book-id required for step B")
            return
        orch.run_stage_b(args.index)
        
    elif args.step == "C":
        if not args.book_id:
            print("Error: --book-id required for step C")
            return
        orch.run_stage_c()
        
    elif args.step == "D":
        if not args.book_id:
            print("Error: --book-id required for step D")
            return
        orch.run_stage_d(args.index)

if __name__ == "__main__":
    main()
