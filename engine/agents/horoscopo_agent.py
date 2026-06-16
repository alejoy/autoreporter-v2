import re
import requests

from utils.logger import get_logger
from llm_adapter import LLMAdapter

SIGNOS_EMOJIS = "♈♉♊♋♌♍♎♏♐♑♒♓"

DIAS_SEMANA = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}
MESES = {
    "January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril",
    "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto",
    "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre",
}


class HoroscopoAgent:
    CATEGORY_NAME = "Generales"

    def __init__(self, agent_cfg=None, pipeline_id: int = 0):
        self.cfg = agent_cfg
        self.pipeline_id = pipeline_id
        self.name = agent_cfg.name if agent_cfg else "HoroscopoAgent"
        self.log = get_logger(self.name)
        self.llm = LLMAdapter(agent_cfg.llm) if agent_cfg and agent_cfg.llm else None

    def run(self, wp_client, dup_checker, category_id: int | None, dry_run: bool = False) -> list[dict]:
        from datetime import datetime
        now = datetime.now()
        fecha = f"{DIAS_SEMANA.get(now.strftime('%A'))} {now.strftime('%d')} de {MESES.get(now.strftime('%B'))} de {now.strftime('%Y')}"
        titulo = f"Horóscopo del día: {fecha}"
        self.log.info(f"=== HoroscopoAgent — {fecha} ===")

        if dup_checker and dup_checker.is_duplicate(titulo):
            self.log.info("SKIP — horóscopo de hoy ya publicado.")
            return [{"title": titulo, "status": "skipped", "reason": "duplicado"}]

        texto_ia = self._generar(fecha)
        if not texto_ia:
            return [{"title": titulo, "status": "error", "reason": "fallo generación IA"}]

        titulo_final, cuerpo = self._limpiar(texto_ia, fecha)
        html_final = self._wrap_html(cuerpo, fecha)

        if dry_run:
            self.log.info(f"[DRY-RUN] {titulo_final}")
            return [{"title": titulo_final, "status": "dry_run", "reason": "modo dry-run"}]

        # Imagen destacada — obligatoria
        media_id = self._generar_imagen_placa(fecha, wp_client)
        if not media_id:
            self.log.warning("SKIP — no se pudo generar/subir imagen de portada.")
            return [{"title": titulo_final, "status": "error", "reason": "sin imagen destacada"}]

        if wp_client:
            post = wp_client.create_post(
                title=titulo_final,
                content=html_final,
                category_id=category_id,
                featured_media=media_id,
                status="publish",
            )
            if post:
                if dup_checker:
                    dup_checker.mark_published(titulo_final)
                return [{"title": titulo_final, "status": "published", "reason": f"post_id={post['id']}"}]
            return [{"title": titulo_final, "status": "error", "reason": "fallo WP"}]

        return [{"title": titulo_final, "status": "error", "reason": "sin wp_client"}]

    IMAGEN_HOROSCOPO_URL = "https://noticiasneuquen.com/wp-content/uploads/horoscope.avif"

    def _generar_imagen_placa(self, fecha: str, wp_client) -> int | None:
        """Descarga la imagen estática del horóscopo y la sube a WP."""
        if not wp_client:
            return None
        return wp_client.upload_media(self.IMAGEN_HOROSCOPO_URL)

    def _generar(self, fecha: str) -> str | None:
        prompt = f"""Actuá como una astróloga experta. Escribí el HORÓSCOPO para hoy: {fecha}.

REGLAS (HTML):
1. NO saludes. Empezá DIRECTO con <h2> para "Energía Cósmica de Hoy" (breve resumen planetario).
2. Luego un bloque por cada signo: <h3> con el nombre y emoji del signo, <p> con la predicción.
   Orden: Aries ♈, Tauro ♉, Géminis ♊, Cáncer ♋, Leo ♌, Virgo ♍, Libra ♎, Escorpio ♏, Sagitario ♐, Capricornio ♑, Acuario ♒, Piscis ♓.
3. Tono: místico, inspirador y útil. Español neutro.
4. SOLO HTML, sin markdown."""
        if not self.llm:
            self.log.error("Sin LLM configurado para HoroscopoAgent.")
            return None
        return self.llm.call(prompt, max_tokens=2500)

    @staticmethod
    def _limpiar(texto: str, fecha: str) -> tuple[str, str]:
        texto = texto.replace("```html", "").replace("```", "").strip()
        titulo = f"Horóscopo del día: {fecha}"
        return titulo, texto

    @staticmethod
    def _wrap_html(cuerpo: str, fecha: str) -> str:
        return f"""<div style="font-family: 'Georgia', serif; font-size: 18px; line-height: 1.7; color: #2c3e50; max-width: 800px; margin: auto;">
  <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 35px; border-radius: 15px; text-align: center; margin-bottom: 30px;">
    <p style="text-transform: uppercase; letter-spacing: 2px; font-size: 13px; margin: 0; opacity: 0.8;">Astrología Diaria</p>
    <h2 style="font-size: 30px; margin: 8px 0; font-family: sans-serif;">Los Astros Hoy</h2>
    <div style="font-size: 17px; opacity: 0.75;">{fecha}</div>
  </div>
  <div>{cuerpo}</div>
  <div style="margin-top: 35px; padding: 18px; background: #f8f9fa; border-left: 4px solid #764ba2; font-size: 14px; color: #666; text-align: center;">
    ✨ <em>"Los astros inclinan, pero no obligan."</em> ✨
  </div>
</div>"""
