"""OpenAI-compatible LLM client (Gonka / OpenAI / any /v1 proxy)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any

from harbormaster.config import get_settings
from harbormaster.reliability.retry import with_retry


def llm_available() -> bool:
    settings = get_settings()
    return bool(settings.openai_api_key or os.getenv("OPENAI_API_KEY"))


def _parse_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                data = json.loads(match.group(0))
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def cache_key(kind: str, *parts: str) -> str:
    blob = kind + "\n" + "\n".join(parts)
    return hashlib.sha256(blob.encode("utf-8", errors="replace")).hexdigest()


class LLMClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY") or ""
        self.base_url = (
            settings.openai_base_url
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        self.model = os.getenv("OPENAI_MODEL") or settings.openai_model
        self.vision_model = os.getenv("VISION_MODEL") or settings.vision_model
        self.timeout = settings.llm_timeout_s
        self.resolved_model = self.model
        self.last_error = ""
        self.last_ok_at: float | None = None
        self._ping: dict[str, Any] | None = None
        self._ping_at = 0.0
        self._remote_models: list[str] | None = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.available,
            "base_url": self.base_url,
            "model": self.resolved_model or self.model,
            "ok": bool(self.last_ok_at),
            "last_error": self.last_error,
        }

    def _client(self):
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": self.api_key, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    def _complete(self, messages: list[dict[str, Any]], model: str, max_tokens: int, temperature: float) -> str:
        resp = self._client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        used = getattr(resp, "model", None) or model
        self.resolved_model = used
        self.last_error = ""
        self.last_ok_at = time.time()
        return (resp.choices[0].message.content or "").strip()

    def _discover_models(self) -> list[str]:
        if self._remote_models is not None:
            return self._remote_models
        try:
            rows = self._client().models.list().data
            self._remote_models = [m.id for m in rows if getattr(m, "id", None)]
        except Exception:
            self._remote_models = []
        return self._remote_models

    def _candidates(self, preferred: str | None = None) -> list[str]:
        settings = get_settings()
        names: list[str] = []
        for name in [preferred, *settings.model_fallbacks, *self._discover_models()]:
            if name and name not in names:
                names.append(name)
        return names

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int = 2000,
    ) -> str:
        if not self.available:
            raise RuntimeError("LLM API key is not configured")
        candidates = self._candidates(model)
        last_exc: Exception | None = None
        for name in candidates:
            if not name:
                continue
            try:
                return with_retry(
                    lambda n=name: self._complete(messages, n, max_tokens, temperature),
                    attempts=2,
                    base_delay=0.5,
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self.last_error = str(exc)[:300]
                continue
        raise RuntimeError(self.last_error or str(last_exc) or "LLM call failed")

    def ping(self, *, ttl: float = 45.0) -> dict[str, Any]:
        now = time.time()
        if self._ping and now - self._ping_at < ttl:
            return self._ping
        if not self.available:
            self._ping = {"ok": False, "error": "LLM API key is not configured", "model": self.model}
            self._ping_at = now
            return self._ping
        try:
            text = self.chat(
                [{"role": "user", "content": "Reply with the single word pong."}],
                max_tokens=8,
            )
            ok = bool(text)
            self._ping = {"ok": ok, "model": self.resolved_model, "error": "" if ok else "empty reply"}
        except Exception as exc:  # noqa: BLE001
            self._ping = {"ok": False, "model": self.model, "error": str(exc)[:300]}
        self._ping_at = now
        return self._ping

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        text = self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        data = _parse_json(text)
        if not data:
            raise ValueError("LLM returned non-JSON")
        return data

    def cached_json(
        self,
        kind: str,
        content: str,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
    ) -> dict[str, Any]:
        from harbormaster.ledger.store import LedgerStore

        settings = get_settings()
        key = cache_key(kind, model or self.resolved_model or self.model, content)
        store = LedgerStore()
        if settings.cache_extractions:
            hit = store.get_llm_cache(key)
            if hit is not None:
                return hit
        data = self.chat_json(messages, model=model)
        if settings.cache_extractions:
            store.put_llm_cache(key, kind, data)
        return data


_CLIENT: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = LLMClient()
    return _CLIENT
