"""
DIAS Pydantic Models

Type-safe models per tutti i messaggi inter-stadio della pipeline.
Basati sugli schema JSON del blueprint v3 (sezione 5).

Ogni stadio produce e consuma modelli definiti qui.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


# --- Enums ---

class TaskStatus(str, Enum):
    """Stati possibili di un task nel Master Registry."""
    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


# --- Stadio A: Ingestion Output ---

class BookMetadata(BaseModel):
    """Metadati di un libro processato dallo stadio A."""
    book_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    author: str = ""
    language: str = "en"
    word_count: int = Field(ge=0)
    chapter_count: int = Field(ge=1)
    file_path: str
    file_format: str
    processing_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestionBlock(BaseModel):
    """Messaggio prodotto dallo stadio A (TextIngester) per ogni blocco di testo."""
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    book_id: str
    chapter_id: str
    chapter_number: int = Field(ge=1)
    chapter_title: str = ""
    block_id: str
    block_text: str = Field(min_length=1)
    word_count: int = Field(ge=1)
    block_index: int = Field(ge=0)
    total_blocks_in_chapter: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Stadio B: MacroAnalysis Output ---

class NarrativeMarker(BaseModel):
    """Punto significativo nell'arco narrativo di un blocco."""
    relative_position: float = Field(ge=0.0, le=1.0)
    event: str
    mood_shift: str


class BlockAnalysis(BaseModel):
    """Analisi emotiva di un singolo blocco testuale."""
    valence: float = Field(ge=0.0, le=1.0)
    arousal: float = Field(ge=0.0, le=1.0)
    tension: float = Field(ge=0.0, le=1.0)
    primary_emotion: str = "neutro"
    secondary_emotion: Optional[str] = None
    setting: Optional[str] = None
    has_dialogue: bool = False
    audio_cues: List[str] = Field(default_factory=list)

    @field_validator("primary_emotion", mode="before")
    @classmethod
    def validate_emotion(cls, v):
        if not v: return "neutro"
        return str(v).lower()


class SemanticEntity(BaseModel):
    """Entità semantica estratta dal testo."""
    entity_id: str
    text: str
    entity_type: str
    emotional_tone: str = "neutro"
    confidence: float = Field(ge=0.0, le=1.0)
    speaking_style: Optional[str] = None  # Nota in inglese su come parla il personaggio (Stage B v2)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("emotional_tone", mode="before")
    @classmethod
    def validate_emotion(cls, v):
        if not v: return "neutro"
        return str(v).lower()


class SemanticRelation(BaseModel):
    """Relazione tra entità."""
    relation_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    confidence: float = Field(ge=0.0, le=1.0)


class SemanticConcept(BaseModel):
    """Concetto chiave estratto dal testo."""
    concept_id: str
    concept: str
    definition: str
    emotional_tone: str = "neutro"
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("emotional_tone", mode="before")
    @classmethod
    def validate_emotion(cls, v):
        if not v: return "neutro"
        return str(v).lower()


class MacroAnalysisResult(BaseModel):
    """Messaggio prodotto dallo stadio B (MacroAnalyzer) per ogni blocco."""
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    book_id: str
    block_id: str
    block_analysis: BlockAnalysis
    narrative_markers: List[NarrativeMarker] = Field(default_factory=list)
    entities: List[SemanticEntity] = Field(default_factory=list)
    relations: List[SemanticRelation] = Field(default_factory=list)
    concepts: List[SemanticConcept] = Field(default_factory=list)


# --- Stadio B→C: Chapter Aggregation ---

class ChapterAnalysis(BaseModel):
    """
    Messaggio aggregato prodotto da B quando tutti i blocchi di un capitolo
    sono analizzati. Input per lo stadio C (SceneDirector).
    """
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    book_id: str
    chapter_id: str
    chapter_number: int = Field(ge=1)
    chapter_title: str = ""
    full_text: str = Field(min_length=1)
    word_count: int = Field(ge=1)
    avg_valence: float = Field(ge=0.0, le=1.0)
    avg_arousal: float = Field(ge=0.0, le=1.0)
    avg_tension: float = Field(ge=0.0, le=1.0)
    dominant_emotion: str = "neutro"
    dominant_setting: Optional[str] = None
    all_audio_cues: List[str] = Field(default_factory=list)
    total_blocks: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("dominant_emotion", mode="before")
    @classmethod
    def validate_emotion(cls, v):
        if not v: return "neutro"
        return str(v).lower()


