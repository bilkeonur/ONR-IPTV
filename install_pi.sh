#!/usr/bin/env bash
# ONR IPTV - Raspberry Pi OS (Pi 4, 64-bit önerilir) kurulum betiği
#   Kullanım:  chmod +x install_pi.sh && ./install_pi.sh
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$APP_DIR/.venv"

echo ">> Sistem paketleri kuruluyor..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip fonts-noto-core
# Video motoru (libmpv). Bookworm/Trixie: libmpv2, eski sürümler: libmpv1
sudo apt-get install -y libmpv2 || sudo apt-get install -y libmpv1

# Qt: önce Pi için derlenmiş sistem paketleri denenir (pip'ten çok daha hızlı kurulur)
sudo apt-get install -y python3-pyqt6 || true
sudo apt-get install -y python3-pyqt6.qtsvg || true
sudo apt-get install -y python3-pyqt6.qtopengl || true

echo ">> Sanal ortam hazırlanıyor..."
python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install --upgrade "python-mpv>=1.0.4" "requests>=2.28" "pychromecast>=14"

if "$VENV/bin/python" -c "import PyQt6.QtOpenGLWidgets, PyQt6.QtSvg" 2>/dev/null; then
    echo ">> Qt: sistem PyQt6 kullanılacak"
elif "$VENV/bin/python" -c "import PySide6.QtOpenGLWidgets" 2>/dev/null; then
    echo ">> Qt: PySide6 kullanılacak"
else
    echo ">> PyQt6 bulunamadı, PySide6 pip ile kuruluyor (birkaç dakika sürebilir)..."
    "$VENV/bin/pip" install "PySide6>=6.5"
fi

"$VENV/bin/python" -c "import mpv" || { echo "HATA: libmpv yüklenemedi"; exit 1; }

cat > "$APP_DIR/run.sh" <<EOF
#!/usr/bin/env bash
cd "$APP_DIR"
exec "$VENV/bin/python" "$APP_DIR/main.py" "\$@"
EOF
chmod +x "$APP_DIR/run.sh"

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/onriptv.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ONR IPTV
Comment=ONR IPTV - Onur BiLKE - IPTV oynatıcı (Xtream / M3U / Stalker)
Exec=$APP_DIR/run.sh
Icon=$APP_DIR/assets/icon.png
Terminal=false
Categories=AudioVideo;Video;Player;TV;
EOF

read -r -p "Pi açılışında ONR IPTV otomatik başlasın mı? [e/H] " ans
if [[ "$ans" =~ ^[eEyY]$ ]]; then
    mkdir -p "$HOME/.config/autostart"
    cp "$HOME/.local/share/applications/onriptv.desktop" "$HOME/.config/autostart/"
    echo ">> Otomatik başlatma etkin."
fi

echo
echo "Kurulum tamamlandı. Başlatmak için:  $APP_DIR/run.sh"
echo "veya menüden: Ses ve Video > ONR IPTV"
