"""
DIAS Common Library

Layer condiviso per tutti i 7 stadi della pipeline DIAS.
"""

from .config import DiasConfig, load_config, get_config, reset_config
from .logging_setup import setup_logging, get_logger
from .redis_client import DiasRedis
from .base_stage import BaseStage
from .models import (
    IngestionBlock,
    BlockAnalysis,
    MacroAnalysisResult,
    NarrativeMarker,
    ChapterAnalysis,
    VoiceDirection,
    TimingEstimate,
    AmbientLayer,
    SpotEffect,
    MusicLayer,
    Transitions,
    AudioLayers,
    SceneScript,
)

__all__ = [
    # Config
    "DiasConfig",
    "load_config",
    "get_config",
    "reset_config",
    # Logging
    "setup_logging",
    "get_logger",
    # Redis
    "DiasRedis",
    # Base Stage
    "BaseStage",
    # Models
    "IngestionBlock",
    "BlockAnalysis",
    "MacroAnalysisResult",
    "NarrativeMarker",
    "ChapterAnalysis",
    "VoiceDirection",
    "TimingEstimate",
    "AmbientLayer",
    "SpotEffect",
    "MusicLayer",
    "Transitions",
    "AudioLayers",
    "SceneScript",
]
