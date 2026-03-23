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
from dotenv import load_dotenv
from typing import Dict, List, Optional, Any
from datetime import datetime


# sys.path.insert is handled if needed

# Aggiungi il path src al Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.base_stage import BaseStage
from src.common.config import get_config
from src.common.redis_client import DiasRedis
from src.common.persistence import DiasPersistence
from src.stages.mock_gemini_client import MockGeminiClient
from src.common.gateway_client import GatewayClient
from src.common.registry import ActiveTaskTracker
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

    def annotate_text_for_qwen3(
        self,
        text_content: str,
        emotion: str,
        emotion_description: str,
        book_id: str,
        block_id: str,
        job_id: Optional[str] = None,
        macro_analysis: Optional[Dict] = None,
    ) -> List[dict]:
        """
        Chiama Gemini per produrre output compatibile con Qwen3-TTS:
        - Suddivisione in SCENE basata su cambi di tono (Emotional Beats).
        - Testo PULITO (senza tag fish, senza return capo).
        - Conversione NUMERI in PAROLE per esteso (es. 2042 -> duemilaquarantadue).
        - Campo qwen3_instruct: istruzione stile in inglese, autosufficiente (V1.4+).

        Args:
            macro_analysis: Output completo di Stage B (utilizzato da V1.4+ per arricchire il prompt).

        Returns:
            Lista di dict con chiavi 'clean_text', 'qwen3_instruct', 'scene_id_suffix'
        """
        # Instruct di fallback dalla mappa statica
        fallback_instruct = EMOTION_TO_INSTRUCT_QWEN3.get(
            emotion.lower(),
            EMOTION_TO_INSTRUCT_QWEN3["neutro"]
        )

        import yaml
        
        # Caricamento del nuovo prompt esternalizzato
        prompt_path = getattr(self.config, "stage_c_prompt_path", "config/prompts/stage_c/v1.0_base.yaml")
        prompt_full_path = Path(__file__).parent.parent.parent / prompt_path
        
        try:
            with open(prompt_full_path, 'r', encoding='utf-8') as f:
                prompt_data = yaml.safe_load(f)
                template = prompt_data.get('prompt_template', '')
                prompt_version = prompt_data.get('version', '1.0')
        except Exception as e:
            self.logger.error(f"Impossibile caricare il prompt {prompt_full_path}: {e}")
            raise RuntimeError(f"PROMPT_LOAD_ERROR: {e}")

        # ── Costruzione dati di contesto Stage B (usati da prompt V1.4+) ──────
        block_analysis = (macro_analysis or {}).get("block_analysis", {})
        secondary_emotion = block_analysis.get("secondary_emotion", "")

        # narrator_base_tone: derivato dalla primary_emotion e secondary_emotion
        narrator_base_tone_map = {
            "tensione":       "Low, unhurried chest voice. The narrator speaks with exhausted clarity — detached but not cold, like someone describing a world they know too well.",
            "tristezza":      "Soft, low chest voice. Measured pace with slight weight on stressed syllables. No warmth — intimate but restrained.",
            "gioia":          "Lighter chest voice, moderate pace. Slightly open mouth quality. Conversational but controlled.",
            "paura":          "Hushed, tight chest voice. Short breath. Words clipped at the edges. Very slow.",
            "rabbia":         "Clipped, low voice. Hard consonants. Fast but deliberate. Jaw barely moving.",
            "curiosità":      "Slightly rising intonation at end of phrases. Mid-chest register. Moderate pace.",
            "determinazione": "Chest voice, firm and forward. Consistent pace without hesitation. No emotional colour.",
        }
        narrator_base_tone = narrator_base_tone_map.get(
            emotion.lower(),
            "Low, unhurried chest voice. Measured and detached."
        )

        # narrative_arc: formattato come lista leggibile da Gemini
        narrative_markers = (macro_analysis or {}).get("narrative_markers", [])
        if narrative_markers:
            arc_lines = []
            for nm in narrative_markers:
                pos_pct = int(nm.get("relative_position", 0) * 100)
                event = nm.get("event", "")
                shift = nm.get("mood_shift", "")
                arc_lines.append(f"  - At ~{pos_pct}%: {event} → Shift: {shift}")
            narrative_arc = "\n".join(arc_lines)
        else:
            narrative_arc = f"  - Whole block: {emotion_description}"

        # entities_speaking_styles: formattato per Gemini
        entities = (macro_analysis or {}).get("entities", [])
        if entities:
            ent_lines = []
            for ent in entities:
                name = ent.get("text", "?")
                style = ent.get("speaking_style") or "(narrator default)"
                role = ent.get("metadata", {}).get("role", "")
                ent_lines.append(f"  - {name} ({role}): speaking_style = \"{style}\"")
            entities_speaking_styles = "\n".join(ent_lines)
        else:
            entities_speaking_styles = "  - No named entities in this block."

        # ── Sostituzione placeholder nel template ────────────────────────────
        prompt = (
            template
            .replace("{emotion_description}", emotion_description)
            .replace("{primary_emotion}", emotion)
            .replace("{secondary_emotion}", secondary_emotion)
            .replace("{narrator_base_tone}", narrator_base_tone)
            .replace("{narrative_arc}", narrative_arc)
            .replace("{entities_speaking_styles}", entities_speaking_styles)
            .replace("{text_content}", text_content)
        )

        self.logger.info(f"Stage C prompt v{prompt_version} loaded. Context: {len(narrative_markers)} markers, {len(entities)} entities.")


        # Applica pacing globale (30s) e verifica quota        # Rate limiting is managed centrally by ARIA.
        
        self.logger.info(f"TextDirector Qwen3 Dynamic: emozione_base={emotion}")
        model_name = self.config.google.model_flash_lite
        
        try:
            # Gestisci client Gateway, reale o mock
            if isinstance(self.gemini_client, GatewayClient):
                # Client ARIA Gateway
                generate_config = {}
                if hasattr(self.config.google, 'response_mime_type'):
                    generate_config["response_mime_type"] = self.config.google.response_mime_type
                
                # Format contents for Gateway (Gemini 2.x standard)
                contents = [{"role": "user", "parts": [{"text": prompt}]}]
                
                # Deterministic Job Meta
                job_meta = {
                    "book_id": book_id,
                    "block_id": block_id,
                    "stage": "stage_c"
                }
                
                response = self.gemini_client.generate_content(
                    contents=contents,
                    model_id=model_name,
                    config=generate_config,
                    job_id=job_id  # Use fixed job_id
                )
                
                if response["status"] == "error":
                    self.logger.error(f"Gateway Error in Stage C: {response.get('error')}")
                    raise RuntimeError(f"GATEWAY_ERROR: {response.get('error')}")
                
                response_text = response["output"].get("text", "")
            
            else:
                # Mock client (MockGeminiClient)
                response_text = self.gemini_client.generate_content(prompt, model=model_name)

            response_text = response_text.strip()
            
            # Robust JSON parsing (Fallbacks per risposte parzialmente sporche)
            import re
            if "```json" in response_text:
                match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)
            elif "[" in response_text and "]" in response_text:
                match = re.search(r"(\[.*\])", response_text, re.DOTALL)
                if match:
                    response_text = match.group(1)

            try:
                scenes_list = json.loads(response_text)
            except json.JSONDecodeError as jde:
                dump_path = "/home/Projects/NH-Mini/sviluppi/dias/logs/json_error_dump.txt"
                with open(dump_path, "w", encoding="utf-8") as f:
                    f.write(response_text)
                self.logger.error(f"JSONDecodeError: Saved raw response to {dump_path}")
                raise jde

            if not isinstance(scenes_list, list):
                scenes_list = [scenes_list]
            
            # Validate and sanitize micro-scenes
            for scene in scenes_list:
                # Caso legacy: se Gemini ha restituito il vecchio formato (tone/rhythm/attitude)
                # convertilo in stringa di prosa leggibile.
                if all(k in scene for k in ["tone", "rhythm", "attitude"]):
                    tone = scene.get('tone', 'Neutral')
                    rhythm = scene.get('rhythm', 'Moderate')
                    attitude = scene.get('attitude', 'Detached')
                    scene["qwen3_instruct"] = (
                        f"Read with a {tone.lower()} tone. "
                        f"Maintain a {rhythm.lower()} pacing throughout. "
                        f"The delivery should be {attitude.lower()}."
                    )
                elif "qwen3_instruct" not in scene or not scene.get("qwen3_instruct"):
                    # Fallback se non ha seguito il formato
                    scene["qwen3_instruct"] = fallback_instruct
                    
                    # Nuovi campi micro-scene (con default safe)
                    if "speaker" not in scene:
                        scene["speaker"] = None
                    if "pause_after_ms" not in scene:
                        scene["pause_after_ms"] = 200  # default pausa breve
                    
                    # Retrocompatibilità: genera has_dialogue dal campo speaker
                    scene["has_dialogue"] = scene.get("speaker") is not None
                    # dialogue_notes ora è integrato nell'instruct stesso
                    if "dialogue_notes" not in scene:
                        scene["dialogue_notes"] = None


                self.logger.info(f"TextDirector Qwen3 OK | Generate {len(scenes_list)} scene dinamiche strutturate")
                return scenes_list

        except Exception as e:
            self.logger.error(f"Errore TextDirector Qwen3: {e}")
            # Rilancia per permettere a BaseStage di gestire il re-enqueue
            raise


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
                self.logger.info(f"Chiamata TextDirector per annotazione Fish S1-mini (LEGACY) - Tentativo {attempt + 1}")
                
                # Use gemini-flash-lite-latest as configured
                model_name = self.config.google.model_flash_lite
                
                if isinstance(self.gemini_client, GatewayClient):
                    # Client ARIA Gateway
                    contents = [{"role": "user", "parts": [{"text": prompt}]}]
                    response = self.gemini_client.generate_content(
                        contents=contents,
                        model_id=model_name
                    )
                    if response["status"] == "error":
                        raise RuntimeError(f"GATEWAY_ERROR: {response.get('error')}")
                    response_text = response["output"].get("text", "")
                
                elif hasattr(self.gemini_client, 'models'):
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
    
    def __init__(self, config_path: Optional[str] = None, logger: Optional[logging.Logger] = None, 
                 gemini_client: Optional[Any] = None):
        # Carica variabili d'ambiente
        load_dotenv()
        
        super().__init__(
            stage_name="scene_director",
            stage_number=3,
            config_path=config_path,
            logger=logger
        )
        # Use standardized queues from config
        self.input_queue = self.cfg.queues.regia
        self.output_queue = self.cfg.queues.voice
            input_queue=cfg.queues.semantic,
            output_queue=cfg.queues.voice,
            config=cfg,
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
            self.logger.info("📡 Using ARIA Gateway v2.0 (MOCK_SERVICES=false)")
            self.gemini_client = GatewayClient(redis_client=self.redis, client_id="dias")
        
        self.tracker = ActiveTaskTracker(self.redis, self.logger)
        
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
        
    def _load_macro_analysis(self, book_id: str, block_id: str, job_id: str = None) -> Dict[str, Any]:
        """Carica analisi semantica da Stage B (Micro o Macro)"""
        try:
            # Coherence check for clean title
            clean_title = "".join([c if c.isalnum() else "-" for c in book_id]).strip("-")
            
            # 1. Prova caricamento diretto basato sul nome (Micro-Chunk)
            # block_id nello Stage C è ora la chunk_label (es: chunk-001-micro-001)
            micro_semantic_label = f"{block_id}-semantic"
            data = self.persistence.load_stage_output("b", clean_title, micro_semantic_label)
            if data:
                return data
            
            # 2. Fallback: logica di scansione originale
            stage_b_path = self.persistence.base_path / "stage_b" / "output" / clean_title
            if stage_b_path.exists():
                for file in stage_b_path.glob("*.json"):
                    try:
                        with open(file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if data.get("block_id") == block_id:
                                return data
                    except Exception:
                        continue
                        
            raise FileNotFoundError(f"Analisi non trovata per block_id={block_id} in Stage B")
                
        except Exception as e:
            self.logger.error(f"Errore caricamento analisi: {e}")
            raise
            
    def _load_text_block(self, book_id: str, block_id: str) -> str:
        """Carica blocco testo da Stage A (Micro o Macro)"""
        try:
            clean_title = "".join([c if c.isalnum() else "-" for c in book_id]).strip("-")
            
            # 1. Prova caricamento diretto (Micro-Chunk)
            data = self.persistence.load_stage_output("a", clean_title, block_id)
            if data:
                return data.get("block_text", "")
            
            # 2. Fallback: logica di scansione originale
            stage_a_path = self.persistence.base_path / "stage_a" / "output" / clean_title
            if stage_a_path.exists():
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
        # --- NEW: Hierarchical Scene ID for Idempotency ---
        # Format: chunk-001-micro-001-scene-001
        scene_id = f"{chunk_label}-scene-{scene_num:03d}"

        mock_scene = {
            "primary_emotion": primary_emotion,
            "word_count": len(dynamic_scene["clean_text"].split()),
            "scene_id": scene_id
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
            "speaker": dynamic_scene.get("speaker", None),
            "pause_after_ms": dynamic_scene.get("pause_after_ms", 200),
            "has_dialogue": dynamic_scene.get("has_dialogue", False),
            "dialogue_notes": dynamic_scene.get("dialogue_notes", None),
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
                
            # Coherence: Use normalized IDs from the message
            raw_book_id = item.get("book_id", "unknown")
            clean_title = item.get("clean_title") or self.persistence.no            block_id = item.get("chunk_label") or item.get("block_id") # Micro-chunk label as primary ID
            
            # --- JOB ID PERSISTENCE ---
            if not item.get("job_id"):
                # Se non c'è, lo generiamo e lo salviamo nell'item originale
                import hashlib
                stable_id_str = f"{book_id}|{block_id}|stage_c_v2"
                job_hash = hashlib.sha256(stable_id_str.encode()).hexdigest()[:12]
                item["job_id"] = f"job-{job_hash}"
                self.logger.info(f"Persisting NEW stable job_id: {item['job_id']}")
                
            job_id = item["job_id"]
            # --------------------------
            
            # Carica dati (ora usano la logica ottimizzata per micro-chunk)
            macro_analysis = self._load_macro_analysis(book_id, block_id, job_id)
            text_content = self._load_text_block(book_id, block_id)
            
            if not text_content:
                self.logger.error(f"Testo blocco vuoto per {block_id}")
                return None

            # --- SKIPPING LOGIC ---
            chunk_label = block_id # e.g. chunk-001-micro-001
            self.logger.info(f"🎬 Stage C: processing {clean_title}-{chunk_label}")
            
            # Registry task ID for Stage C
            registry_task_id = f"stage_c_{chunk_label}"
")
            
            # Registry task ID for Stage C
            registry_task_id = f"stage_c_{chunk_label}"
            
            # Check for Master Scene File
            existing_scenes_master = self.persistence.load_stage_output("c", clean_title, f"{chunk_label}-scenes")
            if existing_scenes_master:
                self.logger.info(f"⏭️ Skipping Gemini: Master scene list già presente per {clean_title}-{chunk_label} (Registry: {registry_task_id})")
                scene_scripts = existing_scenes_master.get("scenes", [])
                
                # Invia ogni scena caricata alla coda successiva SOLO se auto_push è attivo
                auto_push = os.getenv("AUTO_PUSH_TO_STAGE_D", "false").lower() == "true"
                for scene_script in scene_scripts:
                    if self.output_queue and auto_push:
                        self.logger.info(f"Producing (restored) scene {scene_script['scene_id']} to {self.output_queue} (AUTO_PUSH=true)")
                        self.redis.push_to_queue(self.output_queue, scene_script)
                    else:
                        self.logger.info(f"⏸️ Manual Gate (Skip Logic): Scene {scene_script['scene_id']} not pushed (AUTO_PUSH=false)")
                
                # Mark as Completed in Registry if it was skipped due to disk presence
                self.tracker.mark_as_completed(book_id, registry_task_id, "disk_cache")

                return {
                    "stage": self.STAGE_NAME,
                    "book_id": book_id,
                    "block_id": block_id,
                    "job_id": job_id,
                    "scenes_count": len(scene_scripts),
                    "skipped": True
                }
            # ----------------------

            # Mark as In-Flight in Registry (aria:c:dias:job-...)
            self.tracker.mark_as_inflight(book_id, registry_task_id, f"aria:c:dias:job-{book_id}-{chunk_label}")

            # 1. Chiamata UNICA a Gemini per segmentazione e normalizzazione
            self.logger.info("🎬 Generazione scene dinamiche (Emotional Beats)...")
            block_analysis = macro_analysis.get("block_analysis", {})
            primary_emotion = block_analysis.get("primary_emotion", "neutro")
            emotion_desc = block_analysis.get("primary_emotion", "Narrativa")
            
            dynamic_scenes = self.text_director.annotate_text_for_qwen3(
                text_content, 
                emotion=primary_emotion,
                emotion_description=emotion_desc,
                book_id=book_id,
                block_id=block_id,
                job_id=job_id,
                macro_analysis=macro_analysis,  # V1.4: full Stage B context
            )
            
            # 2. Trasformazione in Scene Scripts validi per Stage D
            scene_scripts = []
            # clean_title and chunk_label are already defined above and aligned
            
            for i, d_scene in enumerate(dynamic_scenes):
                # scene_num starts from 1 for each micro-chunk
                script = self._create_scene_script_dynamic(
                    d_scene, i + 1, macro_analysis, book_id, chunk_label, clean_title, "chapter_001", job_id
                )
                scene_scripts.append(script)
                
            # Salva Master JSON con tutte le scene
            master_output = {
                "book_id": book_id,
                "block_id": block_id,
                "chunk_label": chunk_label,
                "scenes": scene_scripts,
                "job_id": job_id,
                "processing_timestamp": datetime.now().isoformat()
            }
            output_file = self.persistence.save_stage_output(
                self.STAGE_NAME, 
                master_output, 
                clean_title, 
                f"{chunk_label}-scenes"
            )
            
            # Mark as Completed in Registry
            self.tracker.mark_as_completed(book_id, registry_task_id, output_file)

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
            self.logger.error(f"Errore processing Stage C (process_item): {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            raise # Rilancia per la Pausa Globale in BaseStage
            
        except Exception as e:
            self.logger.error(f"Errore processing Stage C (process_item fallback): {e}")
            raise # Rilancia

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
        except Exception as e:
            self.logger.error(f"Error in process wrapper: {e}")
            raise # Rilancia per BaseStage.run


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
    from src.common.logging_setup import get_logger
    logger = get_logger("scene_director")
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