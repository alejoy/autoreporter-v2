import difflib
from utils.logger import get_logger

log = get_logger("DuplicateChecker")


class DuplicateChecker:
    """
    Detecta noticias duplicadas usando:
    1. URL exacta (si está disponible)
    2. Similitud de título >= threshold (difflib)

    El cache se construye al inicio desde WordPress (últimos N posts)
    y se actualiza en memoria durante el run. No persiste entre ejecuciones
    (GitHub Actions empieza en blanco cada vez) — WP es la fuente de verdad.
    """

    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self._known_urls: set[str] = set()
        self._known_titles: list[str] = []

    def load_from_wp(self, recent_posts: list[dict]) -> None:
        """Carga títulos y URLs de posts recientes obtenidos desde WP."""
        for post in recent_posts:
            title = post.get("title", "")
            url = post.get("link", "")
            if title:
                self._known_titles.append(self._normalize(title))
            if url:
                self._known_urls.add(url.strip())
        log.info(
            f"Cache inicializado: {len(self._known_titles)} títulos, "
            f"{len(self._known_urls)} URLs conocidas."
        )

    def is_duplicate(self, title: str, source_url: str = None, exact: bool = False) -> bool:
        # 1. Verificar URL exacta
        if source_url and source_url.strip() in self._known_urls:
            log.info(f"DUPLICADO por URL: {source_url}")
            return True

        norm = self._normalize(title)

        # 2a. Modo exacto — para títulos con fecha embebida (horóscopo, clima),
        # donde el título de ayer es fuzzy-similar al de hoy pero NO es duplicado real.
        if exact:
            if norm in self._known_titles:
                log.info(f"DUPLICADO por título exacto: '{title[:60]}'")
                return True
            return False

        # 2b. Verificar similitud de título (fuzzy)
        for known in self._known_titles:
            ratio = difflib.SequenceMatcher(None, norm, known).ratio()
            if ratio >= self.threshold:
                log.info(
                    f"DUPLICADO por título (similitud={ratio:.0%}): "
                    f"'{title[:60]}'"
                )
                return True

        return False

    def mark_published(self, title: str, source_url: str = None) -> None:
        """Registra una nota como publicada en el cache en memoria."""
        self._known_titles.append(self._normalize(title))
        if source_url:
            self._known_urls.add(source_url.strip())

    @staticmethod
    def _normalize(text: str) -> str:
        """Normaliza un título para comparación: minúsculas, sin puntuación extra."""
        import re
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text
