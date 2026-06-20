#!/bin/bash
# =============================================================
# AutoReporter v2 — Script de instalación completo
# Ubuntu 22.04 LTS — Hostinger VPS KVM 2
#
# Uso:
#   1. Conectarse al VPS: ssh root@TU_IP
#   2. Subir este script o copiarlo
#   3. chmod +x install.sh && ./install.sh
# =============================================================

set -euo pipefail

# ── Colores para output ────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Verificaciones previas ─────────────────────────────────────
[ "$EUID" -ne 0 ] && error "Ejecutar como root: sudo ./install.sh"
[ "$(lsb_release -si 2>/dev/null)" != "Ubuntu" ] && error "Este script requiere Ubuntu 22.04."

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     AutoReporter v2 — Instalación VPS        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Variables configurables ────────────────────────────────────
read -rp "Dominio (ej: autoreporter.tudominio.com): " DOMAIN
read -rp "Email para SSL (Let's Encrypt): " SSL_EMAIL
read -rp "Usuario GitHub (tu_usuario): " GH_USER
read -rp "Repo GitHub (autoreporter-v2): " GH_REPO
read -rsp "DB password para usuario 'autoreporter': " DB_PASS; echo ""
read -rsp "Contraseña del panel admin: " ADMIN_PASS; echo ""

# Generar claves automáticamente
ENCRYPTION_KEY=$(python3 -c "import os; print(os.urandom(32).hex())")
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
DB_NAME="autoreporter"
DB_USER="autoreporter"
APP_DIR="/opt/autoreporter"

echo ""
info "Configuración lista. Iniciando instalación..."
echo ""

# =============================================================
# 1. SISTEMA BASE
# =============================================================
info "1/8 — Actualizando sistema..."
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip software-properties-common \
    build-essential libpq-dev \
    python3 python3-pip python3-venv \
    nginx certbot python3-certbot-nginx \
    postgresql postgresql-contrib \
    ufw fail2ban
success "Sistema actualizado."

# =============================================================
# 2. POSTGRESQL
# =============================================================
info "2/8 — Configurando PostgreSQL..."
systemctl enable postgresql --now

sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" 2>/dev/null || \
    sudo -u postgres psql -c "ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || \
    warn "La base de datos ya existe."
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"

success "PostgreSQL listo. DB: ${DB_NAME}"

# =============================================================
# 3. CLONAR REPOSITORIO
# =============================================================
info "3/8 — Clonando repositorio..."
[ -d "$APP_DIR" ] && rm -rf "$APP_DIR"
git clone "https://github.com/${GH_USER}/${GH_REPO}.git" "$APP_DIR"
success "Repo clonado en ${APP_DIR}"

# =============================================================
# 4. PYTHON — VIRTUAL ENV + DEPENDENCIAS
# =============================================================
info "4/8 — Instalando dependencias Python..."
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip -q
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt" -q
success "Dependencias instaladas."

# =============================================================
# 5. VARIABLES DE ENTORNO
# =============================================================
info "5/8 — Configurando variables de entorno..."

# Generar hash bcrypt de la contraseña admin
ADMIN_HASH=$("${APP_DIR}/.venv/bin/python3" -c \
    "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('${ADMIN_PASS}'))")

cat > "${APP_DIR}/.env" << EOF
# Base de datos
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}

# Encriptación AES-256 (NO cambiar después de guardar datos)
ENCRYPTION_KEY=${ENCRYPTION_KEY}

# JWT
JWT_SECRET=${JWT_SECRET}

# Admin del panel
ADMIN_USER=admin
ADMIN_HASH=${ADMIN_HASH}
EOF

chmod 600 "${APP_DIR}/.env"
success ".env creado."

# =============================================================
# 6. SCHEMA DE BASE DE DATOS
# =============================================================
info "6/8 — Aplicando schema SQL..."
DATABASE_URL="postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}"
PGPASSWORD="${DB_PASS}" psql -U "${DB_USER}" -d "${DB_NAME}" -h localhost \
    -f "${APP_DIR}/db/schema.sql" -q
