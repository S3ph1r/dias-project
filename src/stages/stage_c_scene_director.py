#!/usr/bin/env python3
"""
Stage C - Scene Director
Segmenta blocchi di testo in scene e genera audio scripts ottimizzati per Qwen3-TTS.

Backend attivo: qwen3-tts-1.7b
Output: testo pulito (senza tag) + campo qwen3_instruct generato da Gemini.

Il vecchio prompt Fish S1-mini è preservato come FISH_ANNOTATION_PROMPT nel corpo
della classe TextDirector per riuso futuro.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

import google.genai as genai
from dotenv import load_dotenv

# Aggiungi il path src al Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.base_stage import BaseStage
from src.common.config import get_config
from src.common.redis_client import DiasRedis
from src.common.persistence import DiasPersistence
from src.stages.gemini_rate_limiter import gemini_rate_limiter
from src.stages.mock_gemini_client import MockGeminiClient
import logging


# ============================================================
# Mappa emozioni DIAS → istruzione stile Qwen3-TTS
# Usata da TextDirector.annotate_text_for_qwen3()
# ============================================================
EMOTION_TO_INSTRUCT_QWEN3 = {
    "neutro":     "Tone: Neutral. Rhythm: Moderate. Attitude: Factual.",
    "neutral":    "Tone: Neutral. Rhythm: Moderate. Attitude: Factual.",
    "tensione":   "Tone: Tense. Rhythm: Slow. Attitude: Detached.",
    "suspense":   "Tone: Tense. Rhythm: Slow. Attitude: Detached.",
    "paura":      "Tone: Dark. Rhythm: Slow. Attitude: Hesitant.",
    "fear":       "Tone: Dark. Rhythm: Slow. Attitude: Hesitant.",
    "tristezza":  "Tone: Melancholic. Rhythm: Slow. Attitude: Intimate.",
    "sadness":    "Tone: Melancholic. Rhythm: Slow. Attitude: Intimate.",
    "gioia":      "Tone: Bright. Rhythm: Moderate. Attitude: Conversational.",
    "joy":        "Tone: Bright. Rhythm: Moderate. Attitude: Conversational.",
    "rabbia":     "Tone: Dark. Rhythm: Fast. Attitude: Authoritative.",
    "anger":      "Tone: Dark. Rhythm: Fast. Attitude: Authoritative.",
    "curiosità":  "Tone: Bright. Rhythm: Moderate. Attitude: Factual.",
    "curiosity":  "Tone: Bright. Rhythm: Moderate. Attitude: Factual.",
}


class TextDirector:
    """Sub-stage per preparare testo e istruzione stile per Qwen3-TTS."""

    # ------------------------------------------------------------------
    # PROMPT FISH S1-MINI (BACKUP)
    # Mantenuto per riuso futuro se si vorrà tornare al backend Fish.
    # Non viene più chiamato nel flusso principale (usa annotate_text_for_qwen3).
    # ------------------------------------------------------------------
    FISH_ANNOTATION_PROMPT = """
        Sei un esperto regista audio specializzato in romanzi narrativi di alta qualità.
        Il tuo compito è trasformare il testo grezzo in uno SCRIPT ANNOTATO per la sintesi vocale (Fish S1-mini).

        REGOLE MANDATORIE DI FORMATTAZIONE (SILENZIO E RITMO):
        1. TITOLI E SOTTOTITOLI: chiudili con punto e inserisci (long-break) subito dopo.
        2. CAPITOLI E NUMERI: converti numeri romani in ORDINALI (es. "Capitolo I" -> "Capitolo Primo").
        3. PAUSE E RITMO: usa (break) per pausa media, (long-break) per pausa lunga tra paragrafi.
        4. TAG EMOZIONALI (PRIMA della frase):
           USA SOLO: (neutral), (serious), (whispering), (shouting), (sad), (happy), (excited),
           (angry), (fearful), (surprised), (disgusted), (worried), (joyful), (thoughtful),
           (indifferent), (hesitating), (sighing), (sincere), (sarcastic).
        5. PULIZIA: rimuovi ":" residui dopo i titoli.
        6. NORMALIZZAZIONE FONETICA: aggiungi accenti grafici su parole ambigue
           (es. "patina" -> "pàtina", "futon" -> "futòn").

        EMOZIONE SUGGERITA: {emotion_description}
        TESTO: {text_content}

        Rispondi ESCLUSIVAMENTE con JSON: {{"annotated_text": "..."}}
    """

    def __init__(self, gemini_client, config, logger: logging.Logger):
        self.gemini_client = gemini_client
        self.config = config
        self.logger = logger

    def annotate_text_for_qwen3(self, text_content: str, emotion: str, emotion_description: str) -> List[dict]:
        """
        Chiama Gemini per produrre output compatibile con Qwen3-TTS:
        - Suddivisione in SCENE basata su cambi di tono (Emotional Beats).
        - Testo PULITO (senza tag fish, senza return capo).
        - Conversione NUMERI in PAROLE per esteso (es. 2042 -> duemilaquarantadue).
        - Campo qwen3_instruct: istruzione stile in inglese.

        Returns:
            Lista di dict con chiavi 'clean_text', 'qwen3_instruct', 'scene_id_suffix'
        """
        # Instruct di fallback dalla mappa statica
        fallback_instruct = EMOTION_TO_INSTRUCT_QWEN3.get(
            emotion.lower(),
            EMOTION_TO_INSTRUCT_QWEN3["neutro"]
        )

        prompt = f"""
