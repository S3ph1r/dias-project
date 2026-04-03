"""
DIAS Common Library — Test Suite

Tutti i test usano fakeredis (mock) — non serve Redis server.

Run:
    cd /home/Projects/NH-Mini/sviluppi/dias
    pytest tests/test_common.py -v
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import fakeredis
import pytest
import yaml

# Assicura che src/ sia nel path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from common.config import DiasConfig, load_config, reset_config
from common.logging_setup import setup_logging
from common.redis_client import DiasRedis
from common.models import (
    IngestionBlock,
    BlockAnalysis,
    MacroAnalysisResult,
    ChapterAnalysis,
    SceneScript,
    VoiceDirection,
    MusicLayer,
    AudioLayers,
)
from common.base_stage import BaseStage


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def clean_config():
    """Reset config singleton prima di ogni test."""
    reset_config()
    yield
    reset_config()


@pytest.fixture
def sample_config_path(tmp_path):
    """Crea un dias.yaml temporaneo per i test."""
    config_data = {
        "google": {
            "model_flash_lite": "test-model",
            "rate_limit_seconds": 10,
        },
        "redis": {
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "decode_responses": True,
            "retry_attempts": 1,
            "retry_backoff_base": 0.01,
        },
        "queues": {
            "ingestion": "test:queue:1",
            "macro_analysis": "test:queue:2",
        },
        "logging": {
            "level": "DEBUG",
            "format": "json",
        },
    }
    config_file = tmp_path / "config" / "dias.yaml"
    config_file.parent.mkdir(parents=True)
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)
    return config_file


@pytest.fixture
def fake_redis():
    """Client fakeredis per test senza server."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def dias_redis(fake_redis):
    """DiasRedis con client mock."""
    return DiasRedis(client=fake_redis, retry_attempts=1, retry_backoff_base=0.01)


# ============================================================
# Config Tests
# ============================================================

class TestConfig:
    def test_config_loads_yaml(self, sample_config_path):
        """DiasConfig carica dias.yaml correttamente."""
        config = load_config(config_path=sample_config_path)
        assert config.google.model_flash_lite == "test-model"
        assert config.google.rate_limit_seconds == 10
        assert config.redis.host == "localhost"

    def test_config_defaults(self, tmp_path):
        """Valori default quando campi non specificati."""
        config_file = tmp_path / "config" / "dias.yaml"
        config_file.parent.mkdir(parents=True)
        with open(config_file, "w") as f:
            yaml.dump({}, f)

        config = load_config(config_path=config_file)
        assert config.redis.port == 6379
        assert config.audio.sample_rate == 48000
        assert config.pipeline.max_chunk_words == 2500
        assert config.audio.target_lufs == -16

    def test_config_env_override(self, sample_config_path):
        """Environment variable sovrascrive yaml."""
        with patch.dict(os.environ, {"DIAS_REDIS_HOST": "10.0.0.1"}):
            config = load_config(config_path=sample_config_path)
            assert config.redis.host == "10.0.0.1"

    def test_config_env_override_port(self, sample_config_path):
        """Override di port (conversione int)."""
        with patch.dict(os.environ, {"DIAS_REDIS_PORT": "6380"}):
            config = load_config(config_path=sample_config_path)
            assert config.redis.port == 6380

    def test_config_singleton(self, sample_config_path):
        """load_config ritorna la stessa istanza (singleton)."""
        # Simuliamo caricamento da env path per il test
        with patch.dict(os.environ, {"DIAS_CONFIG_PATH": str(sample_config_path)}):
            config1 = load_config()  # Carica e imposta singleton
            config2 = load_config()  # Ritorna singleton già caricato
            assert config1 is config2
            assert config1.google.model_flash_lite == "test-model"


# ============================================================
# Redis Client Tests
# ============================================================

