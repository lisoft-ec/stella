#!/bin/bash
# Instala Stella en la Coral Dev Board (Mendel Linux).
#
# Uso, como usuario mendel y desde el clon del repositorio:
#   ./deploy/install.sh
#
# Variables opcionales: STELLA_VENV (por defecto /home/mendel/stella-venv)
#                       STELLA_DATA (por defecto /home/mendel/stella-data)
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
USER_NAME=$(id -un)
HOME_DIR=$(getent passwd "$USER_NAME" | cut -d: -f6)
VENV=${STELLA_VENV:-$HOME_DIR/stella-venv}
DATA=${STELLA_DATA:-$HOME_DIR/stella-data}
PY=/usr/bin/python3

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

say "Comprobando el sistema"
"$PY" -c 'import sys; assert sys.version_info[:2] == (3, 7), sys.version' \
    || { echo "Se esperaba Python 3.7 (Mendel 5)"; exit 1; }
"$PY" -c 'import pycoral, tflite_runtime' \
    || { echo "Faltan pycoral/tflite_runtime del sistema (paquetes python3-pycoral y python3-tflite-runtime)"; exit 1; }
sudo -n true || { echo "El usuario $USER_NAME necesita sudo sin contraseña"; exit 1; }

say "Entorno virtual en $VENV"
if [ ! -x "$VENV/bin/python" ]; then
    # Mendel no trae ensurepip: venv sin pip y se usa el pip de Debian, que
    # necesita sus wheels "debundled" dentro del propio entorno.
    "$PY" -m venv --without-pip --system-site-packages "$VENV"
    mkdir -p "$VENV/share"
    ln -sfn /usr/share/python-wheels "$VENV/share/python-wheels"
fi
if ! "$VENV/bin/python" -m pip --version | grep -q "pip 24.0"; then
    "$VENV/bin/python" -m pip install -q "pip==24.0"
fi
"$VENV/bin/python" -m pip install -q -r "$REPO/requirements-board.txt"
"$VENV/bin/python" -c 'import cv2, flask, paho.mqtt.client, yaml, periphery; print("dependencias OK, OpenCV", cv2.__version__)'

say "Datos y configuración en $DATA"
mkdir -p "$DATA"
chmod 700 "$DATA"
if [ ! -f "$DATA/config.yaml" ]; then
    install -m 600 "$REPO/config.example.yaml" "$DATA/config.yaml"
    echo "Creado $DATA/config.yaml a partir de config.example.yaml"
else
    echo "Se conserva el $DATA/config.yaml existente"
fi

say "Servicios systemd"
render() {
    sed -e "s#@USER@#$USER_NAME#g" -e "s#@REPO@#$REPO#g" -e "s#@VENV@#$VENV#g" -e "s#@DATA@#$DATA#g" "$1"
}
render "$REPO/deploy/stella.service" | sudo tee /etc/systemd/system/stella.service >/dev/null
render "$REPO/deploy/stella-rollback.service" | sudo tee /etc/systemd/system/stella-rollback.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable stella.service
sudo systemctl restart stella.service

sleep 5
systemctl --no-pager --lines=15 status stella.service || true
IP=$(hostname -I | awk '{print $1}')
say "Listo. Interfaz web: http://$IP:7777  (usuario admin, contraseña inicial stella)"