success "Schema aplicado."

# =============================================================
# 7. SYSTEMD — Servicio de la API
# =============================================================
info "7/8 — Configurando systemd..."

cat > /etc/systemd/system/autoreporter.service << EOF
[Unit]
Description=AutoReporter v2 API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
# --workers 1 es obligatorio: el scheduler de pipelines (APScheduler) arranca
# dentro del lifespan de la app y NO tiene lock entre procesos. Con más de un
# worker, cada uno dispara su propio cron al mismo tiempo y duplica publicaciones.
ExecStart=${APP_DIR}/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Permisos para www-data
chown -R www-data:www-data "${APP_DIR}"
chmod -R 755 "${APP_DIR}"
chmod 600 "${APP_DIR}/.env"

systemctl daemon-reload
systemctl enable autoreporter
systemctl start autoreporter
sleep 3

if systemctl is-active --quiet autoreporter; then
    success "Servicio autoreporter corriendo."
else
    error "El servicio no arrancó. Revisar: journalctl -u autoreporter -n 50"
fi

# =============================================================
# 8. NGINX + SSL
# =============================================================
info "8/8 — Configurando Nginx y SSL..."

cat > /etc/nginx/sites-available/autoreporter << EOF
server {
    listen 80;
    server_name ${DOMAIN};

    # Frontend (React build — se sirve desde aquí cuando lo tengas)
    root ${APP_DIR}/frontend/dist;
    index index.html;

    # API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        # SSE — deshabilitar buffering para logs en tiempo real
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }

    # Frontend SPA — redirigir todo al index.html
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

ln -sf /etc/nginx/sites-available/autoreporter /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# SSL con Certbot
certbot --nginx -d "${DOMAIN}" --email "${SSL_EMAIL}" \
    --agree-tos --non-interactive --redirect
systemctl reload nginx
success "Nginx + SSL configurados para ${DOMAIN}"

# =============================================================
# FIREWALL
# =============================================================
info "Configurando firewall UFW..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 'Nginx Full'
ufw --force enable
success "Firewall activo."

# =============================================================
# FAIL2BAN
# =============================================================
systemctl enable fail2ban --now
success "Fail2ban activo."

# =============================================================
# SCRIPT DE ACTUALIZACIÓN
# =============================================================
cat > /usr/local/bin/autoreporter-update << 'UPDATEEOF'
#!/bin/bash
set -e
APP_DIR="/opt/autoreporter"
echo "Actualizando AutoReporter v2..."
cd "$APP_DIR"
git pull origin main
"${APP_DIR}/.venv/bin/pip" install -r requirements.txt -q
systemctl restart autoreporter
echo "Actualización completada."
UPDATEEOF
chmod +x /usr/local/bin/autoreporter-update

# =============================================================
# RESUMEN FINAL
# =============================================================
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║            INSTALACIÓN COMPLETADA ✓                  ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║                                                      ║"
printf "║  Panel:   https://%-34s ║\n" "${DOMAIN}"
printf "║  API:     https://%-26s ║\n" "${DOMAIN}/api/docs"
echo "║  Usuario: admin                                      ║"
echo "║                                                      ║"
echo "║  Comandos útiles:                                    ║"
echo "║    Ver logs API:   journalctl -u autoreporter -f     ║"
echo "║    Reiniciar API:  systemctl restart autoreporter    ║"
echo "║    Actualizar:     autoreporter-update               ║"
echo "║                                                      ║"
echo "║  IMPORTANTE: guardá el archivo .env en un lugar     ║"
echo "║  seguro. Contiene las claves de encriptación.        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
warn "Guardá estas claves generadas automáticamente:"
echo "  ENCRYPTION_KEY=${ENCRYPTION_KEY}"
echo "  JWT_SECRET=${JWT_SECRET}"
echo ""
