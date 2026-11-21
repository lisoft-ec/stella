#!/bin/sh
# Run by stella-rollback.service when stella.service fails repeatedly.
# If an OTA update is pending confirmation (ota_prev exists), go back to the
# previous commit and start Stella again.
set -eu

REPO=${STELLA_REPO:?}
DATA=${STELLA_DATA:?}
VENV=${STELLA_VENV:?}
PREV="$DATA/ota_prev"

if [ ! -f "$PREV" ]; then
    echo "Stella ha fallado pero no hay ninguna actualización pendiente: no hay nada que revertir."
    exit 0
fi

COMMIT=$(cat "$PREV")
echo "Volviendo a la versión $COMMIT"
git -C "$REPO" reset --hard "$COMMIT"
"$VENV/bin/python" -m pip install -q -r "$REPO/requirements-board.txt" || true
rm -f "$PREV"
echo "$COMMIT" > "$DATA/ota_rolled_back"

sudo -n systemctl reset-failed stella.service
sudo -n systemctl start stella.service
