#!/usr/bin/env python3
"""
DIAS Stage 0 - Book Intelligence
Analyzes the full text of a book to extract metadata, characters, and sound design.

Supports Sequential Contextual Injection for books exceeding the per-minute token quota:
- Books <= block_char_limit: single-block path (existing behavior, no regression)
- Books >  block_char_limit: multi-block path with cumulative preamble and merge
"""

import sys
import os
import json
import logging
import yaml
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.base_stage import BaseStage
from src.common.config import get_config
from src.common.gateway_client import GatewayClient
from src.common.persistence import DiasPersistence


class Stage0Intelligence(BaseStage):
    """
    Stage 0: Book Intelligence.

    For books within the token budget: single call per sub-protocol (0.1, 0.2).
    For large books: Sequential Contextual Injection — N blocks with cumulative
    preamble, merged into one coherent fingerprint.json / preproduction.json.
    """

    def __init__(self, redis_client=None, config=None):
        cfg = config or get_config()
        super().__init__(
            stage_name="stage_0_intel",
            stage_number=0,
            input_queue="dias:q:0:intel",
            output_queue=None,
            config=cfg,
            redis_client=redis_client,
        )
        self.gateway = GatewayClient(redis_client=self.redis, client_id="dias")
        self.model_name = self.config.google.model_flash_lite

        s0 = getattr(self.config, "stage_0", None)
        self.block_char_limit   = getattr(s0, "block_char_limit",   700_000)
        self.block_overlap_chars = getattr(s0, "block_overlap_chars", 2_000)
        self.inter_block_delay_s = getattr(s0, "inter_block_delay_s", 65)

        self.logger.info(
            f"Stage 0 initialized | model={self.model_name} "
            f"| block_limit={self.block_char_limit:,} chars "
            f"| inter_block_delay={self.inter_block_delay_s}s"
        )

    # ─────────────────────────────────────────────────────────────────────
    # UTILITIES
    # ─────────────────────────────────────────────────────────────────────

    def _load_prompt(self, prompt_path_rel: str) -> Dict[str, Any]:
        path = Path(__file__).parent.parent.parent / prompt_path_rel
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _estimate_tokens(self, text: str) -> int:
        """Conservative estimate: Italian text ~3.8 chars/token."""
        return int(len(text) / 3.8)

    def _needs_chunking(self, text: str) -> bool:
        return len(text) > self.block_char_limit

    def _extract_retry_delay(self, error_msg: str) -> int:
        """Parse retryDelay seconds from a 429 error string. Returns 65 if not found."""
        import re
        m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)", error_msg)
        return int(m.group(1)) + 5 if m else 65

    def _call_gateway_with_retry(
        self,
        contents: list,
        job_id_meta: dict,
        step_name: str,
        timeout: int = 1200,
        max_retries: int = 3,
    ) -> Dict:
        """Submit to ARIA gateway with automatic 429-backoff retry."""
        for attempt in range(1, max_retries + 1):
            result = self.gateway.generate_content(
                contents=contents,
                model_id=self.model_name,
                job_id_meta=job_id_meta,
                timeout=timeout,
            )
            if result.get("status") == "success":
                return result
            error = result.get("error", "")
            if "429" in str(error) or "QUOTA_EXHAUSTED" in str(result.get("error_code", "")):
                wait = self._extract_retry_delay(str(error))
                if attempt < max_retries:
                    self.logger.warning(
                        f"⚠️ {step_name} got 429 (attempt {attempt}/{max_retries}) "
                        f"— waiting {wait}s before retry..."
                    )
                    time.sleep(wait)
                    continue
            return result  # non-429 error or exhausted retries
        return result

    def _parse_llm_result(self, result: Dict, step_name: str) -> Optional[Dict]:
        """Extract and JSON-parse the LLM text output from a gateway result."""
        if result.get("status") != "success":
            self.logger.error(f"{step_name} gateway error: {result.get('error')}")
            return None
        raw = result.get("output", {}).get("text", "")
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        try:
            data = json.loads(raw)
            self.logger.info(f"✅ {step_name} parsed successfully")
            return data
        except Exception as e:
            self.logger.error(f"JSON parse failed for {step_name}: {e}")
            return None

    def _pacing_sleep(self, label: str) -> None:
        self.logger.info(
            f"⏳ [PACING] Waiting {self.inter_block_delay_s}s after {label} response..."
        )
        time.sleep(self.inter_block_delay_s)

    # ─────────────────────────────────────────────────────────────────────
    # SPLITTING
    # ─────────────────────────────────────────────────────────────────────

    def _split_text_into_blocks(self, text: str) -> List[str]:
        """
        Split text into character-bounded blocks for 0.1 Discovery.
        - Breaks at paragraph boundaries when possible.
        - Adds overlap at block starts (except first) to catch headings at seams.
        """
        if not self._needs_chunking(text):
            return [text]

        blocks: List[str] = []
        start = 0
        while start < len(text):
            end = min(start + self.block_char_limit, len(text))

            if end < len(text):
                # Prefer a paragraph boundary in the second half of the block
                bp = text.rfind("\n\n", start + self.block_char_limit // 2, end)
                if bp > 0:
                    end = bp + 2

            # Overlap at the start of subsequent blocks
            block_start = max(0, start - self.block_overlap_chars) if blocks else start
            blocks.append(text[block_start:end])
            start = end

        self.logger.info(
            f"0.1 split: {len(text):,} chars → {len(blocks)} blocks "
            f"(limit={self.block_char_limit:,} chars, overlap={self.block_overlap_chars})"
        )
        return blocks

    def _split_by_chapters(
        self, text: str, chapters_list: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Split text into chapter-aligned blocks for 0.2 Intelligence.
        Each block contains complete chapters — never splits a chapter in half.
        Returns list of {text, chapters} dicts.
        """
        if not chapters_list or not self._needs_chunking(text):
            return [{"text": text, "chapters": chapters_list or []}]

        # Locate each chapter heading in the text
        positions: List[tuple] = []
        for ch in chapters_list:
            name = ch.get("name", "")
            if not name:
                continue
            pos = text.find(name)
            if pos >= 0:
                positions.append((pos, ch))

        positions.sort(key=lambda x: x[0])

        if not positions:
            self.logger.warning(
                "No chapter headings found in text — using single block for 0.2"
            )
            return [{"text": text, "chapters": chapters_list}]

        blocks: List[Dict] = []
        current_start = 0
        current_chapters: List[Dict] = []
        current_chars = 0

        for i, (pos, ch) in enumerate(positions):
            next_pos = positions[i + 1][0] if i + 1 < len(positions) else len(text)
            ch_chars = next_pos - pos

            if current_chars + ch_chars > self.block_char_limit and current_chapters:
                blocks.append({"text": text[current_start:pos], "chapters": current_chapters})
                current_start = pos
                current_chapters = []
                current_chars = 0

            current_chapters.append(ch)
            current_chars += ch_chars

        if current_chapters:
            blocks.append({"text": text[current_start:], "chapters": current_chapters})

        self.logger.info(
            f"0.2 chapter-aligned split: {len(blocks)} blocks"
        )
        for i, b in enumerate(blocks):
            names = [c.get("name", "?") for c in b["chapters"]]
            self.logger.info(f"  Block {i+1}: {len(b['text']):,} chars | {names}")

        return blocks

    # ─────────────────────────────────────────────────────────────────────
    # MERGE LOGIC
    # ─────────────────────────────────────────────────────────────────────

    def _merge_discovery_results(self, block_results: List[Dict]) -> Dict:
        """
        Merge N discovery block results.
        - punctuation_style, metadata, language: from block 1 (stable book properties).
        - chapters_list: ordered union, deduplicated by normalised name.
        """
        if not block_results:
            return {}
        if len(block_results) == 1:
            return block_results[0]

        base = dict(block_results[0])
        merged = list(base.get("chapters_list", []))
        seen = {c["name"].strip().lower() for c in merged}

        for block in block_results[1:]:
            for ch in block.get("chapters_list", []):
                key = ch.get("name", "").strip().lower()
                if key and key not in seen:
                    merged.append(ch)
                    seen.add(key)

        # Re-sequence IDs
        for i, ch in enumerate(merged):
            ch["id"] = str(i + 1).zfill(3)

        base["chapters_list"] = merged
        self.logger.info(
            f"Discovery merge: {len(block_results)} blocks → {len(merged)} chapters"
        )
        return base

    def _merge_intelligence_results(self, block_results: List[Dict]) -> Dict:
        """
        Merge N intelligence block results.
        - metadata, narrator, sound_design: from block 1.
        - chapters: all blocks, deduped by id, sorted.
        - characters: deduped by canonical name; richer profile wins, higher
          role_category preserved (primary > secondary > tactical).
        """
        if not block_results:
            return {}
        if len(block_results) == 1:
            return block_results[0]

        base = block_results[0]
        all_chapters: Dict[str, Dict] = {}
        all_chars: Dict[str, Dict] = {}
        narrator = base.get("casting", {}).get("narrator", {})
        role_rank = {"primary": 3, "secondary": 2, "tactical": 1, "": 0}

        for block in block_results:
            # Chapters — standard key ("chapters") used by both block-1 and continuations
            for ch in block.get("chapters", []):
                ch_id = ch.get("id", "").strip()
                if ch_id and ch_id not in all_chapters:
                    all_chapters[ch_id] = ch

            # Characters — block 1 uses casting.characters; continuations use new_characters
            chars = (
                block.get("casting", {}).get("characters", [])
                + block.get("new_characters", [])
            )
            for char in chars:
                name = char.get("name", "").strip()
                if not name:
                    continue
                key = name.lower()
                if key not in all_chars:
                    all_chars[key] = char
                else:
                    existing = all_chars[key]
                    score_new = len(char.get("traits", "")) + len(char.get("vocal_profile", ""))
                    score_old = len(existing.get("traits", "")) + len(existing.get("vocal_profile", ""))
                    if score_new > score_old:
                        merged_char = {**char}
                        # Preserve the higher role_category
                        rc_new = role_rank.get(char.get("role_category", ""), 0)
                        rc_old = role_rank.get(existing.get("role_category", ""), 0)
                        if rc_old > rc_new:
                            merged_char["role_category"] = existing["role_category"]
                        all_chars[key] = merged_char

        sorted_chapters = sorted(all_chapters.values(), key=lambda c: c.get("id", "000"))
        chars_list = list(all_chars.values())

        self.logger.info(
            f"Intelligence merge: {len(block_results)} blocks → "
            f"{len(sorted_chapters)} chapters, {len(chars_list)} characters"
        )
        return {
            "metadata":    base.get("metadata", {}),
            "chapters":    sorted_chapters,
            "casting":     {"narrator": narrator, "characters": chars_list},
            "sound_design": base.get("sound_design", {}),
        }

    # ─────────────────────────────────────────────────────────────────────
    # DISCOVERY  (0.1)
    # ─────────────────────────────────────────────────────────────────────

    def _call_discovery_standalone(
        self, project_id: str, text_content: str
    ) -> Optional[Dict]:
        """Single-block 0.1 Discovery call (also used as block 1 in multi-block)."""
        self.logger.info("0.1 Discovery — standalone / block 1")
        prompt_data = self._load_prompt("config/prompts/stage_0/0.1_discovery_v1.3.yaml")
        prompt = prompt_data["prompt_template"].replace("{text_content}", text_content)
        result = self._call_gateway_with_retry(
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            job_id_meta={"project_id": project_id, "step": "0.1_discovery"},
            step_name="0.1 Discovery",
            timeout=1200,
        )
        return self._parse_llm_result(result, "0.1 Discovery")

    def _call_discovery_continuation(
        self,
        project_id: str,
        text_content: str,
        preamble: Dict,
        block_num: int,
        total_blocks: int,
    ) -> Optional[Dict]:
        """Continuation 0.1 call for blocks 2..N."""
        self.logger.info(f"0.1 Discovery — block {block_num}/{total_blocks}")
        prompt_data = self._load_prompt(
            "config/prompts/stage_0/0.1_discovery_continuation_v1.0.yaml"
        )
        book_language = preamble.get("metadata", {}).get("language", "Italian")
        prompt = (
            prompt_data["prompt_template"]
            .replace("{text_content}", text_content)
            .replace("{previous_chapters_json}",
                     json.dumps(preamble.get("chapters_list", []), ensure_ascii=False, indent=2))
            .replace("{previous_punctuation_json}",
                     json.dumps(preamble.get("punctuation_style", {}), ensure_ascii=False, indent=2))
            .replace("{book_language}", book_language)
            .replace("{block_num}", str(block_num))
            .replace("{total_blocks}", str(total_blocks))
        )
        result = self._call_gateway_with_retry(
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            job_id_meta={"project_id": project_id, "step": f"0.1_discovery_block_{block_num}"},
            step_name=f"0.1 Continuation block {block_num}",
            timeout=1200,
        )
        return self._parse_llm_result(result, f"0.1 Continuation block {block_num}")

    def _run_discovery(self, project_id: str, text_content: str) -> Optional[Dict]:
        """Route to single or multi-block discovery."""
        if not self._needs_chunking(text_content):
            return self._call_discovery_standalone(project_id, text_content)

        blocks = self._split_text_into_blocks(text_content)
        total = len(blocks)
        results: List[Dict] = []
        accumulated: Optional[Dict] = None

        for i, block_text in enumerate(blocks):
            block_num = i + 1
            if i > 0:
                self._pacing_sleep(f"0.1 block {i}")
            result = (
                self._call_discovery_standalone(project_id, block_text)
                if i == 0
                else self._call_discovery_continuation(
                    project_id, block_text, accumulated, block_num, total
                )
            )
            if result is None:
                self.logger.error(f"❌ 0.1 block {block_num}/{total} failed — aborting.")
                return None
            results.append(result)
            accumulated = self._merge_discovery_results(results)
            self.logger.info(
                f"0.1 block {block_num}/{total} ✓ — "
                f"chapters so far: {len(accumulated.get('chapters_list', []))}"
            )

        return accumulated

    # ─────────────────────────────────────────────────────────────────────
    # INTELLIGENCE  (0.2)
    # ─────────────────────────────────────────────────────────────────────

    def _call_intelligence_standalone(
        self,
        project_id: str,
        text_content: str,
        discovery_data: Dict,
        book_language: str,
    ) -> Optional[Dict]:
        """Single-block 0.2 Intelligence call (also used as block 1 in multi-block)."""
        self.logger.info("0.2 Intelligence — standalone / block 1")
        prompt_data = self._load_prompt("config/prompts/stage_0/0.2_intelligence_v1.0.yaml")
        chapters_data = discovery_data.get("chapters_list", [])
        chapters_summary = "\n".join(
            [f"- {c.get('name', c.get('id', 'Unknown'))}" for c in chapters_data]
        )
        prompt = prompt_data["prompt_template"].format(
            text_content=text_content,
            expected_chapters_list=chapters_summary,
            book_language=book_language,
        )
        result = self._call_gateway_with_retry(
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            job_id_meta={"project_id": project_id, "stage": "0", "task": "intelligence_analysis"},
            step_name="0.2 Intelligence",
            timeout=600,
        )
        return self._parse_llm_result(result, "0.2 Intelligence")

    def _call_intelligence_continuation(
        self,
        project_id: str,
        text_content: str,
        block_chapters: List[Dict],
        accumulated: Dict,
        book_language: str,
        block_num: int,
        total_blocks: int,
    ) -> Optional[Dict]:
        """Continuation 0.2 call for blocks 2..N."""
        self.logger.info(f"0.2 Intelligence — block {block_num}/{total_blocks}")
        prompt_data = self._load_prompt(
            "config/prompts/stage_0/0.2_intelligence_continuation_v1.0.yaml"
        )
        prev_chars = accumulated.get("casting", {}).get("characters", [])
        prev_chapters = accumulated.get("chapters", [])
        block_ch_names = "\n".join([f"- {c.get('name', '')}" for c in block_chapters])

        prompt = (
            prompt_data["prompt_template"]
            .replace("{text_content}", text_content)
            .replace("{previous_characters_json}",
                     json.dumps(prev_chars, ensure_ascii=False, indent=2))
            .replace("{previous_chapters_json}",
                     json.dumps(prev_chapters, ensure_ascii=False, indent=2))
            .replace("{expected_chapters_for_this_block}", block_ch_names)
            .replace("{book_language}", book_language)
            .replace("{block_num}", str(block_num))
            .replace("{total_blocks}", str(total_blocks))
        )
        result = self._call_gateway_with_retry(
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            job_id_meta={"project_id": project_id, "stage": "0", "task": f"intelligence_block_{block_num}"},
            step_name=f"0.2 Continuation block {block_num}",
            timeout=600,
        )
        return self._parse_llm_result(result, f"0.2 Continuation block {block_num}")

    def _run_intelligence(
        self,
        project_id: str,
        text_content: str,
        discovery_data: Dict,
        book_language: str,
    ) -> Optional[Dict]:
        """Route to single or multi-block intelligence."""
        if not self._needs_chunking(text_content):
            return self._call_intelligence_standalone(
                project_id, text_content, discovery_data, book_language
            )

        chapter_blocks = self._split_by_chapters(
            text_content, discovery_data.get("chapters_list", [])
        )
        total = len(chapter_blocks)
        results: List[Dict] = []
        accumulated: Optional[Dict] = None

        for i, block in enumerate(chapter_blocks):
            block_num = i + 1
            if i > 0:
                self._pacing_sleep(f"0.2 block {i}")
            result = (
                self._call_intelligence_standalone(
                    project_id, block["text"], discovery_data, book_language
                )
                if i == 0
                else self._call_intelligence_continuation(
                    project_id, block["text"], block["chapters"],
                    accumulated, book_language, block_num, total,
                )
            )
            if result is None:
                self.logger.error(f"❌ 0.2 block {block_num}/{total} failed — aborting.")
                return None
            results.append(result)
            accumulated = self._merge_intelligence_results(results)
            self.logger.info(
                f"0.2 block {block_num}/{total} ✓ — "
                f"chars: {len(accumulated.get('casting',{}).get('characters',[]))}, "
                f"chapters: {len(accumulated.get('chapters',[]))}"
            )

        return accumulated

    # ─────────────────────────────────────────────────────────────────────
    # MAIN PROCESS
    # ─────────────────────────────────────────────────────────────────────

    def process(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self.logger.info(f"DEBUG RAW MSG: {json.dumps(message)}")

        raw_project_id = message.get("project_id") or "unknown"
        project_id = DiasPersistence.normalize_id(raw_project_id)
        persistence = DiasPersistence(project_id=project_id)

        # ── Source file resolution ──
        config_path = persistence.project_root / "config.json"
        source_path = None
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            rel = cfg.get("processed_text")
            if rel:
                source_path = persistence.project_root / rel

        if not source_path or not source_path.exists():
            source_file = message.get("source_file")
            if source_file:
                source_path = Path(persistence.project_root) / "source" / source_file
        if not source_path or not source_path.exists():
            source_path = persistence.get_source_text_path()
        if not source_path or not source_path.exists():
            self.logger.error(f"❌ Source text not found for project {project_id}")
            return None

        self.logger.info(f"🚀 Stage 0 starting for project: {project_id}")
        self.logger.info(f"📍 Source: {source_path.absolute()}")

        try:
            with open(source_path, "r", encoding="utf-8") as f:
                source_text = f.read()

            token_est = self._estimate_tokens(source_text)
            mode = "MULTI-BLOCK" if self._needs_chunking(source_text) else "SINGLE-BLOCK"
            self.logger.info(
                f"📊 Book: {len(source_text):,} chars | ~{token_est:,} tokens | mode={mode}"
            )

            # ── STEP 0.1: DISCOVERY ──
            discovery_data = self._run_discovery(project_id, source_text)
            if not discovery_data:
                self.logger.error("❌ Step 0.1 failed — stopping.")
                return None

            book_language = discovery_data.get("metadata", {}).get("language", "Italian")
            self.logger.info(f"📖 Detected language: {book_language}")

            fingerprint_path = persistence.get_fingerprint_path()
            with open(fingerprint_path, "w", encoding="utf-8") as f:
                json.dump(discovery_data, f, indent=4, ensure_ascii=False)

            # ── STEP 0.1.5: NORMALIZATION ──
            self.logger.info(f"🔄 Normalization for {project_id}...")
            from src.tools.normalize_source import SourceNormalizer
            normalizer = SourceNormalizer(project_id)
            if not normalizer.normalize():
                self.logger.warning("⚠️ Normalization inconclusive — proceeding with source.")

            # ── PACING: 0.1 last response → 0.2 first call ──
            self._pacing_sleep("0.1 final block")

            # ── STEP 0.2: INTELLIGENCE ──
            normalized_path = persistence.get_normalized_text_path()
            if normalized_path and normalized_path.exists():
                self.logger.info(f"📖 Using normalized text: {normalized_path.name}")
                with open(normalized_path, "r", encoding="utf-8") as f:
                    text_for_intel = f.read()
            else:
                self.logger.warning("⚠️ Normalized text not found — using source.")
                text_for_intel = source_text

            intel_data = self._run_intelligence(
                project_id, text_for_intel, discovery_data, book_language
            )
            if not intel_data:
                self.logger.error("❌ Step 0.2 failed — stopping.")
                return None

            # ── MERGE INTO FINAL FINGERPRINT ──
            with open(fingerprint_path, "r", encoding="utf-8") as f:
                fp_data = json.load(f)

            if "metadata" in intel_data:
                fp_data["metadata"].update(intel_data["metadata"])
            fp_data["metadata"]["language"] = book_language   # 0.1 is authoritative

            if intel_data.get("chapters"):
                fp_data["chapters"] = intel_data["chapters"]

            fp_data["casting"]      = intel_data.get("casting", {})
            fp_data["sound_design"] = intel_data.get("sound_design", {})

            with open(fingerprint_path, "w", encoding="utf-8") as f:
                json.dump(fp_data, f, indent=4, ensure_ascii=False)

            self.logger.info(
                f"📁 Fingerprint complete — "
                f"chapters(0.1): {len(fp_data.get('chapters_list',[]))} | "
                f"chapters(0.2): {len(fp_data.get('chapters',[]))} | "
                f"characters: {len(fp_data.get('casting',{}).get('characters',[]))}"
            )

            # ── PREPRODUCTION DOSSIER ──
            self._ensure_preproduction_dossier(project_id, persistence, intel_data)

            # ── UPDATE PROJECT CONFIG ──
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    cfg["status"] = "analisi_completed"
                    cfg["last_analysis"] = datetime.now().isoformat()
                    np = persistence.get_normalized_text_path()
                    if np:
                        cfg["processed_text"] = os.path.relpath(np, persistence.project_root)
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=4)
                except Exception as e:
                    self.logger.error(f"⚠️ config.json update failed: {e}")

            self.logger.info(f"✨ Stage 0 COMPLETED for {project_id}.")
            return {
                "project_id": project_id,
                "status": "stage_0_complete",
                "mode": mode,
                "preproduction": str(persistence.get_preproduction_path()),
                "fingerprint": str(fingerprint_path),
            }

        except Exception as e:
            self.logger.error(f"Unhandled error in Stage 0: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    # ─────────────────────────────────────────────────────────────────────
    # PREPRODUCTION DOSSIER  (unchanged logic)
    # ─────────────────────────────────────────────────────────────────────

    def _ensure_preproduction_dossier(
        self,
        project_id: str,
        persistence: DiasPersistence,
        intel_data: Dict[str, Any] = None,
    ):
        preprod_path = persistence.get_preproduction_path()
        preprod_data = {}
        if preprod_path.exists():
            try:
                with open(preprod_path, "r", encoding="utf-8") as f:
                    preprod_data = json.load(f)
            except Exception as e:
                self.logger.error(f"Error reading preproduction.json: {e}")

        if "theatrical_standard" not in preprod_data:
            preprod_data["theatrical_standard"] = {
                "subtalker_temperature": 0.75,
                "temperature": 0.7,
                "instruct": "Natural Narrative",
                "voice_ref_text_active": True,
            }

        casting_root = intel_data.get("casting", {}) if intel_data else {}
        chars = casting_root.get("characters", [])

        if chars:
            preprod_data["characters_dossier"] = chars
            self.logger.info(f"💾 Dossier: {len(chars)} character profiles.")

            # Always rebuild casting from the fresh canonical dossier.
            # Preserves existing voice assignments; drops stale/non-canonical names.
            existing_assignments = preprod_data.get("casting", {})
            new_casting = {}
            for char_obj in chars:
                char_name = char_obj.get("name")
                if char_name:
                    new_casting[char_name] = existing_assignments.get(char_name, "")
            added = sum(1 for k in new_casting if k not in existing_assignments)
            preprod_data["casting"] = new_casting
            if added > 0:
                self.logger.info(f"Added {added} new characters to casting.")

            # Update palette from fresh model output (user can override in dashboard).
            palettes = (
                intel_data.get("sound_design", {}).get("palette_proposals", [])
                if intel_data else []
            )
            if palettes:
                preprod_data["palette_choice"] = palettes[0].get("name", "Standard Narrative")

        if "palette_choice" not in preprod_data:
            preprod_data["palette_choice"] = "Standard Narrative"

        if "global_voice" not in preprod_data:
            backend_cfg = self.config.models.qwen3_tts
            preprod_data["global_voice"] = getattr(backend_cfg, "default_voice", "luca")

        try:
            with open(preprod_path, "w", encoding="utf-8") as f:
                json.dump(preprod_data, f, indent=4, ensure_ascii=False)
            self.logger.info(f"Preproduction dossier saved for {project_id}")
        except Exception as e:
            self.logger.error(f"Error saving preproduction.json: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DIAS Stage 0 - Book Intelligence")
    parser.add_argument("--once", action="store_true", help="Process one task and exit")
    parser.add_argument("--project-id", type=str, help="Run on a specific project immediately")
    parser.add_argument("--source-file", type=str, help="Specific source file name (optional)")
    args = parser.parse_args()

    stage = Stage0Intelligence()

    if args.project_id:
        norm_id = args.project_id.strip("/")
        if "/" in norm_id:
            norm_id = norm_id.split("/")[-1]
        print(f"🚀 [ON-DEMAND] Starting analysis for: {norm_id}")
        result = stage.process({"project_id": norm_id, "source_file": args.source_file})
        if result:
            print(f"✨ Analysis complete | mode={result.get('mode')}")
            sys.exit(0)
        else:
            print(f"❌ Analysis failed for {args.project_id}")
            sys.exit(1)
    else:
        stage.run(once=args.once)
