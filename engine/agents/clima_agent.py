import json
import math
import re
import time
import requests

from utils.logger import get_logger
from llm_adapter import LLMAdapter

LAT, LON = -38.9516, -68.0591  # Neuquén Capital

DIAS_SEMANA = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}
MESES = {
    "January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril",
    "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto",
    "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre",
}
WMO_MAP = {
    0: ("Despejado", "☀️"), 1: ("Mayormente despejado", "🌤️"), 2: ("Parcialmente nublado", "⛅"),
    3: ("Nublado", "☁️"), 45: ("Niebla", "🌫️"), 48: ("Niebla con escarcha", "🌫️"),
    51: ("Llovizna leve", "🌦️"), 61: ("Lluvia leve", "🌧️"), 63: ("Lluvia moderada", "🌧️"),
    65: ("Lluvia fuerte", "🌧️"), 80: ("Chubascos", "🌦️"), 81: ("Chubascos moderados", "🌦️"),
    95: ("Tormenta", "⛈️"), 96: ("Tormenta con granizo", "⛈️"), 99: ("Tormenta severa", "⛈️"),
}

# Mapea código WMO a una de las 6 categorías de ícono/paleta que soporta el
# estilo "profesional" (_render_profesional). No hace falta 1:1 con WMO_MAP.
WMO_TO_ICON = {
    0: "despejado", 1: "parcial", 2: "parcial", 3: "nublado",
    45: "niebla", 48: "niebla",
    51: "lluvia", 61: "lluvia", 63: "lluvia", 65: "lluvia", 80: "lluvia", 81: "lluvia",
    95: "tormenta", 96: "tormenta", 99: "tormenta",
}


