import re
import time
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from abc import ABC, abstractmethod
from html import unescape as html_unescape

from utils.logger import get_logger
from llm_adapter import LLMAdapter

NS_MEDIA = "http://search.yahoo.com/mrss/"
NS_CONTENT = "http://purl.org/rss/1.0/modules/content/"

DIAS_SEMANA = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}
MESES = {
    "January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril",
    "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto",
    "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre",
}

PROMPT_REDACCION = """Basándote EXCLUSIVAMENTE en el texto fuente que te doy, redactá una nota periodística.
No inventes datos, cifras, nombres ni hechos que no estén en el texto fuente.
Si el texto fuente tiene citas textuales, podés usarlas con el nombre y cargo de quien habla.

TEXTO FUENTE:
\"\"\"
{texto_fuente}
\"\"\"

TÍTULO PARA LA NOTA: {titulo}

{contexto_redactor}

REGLAS DE ESTILO:
- Pirámide invertida: el dato más importante primero
- Párrafos de 3 a 5 líneas, fluidos y bien conectados
- Usá <strong> para nombres propios, cifras y términos clave la primera vez que aparecen
- Tono informativo y neutro
- PROHIBIDO: "es importante destacar", "vale la pena mencionar", "desde una perspectiva",
  "cabe señalar", "en conclusión", "en este contexto", "resulta relevante", "sin lugar a dudas"
- NO escribas la fecha al inicio
- NO uses <h2> ni <h3>, solo párrafos

SEO / GOOGLE DISCOVER:
- El PRIMER párrafo debe responder qué, quién, dónde y cuándo, y contener la palabra clave principal del título de forma natural (no forzada)
- Repetí la palabra clave principal (o una variante natural) al menos una vez más en el cuerpo, sin keyword stuffing
- Mencioná lugares, organismos y nombres propios completos al menos una vez (ayuda a Google a indexar entidades)
- Evitá ambigüedad: cada párrafo debe poder leerse de forma independiente y tener sentido por sí solo
- NO uses títulos clickbait ni preguntas como título; el contenido debe responder exactamente lo que el título promete
- Frases cortas y concretas, evitá oraciones de más de 25-30 palabras
- El último párrafo debe cerrar con un dato concreto o contexto adicional, nunca con una opinión o conclusión genérica

FORMATO:
- Empezá DIRECTO con <p>. Sin título ni encabezado.
- Solo etiquetas <p> y <strong>
- 4 a 5 párrafos
- Solo HTML, sin markdown ni bloques de código
- Español rioplatense"""


