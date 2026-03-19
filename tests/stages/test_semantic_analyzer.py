"""
Test suite per Stage B Semantic Analyzer
Valida l'analisi semantica con Gemini API e rate limiting
"""
import pytest
import json
import time
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from src.stages.stage_b_semantic_analyzer import (
    StageBSemanticAnalyzer,
    gemini_rate_limiter
)
from src.common.models import (
    MacroAnalysisResult,
    BlockAnalysis,
    NarrativeMarker,
    SemanticEntity,
    SemanticRelation,
    SemanticConcept,
    PrimaryEmotion
)
from stages.gemini_rate_limiter import GeminiRateLimiter
from common.redis_client import DiasRedis


class TestGeminiRateLimiter:
    """Test suite per il rate limiter di Gemini API"""
    
    def test_rate_limiter_initialization(self):
        """Test inizializzazione rate limiter"""
        limiter = GeminiRateLimiter(requests_per_interval=2, interval_minutes=10)
        
        assert limiter.requests_per_interval == 2
        assert limiter.interval.total_seconds() == 600  # 10 minuti
        assert len(limiter.request_times) == 0
    
    def test_can_make_request_initially(self):
        """Test che inizialmente possiamo fare richieste"""
        limiter = GeminiRateLimiter(requests_per_interval=1, interval_minutes=5)
        
        assert limiter.can_make_request() == True
    
    def test_rate_limit_blocking(self):
        """Test che il rate limiter blocca dopo il limite"""
        limiter = GeminiRateLimiter(requests_per_interval=1, interval_minutes=0.1)  # 6 secondi
        
        # Prima richiesta dovrebbe passare
        assert limiter.can_make_request() == True
        limiter.request_times.append(datetime.now())
        
        # Seconda richiesta dovrebbe essere bloccata
        assert limiter.can_make_request() == False
    
    def test_wait_for_slot(self):
        """Test attesa per slot disponibile"""
        limiter = GeminiRateLimiter(requests_per_interval=1, interval_minutes=0.05)  # 3 secondi
        
        # Aggiungi richiesta recente
        limiter.request_times.append(datetime.now())
        
        # Test che aspetta correttamente
        start_time = time.time()
        wait_time = limiter.wait_for_slot()
        end_time = time.time()
        
        # Dovrebbe aver atteso circa 3 secondi
        assert end_time - start_time >= 2.5  # Con tolleranza
        # Dopo wait_for_slot, abbiamo usato lo slot, quindi non dovrebbe essere disponibile
        assert limiter.can_make_request() == False
        
        # Aspetta che il tempo scada e verifica che diventi disponibile
        time.sleep(3.5)
        assert limiter.can_make_request() == True
    
    def test_get_status(self):
        """Test ottenimento stato del rate limiter"""
        limiter = GeminiRateLimiter(requests_per_interval=2, interval_minutes=5)
        
        # Aggiungi una richiesta
        limiter.request_times.append(datetime.now())
        
        status = limiter.get_status()
        
        assert status['requests_in_interval'] == 1
        assert status['max_requests'] == 2
        assert status['interval_minutes'] == 5
        assert status['can_make_request'] == True
    
    def test_reset(self):
        """Test reset del rate limiter"""
        limiter = GeminiRateLimiter()
        
        # Aggiungi richieste
        limiter.request_times.append(datetime.now())
        limiter.request_times.append(datetime.now())
        
        assert len(limiter.request_times) == 2
        
        # Reset
        limiter.reset()
        
        assert len(limiter.request_times) == 0


