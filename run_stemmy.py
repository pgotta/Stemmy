"""
run_stemmy.py — start the local Stemmy server.

    python run_stemmy.py            # http://127.0.0.1:5002
    python run_stemmy.py --port 5005

GPU notes live in the README. The server itself starts instantly; models are
downloaded on first separation by audio-separator into ./models_cache.
"""

import argparse
from app import create_app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5002)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    app = create_app()
    print(f"  Stemmy → http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
