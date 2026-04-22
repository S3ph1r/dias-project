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
    subtext: Optional[str] = None            # New in v1.2
    narrative_arc: Optional[str] = None      # New in v1.2
    narrator_base_tone: Optional[str] = None # New in v1.2
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


# --- Master Timing Grid ---

class TimingScene(BaseModel):
    """Timing atomico per una singola voce/scena."""
    scene_id: str
    start_offset: float = Field(ge=0.0)
    voice_duration: float = Field(ge=0.0)
    pause_after: float = Field(ge=0.0, default=0.0)
    total_scene_time: float = Field(ge=0.0)
    speaker: Optional[str] = None


class TimingMicroChunk(BaseModel):
    """Aggregazione timing per un micro-chunk (~300 parole)."""
    micro_chunk_id: str
    start_offset: float = Field(ge=0.0)
    duration: float = Field(ge=0.0)
    scenes: List[TimingScene] = Field(default_factory=list)


class TimingMacroChunk(BaseModel):
    """Aggregazione timing per un macro-chunk (~2500 parole)."""
    macro_chunk_id: str
    start_offset: float = Field(ge=0.0)
    duration: float = Field(ge=0.0)
    micro_chunks: Dict[str, TimingMicroChunk] = Field(default_factory=dict)


class MasterTimingGrid(BaseModel):
    """La Master Timing Grid definitiva per un progetto."""
    project_id: str
    total_duration_seconds: float = Field(ge=0.0)
    macro_chunks: Dict[str, TimingMacroChunk] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Stage B2: Sound Orchestration (v4 — Sound-on-Demand) ---


class PadArcSegment(BaseModel):
    """
    Un segmento della partitura emotiva del PAD per un macro-chunk.
    Descrive il livello di intensità musicale (low/mid/high) in un
    intervallo di tempo specifico. Stage E usa questi segmenti per
    attivare/disattivare gli stem (Bass, Drums, Vocals, Other) nel tempo.

    HTDemucs produce 4 stem:
      - bass:   Frequenze basse (basso, sub-synth, archi gravi)
      - drums:  Elementi percussivi (kick, snare, hi-hat, timpani)
      - vocals: Contenuto vocale (coro, vocal pad, voce umana)
      - other:  Tutto il resto (melodia, armonia, pad, archi, ottoni, synth, effetti)
    """
    start_s: float = Field(ge=0.0, description="Secondo di inizio del segmento")
    end_s: float = Field(gt=0.0, description="Secondo di fine del segmento")
    intensity: str = Field(
        description="Livello di intensità: 'low'=solo Bass, 'mid'=Bass+Other, 'high'=Bass+Other+Drums (+Vocals se presenti)"
    )
    note: Optional[str] = None  # Nota opzionale per traceability (es: "tensione pre-climax")
    roadmap_item: Optional[str] = Field(
        default=None,
        description="ACE-Step structural roadmap in EN. Formato: '[MM:SS - [section_tag]. Description]'"
    )


class PadRequest(BaseModel):
    """
    La richiesta completa di un PAD musicale per un macro-chunk.
    Contiene sia le istruzioni tecniche per ARIA ACE-Step 1.5 XL, sia la partitura
    emotiva (arc) che Stage E userà per gestire i 4 layer stem nel tempo.

    ARIA produce UN SOLO file master (via ACE-Step XL).
    ARIA esegue HTDemucs per isolare: bass, drums, vocals, other.
    Stage D2 scarica master + 4 stem da ARIA.
    Stage E carica i 4 stem e li gestisce dinamicamente via pad_arc.
    """
    canonical_id: str = Field(
        description="ID semantico universale EN. Formato: pad_{style}_{emotion}_{variant_num}"
    )
    production_prompt: str = Field(
        min_length=10,
        description="Descrizione leggibile del PAD (fallback/traceability). "
                    "Il campo primario per ACE-Step è production_tags."
    )
    production_tags: str = Field(
        default="",
        description="Comma-separated EN keywords per ACE-Step: genere, strumenti, effetti, era, texture. "
                    "Es: '70s retro-futuristic, ARP String Ensemble, spring reverb, tape saturation'"
    )
    negative_prompt: str = Field(
        default="epic, cinematic, generic ai, polished pop production",
        description="Comma-separated EN exclusions per ACE-Step CFG. "
                    "Es: 'epic, cinematic, orchestral, modern heroic, edm, dance'"
    )
    guidance_scale: float = Field(
        default=4.5, ge=1.0, le=15.0,
        description="CFG scale per ACE-Step. 4.5=vintage/realistico, 7.0=netto/definito"
    )
    inference_steps: int = Field(
        default=60, ge=10, le=200,
        description="Passi di denoising ACE-Step. 60 per produzione HQ."
    )
    is_leitmotif: bool = Field(
        default=False,
        description="Se True, è un Brand Sound del progetto (già prodotto). D2 non lo rigenera."
    )
    estimated_duration_s: Optional[float] = Field(
        default=None,
        description="Durata stimata in secondi. ARIA gestisce internamente (chaining se >4min)."
    )
    pad_arc: List[PadArcSegment] = Field(
        default_factory=list,
        description="Partitura emotiva: sequenza di segmenti temporali con intensità low/mid/high. "
                    "Ogni segmento contiene anche roadmap_item per la structural roadmap ACE-Step."
    )


