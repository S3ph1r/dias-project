#!/usr/bin/env python3
"""
DIAS - Universal Source Normalizer
----------------------------------
Utilizza i metadati strutturali di Stage 0.1 (fingerprint.json) per normalizzare 
la punteggiatura di un libro secondo lo standard teatrale DIAS:
- Parlato: " [testo] "
- Pensieri: ' [testo] '

Algoritmo Safe-Swap: utilizza placeholder temporanei per evitare collisioni di simboli.
"""

import os
import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional

class SourceNormalizer:
    def __init__(self, project_id: str, base_path: str = "data/projects"):
        self.project_id = project_id
        self.project_root = Path(base_path) / project_id
        self.output_dir = self.project_root / "stages" / "stage_0" / "output"
        self.fingerprint_path = self.output_dir / "fingerprint.json"
        
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
        self.logger = logging.getLogger("Normalizer")

    def normalize(self) -> bool:
        """Esegue la normalizzazione completa del progetto."""
        if not self.fingerprint_path.exists():
            self.logger.error(f"Fingerprint non trovato: {self.fingerprint_path}")
            return False

        # 1. Carica metadati
        with open(self.fingerprint_path, 'r', encoding='utf-8') as f:
            fingerprint = json.load(f)
        
        punc = fingerprint.get("punctuation_style", {})
        if not punc:
            self.logger.error("Dati punteggiatura mancanti nel fingerprint.")
            return False

        # 2. Trova il file sorgente originale
        source_dir = self.project_root / "source"
        txt_files = list(source_dir.glob("*.txt"))
        if not txt_files:
            self.logger.error(f"Nessun file .txt trovato in {source_dir}")
            return False
        
        source_file = txt_files[0]
        self.logger.info(f"Normalizzazione di: {source_file.name}")
        
        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 3. Safe-Swap Algorithm
        normalized_content = self._apply_safe_swap(content, punc)

        # 4. Salvataggio (Mantiene nome originale)
        output_file = self.output_dir / source_file.name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(normalized_content)
            
        self.logger.info(f"✅ Normalizzazione completata: {output_file}")
        return True

    def _apply_safe_swap(self, text: str, punc: Dict[str, Any]) -> str:
        """Applica la sostituzione sicura usando placeholder temporanei."""
        
        diag = punc.get("dialogue", {})
        thot = punc.get("thought", {})

        # Placeholder temporanei
        T_DIAG = "[[DIAS_SPEECH_TOKEN]]"
        T_THOT = "[[DIAS_THOUGHT_TOKEN]]"

        # --- STEP 1: Marcazione Dialoghi ---
        text = self._replace_markers(text, diag, T_DIAG)

        # --- STEP 2: Marcazione Pensieri ---
        text = self._replace_markers(text, thot, T_THOT)

        # --- STEP 3: Finalizzazione Standard DIAS ---
        # Il parlato diventa " (Standard)
        text = text.replace(T_DIAG, '"')
        # I pensieri diventano ' (Standard)
        text = text.replace(T_THOT, "'")

        return text

    def _replace_markers(self, text: str, style: Dict[str, Any], token: str) -> str:
        """Applica la logica universale (Toggle o Enclosed) definita nel fingerprint."""
        open_m = style.get("open")
        close_m = style.get("close")
        logic_type = style.get("logic_type", "")
        
        if not open_m:
            return text

        re_open = re.escape(open_m)
        re_close = re.escape(close_m) if close_m else re_open

        # LOGICA A: TOGGLE PARAGRAPH (Modello Scalzi - Trattini)
        # Il dialogo viene attivato solo se il paragrafo inizia con il marcatore.
        if logic_type == "toggle_paragraph":
            lines = text.splitlines()
            processed_lines = []
            for line in lines:
                stripped = line.lstrip()
                # Se la riga inizia con il marcatore (dialogo rilevato)
                if stripped.startswith(open_m):
                    # Sostituiamo TUTTI i marcatori in questa riga specifica
                    # perché sono delimitatori di parlato/narrato
                    new_line = line.replace(open_m, token)
                    processed_lines.append(new_line)
                else:
                    # Se la riga NON inizia con il marcatore, non tocchiamo nulla
                    # Protegge gli incisi narrativi — come questo — in mezzo al testo.
                    processed_lines.append(line)
            return "\n".join(processed_lines)

        # LOGICA B: ENCLOSED PAIR (Modello Cronache/Guillemets)
        # Il dialogo è racchiuso strettamente tra due simboli (es: "..." o «...»)
        elif logic_type == "enclosed_pair":
            # Usiamo regex non-greedy per trovare le coppie
            # Sostituiamo entrambi i delimitatori con il token DIAS
            pattern = re.compile(rf"{re_open}(.*?){re_close}", re.DOTALL)
            return pattern.sub(f"{token}\\1{token}", text)

        # LOGICA C: FALLBACK / GLOBAL (Markers preceded by punctuation - Scalzi style)
        else:
            # Pattern: riga che inizia col marcatore OPPURE marcatore preceduto da punto/spazio (es: . — o  — )
            # Questo cattura i dialoghi a metà riga comuni in Scalzi.
            pattern = re.compile(rf"(\.|\?|!|\n)\s*{re_open}", re.MULTILINE)
            
            # Conta le sostituzioni per il log
            replaced_text, count = pattern.subn(rf"\1 {token} ", text)
            
            # Gestione anche dell'inizio assoluto del file (se non catturato da riga vuota)
            if text.startswith(open_m):
                replaced_text = token + " " + replaced_text[1:]
                count += 1
            
            self.logger.info(f"🔄 Sostituiti {count} marcatori di dialogo globatli con lo standard DIAS.")
            return replaced_text

        return text

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 normalize_source.py <project_id>")
        sys.exit(1)
    
    normalizer = SourceNormalizer(sys.argv[1])
    normalizer.normalize()
