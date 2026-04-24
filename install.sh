#!/usr/bin/env bash
# =============================================================================
# TVProxy Installer — Ubuntu/Debian (ARM64 & x86_64)
# Usage: sudo bash install.sh [--port 5000] [--no-service]
# =============================================================================
set -euo pipefail

INSTALL_DIR="/opt/tvproxy"
SERVICE_USER="tvproxy"
SERVICE_FILE="/etc/systemd/system/tvproxy.service"
REPO_URL="https://github.com/jeanfraga95/canaistv"
PORT=5050
NO_SERVICE=false
LOG_FILE="/var/log/tvproxy-install.log"

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)    PORT="$2"; shift 2 ;;
        --no-service) NO_SERVICE=true; shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

ARCH=$(uname -m)
echo "=== TVProxy Installer ==="
echo "Arch   : $ARCH"
echo "Port   : $PORT"
echo "Dir    : $INSTALL_DIR"
echo "Log    : $LOG_FILE"
echo ""

exec > >(tee -a "$LOG_FILE") 2>&1

# ── System deps ───────────────────────────────────────────────────────────────
echo "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl

# ── Create user ───────────────────────────────────────────────────────────────
echo "[2/7] Creating system user '$SERVICE_USER'..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false "$SERVICE_USER"
    echo "  User created."
else
    echo "  User already exists."
fi

# ── Clone / update repo ───────────────────────────────────────────────────────
echo "[3/7] Setting up application files..."
if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "  Updating existing repo..."
    cd "$INSTALL_DIR"
    sudo -u "$SERVICE_USER" git pull --ff-only
else
    echo "  Cloning from $REPO_URL..."
    git clone "$REPO_URL" "$INSTALL_DIR" || {
        echo "  Git clone failed. Copying local files instead..."
        mkdir -p "$INSTALL_DIR"
        cp -r "$(dirname "$0")/." "$INSTALL_DIR/"
    }
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/tvproxy_cli.py"

# ── Python venv ───────────────────────────────────────────────────────────────
echo "[4/7] Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

echo "  Dependencies installed."

# ── CLI symlink ───────────────────────────────────────────────────────────────
echo "[5/7] Installing 'tvproxy' CLI command..."
cat > /usr/local/bin/tvproxy <<EOF
#!/bin/bash
exec $INSTALL_DIR/venv/bin/python $INSTALL_DIR/tvproxy_cli.py "\$@"
EOF
chmod +x /usr/local/bin/tvproxy
echo "  CLI available as: tvproxy"

# ── Firewall (ufw) ────────────────────────────────────────────────────────────
echo "[6/7] Configuring firewall..."
if command -v ufw &>/dev/null; then
    ufw allow "$PORT/tcp" comment "TVProxy" || true
    echo "  ufw: port $PORT allowed"
fi

# Oracle Cloud iptables (if iptables-save shows INPUT chain)
if iptables -L INPUT -n 2>/dev/null | grep -q "Chain INPUT"; then
    iptables -I INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true
    echo "  iptables: port $PORT opened"
fi

# ── Systemd service ───────────────────────────────────────────────────────────
if [[ "$NO_SERVICE" == "false" ]]; then
    echo "[7/7] Installing systemd service..."

    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=TVProxy — Brazilian TV streaming proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python app.py --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable tvproxy
    systemctl restart tvproxy

    sleep 2
    if systemctl is-active --quiet tvproxy; then
        echo "  ✓ Service is running!"
    else
        echo "  ✗ Service failed to start. Check: journalctl -u tvproxy -n 50"
    fi
else
    echo "[7/7] Skipping systemd service (--no-service)"
    echo ""
    echo "  To run manually:"
    echo "    cd $INSTALL_DIR && venv/bin/python app.py --port $PORT"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
echo ""
echo "════════════════════════════════════════════"
echo "  ✓ TVProxy installed successfully!"
echo ""
echo "  Dashboard : http://$IP:$PORT/dashboard"
echo "  Playlist  : http://$IP:$PORT/playlist.m3u"
echo ""
echo "  CLI commands:"
echo "    tvproxy list"
echo "    tvproxy info espn"
echo "    tvproxy vlc sportv1"
echo "    tvproxy refresh globorj"
echo ""
echo "  Service:"
echo "    systemctl status tvproxy"
echo "    journalctl -u tvproxy -f"
echo "════════════════════════════════════════════"