class TestStageBSemanticAnalyzer:
    """Test suite per Stage B Semantic Analyzer"""
    
    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client per testing"""
        mock = Mock(spec=DiasRedis)
        mock.push_to_queue = Mock()
        return mock
    
    @pytest.fixture
    def mock_gemini_client(self):
        """Mock Gemini client per testing"""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.text = json.dumps({
            "block_analysis": {
                "valence": 0.3,
                "arousal": 0.7,
                "tension": 0.8,
                "primary_emotion": "tensione",
                "secondary_emotion": "inquietudine",
                "setting": "Neo-Kyoto",
                "has_dialogue": True,
                "audio_cues": ["passi"]
            },
            "narrative_markers": [],
            "entities": [
                {
                    "entity_id": "ent_001",
                    "text": "Marco Polo",
                    "entity_type": "persona",
                    "emotional_tone": "neutro",
                    "confidence": 0.9,
                    "metadata": {}
                }
            ],
            "relations": [],
            "concepts": [],
            "confidence_score": 0.85
        })
        mock_client.models.generate_content.return_value = mock_response
        return mock_client
    
    @pytest.fixture
    def analyzer(self, mock_redis_client):
        """Fixture per Stage B analyzer con mock Redis"""
        # Reset global rate limiter
        gemini_rate_limiter.reset()
        
        with patch('src.stages.stage_b_semantic_analyzer.genai.Client') as mock_genai:
            
            mock_client = Mock()
            mock_response = Mock()
            mock_response.text = json.dumps({
                "entities": [],
                "relations": [],
                "concepts": [],
                "confidence_score": 0.0
            })
            mock_client.models.generate_content.return_value = mock_response
            mock_genai.return_value = mock_client
            
            analyzer = StageBSemanticAnalyzer(redis_client=mock_redis_client)
            return analyzer
    
    def test_analyzer_initialization(self, analyzer):
        """Test inizializzazione analyzer"""
        assert analyzer.model_name == "gemini-flash-lite-latest"
        assert analyzer.redis_client is not None
        assert analyzer.gemini_client is not None
    
    def test_process_valid_message(self, analyzer):
        """Test processing messaggio valido"""
        message = {
            "block_id": "block_123",
            "book_id": "book_456",
            "text": "Marco Polo è stato un famoso esploratore veneziano.",
            "metadata": {"chapter": 1, "position": 100}
        }
        
        result = analyzer.process(message)
        
        assert result["status"] == "success"
        assert result["block_id"] == "block_123"
        assert result["book_id"] == "book_456"
        assert "job_id" in result
        assert analyzer.redis_client.push_to_queue.called
    
    def test_process_missing_required_fields(self, analyzer):
        """Test processing con campi richiesti mancanti"""
        # Manca block_id
        message = {
            "book_id": "book_456",
            "text": "Testo di esempio"
        }
        
        result = analyzer.process(message)
        
        assert result["status"] == "error"
        assert "error" in result
    
    def test_process_missing_text(self, analyzer):
        """Test processing con testo mancante"""
        message = {
            "block_id": "block_123",
            "book_id": "book_456"
            # Manca text
        }
        
        result = analyzer.process(message)
        
        assert result["status"] == "error"
        assert "error" in result
    
    def test_rate_limit_integration(self, analyzer):
        """Test integrazione con rate limiter"""
        # Reset rate limiter
        gemini_rate_limiter.reset()
        
        message = {
            "block_id": "block_123",
            "book_id": "book_456",
            "text": "Testo di esempio per test rate limit",
            "metadata": {}
        }
        
        # Prima richiesta dovrebbe andare bene
        result1 = analyzer.process(message)
        assert result1["status"] == "success"
        
        # Seconda richiesta dovrebbe essere gestita dal rate limiter
        # (ma dovrebbe comunque andare a buon fine con attesa)
        result2 = analyzer.process(message)
        assert result2["status"] == "success"
    
    def test_gemini_response_parsing(self, analyzer):
        """Test parsing risposta Gemini"""
        mock_response_text = """
        {
            "block_analysis": {
                "valence": 0.9,
                "arousal": 0.5,
                "tension": 0.2,
                "primary_emotion": "gioia",
                "setting": "Giardino",
                "has_dialogue": false,
                "audio_cues": []
            },
            "narrative_markers": [],
            "entities": [
                {
                    "entity_id": "ent_test",
                    "text": "Test Entity",
                    "entity_type": "persona",
                    "emotional_tone": "gioia",
                    "confidence": 0.9,
                    "metadata": {"test": true}
                }
            ],
            "relations": [],
            "concepts": [],
            "confidence_score": 0.9
        }
        """
        
        result = analyzer._parse_gemini_response(mock_response_text)
        
        assert len(result['entities']) == 1
        assert result['entities'][0].text == "Test Entity"
        assert result['block_analysis'].primary_emotion == "gioia"
    
    def test_invalid_json_response(self, analyzer):
        """Test gestione risposta JSON invalida"""
        invalid_response = "Questa non è una risposta JSON valida"
        
        result = analyzer._parse_gemini_response(invalid_response)
        
        assert result['entities'] == []
        assert result['relations'] == []
        assert result['concepts'] == []
        assert result['confidence_score'] == 0.0
    
    def test_semantic_entity_validation(self):
        """Test validazione SemanticEntity"""
        # Valid
        entity = SemanticEntity(
            entity_id="ent_001",
            text="Test Entity",
            entity_type="persona",
            emotional_tone="neutro",
            confidence=0.9
        )
        assert entity.entity_id == "ent_001"
        
        # Invalid confidence
        with pytest.raises(ValueError):
            SemanticEntity(
                entity_id="ent_002",
                text="Test",
                entity_type="persona",
                emotional_tone="neutro",
                confidence=1.5  # > 1.0
            )
    
    def test_semantic_relation_validation(self):
        """Test validazione SemanticRelation"""
        relation = SemanticRelation(
            relation_id="rel_001",
            source_entity_id="ent_001",
            target_entity_id="ent_002",
            relation_type="lavora_per",
            confidence=0.8
        )
        assert relation.relation_id == "rel_001"
    
    def test_semantic_concept_validation(self):
        """Test validazione SemanticConcept"""
        concept = SemanticConcept(
            concept_id="conc_001",
            concept="Intelligenza Artificiale",
            definition="Tecnologia che simula intelligenza umana",
            emotional_tone="neutro",
            confidence=0.95
        )
        assert concept.concept == "Intelligenza Artificiale"
    
    def test_semantic_analysis_validation(self):
        """Test validazione MacroAnalysisResult"""
        analysis = MacroAnalysisResult(
            job_id="job_001",
            block_id="block_001",
            book_id="book_001",
            block_analysis=BlockAnalysis(
                valence=0.5, arousal=0.5, tension=0.5, primary_emotion="neutro"
            ),
            entities=[],
            relations=[],
            concepts=[],
            narrative_markers=[]
        )
        assert analysis.job_id == "job_001"
    
    def test_save_analysis_error_handling(self, analyzer):
        """Test gestione errori nel salvataggio"""
        # Mock Redis per sollevare eccezione
        analyzer.redis_client.push_to_queue.side_effect = Exception("Redis error")
        
        analysis = MacroAnalysisResult(
            book_id="book_001",
            block_id="block_001",
            block_analysis=BlockAnalysis(
                valence=0.5, arousal=0.5, tension=0.5, primary_emotion="neutro"
            ),
            entities=[],
            relations=[],
            concepts=[]
        )
        
        # Non dovrebbe sollevare eccezione, solo loggare errore
        with patch.object(analyzer.logger, 'error') as mock_logger:
            analyzer._save_analysis(analysis)
            mock_logger.assert_called()
    
    def test_create_semantic_analysis_prompt(self, analyzer):
        """Test creazione prompt per analisi semantica"""
        text = "Marco Polo viaggiò in Asia nel XIII secolo."
        
        prompt = analyzer._create_semantic_analysis_prompt(text)
        
        assert "Marco Polo viaggiò in Asia nel XIII secolo" in prompt
        assert "entities" in prompt
        assert "relations" in prompt
        assert "concepts" in prompt
        assert "JSON" in prompt
    
    def test_get_rate_limit_status(self, analyzer):
        """Test ottenimento stato rate limit"""
        status = analyzer.get_rate_limit_status()
        
        assert "requests_in_interval" in status
        assert "max_requests" in status
        assert "can_make_request" in status
        assert status["max_requests"] == 1
        assert status["interval_minutes"] == 5


class TestStageBIntegration:
    """Test di integrazione con Stage A output"""
    
    def test_integration_with_stage_a_chunk(self):
        """Test processing di un chunk reale da Stage A"""
        # Simula output di Stage A
        stage_a_chunk = {
            "block_id": "chunk_001_from_cronache_silicio",
            "book_id": "cronache-silicio-2.0",
            "job_id": "test_job_123",
            "text": """
            La rivoluzione digitale ha trasformato radicalmente il nostro modo di vivere e lavorare.
            Internet, lo smartphone e l'intelligenza artificiale hanno creato nuove opportunità
            ma anche nuove sfide per la società contemporanea.
            """,
            "metadata": {
                "chapter_title": "Il Silicio e la Società",
                "chunk_index": 15,
                "word_count": 42,
                "start_position": 1500,
                "end_position": 1600
            }
        }

        with patch('src.stages.stage_b_semantic_analyzer.genai.Client') as mock_genai:
            
            mock_client = Mock()
            mock_response = Mock()
            mock_response.text = json.dumps({
                "entities": [
                    {
                        "entity_id": "ent_digital_rev",
                        "text": "rivoluzione digitale",
                        "entity_type": "concetto",
                        "confidence": 0.95,
                        "start_pos": 4,
                        "end_pos": 24,
                        "metadata": {"importance": "high"}
                    },
                    {
                        "entity_id": "ent_internet",
                        "text": "Internet",
                        "entity_type": "tecnologia",
                        "confidence": 0.98,
                        "start_pos": 95,
                        "end_pos": 103,
                        "metadata": {"category": "infrastructure"}
                    },
                    {
                        "entity_id": "ent_smartphone",
                        "text": "smartphone",
                        "entity_type": "tecnologia",
                        "confidence": 0.97,
                        "start_pos": 109,
                        "end_pos": 119,
                        "metadata": {"category": "device"}
                    },
                    {
                        "entity_id": "ent_ai",
                        "text": "intelligenza artificiale",
                        "entity_type": "tecnologia",
                        "confidence": 0.96,
                        "start_pos": 124,
                        "end_pos": 148,
                        "metadata": {"category": "ai"}
                    }
                ],
                "relations": [
                    {
                        "relation_id": "rel_001",
                        "source_entity_id": "ent_digital_rev",
                        "target_entity_id": "ent_internet",
                        "relation_type": "include",
                        "confidence": 0.9,
                        "evidence_text": "Internet, lo smartphone e l'intelligenza artificiale",
                        "metadata": {"relation_strength": "strong"}
                    },
                    {
                        "relation_id": "rel_002",
                        "source_entity_id": "ent_digital_rev",
                        "target_entity_id": "ent_smartphone",
                        "relation_type": "include",
                        "confidence": 0.9,
                        "evidence_text": "Internet, lo smartphone e l'intelligenza artificiale",
                        "metadata": {"relation_strength": "strong"}
                    },
                    {
                        "relation_id": "rel_003",
                        "source_entity_id": "ent_digital_rev",
                        "target_entity_id": "ent_ai",
                        "relation_type": "include",
                        "confidence": 0.9,
                        "evidence_text": "Internet, lo smartphone e l'intelligenza artificiale",
                        "metadata": {"relation_strength": "strong"}
                    }
                ],
                "concepts": [
                    {
                        "concept_id": "conc_societal_impact",
                        "concept": "impatto sulla società",
                        "definition": "L'effetto della tecnologia sul modo di vivere e lavorare della società",
                        "confidence": 0.92,
                        "frequency": 2,
                        "related_entities": ["ent_digital_rev"],
                        "metadata": {"theme": "society"}
                    },
                    {
                        "concept_id": "conc_opportunities_challenges",
                        "concept": "opportunità e sfide",
                        "definition": "I vantaggi e le difficoltà create dai cambiamenti tecnologici",
                        "confidence": 0.88,
                        "frequency": 1,
                        "related_entities": ["ent_digital_rev"],
                        "metadata": {"theme": "dual_nature"}
                    }
                ],
                "confidence_score": 0.91
            })
            mock_client.models.generate_content.return_value = mock_response
            mock_genai.return_value = mock_client
            
            # Mock Redis
            mock_redis = Mock()
            
            analyzer = StageBSemanticAnalyzer(redis_client=mock_redis)
            result = analyzer.process(stage_a_chunk)
            
            # Verifica risultato
            assert result["status"] == "success"
            assert result["job_id"] == "test_job_123"
            assert result["block_id"] == "chunk_001_from_cronache_silicio"
            assert result["book_id"] == "cronache-silicio-2.0"
            assert result["entities_count"] == 4
            assert result["relations_count"] == 3
            assert result["concepts_count"] == 2
            
            # Verifica che sia stato salvato in Redis
            assert mock_redis.push_to_queue.called
            
            # Verifica che la chiamata API abbia usato il rate limiter
            assert analyzer.get_rate_limit_status()["requests_in_interval"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])