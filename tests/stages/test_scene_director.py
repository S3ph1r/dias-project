import pytest
import json
import logging
from unittest.mock import MagicMock
from src.stages.stage_c_scene_director import SceneDirector, TextDirector
from src.stages.mock_gemini_client import MockGeminiClient

@pytest.fixture
def mock_gemini():
    return MockGeminiClient(logger=logging.getLogger("test"))

@pytest.fixture
def scene_director(mock_gemini):
    return SceneDirector(gemini_client=mock_gemini)

def test_text_director_fish_markers(mock_gemini):
    td = TextDirector(gemini_client=mock_gemini, logger=logging.getLogger("test"))
    # Use keywords that trigger MockGeminiClient Stage C mock
    annotated = td.annotate_text_for_fish("Questa è una scena per il tts marcatori.", "gioia")
    
    assert "(" in annotated
    assert ")" in annotated
    assert "[Istruzione:" in annotated
    assert "Narra con tono cupo" in annotated

def test_scene_director_processing(scene_director):
    # Mock input da Stage B
    message = {
        "status": "success",
        "block_id": "test_block",
        "book_id": "test_book",
        "analysis_id": "test_analysis",
        "entities_count": 2,
        "relations_count": 1,
        "concepts_count": 1,
        "entities": [
            {"entity_id": "ent1", "text": "Kaelen", "entity_type": "persona", "emotional_tone": "gioia"}
        ],
        "relations": [],
        "concepts": [
            {"concept_id": "conc1", "concept": "cyberpunk", "emotional_tone": "tensione"}
        ]
    }
    
    # Mock persistence loading (since we are not actually saving files in this test)
    scene_director._load_text_block = MagicMock(return_value="Kaelen stava correndo tra i grattacieli di Neo-Kyoto. Il cuore batteva forte.")
    scene_director._load_macro_analysis = MagicMock(return_value=message)
    scene_director.persistence.save_stage_output = MagicMock(return_value="/tmp/test.json")
    
    result = scene_director.process(message)
    
    assert result["status"] == "ready_for_stage_d"
    assert result["scenes_count"] > 0
    
    # Verifica che la prima scena abbia il backend corretto e i marcatori fish
    # StageCSceneDirector.process_item ritorna un riassunto, dobbiamo scavare nei log o mockare meglio il salvataggio
    # Ma il process_item chiama _create_scene_script
