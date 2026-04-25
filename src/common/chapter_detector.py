"""
DIAS Chapter Detector

Mathematical detection of chapter boundaries in source text, without LLM calls.
Supports 4 structure types found in real-world Italian/English books:
  Tipo 1 — explicit "Capitolo N: Title" (Cronache del Silicio)
  Tipo 2 — bare integer on isolated line, optional "Prologo" (Uomini in Rosso)
  Tipo 3 — ALL-CAPS multi-word heading (Hyperion)
  Tipo 4 — positional fallback only (no detectable structure)

Usage:
    boundaries = build_chapter_boundaries(full_text, chapters_list)
    # boundaries: [{chapter_id, chapter_number, name, start_char}]
    # start_char of entry N+1 is end_char of entry N; last entry ends at len(full_text)
"""

import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("chapter_detector")

_ROMAN = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7,
    "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12, "XIII": 13,
    "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19,
    "XX": 20, "XXI": 21, "XXII": 22, "XXIII": 23, "XXIV": 24,
    "XXV": 25, "XXVI": 26, "XXVII": 27, "XXVIII": 28, "XXIX": 29,
    "XXX": 30,
}

_IT_CARDINALS = {
    "uno": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5,
    "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
    "undici": 11, "dodici": 12, "tredici": 13, "quattordici": 14,
    "quindici": 15, "sedici": 16, "diciassette": 17, "diciotto": 18,
    "diciannove": 19, "venti": 20, "ventuno": 21, "ventidue": 22,
    "ventitré": 23, "ventitre": 23, "ventiquattro": 24, "venticinque": 25,
    "ventisei": 26, "ventisette": 27, "ventotto": 28, "ventinove": 29,
    "trenta": 30,
    # ordinals
    "primo": 1, "secondo": 2, "terzo": 3, "quarto": 4, "quinto": 5,
    "sesto": 6, "settimo": 7, "ottavo": 8, "nono": 9,
    "decimo": 10, "undicesimo": 11, "dodicesimo": 12, "tredicesimo": 13,
    "quattordicesimo": 14, "quindicesimo": 15, "sedicesimo": 16,
    "diciassettesimo": 17, "diciottesimo": 18, "diciannovesimo": 19,
    "ventesimo": 20,
}


def _roman_to_int(s: str) -> Optional[int]:
    """Parse Roman numeral string → int, or None."""
    return _ROMAN.get(s.upper())


def _parse_ordinal(token: str) -> Optional[int]:
    """Parse token as Italian cardinal, Roman numeral, or plain int."""
    t = token.lower().rstrip(":.,")
    if t in _IT_CARDINALS:
        return _IT_CARDINALS[t]
    roman = _roman_to_int(t)
    if roman:
        return roman
    try:
        return int(t)
    except ValueError:
        return None


def _normalize(s: str) -> str:
    """Lowercase, collapse whitespace."""
    return re.sub(r'\s+', ' ', s).strip().lower()


def _detect_structure_type(text: str) -> str:
    """
    Detect dominant chapter heading style.
    Returns 'tipo1', 'tipo2', 'tipo3', or 'tipo4'.
    """
    tipo1 = len(re.findall(
        r'(?:^|\n)[ \t]*(Capitolo|Chapter|Parte)\s+\S+\s*[:\-]',
        text, re.IGNORECASE
    ))
    tipo2 = len(re.findall(r'(?:^|\n)[ \t]*\d{1,3}[ \t]*\n', text))
    tipo3 = len(re.findall(
        r'(?:^|\n)[ \t]*([A-Z][A-Z\s\'\"À-Ü]{5,})[ \t]*\n',
        text
    ))

    scores = {"tipo1": tipo1, "tipo2": tipo2, "tipo3": tipo3}
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "tipo4"
    logger.info(f"Structure scores: {scores} → {best}")
    return best


def _find_tipo1_positions(text: str, n_expected: int) -> List[int]:
    """
    Find character positions of 'Capitolo/Chapter/Parte N[: ...]' headings.
    Returns list of start_char positions (start of the heading line).
    """
    pattern = re.compile(
        r'(?:^|\n)([ \t]*(Capitolo|Chapter|Parte)\s+\S+[^\n]*)',
        re.IGNORECASE
    )
    positions = []
    for m in pattern.finditer(text):
        line_start = m.start(1)
        positions.append(line_start)
    return positions


