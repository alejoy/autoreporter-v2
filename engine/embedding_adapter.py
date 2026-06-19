"""
Cliente de embeddings — usado por DuplicateChecker para detectar notas
parafraseadas (mismo hecho cubierto por otro medio, texto distinto) que
la similitud de texto (difflib) no puede ver.

Reutiliza el mismo proveedor/API key que ya tiene configurado el agente
(Gemini o OpenAI) — no agrega ninguna dependencia de ML pesada.
"""

import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

_log = logging.getLogger("EmbeddingClient")


class _RetryableEmbeddingError(Exception):
    pass


_RETRY = retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((_RetryableEmbeddingError, requests.RequestException)),
)


class EmbeddingClient:
    def __init__(self, llm_config):
        self.cfg = llm_config  # db.LLMConfig — reutiliza provider + api_key

    def embed(self, text: str) -> list[float] | None:
        provider = self.cfg.provider.lower()
        try:
            if provider == "gemini":
                return self._embed_gemini(text)
            if provider == "openai":
                return self._embed_openai(text)
            return None  # Anthropic no tiene endpoint de embeddings propio
        except Exception as e:
            _log.warning(f"Embedding falló ({provider}): {e}")
            return None

    @_RETRY
    def _embed_gemini(self, text: str) -> list[float] | None:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"text-embedding-004:embedContent?key={self.cfg.api_key}"
        )
        res = requests.post(url, json={"content": {"parts": [{"text": text}]}}, timeout=15)
        if res.status_code == 200:
            return res.json()["embedding"]["values"]
        if res.status_code == 429 or res.status_code >= 500:
            raise _RetryableEmbeddingError(f"Gemini embeddings HTTP {res.status_code}")
        _log.warning(f"Gemini embeddings HTTP {res.status_code} (no reintentable)")
        return None

    @_RETRY
    def _embed_openai(self, text: str) -> list[float] | None:
        res = requests.post(
            "https://api.openai.com/v1/embeddings",
            json={"model": "text-embedding-3-small", "input": text},
            headers={"Authorization": f"Bearer {self.cfg.api_key}", "Content-Type": "application/json"},
            timeout=15,
        )
        if res.status_code == 200:
            return res.json()["data"][0]["embedding"]
        if res.status_code == 429 or res.status_code >= 500:
            raise _RetryableEmbeddingError(f"OpenAI embeddings HTTP {res.status_code}")
        _log.warning(f"OpenAI embeddings HTTP {res.status_code} (no reintentable)")
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)
