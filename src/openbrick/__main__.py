import sys

from waitress import serve

from .app import create_app
from .config import load


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    config = load(path)
    print(f"openBrick listening on http://{config.host}:{config.port}")
    serve(create_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    main()