class TestRedisClient:
    def test_redis_health_check(self, dias_redis):
        """health_check() ritorna True su fakeredis."""
        assert dias_redis.health_check() is True

    def test_redis_push_consume(self, dias_redis):
        """Push + consume round-trip su queue."""
        msg = {"book_id": "test-book", "data": "hello"}
        dias_redis.push_to_queue("test:queue", msg)

        result = dias_redis.consume_from_queue("test:queue", timeout=1)
        assert result is not None
        assert result["book_id"] == "test-book"
        assert result["data"] == "hello"

    def test_redis_consume_empty(self, dias_redis):
        """consume_from_queue ritorna None su coda vuota (timeout)."""
        result = dias_redis.consume_from_queue("empty:queue", timeout=1)
        assert result is None

    def test_redis_queue_length(self, dias_redis):
        """queue_length traccia correttamente."""
        assert dias_redis.queue_length("test:queue") == 0
        dias_redis.push_to_queue("test:queue", {"a": 1})
        dias_redis.push_to_queue("test:queue", {"b": 2})
        assert dias_redis.queue_length("test:queue") == 2

    def test_redis_checkpoint(self, dias_redis):
        """Set/get checkpoint."""
        assert dias_redis.get_checkpoint("book-123") is None

        dias_redis.set_checkpoint("book-123", 3)
        assert dias_redis.get_checkpoint("book-123") == 3

        dias_redis.set_checkpoint("book-123", 5)
        assert dias_redis.get_checkpoint("book-123") == 5

    def test_redis_lock_acquire_release(self, dias_redis):
        """Lock acquire/release."""
        assert dias_redis.acquire_lock("test-lock", ttl=60) is True
        dias_redis.release_lock("test-lock")
        # Dopo il release, possiamo riacquisire
        assert dias_redis.acquire_lock("test-lock", ttl=60) is True

    def test_redis_lock_contention(self, dias_redis):
        """Secondo acquire fallisce se lock attivo."""
        assert dias_redis.acquire_lock("test-lock", ttl=60) is True
        assert dias_redis.acquire_lock("test-lock", ttl=60) is False

    def test_redis_state(self, dias_redis):
        """State hash set/get."""
        dias_redis.set_state("dias:state:scene:s1", "voice_path", "/audio/s1.wav")
        dias_redis.set_state("dias:state:scene:s1", "status", "completed")

        assert dias_redis.get_state("dias:state:scene:s1", "voice_path") == "/audio/s1.wav"

        all_state = dias_redis.get_state("dias:state:scene:s1")
        assert all_state["status"] == "completed"

    def test_redis_throttle(self, dias_redis):
        """Throttle set/get."""
        assert dias_redis.get_throttle("api:google") is None

        dias_redis.set_throttle("api:google")
        ts = dias_redis.get_throttle("api:google")
        assert ts is not None
        assert isinstance(ts, float)


# ============================================================
# Models Tests
# ============================================================

class TestModels:
    def test_models_ingestion_block(self):
        """Validazione Pydantic IngestionBlock."""
        block = IngestionBlock(
            book_id="book-001",
            chapter_id="ch-001",
            chapter_number=1,
            chapter_title="Il Prologo",
            block_id="ch-001-blk-00",
            block_text="Era una notte buia e tempestosa...",
            word_count=6,
            block_index=0,
            total_blocks_in_chapter=1,
        )
        assert block.book_id == "book-001"
        assert block.word_count == 6
        assert block.job_id  # Auto-generated UUID

    def test_models_block_analysis_ranges(self):
        """Valence/arousal/tension devono essere in range 0-1."""
        analysis = BlockAnalysis(
            valence=0.25,
            arousal=0.75,
            tension=0.90,
            primary_emotion="suspense",
        )
        assert analysis.valence == 0.25
        assert analysis.primary_emotion == "suspense"

    def test_models_block_analysis_out_of_range(self):
        """Valori fuori range alzano ValidationError."""
        with pytest.raises(Exception):
            BlockAnalysis(
                valence=1.5,  # Out of range!
                arousal=0.5,
                tension=0.5,
                primary_emotion="neutro",
            )

    def test_models_scene_script(self):
        """SceneScript con sub-models nested."""
        scene = SceneScript(
            book_id="book-001",
            chapter_id="ch-003",
            scene_id="scene-ch003-00",
            scene_number=0,
            text_content="Il mattino del terzo giorno William si svegliò...",
            word_count=320,
            voice_direction=VoiceDirection(
                emotion_description="whispered_curiosity",
                pace_factor=0.82,
                energy=0.4,
            ),
            audio_layers=AudioLayers(
                music=MusicLayer(
                    prompt_for_musicgen="Gregorian choir ambient, distant, cold stone atmosphere",
                    intensity_curve=[0.2, 0.3, 0.5],
                    ducking_db=-8,
                ),
            ),
        )
        assert scene.scene_id == "scene-ch003-00"
        assert scene.voice_direction.pace_factor == 0.82
        assert len(scene.audio_layers.music.intensity_curve) == 3

    def test_models_invalid_rejected(self):
        """Dati invalidi alzano ValidationError."""
        # word_count < 1
        with pytest.raises(Exception):
            IngestionBlock(
                book_id="b1",
                chapter_id="ch1",
                chapter_number=1,
                block_id="blk-1",
                block_text="test",
                word_count=0,
                block_index=0,
                total_blocks_in_chapter=1,
            )

    def test_models_intensity_curve_validation(self):
        """intensity_curve deve avere esattamente 3 valori tra 0 e 1."""
        with pytest.raises(Exception):
            MusicLayer(
                prompt_for_musicgen="ambient test music prompt long enough",
                intensity_curve=[0.5, 0.5],  # Solo 2 valori!
            )

    def test_models_chapter_analysis(self):
        """ChapterAnalysis valida."""
        ch = ChapterAnalysis(
            book_id="book-001",
            chapter_id="ch-003",
            chapter_number=3,
            chapter_title="La Scoperta",
            full_text="Testo completo del capitolo...",
            word_count=2800,
            avg_valence=0.25,
            avg_arousal=0.75,
            avg_tension=0.85,
            dominant_emotion="suspense",
            all_audio_cues=["pages_turning", "door_creak"],
            total_blocks=2,
        )
        assert ch.avg_tension == 0.85
        assert len(ch.all_audio_cues) == 2

    def test_models_serialization_roundtrip(self):
        """Model → dict → JSON → dict → Model roundtrip."""
        block = IngestionBlock(
            book_id="book-001",
            chapter_id="ch-001",
            chapter_number=1,
            block_id="ch-001-blk-00",
            block_text="Test text for roundtrip",
            word_count=4,
            block_index=0,
            total_blocks_in_chapter=1,
        )
        json_str = block.model_dump_json()
        data = json.loads(json_str)
        restored = IngestionBlock(**data)
        assert restored.book_id == block.book_id
        assert restored.word_count == block.word_count


