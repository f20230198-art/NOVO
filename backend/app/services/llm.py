"""Rotating pool of free-tier LLM keys (Groq and Gemini, both OpenAI chat-completions compatible).

Why rotation is safe: every call is stateless. The caller builds the complete message list
(system prompt, retrieved facts, recent conversation) and the pool sends that same list to
whichever key it tries. Switching keys mid-conversation loses nothing, because no key ever
held any state.

Policy
- Each call starts at the next key (round robin), spreading load across all keys.
- 429 / 5xx / timeout: that key cools down (Retry-After if given) and the SAME payload goes
  to the next key, until the call's overall deadline runs out.
- 401 / 403: the key is treated as bad for an hour.
- Keys are never logged; logs show "groq#2".
"""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from ..config import gemini_keys, groq_keys, settings

log = logging.getLogger("seasafe.llm")

ENDPOINTS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-flash"),
}
RATE_LIMIT_COOLDOWN_S = 30.0
SERVER_ERROR_COOLDOWN_S = 10.0
BAD_KEY_COOLDOWN_S = 3600.0
MAX_RETRY_AFTER_S = 120.0


@dataclass
class PoolKey:
    provider: str
    key: str = field(repr=False)
    label: str
    cooldown_until: float = 0.0
    calls: int = 0
    failures: int = 0

    @property
    def url(self) -> str:
        return ENDPOINTS[self.provider][0]

    @property
    def model(self) -> str:
        return settings.llm_model or ENDPOINTS[self.provider][1]


class KeyPool:
    def __init__(self, keys: list[PoolKey]):
        self.keys = keys
        self._next = itertools.count()

    def __len__(self) -> int:
        return len(self.keys)

    def order(self, now: Optional[float] = None) -> list[PoolKey]:
        """Keys to try for one call: ready keys in round-robin order, then cooling ones by soonest-ready."""
        if not self.keys:
            return []
        now = time.monotonic() if now is None else now
        start = next(self._next) % len(self.keys)
        rotated = self.keys[start:] + self.keys[:start]
        ready = [k for k in rotated if k.cooldown_until <= now]
        cooling = sorted((k for k in rotated if k.cooldown_until > now), key=lambda k: k.cooldown_until)
        return ready + cooling

    @staticmethod
    def cool(k: PoolKey, seconds: float, now: Optional[float] = None) -> None:
        now = time.monotonic() if now is None else now
        k.cooldown_until = max(k.cooldown_until, now + seconds)
        k.failures += 1

    def status(self) -> list[dict]:
        now = time.monotonic()
        return [
            {"key": k.label, "model": k.model, "calls": k.calls, "failures": k.failures,
             "cooling_s": max(0, round(k.cooldown_until - now))}
            for k in self.keys
        ]


def _build_pool() -> KeyPool:
    keys: list[PoolKey] = []
    for i, key in enumerate(groq_keys(), 1):
        keys.append(PoolKey("groq", key, f"groq#{i}"))
    for i, key in enumerate(gemini_keys(), 1):
        keys.append(PoolKey("gemini", key, f"gemini#{i}"))
    return KeyPool(keys)


_pool: Optional[KeyPool] = None


def pool() -> KeyPool:
    global _pool
    if _pool is None:
        _pool = _build_pool()
    return _pool


def reset_pool(new: Optional[KeyPool] = None) -> None:
    """Tests swap in a fake pool; None rebuilds from settings on next use."""
    global _pool
    _pool = new


def available() -> bool:
    return len(pool()) > 0


def _retry_after(resp: httpx.Response) -> float:
    raw = resp.headers.get("retry-after")
    try:
        return min(MAX_RETRY_AFTER_S, max(1.0, float(raw))) if raw else RATE_LIMIT_COOLDOWN_S
    except ValueError:
        return RATE_LIMIT_COOLDOWN_S


async def _post(k: PoolKey, payload: dict, timeout: float) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(k.url, json={**payload, "model": k.model}, headers={"Authorization": f"Bearer {k.key}"})
        resp.raise_for_status()
        return resp.json()


async def chat_json(
    messages: list[dict[str, str]],
    *,
    deadline_s: float = 10.0,
    temperature: float = 0.2,
    max_tokens: int = 700,
) -> Optional[dict[str, Any]]:
    """Send one complete conversation and return the parsed JSON object, or None.

    The same `messages` list goes to every key tried, so the answer does not depend on
    which key served it.
    """
    keys = pool().order()
    if not keys:
        return None
    if len(keys) == 1:
        keys = keys * 2  # one retry for a transient failure; a cooled key is skipped below anyway
    payload = {
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    end = time.monotonic() + deadline_s
    for k in keys:
        left = end - time.monotonic()
        if left <= 0.5:
            break
        if k.cooldown_until > time.monotonic():
            # Only cooling keys remain; waiting would blow the deadline, so stop.
            break
        k.calls += 1
        try:
            body = await asyncio.wait_for(_post(k, payload, left), timeout=left)
            data = json.loads(body["choices"][0]["message"]["content"])
            if isinstance(data, dict):
                return data
            log.warning("llm: %s returned non-object JSON", k.label)
        except asyncio.TimeoutError:
            log.warning("llm: %s timed out, trying next key", k.label)
            KeyPool.cool(k, SERVER_ERROR_COOLDOWN_S)
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code == 429:
                wait = _retry_after(exc.response)
                log.warning("llm: %s rate limited, cooling %.0fs, trying next key", k.label, wait)
                KeyPool.cool(k, wait)
            elif code in (401, 403):
                log.error("llm: %s rejected (HTTP %s), disabled for an hour", k.label, code)
                KeyPool.cool(k, BAD_KEY_COOLDOWN_S)
            elif code >= 500:
                log.warning("llm: %s server error %s, trying next key", k.label, code)
                KeyPool.cool(k, SERVER_ERROR_COOLDOWN_S)
            elif "json_validate_failed" in exc.response.text:
                # The model produced broken JSON this time; the same request usually works on a retry.
                log.warning("llm: %s produced invalid JSON, retrying", k.label)
            else:  # 400: the payload itself is wrong; another key will not fix it
                log.warning("llm: %s HTTP %s: %s", k.label, code, exc.response.text[:200])
                return None
        except (ValueError, KeyError, IndexError, TypeError):
            log.warning("llm: %s reply was not valid JSON", k.label)
        except httpx.HTTPError as exc:
            log.warning("llm: %s network error: %s", k.label, exc)
            KeyPool.cool(k, SERVER_ERROR_COOLDOWN_S)
    return None
