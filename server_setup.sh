#!/usr/bin/env bash
# =============================================================================
# server_setup.sh – IKT-Portalen – Oppsett på Ubuntu Server / Proxmox LXC
# =============================================================================
# Bruk:  chmod +x server_setup.sh && sudo ./server_setup.sh
#
# Forutsetninger:
#   - Ubuntu Server 22.04 LTS (eller nyere) / Debian 12
#   - Fast IP-adresse allerede satt via /etc/netplan eller Proxmox DHCP-reservasjon
# =============================================================================

set -euo pipefail

APP_DIR="/opt/ikt-portalen"
SERVICE_USER="iktportal"
SERVICE_NAME="ikt-portalen"
LISTEN_HOST="0.0.0.0"
LISTEN_PORT="5000"

echo "========================================"
echo "  IKT-Portalen – Serveroppsett"
echo "========================================"

# --------------------------------------------------
# 1. Oppdater pakkelister og installer avhengigheter
# --------------------------------------------------
echo "[1/7] Oppdaterer pakkelister..."
apt-get update -qq

echo "[2/7] Installerer Python, pip og git..."
apt-get install -y -q python3 python3-pip python3-venv git

# --------------------------------------------------
# 2. Lag applikasjonsmappe og bruker
# --------------------------------------------------
echo "[3/7] Oppretter systembruker '$SERVICE_USER' og mappe '$APP_DIR'..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi
mkdir -p "$APP_DIR"

# --------------------------------------------------
# 3. Kopier appfiler (kjør dette der repo er klonet)
# --------------------------------------------------
echo "[4/7] Kopierer appfiler til $APP_DIR..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR"/app.py \
       "$SCRIPT_DIR"/requirements.txt \
       "$SCRIPT_DIR"/templates \
       "$SCRIPT_DIR"/static \
       "$APP_DIR"/

chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"

if [ ! -f "$APP_DIR/.env" ]; then
    cat > "$APP_DIR/.env" <<EOF
SECRET_KEY=endre-denne-hemmelige-nokkelen
ADMIN_PASSWORD=endre-dette-passordet
EOF
    chmod 600 "$APP_DIR/.env"
    chown "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR/.env"
fi

# --------------------------------------------------
# 4. Virtualenv og Python-avhengigheter
# --------------------------------------------------
echo "[5/7] Setter opp Python virtuelt miljø og installerer pakker..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/pip" install --quiet gunicorn   # produksjons-WSGI-server

# --------------------------------------------------
# 5. Initialiser database
# --------------------------------------------------
echo "[6/7] Initialiserer SQLite-databasen..."
cd "$APP_DIR"
"$APP_DIR/venv/bin/python" -c "
import sys; sys.path.insert(0, '$APP_DIR')
from app import init_db; init_db()
print('  Database OK.')
"

# --------------------------------------------------
# 6. systemd-tjeneste
# --------------------------------------------------
echo "[7/7] Oppretter systemd-tjeneste '$SERVICE_NAME'..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=IKT-Portalen Flask-applikasjon
After=network.target

[Service]
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/venv/bin"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/gunicorn \
    --workers 2 \
    --bind ${LISTEN_HOST}:${LISTEN_PORT} \
    --access-logfile - \
    --error-logfile - \
    app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "========================================"
echo "  Ferdig!  Applikasjonen kjører nå på:"
echo "  http://<SERVER-IP>:${LISTEN_PORT}"
echo ""
echo "  Nyttige kommandoer:"
echo "    sudo systemctl status $SERVICE_NAME"
echo "    sudo journalctl -u $SERVICE_NAME -f"
echo "========================================"