class ClimaAgent:
    CATEGORY_NAME = "Generales"

    # Defaults — Neuquén Capital, para no romper agentes ya creados antes de
    # que existiera extra_config. Cada agente puede pisar esto vía
    # extra_config: {"ciudad": "...", "lat": ..., "lon": ..., "smn_keywords": [...]}
    _DEFAULT_CIUDAD = "Neuquén Capital"
    _DEFAULT_LAT, _DEFAULT_LON = -38.9516, -68.0591
    _DEFAULT_SMN_KEYWORDS = [
        "confluencia", "zapala", "chos malal", "añelo", "pehuenia",
        "loncopué", "picunches", "ñorquín", "minas", "neuquén norte",
        "neuquén sur", "neuquén centro", "neuquén",
    ]

    def __init__(self, agent_cfg=None, pipeline_id: int = 0):
        self.cfg = agent_cfg
        self.pipeline_id = pipeline_id
        self.name = agent_cfg.name if agent_cfg else "ClimaAgent"
        self.log = get_logger(self.name)
        self.llm = LLMAdapter(agent_cfg.llm, agent_cfg.llm_fallback) if agent_cfg and agent_cfg.llm else None

        extra = agent_cfg.extra_config if agent_cfg else {}
        self.ciudad = extra.get("ciudad", self._DEFAULT_CIUDAD)
        self.lat = extra.get("lat", self._DEFAULT_LAT)
        self.lon = extra.get("lon", self._DEFAULT_LON)
        self.smn_keywords = {k.lower() for k in extra.get("smn_keywords", self._DEFAULT_SMN_KEYWORDS)}
        # "clasico"      = degradé full-bleed con temperatura gigante (placa original Neuquén)
        # "moderno"      = tarjeta redondeada sobre fondo claro, ícono protagonista
        # "profesional"  = gradiente diagonal + viñeta, íconos vectoriales propios
        #                  (sol/nube/lluvia/tormenta/niebla dibujados a mano, sin
        #                  depender de emoji ni fuentes especiales), glass bar de stats
        self.estilo = extra.get("estilo", "clasico")

    def run(self, wp_client, dup_checker, category_id: int | None, dry_run: bool = False) -> list[dict]:
        from datetime import datetime
        now = datetime.now()
        fecha = f"{DIAS_SEMANA.get(now.strftime('%A'))} {now.day} de {MESES.get(now.strftime('%B'))}"

        self.log.info(f"=== ClimaAgent — {fecha} ===")

        clima = self._obtener_clima()
        if not clima:
            return [{"title": "Clima", "status": "error", "reason": "sin datos Open-Meteo"}]

        alertas = self._obtener_alertas()
        cielo_texto, icono = WMO_MAP.get(clima["codigo_wmo"], ("Variable", "⛅"))

        titulo = self._generar_titulo(clima, cielo_texto, alertas, fecha)
        if dup_checker and dup_checker.is_duplicate(titulo, exact=True):
            self.log.info("SKIP — clima de hoy ya publicado.")
            return [{"title": titulo, "status": "skipped", "reason": "duplicado"}]

        texto_ia = self._generar_redaccion(clima, cielo_texto, alertas, fecha, icono)
        if not texto_ia:
            return [{"title": titulo, "status": "error", "reason": "fallo IA"}]

        html_final = self._build_html(clima, cielo_texto, icono, alertas, fecha, texto_ia)

        if dry_run:
            self.log.info(f"[DRY-RUN] {titulo}")
            return [{"title": titulo, "status": "dry_run", "reason": "modo dry-run"}]

        # Imagen destacada — obligatoria
        media_id = self._generar_imagen_placa(clima, cielo_texto, icono, alertas, fecha, wp_client)
        if not media_id:
            self.log.warning("SKIP — no se pudo generar/subir imagen de placa.")
            return [{"title": titulo, "status": "error", "reason": "sin imagen destacada"}]

        meta_desc = f"Pronóstico para {self.ciudad} del {fecha}: máxima de {clima['temp_max']}°C, {cielo_texto.lower()}."

        if wp_client:
            post = wp_client.create_post(
                title=titulo,
                content=html_final,
                category_id=category_id,
                featured_media=media_id,
                status=self.cfg.post_status if self.cfg else "publish",
                author=self.cfg.wp_author_id if self.cfg else None,
                excerpt=meta_desc,
                meta_description=meta_desc,
            )
            if post:
                if dup_checker:
                    dup_checker.mark_published(titulo)
                return [{"title": titulo, "status": "published", "reason": f"post_id={post['id']}"}]
            return [{"title": titulo, "status": "error", "reason": "fallo WP"}]

        return [{"title": titulo, "status": "error", "reason": "sin wp_client"}]

    def _obtener_clima(self) -> dict | None:
        try:
            self.log.info("Consultando Open-Meteo...")
            res = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": self.lat, "longitude": self.lon,
                "current": "temperature_2m,weather_code,wind_speed_10m,wind_gusts_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,uv_index_max,precipitation_probability_max",
                "timezone": "America/Argentina/Salta", "forecast_days": 1,
            }, timeout=10)
            res.raise_for_status()
            d = res.json()
            cur, day = d["current"], d["daily"]
            return {
                "temp_actual": cur["temperature_2m"],
                "viento_vel": cur["wind_speed_10m"],
                "viento_rafagas": cur["wind_gusts_10m"],
                "temp_max": day["temperature_2m_max"][0],
                "temp_min": day["temperature_2m_min"][0],
                "prob_lluvia": day["precipitation_probability_max"][0],
                "uv_index": day["uv_index_max"][0],
                "codigo_wmo": day["weather_code"][0],
            }
        except Exception as e:
            self.log.error(f"Error Open-Meteo: {e}")
            return None

    def _obtener_alertas(self) -> list[dict]:
        alertas = []
        try:
            res = requests.get(
                f"https://ws.smn.gob.ar/alerts/type/AL?v={int(time.time())}",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=5,
            )
            for a in res.json():
                if self._es_alerta_zona(a):
                    alertas.append({"titulo": a.get("title", ""), "nivel": a.get("severity", "")})
        except Exception:
            pass
        self.log.info(f"{len(alertas)} alertas SMN para {self.ciudad}.")
        return alertas

    def _es_alerta_zona(self, a: dict) -> bool:
        """Retorna True solo si la alerta aplica a la zona configurada de este agente."""
        # Revisar campos estructurados de zonas/provincias primero
        for key in ("zones", "zone", "areas", "area", "provinces", "province"):
            val = a.get(key, "")
            if isinstance(val, (list, tuple)):
                val = " ".join(str(v) for v in val)
            elif isinstance(val, dict):
                val = json.dumps(val, ensure_ascii=False)
            val_lower = str(val).lower()
            if any(zona in val_lower for zona in self.smn_keywords):
                return True
        # Fallback: el título menciona explícitamente alguna de las keywords
        titulo = str(a.get("title", "")).lower()
        return any(kw in titulo for kw in self.smn_keywords)

    def _generar_titulo(self, clima, cielo_texto, alertas, fecha) -> str:
        if alertas:
            return f"⚠️ Alerta meteorológica en {self.ciudad}: {alertas[0]['titulo']}"
        # Incluir la fecha para que cada día sea único y no se detecte como duplicado
        return f"Clima en {self.ciudad} del {fecha}: máxima de {clima['temp_max']}°C y cielo {cielo_texto.lower()}"

    def _generar_redaccion(self, clima, cielo_texto, alertas, fecha, icono) -> str | None:
        datos = {
            "fecha": fecha, "ubicacion": self.ciudad,
            "maxima": f"{clima['temp_max']}°C", "minima": f"{clima['temp_min']}°C",
            "cielo": cielo_texto, "viento_rafagas": f"{clima['viento_rafagas']} km/h",
            "prob_lluvia": f"{clima['prob_lluvia']}%", "uv": clima["uv_index"],
            "alertas": [a["titulo"] for a in alertas] if alertas else "Ninguna",
        }
        tono_extra = f"\n- {self.cfg.prompt_writing}" if self.cfg and self.cfg.prompt_writing and not self.cfg.prompt_writing.upper().startswith("N/A") else ""
        prompt = f"""Sos un periodista meteorológico. Redactá una nota de clima para {self.ciudad}.

DATOS OFICIALES:
{json.dumps(datos, ensure_ascii=False, indent=2)}

ESTRUCTURA en HTML:
1. <p> de bajada: resumen del día con los datos más importantes.
2. <p> de desarrollo: temperatura, viento, probabilidad de lluvia. Usá <strong> para los números.
3. <p> de recomendaciones: 2-3 tips útiles según el clima (qué ropa usar, si llevar paraguas, protector solar, etc.).
{"4. <p> de ALERTA: destacar la alerta oficial del SMN con sus implicancias." if alertas else ""}

- Tono directo y útil, como un parte meteorológico profesional
- No inventes datos que no estén arriba
- SOLO HTML con <p> y <strong>, sin markdown{tono_extra}"""

        if not self.llm:
            self.log.error("Sin LLM configurado para ClimaAgent.")
            return None
        return self.llm.call(prompt, max_tokens=800)

    def _generar_imagen_placa(self, clima, cielo_texto, icono, alertas, fecha, wp_client) -> int | None:
        """Genera imagen de la placa de clima con Pillow (sin dependencias de sistema)."""
        if not wp_client:
            return None
        try:
            import io
            if self.estilo == "profesional":
                buf = self._render_profesional(clima, cielo_texto, icono, alertas, fecha)
            elif self.estilo == "moderno":
                buf = self._render_moderna(clima, cielo_texto, icono, alertas, fecha)
            else:
                buf = self._render_clasica(clima, cielo_texto, icono, alertas, fecha)
            return wp_client.upload_media_bytes(buf.getvalue(), f"clima-{int(time.time())}.jpg")
        except ImportError:
            self.log.warning("Pillow no instalado — sin imagen de placa.")
        except Exception as e:
            self.log.warning(f"Error generando placa clima: {e}")
        return None

    @staticmethod
    def _font(size, bold=False):
        from PIL import ImageFont
        paths = [
            f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
            f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else ''}.ttf",
            f"/usr/share/fonts/truetype/freefont/FreeSans{'Bold' if bold else ''}.ttf",
        ]
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
        return ImageFont.load_default()

    def _render_clasica(self, clima, cielo_texto, icono, alertas, fecha):
        """Placa original — degradé full-bleed, temperatura gigante centrada."""
        import io
        from PIL import Image, ImageDraw

        W, H = 1200, 675

        # Colores de fondo según condición
        cielo_l = cielo_texto.lower()
        if alertas:
            top, bot = (180, 30, 30), (100, 0, 0)
        elif "tormenta" in cielo_l:
            top, bot = (50, 50, 100), (20, 20, 60)
        elif "lluvia" in cielo_l or "llovizna" in cielo_l:
            top, bot = (70, 120, 200), (30, 60, 130)
        elif "nublado" in cielo_l:
            top, bot = (120, 140, 160), (60, 80, 100)
        else:  # despejado / soleado
            top, bot = (79, 172, 254), (0, 90, 200)

        # Gradiente vertical
        img = Image.new("RGB", (W, H))
        px = img.load()
        for y in range(H):
            r = int(top[0] + (bot[0] - top[0]) * y / H)
            g = int(top[1] + (bot[1] - top[1]) * y / H)
            b = int(top[2] + (bot[2] - top[2]) * y / H)
            for x in range(W):
                px[x, y] = (r, g, b)

        draw = ImageDraw.Draw(img)
        white = (255, 255, 255)
        cream = (230, 230, 230)

        f_loc    = self._font(32)
        f_temp   = self._font(160, bold=True)
        f_cielo  = self._font(52)
        f_min    = self._font(40)
        f_label  = self._font(30)
        f_val    = self._font(36, bold=True)
        f_alerta = self._font(34, bold=True)

        def center_text(text, y, font, color=white):
            bbox = draw.textbbox((0, 0), text, font=font)
            x = (W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), text, font=font, fill=color)

        # Ubicación y fecha
        draw.text((50, 40), self.ciudad, font=f_loc, fill=cream)
        fecha_bbox = draw.textbbox((0, 0), fecha, font=f_loc)
        draw.text((W - fecha_bbox[2] + fecha_bbox[0] - 50, 40), fecha, font=f_loc, fill=cream)

        # Temperatura principal
        center_text(f"{clima['temp_max']}°C", 130, f_temp)

        # Mín debajo de la máxima
        center_text(f"min {clima['temp_min']}°C", 320, f_min, cream)

        # Descripción del cielo
        center_text(cielo_texto, 385, f_cielo)

        # Banda de datos inferior
        band_y = H - 140
        draw.rectangle([(0, band_y), (W, H)], fill=(0, 0, 0, 80))

        tercio = W // 3
        datos = [
            ("Rafagas", f"{clima['viento_rafagas']} km/h"),
            ("Prob. lluvia", f"{clima['prob_lluvia']}%"),
            ("Indice UV", str(clima['uv_index'])),
        ]
        for i, (label, val) in enumerate(datos):
            cx = tercio * i + tercio // 2
            lb = draw.textbbox((0, 0), label, font=f_label)
            draw.text((cx - (lb[2] - lb[0]) // 2, band_y + 15), label, font=f_label, fill=cream)
            vb = draw.textbbox((0, 0), val, font=f_val)
            draw.text((cx - (vb[2] - vb[0]) // 2, band_y + 55), val, font=f_val, fill=white)

        # Alerta si hay
        if alertas:
            alert_text = f"ALERTA: {alertas[0]['titulo'][:70]}"
            draw.rectangle([(0, band_y - 60), (W, band_y)], fill=(180, 0, 0))
            center_text(alert_text, band_y - 50, f_alerta)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        buf.seek(0)
        return buf

    def _render_moderna(self, clima, cielo_texto, icono, alertas, fecha):
        """Estilo alternativo — tarjeta redondeada sobre fondo claro, ícono protagonista."""
        import io
        from PIL import Image, ImageDraw

        W, H = 1200, 675
        bg = (244, 241, 234)  # crema suave
        accent_map = {
            "tormenta": (220, 90, 60), "lluvia": (60, 130, 200), "llovizna": (60, 130, 200),
            "nublado": (140, 140, 150), "niebla": (150, 150, 160),
        }
        cielo_l = cielo_texto.lower()
        accent = (220, 60, 60) if alertas else next(
            (c for k, c in accent_map.items() if k in cielo_l), (235, 160, 50)  # soleado/despejado default
        )

        img = Image.new("RGB", (W, H), bg)
        draw = ImageDraw.Draw(img)
        ink = (45, 42, 38)
        muted = (120, 115, 105)

        f_loc    = self._font(28)
        f_temp   = self._font(110, bold=True)
        f_cielo  = self._font(40)
        f_label  = self._font(24)
        f_val    = self._font(32, bold=True)
        f_alerta = self._font(24, bold=True)

        def center_text(text, y, font, color=ink, cx=None):
            bbox = draw.textbbox((0, 0), text, font=font)
            x = (cx or W // 2) - (bbox[2] - bbox[0]) // 2
            draw.text((x, y), text, font=font, fill=color)

        # Tarjeta principal redondeada
        margin = 60
        card = (margin, margin, W - margin, H - margin)
        draw.rounded_rectangle(card, radius=40, fill=(255, 255, 255))
        draw.rounded_rectangle((margin, margin, W - margin, margin + 14), radius=8, fill=accent)

        # Encabezado: ciudad + fecha
        draw.text((margin + 50, margin + 40), self.ciudad.upper(), font=f_loc, fill=muted)
        fecha_bbox = draw.textbbox((0, 0), fecha, font=f_loc)
        draw.text((W - margin - 50 - (fecha_bbox[2] - fecha_bbox[0]), margin + 40), fecha, font=f_loc, fill=muted)

        # Insignia circular a la izquierda (no usamos el emoji como texto — muchos
        # caracteres de WMO_MAP son de planos Unicode altos que DejaVuSans no tiene,
        # y se ven como cuadrados vacíos), temperatura grande a la derecha
        badge_cx, badge_cy, badge_r = W // 2 - 220, 250, 95
        draw.ellipse(
            (badge_cx - badge_r, badge_cy - badge_r, badge_cx + badge_r, badge_cy + badge_r),
            fill=tuple(min(255, c + 25) for c in accent), outline=accent, width=6,
        )
        center_text(f"{clima['temp_max']}°", 190, f_temp, color=accent, cx=W // 2 + 180)
        center_text(f"mín {clima['temp_min']}°C", 320, self._font(28), color=muted, cx=W // 2 + 180)
        center_text(cielo_texto, 370, f_cielo)

        # Alerta — va arriba de la línea separadora, nunca pisa la fila de stats
        if alertas:
            alert_text = f"ALERTA: {alertas[0]['titulo'][:55]}"
            draw.rounded_rectangle((margin + 40, 425, W - margin - 40, 472), radius=14, fill=(255, 235, 235))
            center_text(alert_text, 437, f_alerta, color=(180, 30, 30))

        # Fila de stats con separadores
        band_y = H - margin - 130
        draw.line([(margin + 50, band_y), (W - margin - 50, band_y)], fill=(230, 226, 218), width=2)
        tercio = (W - 2 * margin) // 3
        datos = [
            ("RÁFAGAS", f"{clima['viento_rafagas']} km/h"),
            ("PROB. LLUVIA", f"{clima['prob_lluvia']}%"),
            ("ÍNDICE UV", str(clima['uv_index'])),
        ]
        for i, (label, val) in enumerate(datos):
            cx = margin + tercio * i + tercio // 2
            center_text(label, band_y + 30, f_label, color=muted, cx=cx)
            center_text(val, band_y + 65, f_val, color=ink, cx=cx)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        buf.seek(0)
        return buf

    # ------------------------------------------------------------------ #
    #  Estilo "profesional" — gradiente + viñeta + íconos vectoriales      #
    # ------------------------------------------------------------------ #
    _PALETAS_PRO = {
        # condicion: (top, bottom, color_acento_icono)
        "despejado": ((30, 100, 190), (10, 40, 95), (255, 200, 70)),
        "parcial":   ((45, 95, 165), (20, 50, 100), (235, 225, 210)),
        "nublado":   ((90, 105, 125), (45, 55, 70), (225, 228, 232)),
        "lluvia":    ((35, 70, 110), (15, 30, 55), (150, 200, 235)),
        "tormenta":  ((35, 35, 65), (10, 10, 25), (255, 215, 90)),
        "niebla":    ((110, 118, 128), (70, 76, 85), (235, 236, 238)),
        "alerta":    ((150, 25, 25), (70, 8, 8), (255, 220, 210)),
    }

    @staticmethod
    def _diagonal_gradient(w, h, top, bottom):
        from PIL import Image
        base = Image.new("RGB", (1, h * 2))
        for y in range(h * 2):
            t = y / max(h * 2 - 1, 1)
            base.putpixel((0, y), (
                round(top[0] + (bottom[0] - top[0]) * t),
                round(top[1] + (bottom[1] - top[1]) * t),
                round(top[2] + (bottom[2] - top[2]) * t),
            ))
        base = base.resize((1, h * 2))
        img = Image.new("RGB", (w, h))
        px_src, px = base.load(), img.load()
        for y in range(h):
            for x in range(w):
                idx = min(h * 2 - 1, y + int((x / w) * h * 0.6))
                px[x, y] = px_src[0, idx]
        return img

    @staticmethod
    def _add_vignette(img, strength=55):
        from PIL import Image, ImageDraw, ImageFilter
        w, h = img.size
        vig = Image.new("L", (w, h), 0)
        ImageDraw.Draw(vig).ellipse((-w * 0.25, -h * 0.35, w * 1.25, h * 1.35), fill=255)
        vig = vig.filter(ImageFilter.GaussianBlur(120))
        dark = Image.new("RGB", (w, h), (0, 0, 0))
        return Image.composite(img, dark, vig.point(lambda p: 255 - int((255 - p) * strength / 100)))

    @staticmethod
    def _cloud_shape(d, cx, cy, scale, color):
        fill = color if len(color) == 4 else color + (255,)
        d.ellipse((cx - 0.34*scale, cy - 0.05*scale, cx + 0.06*scale, cy + 0.30*scale), fill=fill)
        d.ellipse((cx - 0.10*scale, cy - 0.22*scale, cx + 0.34*scale, cy + 0.22*scale), fill=fill)
        d.ellipse((cx + 0.10*scale, cy - 0.02*scale, cx + 0.46*scale, cy + 0.30*scale), fill=fill)
        d.rounded_rectangle((cx - 0.34*scale, cy + 0.08*scale, cx + 0.46*scale, cy + 0.30*scale),
                             radius=0.11*scale, fill=fill)

    @classmethod
    def _icon_canvas(cls, size, ss=4):
        from PIL import Image, ImageDraw
        s = size * ss
        im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        return im, ImageDraw.Draw(im), s, size

    @classmethod
    def _draw_icon(cls, condicion, size, accent):
        from PIL import Image
        accent = accent if len(accent) == 4 else accent + (255,)

        if condicion == "despejado":
            im, d, s, out = cls._icon_canvas(size)
            cx, cy, r = s / 2, s / 2, s * 0.22
            for i in range(8):
                ang = i * math.pi / 4
                x1, y1 = cx + math.cos(ang) * r * 1.35, cy + math.sin(ang) * r * 1.35
                x2, y2 = cx + math.cos(ang) * r * 2.05, cy + math.sin(ang) * r * 2.05
                w = s * 0.035
                d.line([(x1, y1), (x2, y2)], fill=accent, width=int(w))
                d.ellipse((x2 - w/2, y2 - w/2, x2 + w/2, y2 + w/2), fill=accent)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=accent)

        elif condicion == "parcial":
            im, d, s, out = cls._icon_canvas(size)
            sun_r = s * 0.16
            scx, scy = s * 0.34, s * 0.34
            for i in range(8):
                ang = i * math.pi / 4
                x1, y1 = scx + math.cos(ang) * sun_r * 1.3, scy + math.sin(ang) * sun_r * 1.3
                x2, y2 = scx + math.cos(ang) * sun_r * 1.85, scy + math.sin(ang) * sun_r * 1.85
                d.line([(x1, y1), (x2, y2)], fill=accent, width=int(s * 0.03))
            d.ellipse((scx - sun_r, scy - sun_r, scx + sun_r, scy + sun_r), fill=accent)
            cls._cloud_shape(d, s * 0.56, s * 0.58, s * 1.05, (235, 238, 242, 255))

        elif condicion == "lluvia":
            im, d, s, out = cls._icon_canvas(size)
            cls._cloud_shape(d, s * 0.5, s * 0.40, s * 0.95, (210, 218, 228, 255))
            for i, dx in enumerate((-0.14, 0.02, 0.18)):
                x = s * 0.5 + dx * s
                y0 = s * 0.66
                y1 = y0 + s * (0.16 if i != 1 else 0.22)
                d.line([(x, y0), (x - s*0.04, y1)], fill=accent, width=int(s * 0.028))

        elif condicion in ("tormenta", "alerta"):
            im, d, s, out = cls._icon_canvas(size)
            cloud_color = (200, 200, 215, 255) if condicion == "tormenta" else (235, 210, 210, 255)
            cls._cloud_shape(d, s * 0.5, s * 0.38, s * 0.95, cloud_color)
            pts = [(s*0.56, s*0.55), (s*0.44, s*0.72), (s*0.52, s*0.72), (s*0.42, s*0.92),
                   (s*0.62, s*0.68), (s*0.53, s*0.68)]
            d.polygon(pts, fill=accent)

        elif condicion == "niebla":
            im, d, s, out = cls._icon_canvas(size)
            for i, y in enumerate((0.38, 0.5, 0.62)):
                w = s * (0.62 if i != 1 else 0.78)
                x0 = (s - w) / 2
                d.rounded_rectangle((x0, s*y, x0 + w, s*y + s*0.055), radius=s*0.03, fill=(225, 228, 232, 255))

        else:  # nublado / fallback
            im, d, s, out = cls._icon_canvas(size)
            cls._cloud_shape(d, s * 0.5, s * 0.52, s, (225, 228, 232, 255))

        return im.resize((out, out), Image.LANCZOS)

    @staticmethod
    def _condicion_label(c: str) -> str:
        return {
            "despejado": "Despejado", "parcial": "Parcialmente nublado", "nublado": "Nublado",
            "lluvia": "Lluvia", "tormenta": "Tormenta", "niebla": "Niebla",
        }.get(c, c.capitalize())

    def _tracked_text(self, draw, xy, text, fnt, fill, tracking=0):
        x, y = xy
        for ch in text:
            draw.text((x, y), ch, font=fnt, fill=fill)
            x += draw.textlength(ch, font=fnt) + tracking

    def _render_profesional(self, clima, cielo_texto, icono, alertas, fecha):
        """
        Placa "profesional" — gradiente diagonal con viñeta, íconos vectoriales
        dibujados a mano (sin depender de emoji ni fuentes especiales, que en
        estilos previos se veían como cuadros vacíos en Pillow/DejaVuSans), y
        una banda inferior tipo "glass" translúcida con las 3 métricas clave.

        Nota de implementación: todo lo semi-transparente (glass bar, banner de
        alerta) se dibuja sobre una capa RGBA transparente aparte y se compone
        una sola vez al final con alpha_composite — ImageDraw no mezcla alpha
        contra lo ya pintado si se dibuja directo sobre el lienzo base.
        """
        import io
        from PIL import Image, ImageDraw

        W, H = 1200, 675
        alerta_txt = alertas[0]["titulo"] if alertas else None
        condicion = WMO_TO_ICON.get(clima["codigo_wmo"], "parcial")
        key = "alerta" if alerta_txt else condicion
        top, bottom, accent = self._PALETAS_PRO.get(key, self._PALETAS_PRO["parcial"])

        bg = self._diagonal_gradient(W, H, top, bottom)
        bg = self._add_vignette(bg, strength=55)
        base = bg.convert("RGBA")

        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        white, soft_white, muted = (255, 255, 255, 255), (255, 255, 255, 200), (255, 255, 255, 150)

        f_eyebrow    = self._font(24, bold=True)
        f_date       = self._font(24)
        f_temp       = self._font(200, bold=True)
        f_cond       = self._font(46)
        f_min        = self._font(30)
        f_stat_val   = self._font(34, bold=True)
        f_stat_lbl   = self._font(20, bold=True)
        f_alert_ttl  = self._font(26, bold=True)
        f_alert_body = self._font(22)

        margin = 64

        self._tracked_text(draw, (margin, 56), self.ciudad.upper(), f_eyebrow, soft_white, tracking=3)
        fw = draw.textlength(fecha, font=f_date)
        draw.text((W - margin - fw, 58), fecha, font=f_date, fill=muted)
        draw.line([(margin, 100), (W - margin, 100)], fill=(255, 255, 255, 40), width=1)

        icon_size = 300
        icon = self._draw_icon(condicion, icon_size, accent)
        icon_x, icon_y = margin - 10, 175
        overlay.alpha_composite(icon, (icon_x, icon_y))

        right_x = icon_x + icon_size + 40
        temp_txt = f"{round(clima['temp_max'])}°"
        draw.text((right_x, 130), temp_txt, font=f_temp, fill=white)
        draw.text((right_x + 4, 335), f"Mín. {round(clima['temp_min'])}°C", font=f_min, fill=muted)
        draw.text((right_x, 375), self._condicion_label(condicion), font=f_cond, fill=soft_white)

        band_y = H - margin - 110
        if alerta_txt:
            ay0 = band_y - 78
            draw.rounded_rectangle((margin, ay0, W - margin, band_y - 14), radius=16,
                                    fill=(0, 0, 0, 90), outline=(255, 255, 255, 60), width=1)
            draw.rectangle((margin, ay0, margin + 6, band_y - 14), fill=(255, 90, 90, 255))
            tri_cx, tri_cy, tri_r = margin + 44, ay0 + 26, 13
            draw.polygon([(tri_cx, tri_cy - tri_r), (tri_cx - tri_r, tri_cy + tri_r), (tri_cx + tri_r, tri_cy + tri_r)],
                         fill=(255, 200, 200, 255))
            draw.text((tri_cx - 2, tri_cy - 6), "!", font=self._font(18, bold=True), fill=(120, 20, 20, 255))
            draw.text((margin + 66, ay0 + 10), "ALERTA METEOROLÓGICA", font=f_alert_ttl, fill=(255, 200, 200, 255))
            draw.text((margin + 66, ay0 + 42), alerta_txt[:72], font=f_alert_body, fill=white)

        draw.rounded_rectangle((margin, band_y, W - margin, H - margin), radius=20,
                                fill=(255, 255, 255, 22), outline=(255, 255, 255, 45), width=1)
        stats = [
            ("RÁFAGAS", f"{round(clima['viento_rafagas'])} km/h"),
            ("PROB. LLUVIA", f"{round(clima['prob_lluvia'])}%"),
            ("ÍNDICE UV", str(clima['uv_index'])),
        ]
        col_w = (W - 2 * margin) / 3
        for i, (label, val) in enumerate(stats):
            cx = margin + col_w * i + col_w / 2
            lb, vb = draw.textlength(label, font=f_stat_lbl), draw.textlength(val, font=f_stat_val)
            draw.text((cx - lb / 2, band_y + 20), label, font=f_stat_lbl, fill=muted)
            draw.text((cx - vb / 2, band_y + 52), val, font=f_stat_val, fill=white)
            if i > 0:
                lx = margin + col_w * i
                draw.line([(lx, band_y + 18), (lx, H - margin - 18)], fill=(255, 255, 255, 40), width=1)

        final = Image.alpha_composite(base, overlay).convert("RGB")
        buf = io.BytesIO()
        final.save(buf, format="JPEG", quality=90)
        buf.seek(0)
        return buf

    def _build_html(self, clima, cielo_texto, icono, alertas, fecha, redaccion) -> str:
        redaccion = redaccion.replace("```html", "").replace("```", "").strip()
        return f"""<div style="font-family:'Georgia',serif;font-size:18px;line-height:1.8;max-width:860px;margin:auto;">
  <div style="background:#f0f8ff;border-left:5px solid #4facfe;padding:20px;border-radius:8px;margin-bottom:25px;">
    <strong>📍 {self.ciudad}</strong> — {fecha}<br>
    {icono} <strong>{cielo_texto}</strong> · Máx {clima['temp_max']}°C / Mín {clima['temp_min']}°C ·
    Ráfagas {clima['viento_rafagas']} km/h · Lluvia {clima['prob_lluvia']}% · UV {clima['uv_index']}
  </div>
  {redaccion}
  <div style="margin-top:30px;padding:15px;background:#f4f4f4;font-size:13px;color:#666;">
    ℹ️ Datos: <strong>Open-Meteo</strong> y <strong>SMN Argentina</strong>.
  </div>
</div>"""
