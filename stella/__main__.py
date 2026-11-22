"""Entry point: ``python -m stella --config <path>``."""
import argparse
import logging
import os
import signal
import sys

from . import __version__
from .config import Config

DEFAULT_CONFIG = os.environ.get("STELLA_CONFIG", "data/config.yaml")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="stella", description="Contador de personas Stella")
    parser.add_argument("--config", default=DEFAULT_CONFIG,
                        help="ruta del config.yaml (por defecto: %(default)s)")
    parser.add_argument("--headless", action="store_true",
                        help="solo procesar vídeo e imprimir los cruces (sin web ni integraciones)")
    parser.add_argument("--factory-reset", action="store_true",
                        help="borrar wifi, datos y configuración (detén antes el servicio stella)")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--version", action="version", version="Stella %s" % __version__)
    return parser.parse_args(argv)


def run_headless(config):
    from .pipeline import Pipeline

    def on_event(direction, track):
        print("%s track=%d" % (direction.upper(), track.id), flush=True)

    pipeline = Pipeline(config, on_event=on_event).start()
    try:
        while not pipeline.finished:
            pipeline.join(0.5)
    except KeyboardInterrupt:
        pass
    pipeline.stop()


def run_factory_reset(config):
    import json

    from .factory import factory_reset
    from .net.wifi import Network
    from .storage import Storage

    storage = Storage(os.path.join(config.data_dir, "events.db"))
    summary = factory_reset(config, Network(config, storage), release=storage.close)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = Config(args.config).load()
    logging.getLogger("stella").info("Stella %s, config %s", __version__, config.path)

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    if args.factory_reset:
        run_factory_reset(config)
        return 0
    if args.headless:
        run_headless(config)
        return 0

    from .app import App

    App(config).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
