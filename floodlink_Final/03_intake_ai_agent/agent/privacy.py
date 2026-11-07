"""Mask personal data BEFORE any text leaves our server for an external LLM (Gemini / Groq), and put it back after.

Why: the LLM only has to INTERPRET the message (type, vulnerable people, water level, needs, colour). Phone numbers,
house numbers, GPS points, map links, e-mails, LINE ids, ID-card numbers and names are already read by our own
model / regex on our server, so the LLM never needs them (PDPA: share only what is necessary).

  masked, vault = mask("ยายติดเตียง บ้านเลขที่ 12/3 โทร 081-234-5678 นายสมชาย ใจดี")
  -> "ยายติดเตียง บ้านเลขที่ [บ้านเลขที่1] โทร [เบอร์1] นาย[ชื่อ1] ใจดี"      (vault keeps the real values)
  unmask("ติดต่อ [เบอร์1]", vault) -> "ติดต่อ 081-234-5678"

PrivateLLM wraps the LLM chain so EVERY call is masked: extract(), split_cases() and complete_json() (chatbot).
Turn off with LLM_MASK_PII=0 (not recommended). The masking rules themselves live in floodcommon/pii.py.
"""
import os, re
from floodcommon.pii import (ENABLED, KIN, PATTERNS, HOUSE, SURNAME, CASE_WORDS, FORMAL, NAME,  # noqa: F401  (moved, re-exported)
                             mask, unmask, summary)

TEXT_FIELDS = ("contact", "house_no", "street", "landmark", "area", "summary")
LEFTOVER = re.compile(r"\[(?:เบอร์|บ้านเลขที่|พิกัด|ลิงก์แผนที่|ลิงก์|อีเมล|เลขบัตร|ไลน์|ชื่อ|นามสกุล)\d+\]")


def restore_extraction(e, vault: dict, original: str):
    """Fill the LLM's Extraction back with the real values. Contact / house no. always come from OUR reading of the
    original text (exact), the LLM's version only if ours found nothing."""
    if not vault:
        return e
    from .own_model import extract_entities                 # same extractor as the own model (sets up the import path)
    local = extract_entities(original)
    d = e.model_dump()
    for f in TEXT_FIELDS:
        if isinstance(d.get(f), str):
            d[f] = unmask(d[f], vault)
            if LEFTOVER.search(d[f]):                        # a placeholder the LLM invented / mangled
                d[f] = LEFTOVER.sub("", d[f]).strip() or None
    for f in ("contact", "house_no"):
        if local.get(f):
            d[f] = local[f]
    return type(e).model_validate(d)


class PrivateLLM:
    """Wraps the LLM chain: every text sent out is masked, every answer is unmasked. Other attributes pass through."""

    def __init__(self, inner):
        self.inner = inner
        self.last_masked = {}

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def extract(self, text: str):
        masked, vault = mask(text)
        self.last_masked = summary(vault)
        return restore_extraction(self.inner.extract(masked), vault, text)

    def split_cases(self, text: str) -> list[str]:
        masked, vault = mask(text)
        self.last_masked = summary(vault)
        return [unmask(s, vault) for s in self.inner.split_cases(masked)]

    def complete_json(self, system: str, user: str) -> dict:
        masked, vault = mask(user)
        self.last_masked = summary(vault)
        return unmask(self.inner.complete_json(system, masked), vault)


def wrap(llm):
    return PrivateLLM(llm) if (llm is not None and ENABLED and not isinstance(llm, PrivateLLM)) else llm
