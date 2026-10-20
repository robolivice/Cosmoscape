"""
Cosmoscape-web - the browser build.

The whole backend lives in the shared `Cosmoscape-FS/` package at the repository
root, so this file only starts the server.

    python main.py                 # http://127.0.0.1:8000
    python main.py --port 8001
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FS_DIR = os.path.join(ROOT, "Cosmoscape-FS")
if not getattr(sys, "frozen", False) and FS_DIR not in sys.path:
    sys.path.insert(0, FS_DIR)

from cosmoscape_fs.app import create_app  # noqa: E402

app = create_app(desktop=False)


def main():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Cosmoscape web server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    reload_enabled = os.environ.get("COSMOSCAPE_RELOAD", "").strip().lower() in ("1", "true", "yes")
    if reload_enabled:
        uvicorn.run("main:app", host=args.host, port=args.port, reload=True,
                    reload_dirs=[FS_DIR, os.path.dirname(os.path.abspath(__file__))])
    else:
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