class MacroCue(BaseModel):
    """
    Output dello Stage B2-Macro (v4).
    Contiene la richiesta completa del PAD (da produrre ex-novo) +
    la giustificazione artistica della scelta.
    """
    project_id: str
    chunk_label: str
    pad: PadRequest
    music_justification: str = Field(
        description="Spiegazione della scelta: palette, emozione, ritmo narrativo."
    )


class MicroCueAutomation(BaseModel):
    """
    Automazione sonora per una singola scena (v4).
    I campi pad_ gestiscono il DUCKING locale (respiro micro).
    I layer stem (low/mid/high) sono gestiti da Stage E via pad_arc del MacroCue.
    """
    scene_id: str
    # PAD breathing (micro-level ducking — si sovrappone all'arco macro)
    pad_volume_automation: str = "ducking"   # ducking | build | neutral
    pad_duck_depth: Optional[str] = "medium" # shallow(-6dB) | medium(-12dB) | deep(-18dB)
    pad_fade_speed: str = "smooth"           # snap(0.3s) | smooth(1s) | slow(2.5s)
    # AMB — ambiente fisico
    amb_id: Optional[str] = None
    amb_offset_s: float = 0.0
    amb_duration_s: Optional[float] = None
    # SFX — effetto fisico puntuale
    sfx_id: Optional[str] = None
    sfx_timing: Optional[str] = None  # start | middle | end
    sfx_offset_s: float = 0.0
    # STING — accento drammatico (max 1 per blocco)
    sting_id: Optional[str] = None
    sting_timing: Optional[str] = None  # middle | end (mai start)
    # Traceability
    reasoning: str = ""


class SoundShoppingItem(BaseModel):
    """
    Richiesta di produzione di un asset sonoro ad ARIA (v4.1 — ACE-Step Ready).

    Ogni asset richiesto da B2-Micro contiene sia il copione artistico (per traceability)
    sia le istruzioni tecniche per ACE-Step (tags, negative_prompt, parametri).
    Stage D2 invia questi item ad ARIA su aria:q:mus:local:acestep-1.5-xl-sft:dias.
    """
    type: str = Field(description="Categoria asset: pad | amb | sfx | sting. "
                      "Determina lo strumento usato lato ARIA.")
    canonical_id: str = Field(
        description="ID fisico EN dalla Tassonomia. Formato: {category}_{description}_{variant_num}"
    )
    production_prompt: str = Field(
        min_length=10,
        description="Descrizione leggibile (fallback/traceability). "
                    "Il campo primario per ACE-Step è production_tags."
    )
    production_tags: str = Field(
        default="",
        description="Comma-separated EN keywords per ACE-Step: tipo, frequenze, materiale, durata. "
                    "Es: 'spacecraft interior, engine hum 40-80Hz, air filtration, stereo wide'"
    )
    negative_prompt: str = Field(
        default="",
        description="Comma-separated EN exclusions per ACE-Step. "
                    "Es: 'music, melody, vocals, rhythm' (per SFX/AMB)"
    )
    guidance_scale: float = Field(
        default=7.0, ge=1.0, le=15.0,
        description="CFG scale. 7.0 default per AMB/SFX/STING (suoni netti/definiti)"
    )
    duration_s: float = Field(
        default=10.0, ge=0.1,
        description="Durata desiderata in secondi per l'asset"
    )
    scene_id: Optional[str] = Field(default=None, description="Scena richiedente (per traceability)")


