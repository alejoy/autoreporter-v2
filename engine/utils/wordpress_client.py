import io
import requests
import time
import re
from utils.logger import get_logger

log = get_logger("WordPressClient")

MAX_IMG_WIDTH = 1200
JPEG_QUALITY = 82


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
    @staticmethod
    def _optimize_image(img_bytes: bytes, content_type: str) -> tuple[bytes, str, str]:
        """
        Redimensiona a MAX_IMG_WIDTH y recodifica a JPEG (calidad JPEG_QUALITY)
        para reducir peso antes de subir a WP. Si Pillow no está disponible o
        la imagen no se puede procesar (ej. GIF animado), devuelve el original
        sin tocar.
        """
        try:
            from PIL import Image
        except ImportError:
            log.warning("Pillow no instalado — subiendo imagen sin optimizar.")
            return img_bytes, "imagen.jpg", content_type

        try:
            img = Image.open(io.BytesIO(img_bytes))
            if getattr(img, "is_animated", False):  # GIF animado: no tocar
                return img_bytes, "imagen.gif", content_type

            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            if img.width > MAX_IMG_WIDTH:
                ratio = MAX_IMG_WIDTH / img.width
                img = img.resize((MAX_IMG_WIDTH, int(img.height * ratio)), Image.LANCZOS)

            out = io.BytesIO()
            img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            optimized = out.getvalue()

            if len(optimized) < len(img_bytes):
                log.info(f"Imagen optimizada: {len(img_bytes)} → {len(optimized)} bytes")
                return optimized, "imagen.jpg", "image/jpeg"
            return img_bytes, "imagen.jpg", content_type
        except Exception as e:
            log.warning(f"No se pudo optimizar imagen ({e}) — subiendo original.")
            return img_bytes, "imagen.jpg", content_type

    def upload_media(self, img_url: str, max_attempts: int = 3, alt_text: str | None = None) -> int | None:
        """
        Descarga una imagen desde img_url y la sube a WP.
        Reintenta el ciclo completo (descarga + subida) hasta max_attempts veces.
        Devuelve el media ID o None si todos los intentos fallan.

        alt_text (opcional) — típicamente el título de la nota, para que la imagen
        no quede sin texto alternativo (accesibilidad + señal real de SEO, a
        diferencia del "puntaje" de plugins como AIOSEO que dependen de campos
        propietarios que la REST API no expone).
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

                file_bytes, opt_filename, content_type = self._optimize_image(img_res.content, content_type)
                if opt_filename == "imagen.jpg" and not filename.lower().endswith(("jpg", "jpeg")):
                    filename = re.sub(r"\.\w+$", ".jpg", filename) if "." in filename else f"{filename}.jpg"

                log.info(f"Subiendo a WP media ({len(file_bytes)} bytes)...")
                r = self._post_multipart(
                    "/wp-json/wp/v2/media",
                    filename=filename,
                    file_bytes=file_bytes,
                    content_type=content_type,
                    alt_text=alt_text,
                )
                if r.status_code == 201:
                    media_id = r.json()["id"]
                    log.info(f"Imagen subida OK — media_id={media_id}" + (" (con alt_text)" if alt_text else ""))
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
                           content_type: str = "image/jpeg", max_attempts: int = 3,
                           alt_text: str | None = None) -> int | None:
        """Sube bytes de imagen directamente a WP, con reintentos."""
        for attempt in range(1, max_attempts + 1):
            try:
                log.info(f"Subiendo imagen bytes a WP (intento {attempt}/{max_attempts})...")
                r = self._post_multipart(
                    "/wp-json/wp/v2/media",
                    filename=filename,
                    file_bytes=img_bytes,
                    content_type=content_type,
                    alt_text=alt_text,
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
        author: int | None = None,
        excerpt: str | None = None,
        meta_description: str | None = None,
    ) -> dict | None:
        payload: dict = {"title": title, "content": content, "status": status}
        if category_id:
            payload["categories"] = [category_id]
        if featured_media:
            payload["featured_media"] = featured_media
        if tags:
            payload["tags"] = tags
        if author:
            payload["author"] = author
        if excerpt:
            payload["excerpt"] = excerpt
        if meta_description:
            # Campos meta de Yoast SEO / RankMath, si el plugin los expone en REST.
            # Si no están registrados con show_in_rest, WP los ignora silenciosamente.
            payload["meta"] = {
                "_yoast_wpseo_metadesc": meta_description,
                "rank_math_description": meta_description,
            }

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

    def _post_multipart(self, path: str, filename: str, file_bytes: bytes,
                         content_type: str, alt_text: str | None = None) -> requests.Response:
        """
        Sube el archivo como multipart/form-data (lo que hace un browser/Postman),
        en vez de POST con body crudo + Content-Disposition. Algunos WAFs/plugins
        de seguridad bloquean ese segundo patrón porque se parece a un intento de
        subir un webshell, incluso con credenciales válidas.

        alt_text (opcional) viaja como campo de formulario aparte — la REST API
        de medios de WP acepta alt_text/title/caption junto al archivo en el mismo
        POST, no hace falta un PATCH de seguimiento.
        """
        url = self.base + path
        data = {"alt_text": alt_text[:250]} if alt_text else None
        for attempt in range(3):
            try:
                files = {"file": (filename, file_bytes, content_type)}
                r = requests.post(url, files=files, data=data, auth=self.auth, timeout=60)
                # Reintentar solo en 5xx (errores de servidor transitorios)
                if r.status_code < 500:
                    return r
                log.warning(f"POST multipart {path} HTTP {r.status_code} intento {attempt+1}/3")
            except Exception as e:
                log.warning(f"POST multipart {path} intento {attempt+1}/3 falló: {e}")
            time.sleep(2 ** attempt)
        raise RuntimeError(f"POST multipart {path} falló después de 3 intentos.")