def _match_tipo1_to_fingerprint(text: str, chapters: List[dict]) -> List[dict]:
    """
    For Tipo 1 books: match each fingerprint chapter to its heading in source text
    using the chapter prefix (e.g. "Capitolo I", "Chapter 3") rather than pure
    positional assignment. Chapters whose titles have no heading prefix (e.g.
    "Libro Primo", "Prologo") are placed at the start of the source (char 0).

    Returns boundary list in fingerprint order, with correct start_char.
    """
    boundaries = []
    text_lower = text.lower()

    for i, ch in enumerate(chapters):
        cid = f"chapter_{i + 1:03d}"
        name = ch.get("title", ch.get("name", ""))
        parts = name.split(": ", 1)
        prefix = parts[0].strip()  # e.g. "Capitolo I", "Libro Primo"

        # Only headings that start with chapter keywords get a text search
        _ch_kw = ("capitolo ", "chapter ", "parte ")
        prefix_lower = prefix.lower()
        if any(prefix_lower.startswith(kw) for kw in _ch_kw):
            # Search for the prefix as a line start in the source
            pat = re.compile(
                r'(?:^|\n)([ \t]*' + re.escape(prefix) + r'[^\n]*)',
                re.IGNORECASE
            )
            m = pat.search(text)
            start_char = m.start(1) if m else None
        else:
            start_char = None  # No heading: will be assigned 0 or previous chapter start

        boundaries.append({
            "chapter_id": cid,
            "chapter_number": i + 1,
            "name": name,
            "start_char": start_char,  # None if not found
        })

    # Fill in None start_chars: use 0 for anything before the first found heading,
    # or use the same position as the next found heading (they share a boundary).
    first_found = next((b["start_char"] for b in boundaries if b["start_char"] is not None), 0)

    for b in boundaries:
        if b["start_char"] is None:
            b["start_char"] = 0  # pre-chapter content or intro

    # Sort by start_char, then re-assign in order (dedup if two share position 0)
    boundaries.sort(key=lambda x: (x["start_char"], x["chapter_number"]))

    found_count = sum(1 for b in boundaries if b["start_char"] > 0 or
                      b == next((x for x in boundaries if x["start_char"] == 0), None))
    logger.info(f"Tipo1 match: {found_count}/{len(chapters)} headings matched in source")

    return boundaries


def _find_tipo2_positions(text: str) -> List[tuple]:
    """
    Find (chapter_number, start_char) pairs for bare-integer headings.
    Also handles 'Prologo' and 'Epilogo' as special markers (returns num=0 / num=99999).

    Uses re.MULTILINE (^...$) to avoid the overlapping-newline problem that
    would skip every other number in sequences like "1\n2\n3\n4\n..." (TOC).
    """
    results = []

    # Special chapter markers — match as whole line or "Keyword N:" prefix
    _SPECIAL = [("Prologo", 0), ("Prologue", 0), ("Epilogo", 998), ("Epilogue", 998)]
    for keyword, num in _SPECIAL:
        pat = re.compile(r'^[ \t]*' + keyword + r'[ \t]*$', re.IGNORECASE | re.MULTILINE)
        m = pat.search(text)
        if m:
            results.append((num, m.start()))

    # "Coda N: ..." / "Cado N: ..." — append-style chapter sections (Cado = OCR typo of Coda)
    for m in re.finditer(
        r'^[ \t]*(Coda|Cado|Appendice|Appendix)\s+(\d+)\s*[:\-]',
        text, re.IGNORECASE | re.MULTILINE
    ):
        num = 900 + int(m.group(2))  # high numbers to avoid collision with chapter numbers
        results.append((num, m.start()))

    # Bare integers — whole line, multiline mode avoids consuming separating newlines
    for m in re.finditer(r'^[ \t]*(\d{1,3})[ \t]*$', text, re.MULTILINE):
        num = int(m.group(1))
        results.append((num, m.start()))

    # Sort by position; deduplicate by keeping FIRST occurrence of each number
    # (the first occurrence is the actual chapter heading; later ones may be TOC/index)
    results.sort(key=lambda x: x[1])
    seen: Dict[int, int] = {}
    deduped = []
    for num, start in results:
        if num not in seen:
            seen[num] = start
            deduped.append((num, start))

    return deduped


