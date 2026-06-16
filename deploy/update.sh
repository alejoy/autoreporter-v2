#!/bin/bash
# Actualiza el código y reinicia el servicio sin tocar la DB ni el .env
set -e
APP_DIR="/opt/autoreporter"

echo "[autoreporter-update] Descargando cambios..."
cd "$APP_DIR"
git pull origin main

echo "[autoreporter-update] Actualizando dependencias..."
"${APP_DIR}/.venv/bin/pip" install -r requirements.txt -q

echo "[autoreporter-update] Reiniciando servicio..."
systemctl restart autoreporter

echo "[autoreporter-update] Listo. Estado:"
systemctl status autoreporter --no-pager -l