Sei un DIRETTORE ARTISTICO esperto in audiolibri.
Il tuo compito è trasformare un blocco di testo narrativo in una sequenza di SCENE AUDIO ottimizzate per un motore TTS Zero-Shot (Qwen3).

ANALISI E SEGMENTAZIONE (MANDATORIO):
Non dividere il testo meccanicamente. Crea una nuova scena ogni volta che c'è un cambio strutturale, temporale o emotivo.
Ogni scena narrativa deve avere una lunghezza compresa tra 40 e 300 parole circa.

REGOLE GENERALI SUI TITOLI E SULLA STRUTTURA (ISOLAMENTO MANDATORIO):
Analizza la struttura visiva del testo (ritorni a capo, frasi brevi isolate all'inizio).
Se il blocco inizia con una o più frasi brevi isolate (sotto le 15 parole) separate dal corpo principale da doppi ritorni a capo (\\n\\n) che fungono da Titolo della Saga, Titolo del Libro, o Titolo_Numero del Capitolo, DEVI isolare OGNUNA di queste in una scena singola e separata.
- NON unire mai un titolo strutturale con il paragrafo narrativo (incipit) che lo segue.

REGOLE SUL TESTO DELLA SCENA (clean_text):
1. PULIZIA TESTO:
   - Converti TUTTI i numeri arabi in parole scritte per esteso (es. "2042" → "duemilaquarantadue", "42-B" → "quarantadue B").
   - Converti numeri romani in ordinali (es. "Capitolo I" → "Capitolo Primo").
   - Rimuovi tutti i tag tra parentesi presenti (es. (neutral), (break), ecc.).
   - Rimuovi punteggiatura residua dai titoli (es. i ":" alla fine di un titolo di capitolo).
   - Aggiungi l'accento grafico sulle parole italiane ambigue: "pàtina", "futòn", "sùbito", "ancòra/àncora".
   - NON inserire tag di nessun tipo nel testo (clean_text).
2. PUNTEGGIATURA E RITMO:
   - Inserisci virgole extra (,) o puntini di sospensione (...) dove senti che la voce deve prendere fiato o creare suspense. Il TTS legge la punteggiatura come istruzioni di ritmo.

PARAMETRI DI REGIA (MANDATORIO per qwen3_instruct):
Per ogni scena generata, devi SCEGLIERE una e una sola opzione da ciascuna di queste 3 liste ESATTAMENTE come scritte (in Inglese):

1. Tone (Colore Emotivo): [Dark, Neutral, Bright, Solemn, Intimate, Tense, Melancholic, Joyful]
2. Rhythm (Pacing): [Very Slow, Slow, Moderate, Fast, Urgent]
3. Attitude (Intenzione): [Detached, Conversational, Whispered, Authoritative, Sarcastic, Hesitant, Factual]

EMOZIONE DI BASE (Rilevata nel blocco precedente): {emotion_description}

TESTO DA ELABORARE:
{text_content}

Rispondi ESCLUSIVAMENTE con un JSON che sia un ARRAY di oggetti. Formato esatto richiesto:
[
  {{
    "scene_label": "breve_descrizione_es_titolo_libro_o_descrizione",
    "clean_text": "Il testo pronto per la lettura, normalizzato e con accenti",
    "tone": "valore scelto dalla lista",
    "rhythm": "valore scelto dalla lista",
    "attitude": "valore scelto dalla lista"
  }},
  ...
]
"""

        max_retries = 5
        base_delay = 2

        for attempt in range(max_retries):
            try:
                # Applica pacing globale (30s)
                gemini_rate_limiter.wait_for_slot()
                
                self.logger.info(f"TextDirector Qwen3 Dynamic (tentativo {attempt+1}): emozione_base={emotion}")
                model_name = "gemini-2.5-flash" # Allineato a Stage B per coerenza
                
                if hasattr(self.gemini_client, 'models'):
                    response = self.gemini_client.models.generate_content(
                        model=model_name, contents=prompt
                    )
                    response_text = response.text
                else:
                    response_text = self.gemini_client.generate_content(prompt, model=model_name)

                response_text = response_text.strip()
                import re
                if "```json" in response_text:
                    match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
                    if match:
                        response_text = match.group(1)
                elif "[" in response_text and "]" in response_text:
                    match = re.search(r"(\[.*\])", response_text, re.DOTALL)
                    if match:
                        response_text = match.group(1)

                scenes_list = json.loads(response_text)
                if not isinstance(scenes_list, list):
                    scenes_list = [scenes_list]
                
                # Assemble the structured qwen3_instruct for each scene
                for scene in scenes_list:
                    # Se Gemini ha generato i campi separati, li assembliamo
                    if all(k in scene for k in ["tone", "rhythm", "attitude"]):
                        # Rimuoviamo il prefisso verboso "Warm Italian male voice..."
                        # per lasciare solo le direttive strutturali.
                        scene["qwen3_instruct"] = f"Tone: {scene.get('tone', 'Neutral')}. Rhythm: {scene.get('rhythm', 'Moderate')}. Attitude: {scene.get('attitude', 'Detached')}."
                        
                    elif "qwen3_instruct" not in scene:
                        # Fallback se non ha seguito la formattazione esattamente
                        scene["qwen3_instruct"] = f"Tone: Neutral. Rhythm: Moderate. Attitude: Detached."

                self.logger.info(f"TextDirector Qwen3 OK | Generate {len(scenes_list)} scene dinamiche strutturate")
                return scenes_list

            except Exception as e:
                error_msg = str(e)
                if "503" in error_msg or "429" in error_msg or "UNAVAILABLE" in error_msg or "limit" in error_msg.lower():
                    if "429" in error_msg or "exhausted" in error_msg.lower():
                        gemini_rate_limiter.report_429()
                        
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        self.logger.warning(f"API temporanea ({e}), ritento in {delay}s...")
                        time.sleep(delay)
                    else:
                        self.logger.error(f"TextDirector Qwen3 fallito dopo {max_retries} tentativi")
                else:
                    self.logger.error(f"Errore TextDirector Qwen3: {e}")
                    break

        # Fallback: singola scena con testo originale + instruct dalla mappa statica
        self.logger.warning("Fallback: usata istruzione statica e blocco unico")
        return [{
            "scene_label": "fallback_scene",
            "clean_text": text_content, 
            "qwen3_instruct": fallback_instruct
        }]


    def annotate_text_for_fish(self, text_content: str, emotion_description: str) -> str:
        """
        [LEGACY — Fish S1-mini]
        Chiama Gemini API per inserire marcatori Fish nel testo.
        NON usato nel flusso principale (backend: qwen3-tts-1.7b).
        Conservato per riutilizzo futuro.
        """
        prompt = self.FISH_ANNOTATION_PROMPT.format(
            emotion_description=emotion_description,
            text_content=text_content
        )

        max_retries = 5
        base_delay = 2
        annotated_text = text_content
        
        for attempt in range(max_retries):
            try:
                # Applica pacing globale (30s)
                gemini_rate_limiter.wait_for_slot()
                
                self.logger.info(f"Chiamata TextDirector per annotazione Fish S1-mini (Prompt v2.0) - Tentativo {attempt + 1}")
                
                # Use gemini-2.5-flash as verified in tests (most stable for availability)
                model_name = "gemini-2.5-flash" 
                if hasattr(self.gemini_client, 'models'):
                    # Client reale Google Gemini
                    response = self.gemini_client.models.generate_content(
                        model=model_name,
                        contents=prompt
                    )
                    response_text = response.text
                else:
                    # Mock client
                    response_text = self.gemini_client.generate_content(prompt, model=model_name)
                
                # Robust JSON parsing
                response_text = response_text.strip()
                
                # Extract JSON block if present
                if "```json" in response_text:
                    import re
                    match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
                    if match:
                        response_text = match.group(1)
                elif "{" in response_text and "}" in response_text:
                    import re
                    match = re.search(r"({.*})", response_text, re.DOTALL)
                    if match:
                        response_text = match.group(1)
                
                try:
                    annotation_data = json.loads(response_text)
                    annotated_text = annotation_data.get("annotated_text", text_content)
                except json.JSONDecodeError:
                    self.logger.warning("Failed to parse JSON for TextDirector, using raw text")
                    annotated_text = response_text
                
                break # Success
                
            except Exception as e:
                error_msg = str(e)
                if "503" in error_msg or "429" in error_msg or "UNAVAILABLE" in error_msg or "limit" in error_msg.lower():
                    if "429" in error_msg or "exhausted" in error_msg.lower():
                        gemini_rate_limiter.report_429()

                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        self.logger.warning(f"Errore API temporaneo (503/429), ritento in {delay} secondi... ({e})")
                        time.sleep(delay)
                    else:
                        self.logger.error(f"TextDirector fallito definitivamente dopo {max_retries} tentativi: {e}")
                        annotated_text = text_content
                else:
                    self.logger.error(f"Errore TextDirector critico: {e}")
                    annotated_text = text_content
                    break
            
        # Post-processing deterministico delle pause SEMPRE applicato
        annotated_text = self._deterministic_formatting_fix(annotated_text)
        
        # Log successo globale
        self.logger.info("TextDirector completato: Marcatori e pause ottimizzati")
        
        return annotated_text


    def _deterministic_formatting_fix(self, text: str) -> str:
        """
        Applica correzioni regex per garantire che titoli e capitoli abbiano pause corrette.
        """
        import re
        
        # 1. Garantisce punto e doppio \n dopo "Capitolo [Parola]"
        # Usiamo \b per evitare di spezzare parole come "Primo" in "Prim. o"
        text = re.sub(r'\b(Capitolo\s+[A-Za-zÀ-ÿ]+)\b(?!\.)', r'\1.', text)
        text = re.sub(r'\b(Capitolo\s+[A-Za-zÀ-ÿ]+\.)\s*(?!\n\n)', r'\1\n\n', text)
        
        # 2. Garantisce punto e doppio \n dopo "Libro [Parola]"
        text = re.sub(r'\b(Libro\s+[A-Za-zÀ-ÿ]+)\b(?!\.)', r'\1.', text)
        text = re.sub(r'\b(Libro\s+[A-Za-zÀ-ÿ]+\.)\s*(?!\n\n)', r'\1\n\n', text)
        
        # 3. Rimuove ":" residui se attaccati ai titoli
        text = text.replace("Capitolo Primo:", "Capitolo Primo.")
        text = text.replace("Libro Primo:", "Libro Primo.")
        
        # 4. Evita triple/quadruple \n
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()


class SceneDirector(BaseStage):
    """Stage C - Segmenta blocchi in scene e genera audio scripts"""
    
    STAGE_NAME = "c"
    QUEUE_NAME = "dias_stage_c_queue"
    OUTPUT_QUEUE = "dias_stage_d_queue"
    
    def __init__(self, config_path: Optional[str] = None, logger: Optional[logging.Logger] = None, 
                 gemini_client: Optional[Any] = None):
        # Carica variabili d'ambiente
        load_dotenv()
        
        super().__init__(
            stage_name="scene_director",
            stage_number=3,
            input_queue="dias:queue:2:semantic_analysis",
            output_queue="dias:queue:3:scene_director",
            config=config_path,
        )
        self.persistence = DiasPersistence()
        self.logger = logger or logging.getLogger(__name__)
        
        # Check if mock services are enabled
        mock_services = os.getenv('MOCK_SERVICES', 'false').lower() == 'true'
        
        if gemini_client:
            self.gemini_client = gemini_client
        elif mock_services:
            self.logger.info("🎭 Using Mock Gemini Client (MOCK_SERVICES=true)")
            self.gemini_client = MockGeminiClient(logger=self.logger)
        else:
            # Retrieve Google Gemini API key from environment
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                self.logger.error("GOOGLE_API_KEY non trovata in .env")
                # Fallback a mock se necessario o errore
                self.gemini_client = MockGeminiClient(logger=self.logger)
            else:
                self.gemini_client = genai.Client(api_key=api_key)
        
        # Inizializza TextDirector con il client (mock o reale)
        self.text_director = TextDirector(self.gemini_client, self.config, self.logger)
        
        self.logger.info("Stage C Scene Director inizializzato")
        
    def _validate_input(self, data: Dict[str, Any]) -> bool:
        """Valida input da Stage B - calcola count dai dati reali"""
        # Accetta sia job_id che analysis_id
        if "job_id" not in data and "analysis_id" not in data:
            self.logger.warning("Campo mancante: job_id o analysis_id")
            return False
            
        required_fields = ["book_id", "block_id", "entities", "relations", "concepts"]
        
        # Controlla campi base
        if not all(field in data for field in required_fields):
            self.logger.warning(f"Campi mancanti: {[f for f in required_fields if f not in data]}")
            return False
            
        # Calcola count dai dati reali
        data["entities_count"] = len(data.get("entities", []))
        data["relations_count"] = len(data.get("relations", []))
        data["concepts_count"] = len(data.get("concepts", []))
        
        self.logger.info(f"Validato: {data['entities_count']} entità, {data['relations_count']} relazioni, {data['concepts_count']} concetti")
        return True
        
    def _load_macro_analysis(self, book_id: str, block_id: str, analysis_id: str) -> Dict[str, Any]:
        """Carica analisi semantica da Stage B"""
        try:
            # Cerca in stage_b/output - Cerca tutti i .json e verifica contenuto
            stage_b_path = self.persistence.base_path / "stage_b" / "output"
            for file in stage_b_path.glob("*.json"):
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get("book_id") == book_id and data.get("block_id") == block_id:
                            # Trovato!
                            return data
                except Exception:
                    continue
                    
            raise FileNotFoundError(f"Analisi non trovata per book_id={book_id}, block_id={block_id}")
                
        except Exception as e:
            self.logger.error(f"Errore caricamento analisi: {e}")
            raise
            
    def _load_text_block(self, book_id: str, block_id: str) -> str:
        """Carica blocco testo da Stage A"""
        try:
            stage_a_path = self.persistence.base_path / "stage_a" / "output"
            for file in stage_a_path.glob("*.json"):
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get("book_id") == book_id and data.get("block_id") == block_id:
                            return data.get("block_text", "")
                except Exception:
                    continue
                    
            raise FileNotFoundError(f"Blocco testo non trovato per book_id={book_id}, block_id={block_id}")
                
        except Exception as e:
            self.logger.error(f"Errore caricamento blocco testo: {e}")
            raise
            
    def _segment_into_scenes(self, text_content: str, macro_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Segmenta testo in scene basandosi su analisi semantica
        
        Returns:
            Lista di scene con metadata
        """
        # Target: ~300 parole per scena
        target_words = 300
        overlap_words = 50
        
        words = text_content.split()
        total_words = len(words)
        
        scenes = []
        start_idx = 0
        scene_num = 0
        
        while start_idx < total_words:
            # Calcola fine scena (cerca punto finale preferibilmente)
            end_idx = min(start_idx + target_words, total_words)
            
            # Estendi fino al prossimo punto se possibile
            if end_idx < total_words:
                scene_text = " ".join(words[start_idx:end_idx])
                last_period = scene_text.rfind('.')
                if last_period > len(scene_text) * 0.8:  # Se c'è un punto nell'ultimo 20%
                    end_idx = start_idx + len(scene_text[:last_period+1].split())
            
            scene_words = words[start_idx:end_idx]
            scene_text = " ".join(scene_words)
            
            # Determina emozione principale per questa scena
            emotion = self._determine_scene_emotion(macro_analysis, scene_num)
            
            scene = {
                "scene_id": f"scene_{scene_num:03d}",
                "scene_number": scene_num,
                "text_content": scene_text,
                "start_char_index": len(" ".join(words[:start_idx])),
                "end_char_index": len(" ".join(words[:end_idx])),
                "word_count": len(scene_words),
                "primary_emotion": emotion
            }
            
            scenes.append(scene)
            
            # Prossima scena con overlap
            start_idx = end_idx - overlap_words
            scene_num += 1
            
            if end_idx >= total_words:
                break
                
        self.logger.info(f"Segmentate {len(scenes)} scene da {total_words} parole totali")
        return scenes
        
    def _determine_scene_emotion(self, macro_analysis: Dict[str, Any], scene_num: int) -> str:
        """Determina emozione dominante per scena basandosi su analisi macro"""
        try:
            concepts = macro_analysis.get("concepts", [])
            if concepts and scene_num < len(concepts):
                concept = concepts[scene_num]
                return concept.get("emotional_tone", "neutro")
            
            # Fallback: usa emozione generale del blocco
            block_analysis = macro_analysis.get("block_analysis", {})
            if block_analysis:
                return block_analysis.get("primary_emotion", "neutro")
            
            entities = macro_analysis.get("entities", [])
            if entities:
                emotions = [e.get("emotional_tone", "neutro") for e in entities]
                return max(set(emotions), key=emotions.count)
                
        except Exception as e:
            self.logger.warning(f"Errore determinazione emozione: {e}")
            
        return "neutro"
        
    def _generate_voice_direction(self, scene: Dict[str, Any], macro_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Genera direzioni vocali per la scena"""
        emotion = scene.get("primary_emotion", "neutro")
        
        # Mappa emozioni a parametri vocali (in Italiano)
        emotion_params = {
            "gioia": {"pace_factor": 1.1, "pitch_shift": 2, "energy": 0.8, "desc": "Tono gioioso e vivace"},
            "tristezza": {"pace_factor": 0.9, "pitch_shift": -2, "energy": 0.3, "desc": "Tono malinconico e dimesso"},
            "tensione": {"pace_factor": 0.95, "pitch_shift": 1, "energy": 0.7, "desc": "Tono teso e incalzante"},
            "relax": {"pace_factor": 1.0, "pitch_shift": 0, "energy": 0.5, "desc": "Tono rilassato e calmo"},
            "neutro": {"pace_factor": 1.0, "pitch_shift": 0, "energy": 0.6, "desc": "Tono narrativo standard"}
        }
        
        params = emotion_params.get(emotion, emotion_params["neutro"])
        
        return {
            "emotion_description": params.get("desc", "Tono narrativo"),
            "pace_factor": params["pace_factor"],
            "pitch_shift": params["pitch_shift"],
            "energy": params["energy"],
            "recommended_silence_before_ms": 500,
            "recommended_silence_after_ms": 1000
        }
        
    def _generate_audio_layers(self, scene: Dict[str, Any], macro_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Genera layer audio (music, ambient, SFX)"""
        emotion = scene.get("primary_emotion", "neutro")
        
        # Mappa emozioni a music prompts (Italiano o Descrittori Tecnici)
        music_prompts = {
            "gioia": "Musica solare, positiva, chitarra acustica, pianoforte leggero",
            "tristezza": "Musica malinconica, archi dolci, tempo lento, pianoforte solo",
            "tensione": "Suspense, archi bassi, ritmi sincopati, tensione cinematografica",
            "relax": "Calma, suoni ambientali, pad eterei, atmosfera rilassata",
            "neutro": "Texture ambientale discreta, sottofondo narrativo neutro"
        }
        
        music_prompt = music_prompts.get(emotion, music_prompts["neutro"])
        
        return {
            "music": {
                "prompt_for_musicgen": music_prompt,
                "intensity_curve": [0.3, 0.5, 0.4],  # start, middle, end
                "ducking_db": -15
            },
            "ambient": {
                "soundscape_tag": f"{emotion}_room_tone",
                "volume_db": -25,
                "fade_in_ms": 2000,
                "fade_out_ms": 3000
            },
            "spot_effects": []  # Da popolare con SFX specifici se necessario
        }
        
    def _create_scene_script_dynamic(self, dynamic_scene: Dict[str, Any], scene_num: int, 
                                   macro_analysis: Dict[str, Any], book_id: str, 
                                   chunk_label: str, clean_title: str,
                                   chapter_id: str, job_id: str) -> Dict[str, Any]:
        """Crea scene script basato su una scena generata DINAMICAMENTE da Gemini."""
        
        # Determiniamo l'emozione base per i parametri tecnici (music, ambient)
        # Se Gemini non l'ha fornita esplicitamente, usiamo quella del blocco
        block_analysis = macro_analysis.get("block_analysis", {})
        primary_emotion = block_analysis.get("primary_emotion", "neutro")
        
        # Mock scene object per i generatori esistenti
        mock_scene = {
            "primary_emotion": primary_emotion,
            "word_count": len(dynamic_scene["clean_text"].split()),
            "scene_id": f"scene-{scene_num:03d}"
        }

        # Genera voice direction (tecnica)
        voice_direction = self._generate_voice_direction(mock_scene, macro_analysis)
        
        # Genera audio layers (musica e ambiente basati sull'emozione)
        audio_layers = self._generate_audio_layers(mock_scene, macro_analysis)

        # Timing estimate
        word_count = mock_scene["word_count"]
        wpm = 150
        estimated_seconds = (word_count / wpm) * 60

        return {
            "job_id": job_id,
            "book_id": book_id,
            "clean_title": clean_title,
            "chunk_label": chunk_label,
            "chapter_id": chapter_id,
            "scene_id": mock_scene["scene_id"],
            "scene_number": scene_num,
            "scene_label": dynamic_scene.get("scene_label", "unknown"),
            "text_content": dynamic_scene["clean_text"],
            "qwen3_instruct": dynamic_scene["qwen3_instruct"],
            "fish_annotated_text": None,
            "tts_backend": "qwen3-tts-1.7b",
            "primary_emotion": primary_emotion,
            "word_count": word_count,
            "voice_direction": voice_direction,
            "audio_layers": audio_layers,
            "timing_estimate": {
                "estimated_duration_seconds": estimated_seconds,
                "words_per_minute": wpm
            },
            "processing_timestamp": datetime.now().isoformat()
        }

    def process_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Processa un item da Stage B con la nuova logica Emotional Beats"""
        try:
            self.logger.info(f"Processing Stage C (Dynamic): {item.get('book_id')} - {item.get('block_id')}")
            
            # Valida input
            if not self._validate_input(item):
                self.logger.error("Input validation failed")
                return None
                
            book_id = item["book_id"]
            block_id = item["block_id"]
            job_id = item.get("job_id") or item.get("analysis_id") or f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Carica dati necessari
            macro_analysis = self._load_macro_analysis(book_id, block_id, job_id)
            text_content = self._load_text_block(book_id, block_id)
            
            if not text_content:
                self.logger.error("Testo blocco vuoto")
                return None

            # --- SKIPPING LOGIC ---
            clean_title = item.get("clean_title") or "".join([c if c.isalnum() else "-" for c in book_id]).strip("-")
            chunk_label = item.get("chunk_label") or f"chunk-{item.get('block_index', 0):03d}"
            
            # Check for Master Scene File
            existing_scenes_master = self.persistence.load_stage_output("c", clean_title, f"{chunk_label}-scenes")
            if existing_scenes_master:
                self.logger.info(f"⏭️ Skipping Gemini: Master scene list già presente per {clean_title}-{chunk_label}")
                scene_scripts = existing_scenes_master.get("scenes", [])
                
                # Invia ogni scena caricata alla coda successiva SOLO se auto_push è attivo
                auto_push = os.getenv("AUTO_PUSH_TO_STAGE_D", "false").lower() == "true"
                for scene_script in scene_scripts:
                    if self.output_queue and auto_push:
                        self.logger.info(f"Producing (restored) scene {scene_script['scene_id']} to {self.output_queue} (AUTO_PUSH=true)")
                        self.redis.push_to_queue(self.output_queue, scene_script)
                    else:
                        self.logger.info(f"⏸️ Manual Gate (Skip Logic): Scene {scene_script['scene_id']} not pushed (AUTO_PUSH=false)")
                
                return {
                    "stage": self.STAGE_NAME,
                    "book_id": book_id,
                    "block_id": block_id,
                    "job_id": job_id,
                    "scenes_count": len(scene_scripts),
                    "skipped": True
                }
            # ----------------------

            # 1. Chiamata UNICA a Gemini per segmentazione e normalizzazione
            self.logger.info("🎬 Generazione scene dinamiche (Emotional Beats)...")
            block_analysis = macro_analysis.get("block_analysis", {})
            primary_emotion = block_analysis.get("primary_emotion", "neutro")
            emotion_desc = block_analysis.get("primary_emotion", "Narrativa")
            
            dynamic_scenes = self.text_director.annotate_text_for_qwen3(
                text_content, 
                emotion=primary_emotion,
                emotion_description=emotion_desc
            )
            
            # 2. Trasformazione in Scene Scripts validi per Stage D
            scene_scripts = []
            clean_title = item.get("clean_title") or "".join([c if c.isalnum() else "-" for c in book_id]).strip("-")
            chunk_label = item.get("chunk_label") or f"chunk-{item.get('block_index', 0):03d}"
            
            for i, d_scene in enumerate(dynamic_scenes):
                script = self._create_scene_script_dynamic(
                    d_scene, i, macro_analysis, book_id, chunk_label, clean_title, "chapter_001", job_id
                )
                scene_scripts.append(script)
                
            # Salva Master JSON con tutte le scene
            master_output = {
                "book_id": book_id,
                "block_id": block_id,
                "clean_title": clean_title,
                "chunk_label": chunk_label,
                "scenes_count": len(scene_scripts),
                "scenes": scene_scripts,
                "processing_timestamp": datetime.now().isoformat()
            }
            self.persistence.save_stage_output(
                self.STAGE_NAME, 
                master_output, 
                clean_title, 
                f"{chunk_label}-scenes"
            )

            # 3. Handle Output Pushing (Gatekeeper logic)
            auto_push = os.getenv("AUTO_PUSH_TO_STAGE_D", "false").lower() == "true"
            
            for scene_script in scene_scripts:
                # Salva su disco con naming coerente: Titolo-chunk-000-scene-000
                self.persistence.save_stage_output(
                    self.STAGE_NAME, 
                    scene_script, 
                    clean_title, 
                    chunk_label, 
                    scene_script['scene_id']
                )
                
                # Invia alla coda successiva SOLO se auto_push è attivo o se esplicitamente richiesto
                if self.output_queue:
                    if auto_push:
                        self.logger.info(f"Producing scene {scene_script['scene_id']} to {self.output_queue} (AUTO_PUSH=true)")
                        self.redis.push_to_queue(self.output_queue, scene_script)
                    else:
                        self.logger.info(f"⏸️ Manual Gate: Scene {scene_script['scene_id']} saved to disk but NOT pushed to queue (AUTO_PUSH=false)")
                
            self.logger.info(f"✅ Stage C completato: {len(scene_scripts)} scene dinamiche generate")
            return {
                "stage": self.STAGE_NAME,
                "book_id": book_id,
                "block_id": block_id,
                "job_id": job_id,
                "scenes_count": len(scene_scripts),
                "scenes": scene_scripts,
                "processing_timestamp": datetime.now().isoformat(),
                "status": "ready_for_stage_d"
            }
            
        except Exception as e:
            self.logger.error(f"Errore processing Stage C: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
            
        except Exception as e:
            self.logger.error(f"Errore processing Stage C: {e}")
            return None

    def process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa un messaggio da Stage B con analisi semantica
        
        Args:
            message: Dict con book_id, block_id, analysis_id, entities_count, etc.
            
        Returns:
            Dict con risultato del processing
        """
        self.logger.info(f"=== Stage C Processing Started ===")
        self.logger.info(f"Book ID: {message.get('book_id')}")
        self.logger.info(f"Block ID: {message.get('block_id')}")
        self.logger.info(f"Analysis ID: {message.get('analysis_id')}")
        
        try:
            result = self.process_item(message)
            if result:
                self.logger.info(f"Stage C completato: {result['scenes_count']} scene generate")
                return result
            else:
                self.logger.error("Stage C fallito")
                return {"error": "Stage C processing failed"}
                
        except Exception as e:
            self.logger.error(f"Errore in Stage C process: {e}")
            return {"error": str(e)}


def main():
    """Main entry point per Stage C"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DIAS Stage C - Scene Director")
    parser.add_argument("--config", help="Path to config file")
    parser.add_argument("--mock", action="store_true", help="Use mock services")
    parser.add_argument("--single", help="Process single file instead of queue")
    
    args = parser.parse_args()
    
    # Setup environment
    if args.mock:
        os.environ["MOCK_SERVICES"] = "true"
        
    # Setup logging
    logger = logging.getLogger(__name__)
    logger.info("🎬 Starting DIAS Stage C - Scene Director")
    
    try:
        director = SceneDirector(config_path=args.config, logger=logger)
        
        if args.single:
            # Modalità single file per testing
            logger.info(f"Processing single file: {args.single}")
            with open(args.single, 'r', encoding='utf-8') as f:
                item = json.load(f)
            result = director.process_item(item)
            
            if result:
                logger.info("✅ Single file processing completed successfully")
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                logger.error("❌ Single file processing failed")
                return 1
        else:
            # Modalità queue (default)
            director.run()
            
    except KeyboardInterrupt:
        logger.info("🛑 Interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())