def _find_tipo3_positions(text: str, n_expected: int) -> List[int]:
    """
    Find character positions of ALL-CAPS headings (≥6 chars, no digits).

    Strategy:
    1. Collect all ALL-CAPS heading candidates.
    2. Find the dominant heading series by clustering on the first 2 words.
       A group of ≥2 headings with the same prefix forms a "chapter series".
    3. Always include PROLOGO/EPILOGO keywords (they're chapter headings even if unique).
    4. If the resulting set matches n_expected: use it.
       Otherwise fall back to simple positional trimming.
    """
    from collections import Counter

    pattern = re.compile(
        r'(?:^|\n)[ \t]*([A-Z][A-Z\s\'\"À-ÜÀ-ü\-]{5,})[ \t]*\n'
    )
    candidates: List[tuple] = []  # (start_char, heading_text)
    for m in pattern.finditer(text):
        heading_text = m.group(1).strip()
        if re.search(r'\d', heading_text):
            continue
        line_start = m.start() if text[m.start()] != '\n' else m.start() + 1
        candidates.append((line_start, heading_text))

    if not candidates:
        return []

    # Cluster by first 2 words of heading
    prefix_counter: Counter = Counter()
    for _, htxt in candidates:
        words = htxt.split()
        prefix = " ".join(words[:2]) if len(words) >= 2 else words[0] if words else ""
        prefix_counter[prefix] += 1

    # Build set of "series" headings: dominant (≥2 occurrences) + PROLOGO/EPILOGO
    _prologo_kw = {"PROLOGO", "EPILOGO", "PROLOGUE", "EPILOGUE", "PROLOGO:", "EPILOGO:"}
    dominant_prefixes = {p for p, cnt in prefix_counter.items() if cnt >= 2}

    def _is_chapter_heading(htxt: str) -> bool:
        words = htxt.split()
        prefix = " ".join(words[:2]) if len(words) >= 2 else words[0] if words else ""
        if prefix in dominant_prefixes:
            return True
        if htxt.strip().upper() in _prologo_kw or htxt.strip().upper().rstrip(":") in _prologo_kw:
            return True
        return False

    series = [(pos, htxt) for pos, htxt in candidates if _is_chapter_heading(htxt)]

    if series and len(series) == n_expected:
        return [s[0] for s in series]

    # Fallback: if series doesn't match, try just all candidates with front-trimming
    if len(candidates) >= n_expected:
        # Drop from front until we have n_expected
        trimmed = candidates
        while len(trimmed) > n_expected:
            trimmed = trimmed[1:]
        return [c[0] for c in trimmed]

    return [c[0] for c in candidates]


def _positional_assign(positions: List[int], chapters: List[dict]) -> List[dict]:
    """
    Assign N positions → N chapters positionally.
    chapters: list of fingerprint chapter dicts (in order).
    positions: sorted list of start_char positions in source text.
    Returns boundary list.
    """
    n = min(len(positions), len(chapters))
    boundaries = []
    for i in range(n):
        ch = chapters[i]
        name = ch.get("title", ch.get("name", ""))
        boundaries.append({
            "chapter_id": f"chapter_{i + 1:03d}",
            "chapter_number": i + 1,
            "name": name,
            "start_char": positions[i],
        })
    return boundaries


