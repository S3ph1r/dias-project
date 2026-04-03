"""
Stage B - Semantic Analyzer
Analizza i chunk di testo da Stage A per estrarre entità, relazioni e concetti chiave
utilizzando Google Gemini Flash Lite API con rate limiting
"""
import os
import json
import logging
import sys
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

# Load environment variables for API keys
from dotenv import load_dotenv
load_dotenv()

# Aggiungi il path root al Python path per trovare il modulo 'src'
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.stages.mock_gemini_client import MockGeminiClient
from src.common.gateway_client import GatewayClient
from src.common.base_stage import BaseStage
from src.common.registry import ActiveTaskTracker
from src.common.redis_client import DiasRedis
from src.common.models import IngestionBlock
from src.common.persistence import DiasPersistence


from src.common.models import (
    MacroAnalysisResult, 
    BlockAnalysis, 
    NarrativeMarker, 
    SemanticEntity, 
    SemanticRelation, 
    SemanticConcept
)


class StageBSemanticAnalyzer(BaseStage):
    """
    Stage B: Analizza semanticamente i chunk di testo da Stage A
    Utilizza ARIA Gateway v2.0 per accedere dei modelli Cloud (Gemini)
    """
    
    STAGE_NAME = "b"
    
    def __init__(self, redis_client: Optional[DiasRedis] = None, config=None):
        # Load config to get standard queue names
        from src.common.config import get_config
        cfg = config or get_config()
        
        super().__init__(
            stage_name="semantic_analyzer",
            stage_number=2,
            input_queue=cfg.queues.ingestion,
            output_queue=cfg.queues.semantic,
            config=cfg,
            redis_client=redis_client
        )
        # self.persistence = DiasPersistence() # Decommissioned global persistence
        self.tracker = ActiveTaskTracker(self.redis, self.logger)
        
        # Check if mock services are enabled
        mock_services = os.getenv('MOCK_SERVICES', 'false').lower() == 'true'
        
        if mock_services:
            self.logger.info("🎭 Using Mock Gemini Client (MOCK_SERVICES=true)")
            self.gemini_client = MockGeminiClient(logger=self.logger)
            self.model_name = "gemini-flash-latest-mock"
        else:
            self.logger.info("📡 Using ARIA Gateway v2.0 (MOCK_SERVICES=false)")
            # No longer need local API key check here - ARIA handles it.
            self.gemini_client = GatewayClient(redis_client=self.redis, client_id="dias")
            self.model_name = self.config.google.model_flash_lite
        
        self.logger.info(f"Stage B Semantic Analyzer inizializzato con modello {self.model_name} via Gateway")
    
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa un messaggio da Stage A con chunk di testo
        
        Args:
            message: Dict con block_id, book_id, text, metadata
            
        Returns:
            Dict con risultato del processing
        """
        self.logger.info(f"=== Stage B Processing Started ===")
        self.logger.info(f"Full message keys: {list(message.keys())}")
        self.logger.info(f"Block ID: {message.get('block_id')}")
        self.logger.info(f"Book ID: {message.get('book_id')}")
        self.logger.info(f"Text length: {len(message.get('text', ''))} characters")
        
        try:
            # [SANITY CHECK] Force the official sanitized ID as the only truth
            raw_id = message.get("project_id") or message.get("book_id") or "unknown"
            project_id = DiasPersistence.normalize_id(raw_id)
            
            self.logger.info(f"Using project-aware persistence for: {project_id}")
            self.persistence = DiasPersistence(project_id=project_id)

            self.logger.info(f"Processing block {message.get('block_id')} from book {project_id}")
            
            # Valida input
            if not message.get('block_id') or not message.get('text'):
                raise ValueError("block_id e text sono richiesti")
            
            # Coherence: Use the unified project_id
            block_id = message.get('block_id')
            block_index = message.get('block_index', 0)
            chunk_label = message.get('chunk_label') or f"chunk-{block_index:03d}"

            # Registry task ID for Stage B
            registry_task_id = f"stage_b_{block_id}"

            self.logger.info(f"Processing Stage B: Project {project_id}, Block {block_id}")

            # 1. Registry Check (Idempotency)
            if not self.tracker.is_task_ready_to_send(project_id, registry_task_id):
                entry = self.tracker.get_entry(project_id, registry_task_id)
                if entry and entry.status == "COMPLETED":
                    self.logger.info(f"⏭️ Chunk {block_id} già completato nel registro. Salto.")
                    # If already completed, we should return the original message or the stored result
                    # For now, just return the message to allow downstream stages to proceed if they handle idempotency
                    return message 
                
                self.logger.info(f"Chunk {block_id} già in corso (IN_FLIGHT).")
                # If in-flight, we might want to wait or skip, depending on desired behavior.
                # For now, we'll let it proceed, assuming the in-flight status is for another worker.
                # A more robust solution might involve a lock or a wait.
            
            # --- SKIPPING LOGIC (Disk Check) ---
            # Controlla se l'analisi esiste già su disco
            existing_analysis = self.persistence.load_stage_output("b", project_id, chunk_label)
            if existing_analysis:
                self.logger.info(f"⏭️ Skipping Gemini: Analisi già presente su disco per {project_id}-{chunk_label}")
                
                # --- NEW: Assicuriamoci che i micro-chunk siano distribuiti ---
                self.logger.info(f"Checking micro-chunk distribution (from disk cache)...")
                self._distribute_micro_chunks(existing_analysis, message)
                
                # Mark as Completed in Registry if it was skipped due to disk presence
                self.tracker.mark_as_completed(project_id, registry_task_id, "disk_cache")

                return {
                    "status": "success",
                    "block_id": message['block_id'],
                    "project_id": project_id,
                    "job_id": existing_analysis.get("job_id", "skipped"),
                    "skipped": True,
                    "file_path": "already_exists",
                    # Minimal info for skip result
                    "entities_count": len(existing_analysis.get("entities", []))
                }
            # ----------------------
            
            # Mark as In-Flight in Registry
            self.tracker.mark_as_inflight(project_id, registry_task_id, f"aria:c:dias:job-{project_id}-{block_id}")

            # Analizza semanticamente il testo
            self.logger.info("Starting semantic analysis...")
            semantic_analysis = self._analyze_semantics(message)
            
            # QUALITY CHECK: Don't allow empty "skeleton" successes
            if not semantic_analysis.entities and not semantic_analysis.relations and not semantic_analysis.concepts:
                self.logger.error("Empty analysis received (0 entities, 0 relations, 0 concepts). Rejecting as failure.")
                raise RuntimeError("EMPTY_ANALYSIS_REJECTED")

            self.logger.info(f"Semantic analysis completed: {len(semantic_analysis.entities)} entities, "
                           f"{len(semantic_analysis.relations)} relations, "
                           f"{len(semantic_analysis.concepts)} concepts")
            
            # Salva risultato
            result = {
                "status": "success",
                "block_id": message['block_id'],
                "project_id": project_id,
                "job_id": semantic_analysis.job_id,
                "entities_count": len(semantic_analysis.entities),
                "relations_count": len(semantic_analysis.relations),
                "concepts_count": len(semantic_analysis.concepts),
                # Includi i dati completi per il risultato
                "entities": [e.model_dump() if hasattr(e, "model_dump") else e for e in semantic_analysis.entities],
                "relations": [r.model_dump() if hasattr(r, "model_dump") else r for r in semantic_analysis.relations],
                "concepts": [c.model_dump() if hasattr(c, "model_dump") else c for c in semantic_analysis.concepts]
            }
            
            # Salva l'analisi completa su disco con naming coerente
            self.logger.info("Saving analysis to disk...")
            analysis_dict = semantic_analysis.model_dump()
            
            # Use pre-extracted coherence fields
            # Salva checkpoint Stage B
            # Use pre-extracted coherence fields
            # Salva checkpoint Stage B (Macro Analysis)
            output_file = self.persistence.save_stage_output(
                self.STAGE_NAME, 
                analysis_dict, 
                project_id, 
                chunk_label,
                include_timestamp=False
            )
            
            # Mark as Completed in Registry (Macro Task)
            self.tracker.mark_as_completed(project_id, registry_task_id, str(output_file))

            self.logger.info(f"Macro-Analysis saved to disk: {output_file}")
            
            # --- NEW: Distribuzione Micro-Chunk per Stage C ---
            self.logger.info(f"Distributing micro-chunks for {chunk_label}...")
            self._distribute_micro_chunks(analysis_dict, message)
            
            # Aggiungi info sul file salvato al risultato
            result["file_path"] = str(output_file)
            
            self.logger.info(f"=== Stage B Processing Completed Successfully ===")
            
            # Rate limit stabilization
            import time
            delay = int(os.getenv('STAGE_B_STAGGER_DELAY', '10'))
            self.logger.info(f'Sleeping for {delay}s for rate limit stabilization...')
            time.sleep(delay)
            
            return result
            
        except Exception as e:
            self.logger.error(f"=== Stage B Processing Failed ===")
            self.logger.error(f"Errore nel processing del block {message.get('block_id', 'unknown')}: {e}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Error details: {str(e)}")
            raise e
    
    def _analyze_semantics(self, message: Dict[str, Any]) -> MacroAnalysisResult:
        """
        Analizza semanticamente il testo usando Gemini API
        """
        block_id = message['block_id']
        # [DETERMINISTIC] Always use the normalized project_id
        project_id = self.persistence.project_id
        text = message['text']
        metadata = message.get('metadata', {})
        
        # Rate Limiting and Quota is now managed centrally by ARIA Gateway.
        # Stages simply submit the task and wait for the slot/result.
            
        # Prompt per Gemini API
        prompt = self._create_semantic_analysis_prompt(text)
        
        # 1. Deterministic Job ID Persistence
        import hashlib
        if not message.get('job_id'):
            # Create a stable ID from core metadata to ensure it survives re-queuing
            stable_id_str = f"{project_id}|{block_id}|stage_b"
            job_hash = hashlib.sha256(stable_id_str.encode()).hexdigest()[:12]
            message['job_id'] = f"job-{job_hash}"
            self.logger.info(f"Persisting NEW stable job_id in message: {message['job_id']}")
        else:
            self.logger.info(f"Reusing EXISTING job_id from message: {message['job_id']}")
        
        job_id = message['job_id']
        
        try:
            # Gestisci client Gateway, reale o mock
            if isinstance(self.gemini_client, GatewayClient):
                # Client ARIA Gateway
                generate_config = {}
                if hasattr(self.config.google, 'response_mime_type'):
                    generate_config["response_mime_type"] = self.config.google.response_mime_type
                
                # Format contents for Gateway (Gemini 2.x standard)
                contents = [{"role": "user", "parts": [{"text": prompt}]}]
                
                response = self.gemini_client.generate_content(
                    contents=contents,
                    model_id=self.model_name,
                    config=generate_config,
                    job_id=job_id  # Pass the stable ID
                )
                
                if response["status"] == "error":
                    self.logger.error(f"Gateway Error: {response.get('error')}")
                    raise RuntimeError(f"GATEWAY_ERROR: {response.get('error')}")
                
                response_text = response["output"].get("text", "")
            
            else:
                # Mock client
                response_text = self.gemini_client.generate_content(prompt, model=self.model_name)
            
            # Parse risposta
            analysis_result = self._parse_gemini_response(response_text)
            
            # Assembla MacroAnalysisResult
            def ensure_mapping(item):
                if hasattr(item, "model_dump"):
                    return item.model_dump()
                return item

            analysis = MacroAnalysisResult(
                job_id=message.get('job_id', f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
                book_id=project_id,
                block_id=block_id,
                block_analysis=analysis_result.get('block_analysis') if isinstance(analysis_result.get('block_analysis'), BlockAnalysis) else BlockAnalysis(**ensure_mapping(analysis_result.get('block_analysis', {}))),
                narrative_markers=[
                    m if isinstance(m, NarrativeMarker) else NarrativeMarker(**ensure_mapping(m))
                    for m in analysis_result.get('narrative_markers', [])
                ],
                entities=[
                    e if isinstance(e, SemanticEntity) else SemanticEntity(**ensure_mapping(e))
                    for e in analysis_result.get('entities', [])
                ],
                relations=[
                    r if isinstance(r, SemanticRelation) else SemanticRelation(**ensure_mapping(r))
                    for r in analysis_result.get('relations', [])
                ],
                concepts=[
                    c if isinstance(c, SemanticConcept) else SemanticConcept(**ensure_mapping(c))
                    for c in analysis_result.get('concepts', [])
                ]
            )
            
            return analysis
            
        except Exception as e:
            err_msg = str(e).lower()
            is_transient = any(code in err_msg for code in ["503", "unavailable", "high demand", "429", "timeout", "network"])
            
            if is_transient:
                # Imposta pausa globale su Redis
                pause_key = "dias:status:paused"
                pause_reason = f"Gemini API 503/429 detected in Stage B: {e}. Pausing globally to respect Google pacing."
                self.redis.set(pause_key, pause_reason)
                self.logger.critical(f"🛑 GLOBAL PAUSE SET: {pause_reason}")
            
            self.logger.error(f"Errore nell'analisi semantica per block {block_id}: {e}")
            raise
    
    def _create_semantic_analysis_prompt(self, text: str) -> str:
        """
        Crea prompt per analisi semantica e macro-emotiva con Gemini.
        Carica il template da un file YAML esterno per supportare il versioning.
        """
        import yaml
        from pathlib import Path

        # Caricamento del prompt esternalizzato
        prompt_path = getattr(self.config, "stage_b_prompt_path", "config/prompts/stage_b/v1.0_base.yaml")
        prompt_full_path = Path(__file__).parent.parent.parent / prompt_path

        try:
            with open(prompt_full_path, 'r', encoding='utf-8') as f:
                prompt_data = yaml.safe_load(f)
                template = prompt_data.get('prompt_template', '')
                prompt_version = prompt_data.get('version', '1.0')
        except Exception as e:
            self.logger.error(f"Impossibile caricare il prompt Stage B da {prompt_full_path}: {e}")
            # Fallback al prompt hardcoded (copia di sicurezza del v1.0)
            template = """
            Sei un analista narrativo e semantico esperto. Analizza il seguente testo (in Italiano) per estrarre:
            1. Analisi Emotiva: valence, arousal, tension (0.0-1.0) e l'emozione primaria del BLOCCO INTERO.
            2. Marcatori Narrativi: punti di svolta e shift di mood SIGNIFICATIVI.
            ... {text} ... (fallback)
            """
            self.logger.warning("Usando prompt fallback per Stage B")

        self.logger.info(f"Stage B prompt v{prompt_version} loaded from {prompt_path}")
        return template.replace("{text}", text)
    
    def _parse_gemini_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse la risposta JSON da Gemini API
        """
        try:
            # Estrai JSON dalla risposta (potrebbe avere markdown)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
            else:
                # Prova a parsare direttamente
                result = json.loads(response_text)
            
            # Converti a oggetti Pydantic
            entities = [SemanticEntity(**e) for e in result.get('entities', [])]
            relations = [SemanticRelation(**r) for r in result.get('relations', [])]
            concepts = [SemanticConcept(**c) for c in result.get('concepts', [])]
            narrative_markers = [NarrativeMarker(**m) for m in result.get('narrative_markers', [])]
            
            block_analysis_data = result.get('block_analysis', {})
            block_analysis = BlockAnalysis(
                valence=block_analysis_data.get('valence', 0.5),
                arousal=block_analysis_data.get('arousal', 0.5),
                tension=block_analysis_data.get('tension', 0.5),
                primary_emotion=block_analysis_data.get('primary_emotion', 'neutro'),
                secondary_emotion=block_analysis_data.get('secondary_emotion'),
                setting=block_analysis_data.get('setting'),
                has_dialogue=block_analysis_data.get('has_dialogue', False),
                audio_cues=block_analysis_data.get('audio_cues', [])
            )
            
            return {
                'entities': entities,
                'relations': relations,
                'concepts': concepts,
                'narrative_markers': narrative_markers,
                'block_analysis': block_analysis
            }
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Errore nel parsing JSON da Gemini: {e}")
            self.logger.error(f"Risposta raw: {response_text[:500]}...")
            raise RuntimeError("GEMINI_JSON_PARSE_FAILED_NO_FALLBACK")
        except Exception as e:
            self.logger.error(f"Errore generico nel parsing della risposta Gemini: {e}")
            raise
            return {
                'entities': [],
                'relations': [],
                'concepts': [],
                'narrative_markers': [],
                'block_analysis': BlockAnalysis(valence=0.5, arousal=0.5, tension=0.5, primary_emotion='neutro'),
                'confidence_score': 0.0
            }
    
    def _distribute_micro_chunks(self, macro_analysis: Dict[str, Any], original_message: Dict[str, Any]):
        """
        Scans disk for micro-chunks of the current macro-chunk,
        creates simplified semantic context for each, and pushes to Stage C.
        """
        try:
            # [SANITY CHECK] Use only the official sanitized project_id
            project_id = self.persistence.project_id
            macro_index = original_message.get("block_index")
            
            # Fallback per macro_index se manca block_index (es: trigger da Orchestratore)
            if macro_index is None and original_message.get("block_id"):
                import re
                match = re.search(r"chunk-(\d{3})", original_message["block_id"])
                if match:
                    macro_index = int(match.group(1))

            # Load entities from fingerprint (intelligence DNA)
            fingerprint_path = self.persistence.get_fingerprint_path()
            entities = []
            if fingerprint_path.exists():
                with open(fingerprint_path, 'r', encoding='utf-8') as f:
                    fingerprint_data = json.load(f)
                    entities = fingerprint_data.get("entities", [])

            # 1. Scan for micro-chunks in Stage A output
            stage_a_path = self.persistence.project_root / "stages" / "stage_a" / "output"
            if not stage_a_path.exists():
                self.logger.error(f"Directory micro-chunk non trovata: {stage_a_path}")
                return

            # Pattern per trovare i micro-chunk di questo macro-chunk: *-chunk-001-micro-*.json
            pattern = f"*-chunk-{macro_index:03d}-micro-*.json"
            micro_files = sorted(list(stage_a_path.glob(pattern)))
            
            if not micro_files:
                self.logger.warning(f"Nessun micro-chunk trovato per macro-chunk {macro_index} in {stage_a_path}")
                return

            self.logger.info(f"Found {len(micro_files)} micro-chunks for distribution.")

            # 2. Prepare Simplified Semantic Context (Bible)
            # We only keep the essential "Character Bible" and the "Mood"
            simplified_context = {
                "entities": macro_analysis.get("entities", []),
                "relations": macro_analysis.get("relations", []),
                "narrative_markers": macro_analysis.get("narrative_markers", []),
                "block_analysis": {
                    "primary_emotion": macro_analysis.get("block_analysis", {}).get("primary_emotion", "neutro"),
                    "secondary_emotion": macro_analysis.get("block_analysis", {}).get("secondary_emotion"),
                    "setting": macro_analysis.get("block_analysis", {}).get("setting"),
                    "valence": macro_analysis.get("block_analysis", {}).get("valence", 0.5),
                    "arousal": macro_analysis.get("block_analysis", {}).get("arousal", 0.5),
                    "tension": macro_analysis.get("block_analysis", {}).get("tension", 0.5)
                },
                "macro_job_id": macro_analysis.get("job_id", "unknown"),
                # Carry over metadata
                "project_id": project_id,
                "macro_index": macro_index
            }

            # 3. Save and Enqueue each micro-chunk
            for micro_file in micro_files:
                # Extract micro_label from filename (e.g., chunk-001-micro-001)
                # Filename is typically like: Book-Title-chunk-001-micro-001.json
                parts = micro_file.stem.split("-")
                micro_label = "-".join(parts[-4:]) # chunk-XXX-micro-YYY
                
                # Salva il contesto semplificato per questo specifico micro-chunk
                # Inject micro-specific block_id into the context
                current_context = simplified_context.copy()
                current_context["block_id"] = f"{project_id}-{micro_label}"
                
                self.persistence.save_stage_output(
                    stage="b",
                    data=current_context,
                    book_id=project_id,
                    block_id=f"{micro_label}-semantic",
                    include_timestamp=False
                )
                
                # Push task to Stage C queue (dias:q:3:regia)
                task_message = {
                    "project_id": project_id,
                    "chunk_label": micro_label,
                    "macro_index": macro_index,
                    "micro_index": int(micro_label.split("-")[-1]),
                    "job_id": f"job-{micro_label}",
                    "stage": "semantic_micro",
                    "timestamp": datetime.now().isoformat()
                }
                
                self.redis.push_to_queue(self.output_queue, task_message)
                self.logger.debug(f"Pushed micro-chunk {micro_label} to Stage C queue.")

            self.logger.info(f"✅ Distributed {len(micro_files)} micro-chunks to Stage C.")

        except Exception as e:
            self.logger.error(f"Errore nella distribuzione dei micro-chunk: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Ritorna stato corrente del rate limiter
        """
        return gemini_rate_limiter.get_status()
def main():
    """Main entry point per Stage B"""
    import argparse
    from src.common.config import get_config, load_config
    from pathlib import Path
    
    parser = argparse.ArgumentParser(description="DIAS Stage B - Semantic Analyzer")
    parser.add_argument("--config", help="Path to config file")
    parser.add_argument("--mock", action="store_true", help="Use mock services")
    
    args = parser.parse_args()
    
    if args.mock:
        os.environ["MOCK_SERVICES"] = "true"
        
    if args.config:
        config = load_config(Path(args.config))
    else:
        config = get_config()
    
    # Setup logging
    logger = logging.getLogger(__name__)
    logger.info("🧠 Starting DIAS Stage B - Semantic Analyzer")
    
    try:
        analyzer = StageBSemanticAnalyzer(config=config)
        analyzer.run()
    except Exception as e:
        logger.error(f"Fatal error in Stage B: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
