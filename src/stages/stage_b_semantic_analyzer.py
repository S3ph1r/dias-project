"""
Stage B - Semantic Analyzer
Analizza i chunk di testo da Stage A per estrarre entità, relazioni e concetti chiave
utilizzando Google Gemini 2.5 Flash API con rate limiting
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

import google.genai as genai
from pydantic import BaseModel, Field
from src.common.redis_client import DiasRedis
from src.common.models import IngestionBlock
from src.common.persistence import DiasPersistence
from src.stages.gemini_rate_limiter import gemini_rate_limiter
from src.stages.mock_gemini_client import MockGeminiClient
from src.common.quota_manager import get_quota_manager


from src.common.models import (
    MacroAnalysisResult, 
    BlockAnalysis, 
    NarrativeMarker, 
    SemanticEntity, 
    SemanticRelation, 
    SemanticConcept, 
    PrimaryEmotion
)


class StageBSemanticAnalyzer:
    """
    Stage B: Analizza semanticamente i chunk di testo da Stage A
    Utilizza Google Gemini 2.5 Flash API con rate limiting
    """
    
    def __init__(self, redis_client: Optional[DiasRedis] = None):
        self.logger = logging.getLogger(__name__)
        self.redis_client = redis_client or DiasRedis()
        self.persistence = DiasPersistence()
        
        # Check if mock services are enabled
        mock_services = os.getenv('MOCK_SERVICES', 'false').lower() == 'true'
        
        if mock_services:
            self.logger.info("🎭 Using Mock Gemini Client (MOCK_SERVICES=true)")
            self.gemini_client = MockGeminiClient(logger=self.logger)
            self.model_name = "gemini-2.5-flash-mock"
        else:
            # Retrieve Google Gemini API key from environment
            self.logger.info("🔑 Using Real Gemini API (MOCK_SERVICES=false)")
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key or api_key == "your-google-api-key-here":
                raise ValueError(
                    "Google Gemini API key not found in environment. "
                    "Please set GOOGLE_API_KEY in your .env file. "
                    "Get your API key from: https://makersuite.google.com/app/apikey"
                )
            
            self.logger.info("✅ Successfully retrieved API key from environment")
            
            # Configure Gemini client with secure API key
            self.gemini_client = genai.Client(api_key=api_key)
            self.model_name = "gemini-2.5-flash"
        
        self.logger.info(f"Stage B Semantic Analyzer inizializzato con modello {self.model_name}")
    
    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa un messaggio da Stage A con chunk di testo
        
        Args:
            message: Dict con block_id, book_id, text, metadata
            
        Returns:
            Dict con risultato del processing
        """
        self.logger.info(f"=== Stage B Processing Started ===")
        self.logger.info(f"Block ID: {message.get('block_id')}")
        self.logger.info(f"Book ID: {message.get('book_id')}")
        self.logger.info(f"Text length: {len(message.get('text', ''))} characters")
        
        try:
            self.logger.info(f"Processing block {message.get('block_id')} from book {message.get('book_id')}")
            
            # Valida input
            if not message.get('block_id') or not message.get('text'):
                raise ValueError("block_id e text sono richiesti")
            
            # --- SKIPPING LOGIC ---
            # Recupera titoli e indici per naming coerente e check esistenza
            book_metadata = message.get('book_metadata', {})
            title = book_metadata.get('title', 'Unknown')
            clean_title = "".join([c if c.isalnum() else "-" for c in title]).strip("-")
            block_index = message.get('block_index', 0)
            chunk_label = f"chunk-{block_index:03d}"

            # Controlla se l'analisi esiste già su disco
            existing_analysis = self.persistence.load_stage_output("b", clean_title, chunk_label)
            if existing_analysis:
                self.logger.info(f"⏭️ Skipping Gemini: Analisi già presente su disco per {clean_title}-{chunk_label}")
                # Re-iniettiamo in Redis per sicurezza nel caso lo Stage C ne abbia bisogno
                self._save_analysis_from_dict(existing_analysis, message)
                
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
            
            # Analizza semanticamente il testo
            self.logger.info("Starting semantic analysis...")
            semantic_analysis = self._analyze_semantics(message)
            
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
            
            # Recupera titoli e indici per naming coerente
            book_metadata = message.get('book_metadata', {})
            title = book_metadata.get('title', 'Unknown')
            clean_title = "".join([c if c.isalnum() else "-" for c in title]).strip("-")
            block_index = message.get('block_index', 0)
            chunk_label = f"chunk-{block_index:03d}"
            
            filepath = self.persistence.save_stage_output("b", analysis_dict, clean_title, chunk_label)
            self.logger.info(f"Analysis saved to disk: {filepath}")
            
            # Salva in Redis per Stage C passando i metadati originali
            self.logger.info("Saving analysis to Redis...")
            self._save_analysis(semantic_analysis, message)
            
            # Aggiungi info sul file salvato al risultato
            result["file_path"] = filepath
            
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
        
        # Gestione Quota Giornaliera
        quota_manager = get_quota_manager()
        if not quota_manager.is_available():
            self.logger.warning("⚠️ Quota API Gemini esaurita per oggi. Sospensione stage.")
            raise RuntimeError("GEMINI_QUOTA_EXHAUSTED")

        # Gestione Rate Limiting
        self.logger.info("Waiting for rate limit slot (Stage B)...")
        wait_time = gemini_rate_limiter.wait_for_slot()
        if wait_time > 0:
            self.logger.info(f"Rate limit: attesi {wait_time:.1f} secondi")
            
        # Prompt per Gemini API
        prompt = self._create_semantic_analysis_prompt(text)
        
        try:
            # Gestisci sia client reale che mock
            if hasattr(self.gemini_client, 'models'):
                # Client reale Google Gemini
                response = self.gemini_client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                response_text = response.text
            else:
                # Mock client
                response_text = self.gemini_client.generate_content(prompt, model=self.model_name)
            
            # Incrementa quota dopo successo
            quota_manager.increment()
            
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
            error_msg = str(e)
            if "429" in error_msg or "exhausted" in error_msg.lower():
                gemini_rate_limiter.report_429()
                
            self.logger.error(f"Errore nell'analisi semantica per block {block_id}: {e}")
            # Ritorna analisi vuota in caso di errore
            return MacroAnalysisResult(
                book_id=book_id,
                block_id=block_id,
                block_analysis=BlockAnalysis(
                    valence=0.5, arousal=0.5, tension=0.5, primary_emotion='neutro'
                )
            )
    
    def _create_semantic_analysis_prompt(self, text: str) -> str:
        """
        Crea prompt per analisi semantica e macro-emotiva con Gemini.
        Strategia Mediterranean Prompting: Rigorosamente in Italiano.
        """
        return f"""
        Sei un analista narrativo e semantico esperto. Analizza il seguente testo (in Italiano) per estrarre:
        1. Analisi Emotiva: valence, arousal, tension (0.0-1.0) e l'emozione primaria.
        2. Marcatori Narrativi: eventi chiave e shift di mood.
        3. Entità: persona, luogo, organizzazione, concetto, evento (con relativa emozione).
        4. Relazioni tra entità.
        5. Concetti chiave e loro definizioni.
        
        Testo da analizzare:
        {text}
        
        Rispondi ESCLUSIVAMENTE in formato JSON con questa struttura:
        {{
            "block_analysis": {{
                "valence": 0.5,
                "arousal": 0.5,
                "tension": 0.5,
                "primary_emotion": "neutro|gioia|tristezza|rabbia|paura|tensione|curiosita|relax|melanconia|stupore|determinazione|ansia|nostalgia",
                "secondary_emotion": "descrizione opzionale",
                "setting": "luogo della scena",
                "has_dialogue": false,
                "audio_cues": ["lista", "di", "effetti", "sonori", "suggeriti"]
            }},
            "narrative_markers": [
                {{
                    "relative_position": 0.1,
                    "event": "nome evento",
                    "mood_shift": "descrizione cambio mood"
                }}
            ],
            "entities": [
                {{
                    "entity_id": "ent_001",
                    "text": "testo dell'entità",
                    "entity_type": "persona|luogo|organizzazione|concetto|evento",
                    "emotional_tone": "neutro|gioia|tristezza|rabbia|paura|tensione|curiosita|relax",
                    "confidence": 0.9,
                    "metadata": {{}}
                }}
            ],
            "relations": [
                {{
                    "relation_id": "rel_001",
                    "source_entity_id": "ent_001",
                    "target_entity_id": "ent_002",
                    "relation_type": "tipo_relazione_in_italiano",
                    "confidence": 0.8
                }}
            ],
            "concepts": [
                {{
                    "concept_id": "conc_001",
                    "concept": "nome concetto",
                    "definition": "definizione in italiano",
                    "emotional_tone": "neutro|gioia|tristezza|rabbia|paura|tensione|curiosita|relax",
                    "confidence": 0.85
                }}
            ]
        }}
        
        REGOLE:
        - Usa solo le emozioni nell'enum fornito (in italiano).
        - Sii conservatore nell'analisi emotiva.
        - Le relazioni devono essere espresse in italiano.
        """
    
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
            return {
                'entities': [],
                'relations': [],
                'concepts': [],
                'narrative_markers': [],
                'block_analysis': BlockAnalysis(valence=0.5, arousal=0.5, tension=0.5, primary_emotion='neutro'),
                'confidence_score': 0.0
            }
        except Exception as e:
            self.logger.error(f"Errore generico nel parsing della risposta Gemini: {e}")
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
            
            # Porta avanti i metadati per il naming coerente nello Stage C
            analysis_dict["clean_title"] = original_message.get("clean_title")
            analysis_dict["chunk_label"] = original_message.get("chunk_label")
            analysis_dict["book_metadata"] = original_message.get("book_metadata")
            analysis_dict["block_index"] = original_message.get("block_index")
            
            # Converti datetime a stringa ISO per JSON serialization
            if 'processing_timestamp' in analysis_dict and analysis_dict['processing_timestamp']:
                if hasattr(analysis_dict['processing_timestamp'], 'isoformat'):
                    analysis_dict['processing_timestamp'] = analysis_dict['processing_timestamp'].isoformat()
            
            # Salva nella coda per Stage C
            queue_name = "dias_stage_c_queue"
            self.redis_client.push_to_queue(queue_name, analysis_dict)
            
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
            
            # Salva nella coda per Stage C
            queue_name = "dias_stage_c_queue"
            self.redis_client.push_to_queue(queue_name, analysis_dict)
            self.logger.info(f"Analisi ripristinata salvata in Redis per Stage C")
            
        except Exception as e:
            self.logger.error(f"Errore nel salvataggio dell'analisi ripristinata: {e}")

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Ritorna stato corrente del rate limiter
        """
        return gemini_rate_limiter.get_status()