class LeitmotifEvent(BaseModel):
    """Assegnazione di un leitmotif a una scena specifica (v4.1)."""
    scene_id: str
    leitmotif_id: str = Field(description="canonical_id da project_sound_palette (es. leitmotif_andrew_dahl_base)")
    timing: str = "start"   # start | middle | end
    reasoning: str = ""


class IntegratedCueSheet(BaseModel):
    """
    Il 'Copione Artistico Integrato' prodotto da B2-Micro (v4).
    Contiene TUTTE le scene del micro-blocco (anche quelle silenziose)
    più la sound_shopping_list che è la faccia duale del copione:
    ogni canonical_id usato nelle scene DEVE avere un entry corrispondente
    nella shopping list (Stage D2 produrrà quell'asset).
    """
    project_id: str
    block_id: str
    pad_canonical_id: str = Field(
        description="canonical_id del PAD ereditato da MacroCue. "
                    "Stage E lo usa per trovare gli stem nel manifest di D2."
    )
    scenes_automation: List[MicroCueAutomation] = Field(default_factory=list)
    sound_shopping_list: List[SoundShoppingItem] = Field(
        default_factory=list,
        description="TUTTI gli asset richiesti in questo blocco (AMB, SFX, STING). "
                    "Deve essere coerente con scenes_automation: se amb_id='X' è in una scena, "
                    "allora 'X' DEVE essere nella shopping list."
    )
    leitmotif_events: List[LeitmotifEvent] = Field(
        default_factory=list,
        description="Eventi leitmotif non-diegetici del blocco. "
                    "Prodotti da D2 (ACE-Step), mixati da Stage E sopra il PAD."
    )


# Alias di retrocompatibilità (non usare in nuovo codice)
ShoppingItem = SoundShoppingItem


# --- Stage B2-Micro: Director/Engineer Split (v1.0) ---

class AmbientEvent(BaseModel):
    """Evento ambientale fisico identificato dal Director. Nessun vocabolario tecnico."""
    trigger_description: str = Field(description="Descrizione narrativa del cambio di scena")
    physical_description: str = Field(description="Descrizione fisica dell'ambiente (italiano)")
    estimated_duration_s: float = Field(default=4.0, ge=3.0, le=5.0)
    target_scene_id: Optional[str] = Field(default=None, description="Scena di applicazione")


class SfxEvent(BaseModel):
    """Evento SFX fisico identificato dal Director. Solo momenti culminanti."""
    trigger_description: str = Field(description="Descrizione narrativa dell'azione culminante")
    physical_description: str = Field(description="Descrizione fisica del suono prodotto")
    estimated_duration_s: float = Field(default=0.5, ge=0.1, le=3.0)


class StingEvent(BaseModel):
    """Evento STING identificato dal Director. Solo rivelazioni irreversibili."""
    trigger_description: str = Field(description="Descrizione della rivelazione/svolta")
    revelation_type: str = Field(description="Tipo di momento irreversibile")
    estimated_duration_s: float = Field(default=3.0, ge=1.5, le=4.0)


class SceneEvent(BaseModel):
    """
    Copione eventi sonori per una singola scena — output del B2-Micro-Director.
    Contiene COSA succede fisicamente. Nessuna specifica tecnica ACE-Step.
    """
    scene_id: str
    pad_behavior: str = Field(
        default="ducking",
        description="Comportamento PAD: ducking | build | full | silence"
    )
    pad_duck_depth: Optional[str] = Field(
        default="medium",
        description="shallow | medium | deep. Null se pad_behavior='build'"
    )
    ambient_event: Optional[AmbientEvent] = None
    sfx_event: Optional[SfxEvent] = None
    sting_event: Optional[StingEvent] = None


class SoundEventScore(BaseModel):
    """
    Output del B2-Micro-Director.
    Descrive gli eventi fisici che giustificano un suono, scena per scena.
    Input per il B2-Micro-Engineer che produce le spec ACE-Step.
    """
    project_id: str
    block_id: str
    pad_canonical_id: str
    scenes: List[SceneEvent]
    asset_summary: List[str] = Field(
        default_factory=list,
        description="Sommario degli asset richiesti: ['AMB: urban street 4s', 'SFX: gunshot 0.3s']"
    )


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
