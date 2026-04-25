#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/tvproxy"
SERVICE_USER="tvproxy"
SERVICE_FILE="/etc/systemd/system/tvproxy.service"
REPO_URL="https://github.com/jeanfraga95/canaistv"
PORT=5050
NO_SERVICE=false
LOG_FILE="/var/log/tvproxy-install.log"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        --no-service) NO_SERVICE=true; shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

echo "=== TVProxy CLEAN Installer ==="
echo "Port   : $PORT"
echo "Dir    : $INSTALL_DIR"
echo ""

exec > >(tee -a "$LOG_FILE") 2>&1

# ── CLEAN OLD INSTALL ─────────────────────────────────────────────────────────
echo "[0/7] Cleaning previous installation..."

# Stop and remove service
if systemctl list-units --full -all | grep -Fq "tvproxy.service"; then
    systemctl stop tvproxy || true
    systemctl disable tvproxy || true
fi

if [[ -f "$SERVICE_FILE" ]]; then
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    echo "  Old service removed."
fi

# Kill process using the port
if lsof -i :$PORT &>/dev/null; then
    echo "  Port $PORT is in use. Killing process..."
    lsof -t -i :$PORT | xargs -r kill -9
    sleep 1
fi

# Remove old install dir
if [[ -d "$INSTALL_DIR" ]]; then
    echo "  Removing old installation..."
    rm -rf "$INSTALL_DIR"
fi

# Remove CLI
if [[ -f /usr/local/bin/tvproxy ]]; then
    rm -f /usr/local/bin/tvproxy
fi

echo "  Clean done."

# ── System deps ───────────────────────────────────────────────────────────────
echo "[1/7] Installing dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl lsof

# ── User ──────────────────────────────────────────────────────────────────────
echo "[2/7] Creating user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false "$SERVICE_USER"
fi

# ── Clone repo ────────────────────────────────────────────────────────────────
echo "[3/7] Cloning repo..."
git clone "$REPO_URL" "$INSTALL_DIR"

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/tvproxy_cli.py"

# ── Python clean env ──────────────────────────────────────────────────────────
echo "[4/7] Creating clean Python environment..."

# remove possible old venv
rm -rf "$INSTALL_DIR/venv"

python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# ── CLI ───────────────────────────────────────────────────────────────────────
echo "[5/7] Installing CLI..."

cat > /usr/local/bin/tvproxy <<EOF
#!/bin/bash
exec $INSTALL_DIR/venv/bin/python $INSTALL_DIR/tvproxy_cli.py "\$@"
EOF

chmod +x /usr/local/bin/tvproxy

# ── Firewall ──────────────────────────────────────────────────────────────────
echo "[6/7] Opening port..."

if command -v ufw &>/dev/null; then
    ufw allow "$PORT/tcp" || true
fi

iptables -I INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true

# ── Service ───────────────────────────────────────────────────────────────────
if [[ "$NO_SERVICE" == "false" ]]; then
    echo "[7/7] Creating service..."

    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=TVProxy
After=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python app.py --host 0.0.0.0 --port $PORT
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable tvproxy
    systemctl restart tvproxy

    sleep 2

    if systemctl is-active --quiet tvproxy; then
        echo "  ✓ Running"
    else
        echo "  ✗ Failed"
        journalctl -u tvproxy -n 50
    fi
else
    echo "[7/7] Skipped service"
fi

IP=$(hostname -I | awk '{print $1}')

echo ""
echo "✓ INSTALAÇÃO LIMPA CONCLUÍDA"
echo "http://$IP:$PORT/dashboard"