def build_chapter_boundaries(full_text: str, chapters: List[dict]) -> List[dict]:
    """
    Main entry point.

    Parameters
    ----------
    full_text : str
        The complete source text (as extracted by Stage A).
    chapters : list of dict
        Chapters from fingerprint.json — each has 'id', 'title' (or 'name'), 'summary'.
        Expected to be in reading order.

    Returns
    -------
    list of dict, sorted by start_char:
        [{chapter_id, chapter_number, name, start_char}, ...]
    The last entry's implicit end_char is len(full_text).
    Empty list on failure (caller falls back to single-chapter mode).
    """
    if not chapters:
        return []

    n = len(chapters)
    structure = _detect_structure_type(full_text)

    boundaries: List[dict] = []

    if structure == "tipo1":
        # Use prefix-matching strategy: each fingerprint chapter is searched by its
        # "Capitolo X" prefix so that extra entries ("Libro Primo") map to char 0.
        matched = _match_tipo1_to_fingerprint(full_text, chapters)
        if matched:
            boundaries = matched
        else:
            # Pure positional fallback
            positions = _find_tipo1_positions(full_text, n)
            if positions:
                boundaries = _positional_assign(positions[:n], chapters[:len(positions)])
            else:
                logger.warning("Tipo1 detection found no headings, falling back to tipo4")
                structure = "tipo4"

    if structure == "tipo2":
        raw = _find_tipo2_positions(full_text)
        # raw: [(chapter_number_hint, start_char)]
        # Map: chapter at list position i → fingerprint chapters[i]
        # Use chapter_number_hint to try to align; fall back to positional if ambiguous.
        if raw:
            # Build chapter number → fingerprint index map
            # Fingerprint titles for Tipo2 books are often just the number ("1", "2", ...)
            # or "Prologo"/"Coda N: ...". Use direct numeric/keyword match.
            num_to_fp_idx = {}
            for fi, ch in enumerate(chapters):
                ch_title = ch.get("title", ch.get("name", "")).strip()
                try:
                    num_to_fp_idx[int(ch_title)] = fi
                except ValueError:
                    pass
                ch_lower = ch_title.lower()
                if ch_lower in ("prologo", "epilogo", "prologue", "epilogue"):
                    num_to_fp_idx[0 if "pro" in ch_lower else 998] = fi
                # Coda N / Appendice N  (e.g. "Coda 1: Prima persona")
                _coda_m = re.match(r'(coda|cado|appendice|appendix)\s+(\d+)', ch_lower)
                if _coda_m:
                    num_to_fp_idx[900 + int(_coda_m.group(2))] = fi

            assigned: Dict[int, int] = {}  # fp_idx → start_char
            for hint_num, start_char in raw:
                fi = num_to_fp_idx.get(hint_num)
                if fi is not None:
                    assigned[fi] = start_char

            if len(assigned) >= max(1, n // 2):
                for fi, start_char in sorted(assigned.items()):
                    ch = chapters[fi]
                    name = ch.get("title", ch.get("name", ""))
                    boundaries.append({
                        "chapter_id": f"chapter_{fi + 1:03d}",
                        "chapter_number": fi + 1,
                        "name": name,
                        "start_char": start_char,
                    })
                boundaries.sort(key=lambda x: x["start_char"])
            else:
                # Positional fallback
                positions = [r[1] for r in raw[:n]]
                boundaries = _positional_assign(positions, chapters)
        else:
            structure = "tipo4"

    if structure == "tipo3":
        positions = _find_tipo3_positions(full_text, n)
        if positions:
            boundaries = _positional_assign(positions, chapters)
        else:
            structure = "tipo4"

    if structure == "tipo4" or not boundaries:
        # No structure detected: treat entire text as a single chapter or use fingerprint count
        # For a single-chapter fallback: all text belongs to chapter_001
        logger.warning("tipo4/fallback: no chapter boundaries found. Treating whole text as chapter_001.")
        if chapters:
            ch = chapters[0]
            name = ch.get("title", ch.get("name", ""))
            boundaries = [{
                "chapter_id": "chapter_001",
                "chapter_number": 1,
                "name": name,
                "start_char": 0,
            }]

    if boundaries:
        logger.info(f"Chapter boundaries built: {len(boundaries)} chapters, structure={structure}")
        for b in boundaries[:3]:
            logger.info(f"  chapter_id={b['chapter_id']} start={b['start_char']} name={b['name'][:50]!r}")

    return boundaries


def load_or_build_boundaries(
    project_root: Path,
    full_text: str,
    fingerprint_path: Optional[Path] = None,
    force_rebuild: bool = False,
) -> List[dict]:
    """
    Load chapter_boundaries.json if it exists, otherwise build and save it.

    Parameters
    ----------
    project_root : Path
    full_text : str
    fingerprint_path : Path, optional — defaults to project_root / "fingerprint.json"
    force_rebuild : bool — ignore cached file
    """
    boundaries_path = project_root / "chapter_boundaries.json"

    if boundaries_path.exists() and not force_rebuild:
        try:
            with open(boundaries_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Loaded cached chapter_boundaries.json ({len(data)} chapters)")
            return data
        except Exception as e:
            logger.warning(f"Failed to load chapter_boundaries.json: {e}. Rebuilding.")

    if fingerprint_path is None:
        fingerprint_path = project_root / "fingerprint.json"

    # Also check stages/stage_0/output/fingerprint.json as fallback
    if not fingerprint_path.exists():
        alt = project_root / "stages" / "stage_0" / "output" / "fingerprint.json"
        if alt.exists():
            fingerprint_path = alt

    if not fingerprint_path.exists():
        logger.warning(f"No fingerprint.json found at {fingerprint_path}. Cannot build boundaries.")
        return []

    try:
        with open(fingerprint_path, "r", encoding="utf-8") as f:
            fp = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load fingerprint: {e}")
        return []

    chapters = fp.get("chapters", fp.get("chapters_list", []))
    if not chapters:
        logger.warning("Fingerprint has no chapters list.")
        return []

    boundaries = build_chapter_boundaries(full_text, chapters)

    if boundaries:
        try:
            with open(boundaries_path, "w", encoding="utf-8") as f:
                json.dump(boundaries, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved chapter_boundaries.json → {boundaries_path}")
        except Exception as e:
            logger.warning(f"Failed to save chapter_boundaries.json: {e}")

    return boundaries
