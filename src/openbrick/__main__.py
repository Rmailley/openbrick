import logging
import sys
import threading
import time
from pathlib import Path

from waitress import serve

from .app import create_app
from .config import load, load_env

log = logging.getLogger("openbrick")


def _every_minute(app) -> None:
    while True:
        time.sleep(60)
        try:
            app.config["sweep"]()
        except Exception:
            log.exception("sweeping expired mutes failed")


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_env(Path(path).resolve().parent / ".env")  # next to config.yaml
    config = load(path)
    app = create_app(config)
    # A mute that runs out while nobody texts still gets its summary sent.
    threading.Thread(target=_every_minute, args=(app,), daemon=True).start()
    print(f"openBrick listening on http://{config.host}:{config.port}")
    serve(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
