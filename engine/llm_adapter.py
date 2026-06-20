"""
Adaptador LLM — interfaz única para Gemini, OpenAI y Anthropic.
El agente llama a LLMAdapter.call() sin saber qué proveedor usa por debajo.

Retries con backoff exponencial vía `tenacity`. Si el proveedor primario
falla (cuota agotada, 5xx persistente, etc.) y el agente tiene un
`fallback_config`, se reintenta automáticamente con ese segundo proveedor.
"""

import logging
import requests
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, RetryError,
)

_log = logging.getLogger("LLMAdapter")


class _RetryableLLMError(Exception):
    """Error transitorio (5xx, 429, timeout) — vale la pena reintentar."""


_RETRY = retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((_RetryableLLMError, requests.RequestException)),
)


class LLMAdapter:
    def __init__(self, llm_config, fallback_config=None):
        self.cfg = llm_config              # db.LLMConfig
        self.fallback_cfg = fallback_config  # db.LLMConfig | None

    def call(self, prompt: str, max_tokens: int | None = None) -> str | None:
        try:
            return self._call_provider(self.cfg, prompt, max_tokens)
        except RetryError as e:
            _log.warning(f"Proveedor primario [{self.cfg.provider}/{self.cfg.model_name}] "
                         f"agotó reintentos: {e.last_attempt.exception()}")
        except Exception as e:
            _log.warning(f"Proveedor primario [{self.cfg.provider}/{self.cfg.model_name}] falló: {e}")

        if not self.fallback_cfg:
            return None

        _log.warning(f"Reintentando con fallback [{self.fallback_cfg.provider}/{self.fallback_cfg.model_name}]...")
        try:
            return self._call_provider(self.fallback_cfg, prompt, max_tokens)
        except RetryError as e:
            _log.error(f"Fallback [{self.fallback_cfg.provider}] también agotó reintentos: {e.last_attempt.exception()}")
        except Exception as e:
            _log.error(f"Fallback [{self.fallback_cfg.provider}] falló: {e}")
        return None

    def _call_provider(self, cfg, prompt: str, max_tokens: int | None) -> str | None:
        max_tokens = max_tokens or cfg.max_tokens
        provider = cfg.provider.lower()
        if provider == "gemini":
            return self._call_gemini(cfg, prompt, max_tokens)
        if provider == "openai":
            return self._call_openai(cfg, prompt, max_tokens)
        if provider == "anthropic":
            return self._call_anthropic(cfg, prompt, max_tokens)
        if provider == "openrouter":
            return self._call_openrouter(cfg, prompt, max_tokens)
        raise ValueError(f"Proveedor LLM desconocido: {provider}")

    # ── Gemini ─────────────────────────────────────────────────────────────────

    @_RETRY
    def _call_gemini(self, cfg, prompt: str, max_tokens: int) -> str | None:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{cfg.model_name}:generateContent?key={cfg.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": cfg.temperature,
                "maxOutputTokens": max_tokens,
                # Gemini 2.5 gasta tokens de "thinking" del mismo presupuesto que
                # maxOutputTokens; lo desactivamos para no truncar la respuesta real.
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        res = requests.post(url, json=payload,
                             headers={"Content-Type": "application/json"}, timeout=30)
        if res.status_code == 200:
            data = res.json()
            candidate = data["candidates"][0]
            finish = candidate.get("finishReason", "UNKNOWN")
            if finish == "MAX_TOKENS":
                _log.warning(f"Gemini MAX_TOKENS alcanzado (maxOutputTokens={max_tokens})")
            elif finish != "STOP":
                _log.warning(f"Gemini finishReason={finish}")
            return candidate["content"]["parts"][0]["text"]
        if res.status_code == 429 or res.status_code >= 500:
            raise _RetryableLLMError(f"Gemini HTTP {res.status_code}: {res.text[:300]}")
        _log.warning(f"Gemini HTTP {res.status_code} (no reintentable): {res.text[:300]}")
        return None

    # ── OpenAI ─────────────────────────────────────────────────────────────────

    @_RETRY
    def _call_openai(self, cfg, prompt: str, max_tokens: int) -> str | None:
        payload = {
            "model": cfg.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.temperature,
            "max_tokens": max_tokens,
        }
        res = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"]
        if res.status_code == 429 or res.status_code >= 500:
            raise _RetryableLLMError(f"OpenAI HTTP {res.status_code}: {res.text[:300]}")
        _log.warning(f"OpenAI HTTP {res.status_code} (no reintentable): {res.text[:300]}")
        return None

    # ── OpenRouter (API compatible con OpenAI, agrega muchos proveedores) ───────

    @_RETRY
    def _call_openrouter(self, cfg, prompt: str, max_tokens: int) -> str | None:
        payload = {
            "model": cfg.model_name,  # ej: "google/gemini-2.0-flash-exp:free"
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.temperature,
            "max_tokens": max_tokens,
        }
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"]
        if res.status_code == 429 or res.status_code >= 500:
            raise _RetryableLLMError(f"OpenRouter HTTP {res.status_code}: {res.text[:300]}")
        _log.warning(f"OpenRouter HTTP {res.status_code} (no reintentable): {res.text[:300]}")
        return None

    # ── Anthropic ──────────────────────────────────────────────────────────────

    @_RETRY
    def _call_anthropic(self, cfg, prompt: str, max_tokens: int) -> str | None:
        payload = {
            "model": cfg.model_name,
            "max_tokens": max_tokens,
            "temperature": cfg.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={
                "x-api-key": cfg.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        if res.status_code == 200:
            return res.json()["content"][0]["text"]
        if res.status_code == 429 or res.status_code >= 500:
            raise _RetryableLLMError(f"Anthropic HTTP {res.status_code}: {res.text[:300]}")
        _log.warning(f"Anthropic HTTP {res.status_code} (no reintentable): {res.text[:300]}")
        return None