class BaseNewsAgent(ABC):
    """
    Clase base para agentes RSS.
    Recibe un AgentConfig (desde DB) en lugar de leer config.py.
    """

    def __init__(self, agent_cfg, pipeline_id: int = 0):
        self.cfg = agent_cfg          # db.AgentConfig
        self.pipeline_id = pipeline_id
        self.name = agent_cfg.name
        self.log = get_logger(self.name)
        self.llm = LLMAdapter(agent_cfg.llm, agent_cfg.llm_fallback) if agent_cfg.llm else None

    # ── Método principal ────────────────────────────────────────────────────────

    def run(self, wp_client, dup_checker, category_id: int | None, dry_run: bool = False) -> list[dict]:
        fecha_hoy = self._fecha_hoy()
        self.log.info(f"=== {self.name} — {fecha_hoy} ===")
        results = []

        noticias = self._fetch_rss()
        if not noticias:
            self.log.warning("Sin noticias disponibles.")
            return results

        temas = self._select_topics(noticias, fecha_hoy)
        if not temas:
            self.log.warning("No se pudieron seleccionar temas.")
            return results

        for tema in temas:
            result = self._process_topic(tema, fecha_hoy, wp_client, dup_checker, category_id, dry_run)
            results.append(result)
            time.sleep(2)

        return results

    def _process_topic(self, tema, fecha_hoy, wp_client, dup_checker, category_id, dry_run) -> dict:
        titulo = tema.get("titulo_sugerido", "Sin título")
        link = tema.get("link", "")
        self.log.info(f"Procesando: {titulo[:70]}")

        if dup_checker and dup_checker.is_duplicate(titulo, link):
            self.log.info("SKIP — duplicado.")
            self._log_db("info", f"SKIP duplicado: {titulo[:80]}", titulo, status="skipped")
            return {"title": titulo, "status": "skipped", "reason": "duplicado"}

        og_image, texto_fuente = self._fetch_article(link)
        if not texto_fuente:
            self.log.warning("Sin texto fuente — usando solo el título.")
            texto_fuente = titulo

        html_nota = self._generate_article(titulo, texto_fuente)
        if not html_nota:
            self._log_db("error", f"Fallo generación IA: {titulo[:80]}", titulo, status="error")
            return {"title": titulo, "status": "error", "reason": "fallo generación IA"}

        html_nota = html_nota.replace("```html", "").replace("```", "").strip()

        if self._es_rechazo_ia(html_nota):
            self.log.warning(f"SKIP — IA rechazó: {titulo[:60]}")
            self._log_db("warning", f"IA rechazó contenido: {titulo[:80]}", titulo, status="error")
            return {"title": titulo, "status": "error", "reason": "contenido fuente inválido (IA rechazó)"}

        if dry_run:
            extracto = re.sub(r"<[^>]+>", "", html_nota)[:200]
            self.log.info(f"[DRY-RUN] {titulo}\nExtracto: {extracto}...")
            self._log_db("info", f"[DRY-RUN] {titulo[:80]}", titulo, status="dry_run")
            return {"title": titulo, "status": "dry_run", "reason": "modo dry-run"}

        if not og_image:
            self.log.warning(f"SKIP — sin imagen: {titulo[:60]}")
            self._log_db("warning", f"Sin imagen destacada: {titulo[:80]}", titulo, status="error")
            return {"title": titulo, "status": "error", "reason": "sin imagen destacada"}

        media_id = wp_client.upload_media(og_image) if wp_client else None
        if not media_id:
            self._log_db("error", f"Fallo subir imagen: {titulo[:80]}", titulo, status="error")
            return {"title": titulo, "status": "error", "reason": "fallo al subir imagen"}

        meta_desc = self._build_meta_description(html_nota)

        if wp_client:
            post = wp_client.create_post(
                title=titulo,
                content=html_nota,
                category_id=category_id,
                featured_media=media_id,
                status=self.cfg.post_status,
                author=self.cfg.wp_author_id,
                excerpt=meta_desc,
                meta_description=meta_desc,
            )
            if post:
                if dup_checker:
                    dup_checker.mark_published(titulo, link)
                url = post.get("link", "")
                self._log_db("info", f"Publicado: {titulo[:80]}", titulo, article_url=url, status="published")
                return {"title": titulo, "status": "published", "reason": f"post_id={post['id']}"}
            self._log_db("error", f"Fallo publicación WP: {titulo[:80]}", titulo, status="error")
            return {"title": titulo, "status": "error", "reason": "fallo publicación WP"}

        return {"title": titulo, "status": "error", "reason": "sin wp_client"}

    # ── RSS ─────────────────────────────────────────────────────────────────────

    def _fetch_rss(self) -> list[dict]:
        noticias = []
        headers = {"User-Agent": "Mozilla/5.0 (AutoReporter/2.0)"}
        required_kw = self.cfg.keywords_required   # list[str] o []
        skip_kw = self.cfg.keywords_skip           # list[str] o []

        for url in self.cfg.feeds:
            try:
                self.log.info(f"RSS: {url}")
                res = requests.get(url, headers=headers, timeout=10)
                res.raise_for_status()
                root = ET.fromstring(res.content)
                for item in root.findall(".//item")[:6]:
                    titulo = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    if not titulo or len(titulo) <= 10 or not link:
                        continue
                    titulo_lower = titulo.lower()
                    if skip_kw and any(kw in titulo_lower for kw in skip_kw):
                        self.log.debug(f"Filtrado (dinámico): {titulo[:60]}")
                        continue
                    if required_kw and not any(kw in titulo_lower for kw in required_kw):
                        self.log.debug(f"Filtrado (keyword): {titulo[:60]}")
                        continue
                    noticias.append({"titulo": titulo, "link": link})
            except Exception as e:
                self.log.warning(f"Error en {url}: {e}")
            time.sleep(0.4)

        self.log.info(f"{len(noticias)} noticias obtenidas.")
        return noticias[:15]

    # ── Artículo fuente ─────────────────────────────────────────────────────────

    def _fetch_article(self, url: str) -> tuple[str | None, str]:
        og_image = None
        texto = ""
        if not url:
            return og_image, texto
        try:
            headers = {"User-Agent": "Mozilla/5.0 (AutoReporter/2.0)"}
            res = requests.get(url, headers=headers, timeout=12)
            res.raise_for_status()
            html = res.text

            for patron in [
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            ]:
                m = re.search(patron, html, re.IGNORECASE)
                if m:
                    candidate = html_unescape(m.group(1))
                    if candidate.startswith("http"):
                        og_image = candidate
                        break

            parrafos = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
            limpios = [self._strip_html(p) for p in parrafos]
            limpios = [t for t in limpios if self._es_parrafo_noticia(t)]
            texto = "\n\n".join(limpios[:20])

        except Exception as e:
            self.log.warning(f"Error descargando artículo {url}: {e}")

        return og_image, texto

    # ── Selección de temas ──────────────────────────────────────────────────────

    def _select_topics(self, noticias: list[dict], fecha_hoy: str) -> list[dict] | None:
        if not self.llm:
            self.log.error("Sin LLM configurado para este agente.")
            return None

        titulares = "\n".join([f"{i}. {n['titulo']}" for i, n in enumerate(noticias)])
        prompt = f"""Titulares del {fecha_hoy}:

{titulares}

{self.cfg.prompt_selection}

Seleccioná como máximo {self.cfg.max_topics} titulares.
Para "titulo_sugerido" generá un título optimizado para Google Discover:
- Claro y concreto, sin clickbait ni preguntas
- Incluí la palabra clave principal (lugar, organismo o tema) cerca del inicio
- Nombres propios completos (no abreviar)
- Sin mayúsculas innecesarias ni signos de exclamación
- Máximo 70-75 caracteres

Respondé SOLO con JSON válido, sin texto adicional:
[
  {{"indice": 0, "titulo_sugerido": "Título periodístico"}},
  {{"indice": 1, "titulo_sugerido": "..."}}
]"""
        respuesta = self.llm.call(prompt, max_tokens=2048)
        if not respuesta:
            return None
        try:
            respuesta = re.sub(r"```(?:json)?", "", respuesta).strip()
            seleccion = json.loads(respuesta)
            if not isinstance(seleccion, list):
                return None
            for tema in seleccion:
                idx = tema.get("indice", 0)
                if 0 <= idx < len(noticias):
                    tema["link"] = noticias[idx]["link"]
                    tema["titulo_original"] = noticias[idx]["titulo"]
                else:
                    tema["link"] = ""
                    tema["titulo_original"] = ""
            return seleccion
        except Exception as e:
            self.log.warning(f"Error parseando JSON de temas: {e}\n{respuesta[:200]}")
            return None

    # ── Generación de artículo ──────────────────────────────────────────────────

    def _generate_article(self, titulo: str, texto_fuente: str) -> str | None:
        if not self.llm:
            return None
        prompt = PROMPT_REDACCION.format(
            texto_fuente=texto_fuente[:3000],
            titulo=titulo,
            contexto_redactor=self.cfg.prompt_writing,
        )
        return self.llm.call(prompt, max_tokens=3000)

    # ── DB logging ──────────────────────────────────────────────────────────────

    def _log_db(self, level: str, message: str, article_title: str = "",
                article_url: str = "", status: str = "") -> None:
        try:
            from db import save_log
            save_log(self.pipeline_id, self.cfg.id, level, message, article_title, article_url, status)
        except Exception:
            pass

    # ── Helpers ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _fecha_hoy() -> str:
        now = datetime.now()
        dia = DIAS_SEMANA.get(now.strftime("%A"), now.strftime("%A"))
        mes = MESES.get(now.strftime("%B"), now.strftime("%B"))
        return f"{dia} {now.strftime('%d')} de {mes} de {now.strftime('%Y')}"

    @staticmethod
    def _build_meta_description(html_nota: str, max_len: int = 155) -> str:
        """Genera meta description (Yoast/RankMath/excerpt) a partir del primer párrafo,
        sin pegarle otra llamada al LLM — barato y determinístico."""
        texto = re.sub(r"<[^>]+>", " ", html_nota)
        texto = re.sub(r"\s+", " ", texto).strip()
        if len(texto) <= max_len:
            return texto
        recortado = texto[:max_len]
        corte = recortado.rfind(" ")
        return (recortado[:corte] if corte > 0 else recortado) + "…"

    @staticmethod
    def _strip_html(texto: str) -> str:
        texto = re.sub(r"<[^>]+>", "", texto or "")
        return re.sub(r"\s+", " ", texto).strip()

    @staticmethod
    def _es_parrafo_noticia(texto: str) -> bool:
        if len(texto) < 60:
            return False
        code_chars = texto.count("{") + texto.count("}") + texto.count(";")
        if code_chars / max(len(texto), 1) > 0.02:
            return False
        alpha = sum(c.isalpha() or c.isspace() for c in texto) / len(texto)
        return alpha > 0.65

    _REFUSAL_SIGNALS = (
        "no es posible redactar", "no es posible generar",
        "no puedo redactar", "no puedo generar",
        "definiciones de propiedades css", "propiedades css",
        "sin contenido periodístico", "no contiene información periodística",
        "el texto fuente no contiene", "texto fuente consiste en",
        "texto fuente proporcionado consiste", "no hay hechos",
        "no se puede redactar",
    )

    @classmethod
    def _es_rechazo_ia(cls, html_nota: str) -> bool:
        texto_plano = re.sub(r"<[^>]+>", "", html_nota).lower()
        return any(signal in texto_plano for signal in cls._REFUSAL_SIGNALS)
