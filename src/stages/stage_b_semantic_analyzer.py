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
        self.persistence = DiasPersistence()
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
            self.logger.info(f"Processing block {message.get('block_id')} from book {message.get('book_id')}")
            
            # Valida input
            if not message.get('block_id') or not message.get('text'):
                raise ValueError("block_id e text sono richiesti")
            
            # Coherence: Use IDs directly from the message (already normalized by Stage A)
            book_id = message.get('book_id')
            block_id = message.get('block_id')
            clean_title = message.get('clean_title') or self.persistence.normalize_id(book_id)
            block_index = message.get('block_index', 0)
            chunk_label = message.get('chunk_label') or f"chunk-{block_index:03d}"

            # Registry task ID for Stage B
            registry_task_id = f"stage_b_{block_id}"

            self.logger.info(f"Processing Stage B: Book {book_id}, Block {block_id}")

            # 1. Registry Check (Idempotency)
            if not self.tracker.is_task_ready_to_send(book_id, registry_task_id):
                entry = self.tracker.get_entry(book_id, registry_task_id)
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
            existing_analysis = self.persistence.load_stage_output("b", clean_title, chunk_label)
            if existing_analysis:
                self.logger.info(f"⏭️ Skipping Gemini: Analisi già presente su disco per {clean_title}-{chunk_label}")
                # Re-iniettiamo in Redis per sicurezza nel caso lo Stage C ne abbia bisogno
                self._save_analysis_from_dict(existing_analysis, message)
                
                # Mark as Completed in Registry if it was skipped due to disk presence
                self.tracker.mark_as_completed(book_id, registry_task_id, "disk_cache")

                return {
                    "status": "success",
                    "block_id": message['block_id'],
                    "book_id": message['book_id'],
                    "job_id": existing_analysis.get("job_id", "skipped"),
                    "skipped": True,
                    "file_path": "already_exists",
                    # Includi i dati completi per lo Stage C
                    "entities": existing_analysis.get("entities", []),
                    "relations": existing_analysis.get("relations", []),
                    "concepts": existing_analysis.get("concepts", [])
                }
            # ----------------------
            
            # Mark as In-Flight in Registry
            self.tracker.mark_as_inflight(book_id, registry_task_id, f"global:callback:dias:job-{book_id}-{block_id}") # Callback logic is internal to GatewayClient now

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
                "book_id": message['book_id'],
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
            output_file = self.persistence.save_stage_output(self.STAGE_NAME, analysis_dict, clean_title, chunk_label)
            
            # Mark as Completed in Registry
            self.tracker.mark_as_completed(book_id, registry_task_id, output_file)

            self.logger.info(f"Analysis saved to disk: {output_file}")
            
            # Salva in Redis per Stage C passando i metadati originali
            self.logger.info("Saving analysis to Redis...")
            self._save_analysis(semantic_analysis, message)
            
            # Aggiungi info sul file salvato al risultato
            result["file_path"] = str(output_file)
            
            self.logger.info(f"=== Stage B Processing Completed Successfully ===")
            self.logger.info(f"Analisi semantica completata per block {message['block_id']}: "
                           f"{len(semantic_analysis.entities)} entità, "
                           f"{len(semantic_analysis.relations)} relazioni, "
                           f"{len(semantic_analysis.concepts)} concetti")
            
            return result
            
        except Exception as e:
            self.logger.error(f"=== Stage B Processing Failed ===")
            self.logger.error(f"Errore nel processing del block {message.get('block_id', 'unknown')}: {e}")
            self.logger.error(f"Error type: {type(e).__name__}")
            self.logger.error(f"Error details: {str(e)}")
            return {
                "status": "error",
                "block_id": message.get('block_id'),
                "book_id": message.get('book_id'),
                "error": str(e),
                "processing_timestamp": datetime.now().isoformat()
            }
    
    def _analyze_semantics(self, message: Dict[str, Any]) -> MacroAnalysisResult:
        """
        Analizza semanticamente il testo usando Gemini API
        """
        block_id = message['block_id']
        book_id = message['book_id']
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
            stable_id_str = f"{book_id}|{block_id}|stage_b"
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
            # Se analysis_result è già un dict con oggetti Pydantic (da _parse_gemini_response)
            # Dobbiamo assicurarci di non chiamare Pydantic(**Pydantic)
            
            def ensure_mapping(item):
                if hasattr(item, "model_dump"):
                    return item.model_dump()
                return item

            analysis = MacroAnalysisResult(
                job_id=message.get('job_id', f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
                book_id=book_id,
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
                'block_analysis': block_analysis,
                'confidence_score': result.get('confidence_score', 0.0)
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
    
    def _save_analysis(self, analysis: MacroAnalysisResult, original_message: Dict[str, Any]):
        """
        Salva l'analisi in Redis per Stage C
        """
        try:
            # Converti a dict per salvataggio con conversione datetime
            analysis_dict = analysis.model_dump()
            
            # Salva nella coda per Stage C
            analysis_dict["clean_title"] = original_message.get("clean_title")
            analysis_dict["chunk_label"] = original_message.get("chunk_label")
            analysis_dict["book_metadata"] = original_message.get("book_metadata")
            analysis_dict["block_index"] = original_message.get("block_index")
            analysis_dict["book_id"] = original_message.get("book_id")
            analysis_dict["block_id"] = original_message.get("block_id")
            analysis_dict["job_id"] = analysis.job_id
            
            # Converti datetime a stringa ISO per JSON serialization
            if 'processing_timestamp' in analysis_dict and analysis_dict['processing_timestamp']:
                if hasattr(analysis_dict['processing_timestamp'], 'isoformat'):
                    analysis_dict['processing_timestamp'] = analysis_dict['processing_timestamp'].isoformat()
            
            # Salva nella coda per Stage C
            queue_name = self.output_queue
            self.redis.push_to_queue(queue_name, analysis_dict)
            
            self.logger.info(f"Analisi {analysis.job_id} salvata in Redis per Stage C")
            
        except Exception as e:
            self.logger.error(f"Errore nel salvataggio dell'analisi {analysis.job_id}: {e}")
    
    def _save_analysis_from_dict(self, analysis_dict: Dict[str, Any], original_message: Dict[str, Any]):
        """
        Salva un'analisi (caricata da disco) in Redis per Stage C
        """
        try:
            # Porta avanti i metadati per il naming coerente nello Stage C
            analysis_dict["clean_title"] = original_message.get("clean_title")
            analysis_dict["chunk_label"] = original_message.get("chunk_label")
            analysis_dict["book_metadata"] = original_message.get("book_metadata")
            analysis_dict["block_index"] = original_message.get("block_index")
            analysis_dict["book_id"] = original_message.get("book_id")
            analysis_dict["block_id"] = original_message.get("block_id")
            if "job_id" not in analysis_dict:
                analysis_dict["job_id"] = original_message.get("job_id") or f"restored-{datetime.now().timestamp()}"
            
            # Salva nella coda per Stage C
            queue_name = self.output_queue
            self.redis.push_to_queue(queue_name, analysis_dict)
            self.logger.info(f"Analisi ripristinata salvata in Redis per Stage C")
            
        except Exception as e:
            self.logger.error(f"Errore nel salvataggio dell'analisi ripristinata: {e}")

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
