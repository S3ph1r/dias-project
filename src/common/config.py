"""
DIAS Configuration System

Carica config/dias.yaml con supporto per:
- Validazione Pydantic
- Override via environment variables (DIAS_REDIS_HOST, etc.)
- Singleton pattern per accesso globale
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


# --- Sub-models ---

class GoogleConfig(BaseModel):
    model_flash_lite: str = "gemini-2.5-flash-lite-preview-06-17"
    rate_limit_seconds: int = 30
    rate_limit_penalty_seconds: int = 120
    max_retries: int = 3
    temperature: float = 0.2
    response_mime_type: str = "application/json"


class ModelSpec(BaseModel):
    name: str
    device: str = "cuda"
    max_memory_gb: int = 8
    batch_size: int = 1


class ModelsConfig(BaseModel):
    qwen3_tts: ModelSpec = ModelSpec(name="Qwen3-TTS-12Hz-1.7B-Base")
    musicgen: ModelSpec = ModelSpec(name="musicgen-small", max_memory_gb=4)


class RedisConfig(BaseModel):
    host: str = "192.168.1.120"
    port: int = 6379
    db: int = 0
    decode_responses: bool = True
    retry_attempts: int = 3
    retry_backoff_base: float = 1.0


class QueuesConfig(BaseModel):
    ingestion: str = "dias:queue:1:ingestion"
    macro_analysis: str = "dias:queue:2:macro_analysis"
    scene_director: str = "dias:queue:3:scene_director"
    voice_gen: str = "dias:queue:4:voice_gen"
    music_gen: str = "dias:queue:5:music_gen"
    mixing: str = "dias:queue:6:mixing"
    mastering: str = "dias:queue:7:mastering"


class StorageConfig(BaseModel):
    base_path: str = "/mnt/dias/storage"
    temp_path: str = "/mnt/dias/temp"
    voice_output: str = "{base_path}/audio/voice/{book_id}"
    music_output: str = "{base_path}/audio/music/{book_id}"
    final_output: str = "{base_path}/output/{book_id}"


class PipelineConfig(BaseModel):
    max_chunk_words: int = 2500
    chunk_overlap_words: int = 100
    scene_max_words: int = 300
    default_voice_sample: str = "/voices/default_narrator.wav"


class AudioConfig(BaseModel):
    sample_rate: int = 48000
    voice_channels: int = 1
    music_channels: int = 2
    final_bitrate: str = "320k"
    target_lufs: int = -16
    head_silence_seconds: int = 2
    tail_silence_seconds: int = 3


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"
    file: Optional[str] = None


# --- Main Config ---

class DiasConfig(BaseModel):
    """Configurazione completa DIAS Pipeline."""
    google: GoogleConfig = GoogleConfig()
    models: ModelsConfig = ModelsConfig()
    redis: RedisConfig = RedisConfig()
    queues: QueuesConfig = QueuesConfig()
    storage: StorageConfig = StorageConfig()
    pipeline: PipelineConfig = PipelineConfig()
    audio: AudioConfig = AudioConfig()
    logging: LoggingConfig = LoggingConfig()


# --- Singleton ---

_config_instance: Optional[DiasConfig] = None


def _find_config_file() -> Path:
    """Cerca dias.yaml risalendo dalla directory corrente."""
    # 1. Env var esplicita
    env_path = os.environ.get("DIAS_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # 2. Path relativo standard dal progetto DIAS
    candidates = [
        Path(__file__).parent.parent.parent / "config" / "dias.yaml",  # src/common/ -> root
        Path.cwd() / "config" / "dias.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "dias.yaml non trovato. Imposta DIAS_CONFIG_PATH o esegui dalla root del progetto DIAS."
    )


def _apply_env_overrides(data: dict) -> dict:
    """Override valori config con environment variables DIAS_*."""
    env_map = {
        "DIAS_REDIS_HOST": ("redis", "host"),
        "DIAS_REDIS_PORT": ("redis", "port"),
        "DIAS_REDIS_DB": ("redis", "db"),
        "DIAS_LOG_LEVEL": ("logging", "level"),
        "DIAS_STORAGE_BASE": ("storage", "base_path"),
    }
    for env_key, path in env_map.items():
        value = os.environ.get(env_key)
        if value is not None:
            section, key = path
            if section not in data:
                data[section] = {}
            # Conversione tipo per port/db
            if key in ("port", "db"):
                value = int(value)
            data[section][key] = value
    return data


def load_config(config_path: Optional[Path] = None) -> DiasConfig:
    """
    Carica la configurazione DIAS.

    Args:
        config_path: Path esplicito al file dias.yaml. Se None, cerca automaticamente.

    Returns:
        DiasConfig validata e pronta all'uso.
    """
    global _config_instance

    if _config_instance is not None and config_path is None:
        return _config_instance

    path = config_path or _find_config_file()
    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}

    raw = _apply_env_overrides(raw)
    config = DiasConfig(**raw)

    if config_path is None:
        _config_instance = config

    return config


def get_config() -> DiasConfig:
    """Ritorna la config singleton. Chiama load_config() se non ancora caricata."""
    if _config_instance is None:
        return load_config()
    return _config_instance


def reset_config() -> None:
    """Reset del singleton (utile per testing)."""
    global _config_instance
    _config_instance = None
