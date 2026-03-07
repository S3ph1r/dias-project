"""
Mock Google Gemini API Client per testing e sviluppo
Evita chiamate API reali riutilizzando risposte salvate
"""

import json
import hashlib
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime


class MockGeminiClient:
    """Mock client per Google Gemini API con caching"""
    
    def __init__(self, cache_dir: Optional[str] = None, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        
        # Directory per cache delle risposte
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(__file__).parent.parent.parent / "data" / "gemini_cache"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"MockGeminiClient cache directory: {self.cache_dir}")
    
    def _generate_cache_key(self, prompt: str, model: str = "gemini-2.5-flash") -> str:
        """Genera una chiave univoca per il prompt e modello"""
        content = f"{model}:{prompt}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cache_file(self, cache_key: str) -> Path:
        """Ottiene il percorso del file di cache"""
        return self.cache_dir / f"{cache_key}.json"
    
    def _load_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Carica risposta dalla cache se esiste"""
        cache_file = self._get_cache_file(cache_key)
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    self.logger.info(f"Risposta caricata dalla cache: {cache_key}")
                    return cached_data.get('response')
            except Exception as e:
                self.logger.warning(f"Errore nel caricamento cache {cache_key}: {e}")
        
        return None
    
    def _save_to_cache(self, cache_key: str, response: Dict[str, Any], prompt: str):
        """Salva la risposta in cache"""
        cache_file = self._get_cache_file(cache_key)
        
        cache_data = {
            'cache_key': cache_key,
            'prompt': prompt,
            'response': response,
            'cached_at': datetime.now().isoformat(),
            'model': 'gemini-2.5-flash'
        }
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Risposta salvata in cache: {cache_key}")
        except Exception as e:
            self.logger.warning(f"Errore nel salvataggio cache {cache_key}: {e}")
    
    def generate_content(self, prompt: str, model: str = "gemini-2.5-flash") -> str:
        """Metodo principale per generare contenuto (mock)"""
        cache_key = self._generate_cache_key(prompt, model)
        
        # Prova a caricare dalla cache
        cached_response = self._load_from_cache(cache_key)
        if cached_response:
            return cached_response.get('text', 'Mock response from cache')
        
        # Se non in cache, genera una risposta mock realistico
        self.logger.info(f"Generazione risposta mock per cache key: {cache_key}")
        
        # Qui possiamo aggiungere logica per generare risposte mock realistiche
        # basate sul contenuto del prompt
        mock_response = self._generate_mock_response(prompt)
        
        # Salva in cache per uso futuro
        self._save_to_cache(cache_key, {'text': mock_response}, prompt)
        
        return mock_response
    
    def _generate_mock_response(self, prompt: str) -> str:
        """Genera una risposta mock realistico basata sul prompt"""
        
        # Analizza il prompt per capire che tipo di analisi è richiesta
        prompt_lower = prompt.lower()
        
        # Stage B: analisi semantica / analista narrativo
        if any(keyword in prompt_lower for keyword in ['entità', 'entities', 'relazioni', 'relations', 'concetti', 'concepts', 'analista narrativo', 'semantico']):
            return self._generate_semantic_analysis_mock()
        # Stage C: analisi scene / direttore artistico
        elif any(keyword in prompt_lower for keyword in ['scene', 'direttore artistico', 'audiolibri', 'marcatori', 'fish', 'tts']):
            return self._generate_scene_analysis_mock()
        else:
            # Risposta generica per debug
            self.logger.info(f"Prompt non riconosciuto per mock specifico, uso generico. Keywords trovate: {[k for k in ['entities', 'relations', 'concepts', 'scene', 'orpheus'] if k in prompt_lower]}")
            return self._generate_semantic_analysis_mock()  # Default a Stage B per ora
    
    def _generate_semantic_analysis_mock(self) -> str:
        """Genera una risposta mock per analisi semantica e macro-emotiva"""
        mock_data = {
            "block_analysis": {
                "valence": 0.3,
                "arousal": 0.7,
                "tension": 0.8,
                "primary_emotion": "tensione",
                "secondary_emotion": "inquietudine crescente",
                "setting": "Neo-Kyoto, distretto industriale",
                "has_dialogue": True,
                "audio_cues": ["pioggia", "ronzio_elettrico", "passi"]
            },
            "narrative_markers": [
                {
                    "relative_position": 0.2,
                    "event": "incontro misterioso",
                    "mood_shift": "neutro -> tensione"
                }
            ],
            "entities": [
                {
                    "entity_id": "ent_001",
                    "text": "Neo-Kyoto",
                    "entity_type": "luogo",
                    "emotional_tone": "neutro",
                    "confidence": 0.98,
                    "metadata": {}
                },
                {
                    "entity_id": "ent_002",
                    "text": "Kaelen",
                    "entity_type": "persona",
                    "emotional_tone": "tensione",
                    "confidence": 0.99,
                    "metadata": {}
                }
            ],
            "relations": [
                {
                    "relation_id": "rel_001",
                    "source_entity_id": "ent_002",
                    "target_entity_id": "ent_001",
                    "relation_type": "localizzazione",
                    "confidence": 0.95
                }
            ],
            "concepts": [
                {
                    "concept_id": "concept_001",
                    "concept": "città cyberpunk",
                    "definition": "Un ambiente urbano futuristico caratterizzato da tecnologia avanzata e decadimento sociale",
                    "emotional_tone": "neutro",
                    "confidence": 0.92
                }
            ],
            "confidence_score": 0.95
        }
        
        return json.dumps(mock_data, indent=2, ensure_ascii=False)
    
    def _generate_scene_analysis_mock(self) -> str:
        """Genera una risposta mock per annotazione testo Fish"""
        # Risposta pulita per evitare errori di parsing
        return '{"annotated_text": "[Istruzione: Narra con tono cupo.] (sospira) Neo-Kyoto rifletteva sul metallo. (passi) Kaelen era seguito."}'


def create_mock_gemini_client(logger: Optional[logging.Logger] = None) -> MockGeminiClient:
    """Factory function per creare un mock client"""
    return MockGeminiClient(logger=logger)