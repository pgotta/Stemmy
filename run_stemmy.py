"""
run_stemmy.py — start the local Stemmy server.

    python run_stemmy.py            # http://127.0.0.1:5002
    python run_stemmy.py --port 5005

GPU notes live in the README. The server itself starts instantly; models are
downloaded on first separation by audio-separator into ./models_cache.
"""

import argparse
import sys

from app import create_app


def _configure_console_output() -> None:
    """Keep Windows legacy console encodings from crashing the server.

    Stemmy normally redirects stdout/stderr to log files. Some Windows Python
    installations still choose cp1252 for those streams, which can raise a
    UnicodeEncodeError before Flask starts. UTF-8 with replacement is safe for
    both redirected logs and visible consoles.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def main():
    _configure_console_output()

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5002)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    app = create_app()
    # Deliberately ASCII-only: this line may be written through a legacy
    # Windows console or redirected log stream during early startup.
    print(f"  Stemmy -> http://{args.host}:{args.port}", flush=True)
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
