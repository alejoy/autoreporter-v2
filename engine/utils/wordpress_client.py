import requests
import time
import re
from utils.logger import get_logger

log = get_logger("WordPressClient")


class WordPressClient:
    def __init__(self, url: str, user: str, password: str):
        self.base = url.rstrip("/")
        self.auth = (user, password)
        self._categories: dict[str, int] = {}

    # ------------------------------------------------------------------ #
    #  Categorías                                                           #
    # ------------------------------------------------------------------ #
    def get_categories(self) -> dict[str, int]:
        """Devuelve {nombre_categoria: id} obtenido de la API de WP."""
        if self._categories:
            return self._categories
        try:
            r = self._get("/wp-json/wp/v2/categories", params={"per_page": 100})
            self._categories = {c["name"]: c["id"] for c in r}
            log.info(f"Categorías cargadas: {list(self._categories.keys())}")
        except Exception as e:
            log.error(f"Error cargando categorías: {e}")
        return self._categories

    def get_category_id(self, name: str) -> int | None:
        cats = self.get_categories()
        cat_id = cats.get(name)
        if cat_id is None:
            log.warning(f"Categoría '{name}' no encontrada en WordPress.")
        return cat_id

    # ------------------------------------------------------------------ #
    #  Posts recientes (para duplicate checker)                             #
    # ------------------------------------------------------------------ #
    def get_recent_posts(self, count: int = 100) -> list[dict]:
        """Devuelve lista de {title, link} de los últimos N posts."""
        posts = []
        try:
            data = self._get("/wp-json/wp/v2/posts", params={
                "per_page": min(count, 100),
                "status": "any",
                "_fields": "id,title,link",
            })
            posts = [{"title": p["title"]["rendered"], "link": p["link"]} for p in data]
            log.info(f"{len(posts)} posts recientes cargados desde WP.")
        except Exception as e:
            log.error(f"Error obteniendo posts recientes: {e}")
        return posts

    # ------------------------------------------------------------------ #
    #  Media                                                               #
    # ------------------------------------------------------------------ #
    def upload_media(self, img_url: str, max_attempts: int = 3) -> int | None:
        """
        Descarga una imagen desde img_url y la sube a WP.
        Reintenta el ciclo completo (descarga + subida) hasta max_attempts veces.
        Devuelve el media ID o None si todos los intentos fallan.
        """
        headers_dl = {"User-Agent": "Mozilla/5.0 (AutoReporter/2.0)"}
        for attempt in range(1, max_attempts + 1):
            try:
                log.info(f"Descargando imagen (intento {attempt}/{max_attempts}): {img_url}")
                img_res = requests.get(img_url, headers=headers_dl, timeout=20)
                img_res.raise_for_status()

                content_type = img_res.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                ext_map = {
                    "image/jpeg": "jpg", "image/png": "png",
                    "image/webp": "webp", "image/avif": "avif", "image/gif": "gif",
                }
                ext = ext_map.get(content_type, "jpg")
                allowed_exts = ("jpg", "jpeg", "png", "webp", "avif", "gif")

                filename = img_url.split("/")[-1].split("?")[0]
                if not any(filename.lower().endswith(e) for e in allowed_exts):
                    filename = f"imagen-{int(time.time())}.{ext}"

                log.info(f"Subiendo a WP media ({len(img_res.content)} bytes)...")
                r = self._post_raw(
                    "/wp-json/wp/v2/media",
                    data=img_res.content,
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"',
                        "Content-Type": content_type,
                    },
                )
                if r.status_code == 201:
                    media_id = r.json()["id"]
                    log.info(f"Imagen subida OK — media_id={media_id}")
                    return media_id
                # HTTP 5xx → reintentar; HTTP 4xx → error permanente
                log.warning(f"WP media HTTP {r.status_code} — {r.text[:200]}")
                if r.status_code < 500:
                    break
            except Exception as e:
                log.warning(f"Excepción subiendo imagen intento {attempt}: {e}")

            if attempt < max_attempts:
                wait = 2 ** attempt
                log.info(f"Reintentando imagen en {wait}s...")
                time.sleep(wait)

        log.error(f"No se pudo subir imagen tras {max_attempts} intentos: {img_url}")
        return None

    def upload_media_bytes(self, img_bytes: bytes, filename: str = "imagen.jpg",
                           content_type: str = "image/jpeg", max_attempts: int = 3) -> int | None:
        """Sube bytes de imagen directamente a WP, con reintentos."""
        for attempt in range(1, max_attempts + 1):
            try:
                log.info(f"Subiendo imagen bytes a WP (intento {attempt}/{max_attempts})...")
                r = self._post_raw(
                    "/wp-json/wp/v2/media",
                    data=img_bytes,
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"',
                        "Content-Type": content_type,
                    },
                )
                if r.status_code == 201:
                    media_id = r.json()["id"]
                    log.info(f"Imagen (bytes) subida OK — media_id={media_id}")
                    return media_id
                log.warning(f"WP media bytes HTTP {r.status_code} — {r.text[:200]}")
                if r.status_code < 500:
                    break
            except Exception as e:
                log.warning(f"Excepción subiendo imagen bytes intento {attempt}: {e}")

            if attempt < max_attempts:
                wait = 2 ** attempt
                log.info(f"Reintentando en {wait}s...")
                time.sleep(wait)

        log.error(f"No se pudo subir imagen (bytes) tras {max_attempts} intentos.")
        return None

    # ------------------------------------------------------------------ #
    #  Posts                                                               #
    # ------------------------------------------------------------------ #
    def create_post(
        self,
        title: str,
        content: str,
        category_id: int | None = None,
        featured_media: int | None = None,
        status: str = "draft",
        tags: list[int] | None = None,
    ) -> dict | None:
        payload: dict = {"title": title, "content": content, "status": status}
        if category_id:
            payload["categories"] = [category_id]
        if featured_media:
            payload["featured_media"] = featured_media
        if tags:
            payload["tags"] = tags

        try:
            r = self._post_json("/wp-json/wp/v2/posts", json=payload)
            if r.status_code == 201:
                data = r.json()
                log.info(
                    f"Post creado OK — id={data['id']}, "
                    f"featured_media={data.get('featured_media','N/A')}, "
                    f"status={status}"
                )
                return data
            log.error(f"Error creando post: HTTP {r.status_code} — {r.text[:400]}")
        except Exception as e:
            log.error(f"Excepción creando post: {e}")
        return None

    # ------------------------------------------------------------------ #
    #  HTTP helpers con retry                                              #
    # ------------------------------------------------------------------ #
    # Delays en segundos entre reintentos según tipo de error
    # Errores de red (conexión rechazada, host inalcanzable) → esperar más
    _NETWORK_ERRORS = (
        "Failed to establish a new connection",
        "Network is unreachable",
        "Connection refused",
        "Name or service not known",
        "Max retries exceeded",
    )
    _RETRY_DELAYS_NETWORK = [15, 30, 60, 120]   # ~4 min total
    _RETRY_DELAYS_DEFAULT = [2, 5, 10, 20]       # ~37s total

    def _get(self, path: str, params: dict = None) -> list | dict:
        url = self.base + path
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                r = requests.get(url, params=params, auth=self.auth, timeout=20)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                err_str = str(e)
                is_network = any(kw in err_str for kw in self._NETWORK_ERRORS)
                delays = self._RETRY_DELAYS_NETWORK if is_network else self._RETRY_DELAYS_DEFAULT
                log.warning(f"GET {path} intento {attempt+1}/{max_attempts} falló: {err_str[:120]}")
                if attempt < max_attempts - 1:
                    wait = delays[min(attempt, len(delays) - 1)]
                    log.info(f"Esperando {wait}s antes de reintentar...")
                    time.sleep(wait)
        raise RuntimeError(f"GET {path} falló después de {max_attempts} intentos.")

    def _post_json(self, path: str, json: dict) -> requests.Response:
        url = self.base + path
        max_attempts = 4
        for attempt in range(max_attempts):
            try:
                r = requests.post(url, json=json, auth=self.auth, timeout=30)
                return r
            except Exception as e:
                err_str = str(e)
                is_network = any(kw in err_str for kw in self._NETWORK_ERRORS)
                delays = self._RETRY_DELAYS_NETWORK if is_network else self._RETRY_DELAYS_DEFAULT
                log.warning(f"POST JSON {path} intento {attempt+1}/{max_attempts} falló: {err_str[:120]}")
                if attempt < max_attempts - 1:
                    wait = delays[min(attempt, len(delays) - 1)]
                    time.sleep(wait)
        raise RuntimeError(f"POST {path} falló después de {max_attempts} intentos.")

    def _post_raw(self, path: str, data: bytes, headers: dict) -> requests.Response:
        url = self.base + path
        for attempt in range(3):
            try:
                r = requests.post(url, data=data, headers=headers, auth=self.auth, timeout=60)
                # Reintentar solo en 5xx (errores de servidor transitorios)
                if r.status_code < 500:
                    return r
                log.warning(f"POST RAW {path} HTTP {r.status_code} intento {attempt+1}/3")
            except Exception as e:
                log.warning(f"POST RAW {path} intento {attempt+1}/3 falló: {e}")
            time.sleep(2 ** attempt)
        raise RuntimeError(f"POST RAW {path} falló después de 3 intentos.")
