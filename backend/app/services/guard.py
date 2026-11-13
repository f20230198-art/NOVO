"""Prompt-injection defences for the voice assistant.

Layers (no single one is relied on):
1. Input screen: obvious attempts to rewrite the assistant's instructions are answered with a
   fixed reply and never reach the model (this also saves key-pool quota).
2. Fencing: the fisher's words and retrieved community text are wrapped in tagged blocks and
   any tag look-alikes inside them are neutralised, so text cannot "close" its block.
3. The system prompt tells the model that fenced text is data, never instructions.
4. Output checks (in assistant.py): JSON shape, an action allow-list, verdict words that must
   match the risk engine, a canary that reveals a leaked system prompt, and a length cap.
5. The model never sees phone numbers, other fishers' positions, tokens or keys, so a
   successful injection still has nothing private to leak.
"""
from __future__ import annotations

import re
import unicodedata

MAX_INPUT_CHARS = 500

# Phrases that only make sense as an attempt to change the assistant's rules.
_INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(previous|above|prior|earlier|all|your|the|system)\b.{0,30}\b(instructions?|rules?|prompts?|messages?|guidelines?|directions?)\b",
    r"\b(system|developer|hidden|initial|original)\s+(prompt|message|instructions?)\b",
    r"\byou\s+are\s+(now|no\s+longer)\b",
    r"\b(act|behave|pretend|roleplay)\s+(as|like)\s+(an?\s+)?(different|unrestricted|evil|jailbroken|dan|developer)\b",
    r"\b(jailbreak|dan\s+mode|developer\s+mode|god\s+mode)\b",
    r"\b(reveal|print|show|repeat|output|leak|tell\s+me)\b.{0,30}\b(prompt|instructions|api\s*keys?|secrets?|tokens?|password)\b",
    r"\b(mark|say|call|declare|tell\s+(me|them))\b.{0,40}\b(it\s+is|it's|the\s+sea\s+is)?\s*\bsafe\b.{0,30}\b(regardless|anyway|no\s+matter|even\s+if|ignore)\b",
    r"</?\s*(system|assistant|fisher_message|retrieved|engine_facts|context)\s*>",
    r"\[\s*(system|inst)\s*\]|<<\s*sys\s*>>|<\|im_start\|>",
]
_COMPILED = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _INJECTION_PATTERNS]

_TAG_LIKE = re.compile(r"<\s*/?\s*[a-zA-Z_][\w\-]*\s*>")
_CONTROL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-‏‪-‮⁦-⁩]")


def _clean(text: str, cap: int) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = _CONTROL.sub("", text)
    return re.sub(r"\s+", " ", text).strip()[:cap]


def normalise(text: str) -> str:
    """NFKC (folds look-alike characters), drop control and bidi characters, cap the length."""
    return _clean(text, MAX_INPUT_CHARS)


def looks_like_injection(text: str) -> bool:
    t = normalise(text)
    return any(p.search(t) for p in _COMPILED)


def fence(text: str, cap: int = 1500) -> str:
    """Make text safe to place inside a tagged block: tag look-alikes are bracketed out."""
    return _TAG_LIKE.sub(lambda m: "(" + m.group(0).strip("<>/ ") + ")", _clean(text, cap))


REFUSAL_EN = (
    "I can only help with sea safety, weather for your boat, planning and scheduling your trips, "
    "and Sea Safe features. Ask me something like: can I go out tomorrow morning?"
)
