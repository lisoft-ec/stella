#!/bin/sh
# Ejecuta la batería de tests con Python 3.7 y las versiones exactas de
# requirements-board.txt (Flask 2.2, numpy 1.21...), igual que en la placa.
# tflite-runtime 2.11 (x86_64) sustituye al 2.5 de la placa para el detector en CPU.
# La imagen no trae git: los tests de OTA se omiten aquí.
#
#   ./tests/run_py37.sh            # tests rápidos
#   ./tests/run_py37.sh "slow or not slow"   # incluye el vídeo demo
set -eu
REPO=$(cd "$(dirname "$0")/.." && pwd)
exec docker run --rm -v "$REPO:/src:ro" -w /tmp -e PYTHONDONTWRITEBYTECODE=1 \
    python:3.7-slim-bullseye sh -c "
        pip install -q --disable-pip-version-check -r /src/requirements-board.txt pytest tflite-runtime==2.11.0 &&
        cp -r /src /tmp/stella && cd /tmp/stella &&
        python -m pytest -q -p no:cacheprovider -m '${1:-not slow}' ${2:-}
    "
