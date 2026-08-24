import difflib
from utils.logger import get_logger

log = get_logger("DuplicateChecker")


class DuplicateChecker:
    """
    Detecta noticias duplicadas usando:
    1. URL exacta (si está disponible)
    2. Similitud de título >= threshold (difflib)
    3. Similitud semántica (embeddings) SOLO para títulos en "zona gris"
       (fuzzy entre gray_zone_low y threshold) — detecta la misma noticia
       cubierta por distintos medios con texto reescrito, que el fuzzy
       matching de texto no puede ver. Se computa on-demand y se cachea
       para no gastar cuota de API innecesariamente.

    El cache se construye al inicio desde WordPress (últimos N posts)
    y se actualiza en memoria durante el run. No persiste entre ejecuciones
    (GitHub Actions empieza en blanco cada vez) — WP es la fuente de verdad.
    """

    def __init__(self, threshold: float = 0.85, embedder=None,
                 semantic_threshold: float = 0.90, gray_zone_low: float = 0.55):
        self.threshold = threshold
        self.embedder = embedder                  # embedding_adapter.EmbeddingClient | None
        self.semantic_threshold = semantic_threshold
        self.gray_zone_low = gray_zone_low
        self._known_urls: set[str] = set()
        self._known_titles: list[str] = []
        self._embedding_cache: dict[int, list[float] | None] = {}

    def load_from_wp(self, recent_posts: list[dict]) -> None:
        """Carga títulos y URLs de posts recientes obtenidos desde WP."""
        for post in recent_posts:
            title = post.get("title", "")
            url = post.get("link", "")
            if title:
                self._known_titles.append(self._normalize(title))
            if url:
                self._known_urls.add(self._normalize_url(url))
        log.info(
            f"Cache inicializado: {len(self._known_titles)} títulos, "
            f"{len(self._known_urls)} URLs conocidas."
        )

    def load_source_urls(self, urls: list[str]) -> None:
        """
        Suma URLs FUENTE ya usadas (de corridas anteriores, vía run_logs) al
        cache de URLs conocidas. Complementa a load_from_wp(), que solo carga
        los links de los propios posts de WP — inútiles para matchear contra
        la URL de un artículo externo.
        """
        antes = len(self._known_urls)
        for url in urls:
            if url:
                self._known_urls.add(self._normalize_url(url))
        log.info(f"{len(self._known_urls) - antes} URLs fuente sumadas al cache (historial de publicaciones).")

    def is_duplicate(self, title: str, source_url: str = None, exact: bool = False) -> bool:
        # 1. Verificar URL (normalizada, sin query string — evita que un
        # ?utm_source=rss distinto haga pasar la misma URL como "nueva")
        if source_url and self._normalize_url(source_url) in self._known_urls:
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

        # 2b. Verificar similitud de título (fuzzy) — guardamos el mejor candidato
        # de la "zona gris" para confirmarlo (o no) con embeddings.
        best_ratio, best_idx = 0.0, -1
        for i, known in enumerate(self._known_titles):
            ratio = difflib.SequenceMatcher(None, norm, known).ratio()
            if ratio >= self.threshold:
                log.info(
                    f"DUPLICADO por título (similitud={ratio:.0%}): "
                    f"'{title[:60]}'"
                )
                return True
            if ratio > best_ratio:
                best_ratio, best_idx = ratio, i

        # 3. Zona gris — posible paráfrasis de la misma noticia en otro medio
        if self.embedder and best_idx >= 0 and self.gray_zone_low <= best_ratio < self.threshold:
            sim = self._semantic_similarity(title, best_idx)
            if sim is not None and sim >= self.semantic_threshold:
                log.info(
                    f"DUPLICADO semántico (similitud={sim:.0%}, fuzzy previo={best_ratio:.0%}): "
                    f"'{title[:60]}'"
                )
                return True

        return False

    def _semantic_similarity(self, title: str, known_idx: int) -> float | None:
        from embedding_adapter import cosine_similarity
        emb_new = self.embedder.embed(title)
        if emb_new is None:
            return None
        emb_known = self._embedding_cache.get(known_idx)
        if emb_known is None:
            emb_known = self.embedder.embed(self._known_titles[known_idx])
            self._embedding_cache[known_idx] = emb_known
        if emb_known is None:
            return None
        return cosine_similarity(emb_new, emb_known)

    def mark_published(self, title: str, source_url: str = None) -> None:
        """Registra una nota como publicada en el cache en memoria."""
        self._known_titles.append(self._normalize(title))
        if source_url:
            self._known_urls.add(self._normalize_url(source_url))

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Quita query string y trailing slash — evita que ?utm_source=rss u
        otros parámetros de tracking hagan pasar la misma URL como distinta."""
        return url.strip().split("?")[0].rstrip("/")

    @staticmethod
    def _normalize(text: str) -> str:
        """Normaliza un título para comparación: minúsculas, sin puntuación extra."""
        import re
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text
