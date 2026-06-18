"""
Adaptador LLM — interfaz única para Gemini, OpenAI y Anthropic.
El agente llama a LLMAdapter.call() sin saber qué proveedor usa por debajo.
"""

import time
import logging
import requests

_log = logging.getLogger("LLMAdapter")


class LLMAdapter:
    def __init__(self, llm_config):
        self.cfg = llm_config  # db.LLMConfig

    def call(self, prompt: str, max_tokens: int | None = None) -> str | None:
        max_tokens = max_tokens or self.cfg.max_tokens
        provider = self.cfg.provider.lower()
        if provider == "gemini":
            return self._call_gemini(prompt, max_tokens)
        if provider == "openai":
            return self._call_openai(prompt, max_tokens)
        if provider == "anthropic":
            return self._call_anthropic(prompt, max_tokens)
        raise ValueError(f"Proveedor LLM desconocido: {provider}")

    # ── Gemini ─────────────────────────────────────────────────────────────────

    def _call_gemini(self, prompt: str, max_tokens: int) -> str | None:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.cfg.model_name}:generateContent?key={self.cfg.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.cfg.temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        for attempt in range(3):
            try:
                res = requests.post(url, json=payload,
                                    headers={"Content-Type": "application/json"}, timeout=30)
                if res.status_code == 200:
                    data = res.json()
                    candidate = data["candidates"][0]
                    finish = candidate.get("finishReason", "UNKNOWN")
                    if finish not in ("STOP", "MAX_TOKENS"):
                        _log.warning(f"Gemini finishReason={finish}")
                    if finish == "MAX_TOKENS":
                        _log.warning(f"Gemini MAX_TOKENS alcanzado (maxOutputTokens={max_tokens})")
                    return candidate["content"]["parts"][0]["text"]
                _log.warning(f"Gemini HTTP {res.status_code}: {res.text[:300]}")
                if res.status_code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                break  # 4xx — no reintentar
            except Exception:
                time.sleep(2 ** attempt)
        return None

    # ── OpenAI ─────────────────────────────────────────────────────────────────

    def _call_openai(self, prompt: str, max_tokens: int) -> str | None:
        payload = {
            "model": self.cfg.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.cfg.temperature,
            "max_tokens": max_tokens,
        }
        for attempt in range(3):
            try:
                res = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.cfg.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
                if res.status_code == 200:
                    return res.json()["choices"][0]["message"]["content"]
                if res.status_code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                break
            except Exception:
                time.sleep(2 ** attempt)
        return None

    # ── Anthropic ──────────────────────────────────────────────────────────────

    def _call_anthropic(self, prompt: str, max_tokens: int) -> str | None:
        payload = {
            "model": self.cfg.model_name,
            "max_tokens": max_tokens,
            "temperature": self.cfg.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        for attempt in range(3):
            try:
                res = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers={
                        "x-api-key": self.cfg.api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    timeout=30,
                )
                if res.status_code == 200:
                    return res.json()["content"][0]["text"]
                if res.status_code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                break
            except Exception:
                time.sleep(2 ** attempt)
        return None