# ============================================================
# Base Stage Tests
# ============================================================

class ConcreteStage(BaseStage):
    """Implementazione concreta per test."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.processed = []

    def process(self, message):
        self.processed.append(message)
        return {"result": True, "book_id": message.get("book_id")}


class TestBaseStage:
    def test_base_stage_abstract(self):
        """BaseStage non istanziabile direttamente."""
        with pytest.raises(TypeError):
            BaseStage(
                stage_name="test",
                stage_number=1,
                input_queue="q:in",
            )

    def test_base_stage_subclass(self, sample_config_path, fake_redis):
        """Sottoclasse con process() si istanzia correttamente."""
        config = load_config(config_path=sample_config_path)
        redis_client = DiasRedis(client=fake_redis)

        stage = ConcreteStage(
            stage_name="test_stage",
            stage_number=1,
            input_queue="test:queue:in",
            output_queue="test:queue:out",
            config=config,
            redis_client=redis_client,
        )
        assert stage.stage_name == "test_stage"
        assert stage.stage_number == 1

    def test_base_stage_process_message(self, sample_config_path, fake_redis):
        """Stage processa un messaggio e produce output."""
        config = load_config(config_path=sample_config_path)
        redis_client = DiasRedis(client=fake_redis)

        stage = ConcreteStage(
            stage_name="test_stage",
            stage_number=1,
            input_queue="test:in",
            output_queue="test:out",
            config=config,
            redis_client=redis_client,
        )

        # Simula un messaggio in coda
        msg = {"book_id": "book-test", "data": "payload"}
        redis_client.push_to_queue("test:in", msg)

        # Processa un singolo messaggio manualmente
        raw = redis_client.consume_from_queue("test:in", timeout=1)
        result = stage.process(raw)

        assert result is not None
        assert result["result"] is True
        assert len(stage.processed) == 1

    def test_base_stage_shutdown(self, sample_config_path, fake_redis):
        """shutdown() imposta _running a False."""
        config = load_config(config_path=sample_config_path)
        redis_client = DiasRedis(client=fake_redis)

        stage = ConcreteStage(
            stage_name="test",
            stage_number=1,
            input_queue="q:in",
            config=config,
            redis_client=redis_client,
        )
        stage._running = True
        stage.shutdown()
        assert stage._running is False


# ============================================================
# Logging Tests
# ============================================================

class TestLogging:
    def test_logging_structured(self, capsys):
        """Output JSON con campi richiesti."""
        logger = setup_logging("test_stage", level="INFO")
        logger.info("Test message")

        captured = capsys.readouterr()
        log_line = captured.err.strip()
        log_data = json.loads(log_line)

        assert "timestamp" in log_data
        assert log_data["stage"] == "test_stage"
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test message"

    def test_logging_extra_fields(self, capsys):
        """Campi extra (book_id) inclusi se presenti."""
        logger = setup_logging("test_stage_extra", level="DEBUG")
        logger.info("Processing", extra={"book_id": "book-123"})

        captured = capsys.readouterr()
        log_line = captured.err.strip()
        log_data = json.loads(log_line)

        assert log_data["book_id"] == "book-123"
