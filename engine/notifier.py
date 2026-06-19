"""
Notificación de fallos por Telegram — avisa solo cuando algo salió mal,
para no generar ruido en cada corrida exitosa.

Activación: definir TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID como variables
de entorno. Si no están seteadas, no hace nada (silencioso).

Cómo conseguirlas:
1. Hablale a @BotFather en Telegram, /newbot → te da el TOKEN.
2. Mandale un mensaje a tu bot nuevo, después abrí:
   https://api.telegram.org/bot<TOKEN>/getUpdates
   y copiá el "chat":{"id": ...} de la respuesta — ese es el CHAT_ID.
"""

import os
import requests
from utils.logger import get_logger

log = get_logger("Notifier")


def notify_if_needed(pipeline_name: str, totals: dict, dry_run: bool) -> None:
    if dry_run:
        return

    hubo_problema = totals.get("error", 0) > 0 or totals.get("published", 0) == 0
    if not hubo_problema:
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    texto = (
        f"⚠️ AutoReporter — {pipeline_name}\n"
        f"Publicadas: {totals.get('published', 0)}\n"
        f"Duplicadas: {totals.get('skipped', 0)}\n"
        f"Errores: {totals.get('error', 0)}"
    )
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": texto},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"No se pudo notificar por Telegram: {e}")