# --- Stadio C: SceneDirector Output ---

class VoiceDirection(BaseModel):
    """Direzione vocale per una scena."""
    emotion_description: str = Field(max_length=100)
    pace_factor: float = Field(ge=0.5, le=1.5)
    pitch_shift: int = Field(ge=-5, le=5, default=0)
    energy: float = Field(ge=0.0, le=1.0, default=0.5)
    recommended_silence_before_ms: int = Field(ge=0, default=0)
    recommended_silence_after_ms: int = Field(ge=0, default=0)


class TimingEstimate(BaseModel):
    """Stima temporale per una scena."""
    estimated_duration_seconds: float = Field(ge=0)
    words_per_minute: int = Field(ge=50, le=300, default=150)


class AmbientLayer(BaseModel):
    """Layer audio ambientale continuo."""
    type: str = "continuous"
    soundscape_tag: str
    volume_db: float = Field(ge=-60, le=0, default=-22)
    fade_in_ms: int = Field(ge=0, default=3000)
    fade_out_ms: int = Field(ge=0, default=4000)
    frequency_focus: Optional[str] = None


class SpotEffect(BaseModel):
    """Effetto sonoro puntuale in una scena."""
    trigger_anchor: Optional[str] = None
    effect_name: str
    offset_from_scene_start_ms: int = Field(ge=0)
    duration_ms: Optional[int] = Field(ge=0, default=None)
    volume_db: float = Field(ge=-60, le=0, default=-18)
    spatial_position: Optional[str] = None


class MusicLayer(BaseModel):
    """Layer musicale per una scena."""
    prompt_for_musicgen: str = Field(min_length=10, max_length=500)
    intensity_curve: List[float] = Field(default_factory=lambda: [0.3, 0.5, 0.3])
    entry_point: str = "with_voice"
    ducking_db: float = Field(ge=-30, le=0, default=-8)
    ducking_attack_ms: int = Field(ge=0, default=200)
    ducking_release_ms: int = Field(ge=0, default=800)

    @field_validator("intensity_curve")
    @classmethod
    def validate_intensity_curve(cls, v):
        if len(v) != 3:
            raise ValueError("intensity_curve must have exactly 3 values")
        for val in v:
            if not 0.0 <= val <= 1.0:
                raise ValueError("intensity_curve values must be between 0.0 and 1.0")
        return v


class Transitions(BaseModel):
    """Transizioni audio tra scene."""
    from_previous: str = "fade_in_1000ms"
    to_next: str = "crossfade_1500ms"


class TTSBackend(str, Enum):
    FISH_S1_MINI = "fish-s1-mini"
    ORPHEUS = "orpheus"
    ELEVENLABS = "elevenlabs"
    KOKORO = "kokoro"


class AudioLayers(BaseModel):
    """Tutti i layer audio per una scena."""
    ambient: Optional[AmbientLayer] = None
    spot_effects: List[SpotEffect] = Field(default_factory=list)
    music: MusicLayer
    transitions: Transitions = Transitions()


class SceneScript(BaseModel):
    """
    Audio script completo per una scena.
    Prodotto dallo stadio C (SceneDirector), consumato da D (VoiceGen).
    """
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    book_id: str
    chapter_id: str
    scene_id: str
    scene_number: int = Field(ge=0)
    text_content: str = Field(min_length=1)
    tts_backend: TTSBackend = TTSBackend.FISH_S1_MINI
    start_char_index: int = Field(ge=0, default=0)
    end_char_index: int = Field(ge=0, default=0)
    word_count: int = Field(ge=1)
    voice_direction: VoiceDirection
    timing_estimate: Optional[TimingEstimate] = None
    audio_layers: AudioLayers
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Master Registry ---

class RegistryEntry(BaseModel):
    """Voce del Master Registry di DIAS per il tracciamento dei task."""
    task_id: str
    status: TaskStatus
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempts: int = Field(default=0, ge=0)
    worker_id: Optional[str] = None
    callback_key: Optional[str] = None
    error: Optional[str] = None
    output_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
