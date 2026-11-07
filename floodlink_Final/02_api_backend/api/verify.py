"""Verify Agent (v1): find whether a new request is a duplicate of an existing open case.

v1 uses cheap signals (same area + text similarity + matching household profile).
Day-3 upgrade: replace `text_similarity` with embeddings (e.g. Gemini text-embedding / bge-m3).
"""
from dataclasses import dataclass, field
from floodcommon.schemas import Extraction

import os

# score >= DUP_THRESHOLD -> merged automatically. SUGGEST_THRESHOLD <= score < DUP_THRESHOLD -> a NEW case is made but the
# officer sees "อาจซ้ำกับ C-xxx" and decides (a wrong automatic merge hides a real household inside another case).
DUP_THRESHOLD = float(os.getenv("DUP_THRESHOLD", "0.70"))
SUGGEST_THRESHOLD = float(os.getenv("DUP_SUGGEST_THRESHOLD", "0.40"))


def _ngrams(s: str, n: int = 3) -> set[str]:
    s = "".join(s.split()).replace("นำ้", "น้ำ")
    return {s[i:i + n] for i in range(max(len(s) - n + 1, 1))}


def text_similarity(a: str, b: str) -> float:
    A, B = _ngrams(a), _ngrams(b)
    return len(A & B) / max(len(A | B), 1)


@dataclass
class CaseView:
    """Minimal view of an existing case used for matching (from DB or in-memory)."""
    case_id: str
    area: str | None
    text: str
    adults: int | None = None
    elderly_ages: list[int] = field(default_factory=list)
    children_ages: list[float] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    house_no: str | None = None
    street: str | None = None


def match_score(e: Extraction, text: str, c: CaseView) -> float:
    if e.area and c.area and e.area != c.area:
        return 0.0
    score = text_similarity(text, c.text)
    if e.house_no and c.house_no and e.house_no == c.house_no:
        score += 0.3
        if e.street and c.street and "".join(e.street.split()) == "".join(c.street.split()):
            score += 0.25                                   # same house number on the same soi: almost surely the same home
    if e.elderly_ages and sorted(e.elderly_ages) == sorted(c.elderly_ages): score += 0.25
    if e.children_ages and sorted(e.children_ages) == sorted(c.children_ages): score += 0.15
    if e.adults is not None and e.adults == c.adults: score += 0.1
    if e.flags and set(f.value for f in e.flags) == set(c.flags): score += 0.1
    return score


def find_duplicate(e: Extraction, text: str, open_cases: list[CaseView]) -> tuple[str | None, float]:
    best, best_score = None, 0.0
    for c in open_cases:
        s = match_score(e, text, c)
        if s > best_score:
            best, best_score = c.case_id, s
    return (best, best_score) if best_score >= DUP_THRESHOLD else (None, best_score)


def best_match(e: Extraction, text: str, open_cases: list[CaseView]) -> tuple[str | None, float]:
    best, best_score = None, 0.0
    for c in open_cases:
        sc = match_score(e, text, c)
        if sc > best_score:
            best, best_score = c.case_id, sc
    return best, best_score


def find_case_for_update(e: Extraction, text: str, open_cases: list[CaseView], threshold: float = 0.12):
    """Looser match for short follow-ups like "ได้รับความช่วยเหลือแล้ว": same area + any overlap in street/landmark text."""
    best, best_score = None, 0.0
    for c in open_cases:
        if e.area and c.area and e.area != c.area:
            continue
        s = text_similarity(text, c.text) + (0.3 if e.street and e.street in c.text else 0)
        if s > best_score:
            best, best_score = c.case_id, s
    return (best, best_score) if best_score >= threshold else (None, best_score)
