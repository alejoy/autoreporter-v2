#!/bin/bash
# Backup diario de la base de datos — poner en crontab:
# 0 3 * * * /opt/autoreporter/deploy/backup.sh
set -e

source /opt/autoreporter/.env

BACKUP_DIR="/opt/autoreporter/backups"
DATE=$(date +%Y%m%d_%H%M%S)
FILE="${BACKUP_DIR}/autoreporter_${DATE}.sql.gz"

mkdir -p "$BACKUP_DIR"
pg_dump "$DATABASE_URL" | gzip > "$FILE"

# Mantener solo los últimos 7 backups
ls -t "${BACKUP_DIR}"/autoreporter_*.sql.gz | tail -n +8 | xargs -r rm

echo "Backup creado: ${FILE}"
