#!/usr/bin/env python3
"""Entry point. `python run.py` and you are running.

    python run.py --data-dir ~/Documents/emberproof --port 8787
    python run.py --demo          # create a sample house to look at
"""

from __future__ import annotations

import argparse
import os
import sys

from emberproof.app import create_app


def main() -> int:
    ap = argparse.ArgumentParser(description="EmberProof — local-first home inventory")
    ap.add_argument("--data-dir", default=os.environ.get("EMBERPROOF_DATA", "./data"),
                    help="where the database and photos live (default: ./data)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("EMBERPROOF_PORT", 8787)))
    ap.add_argument("--demo", action="store_true", help="seed a sample property and exit")
    args = ap.parse_args()

    if args.demo:
        from emberproof.demo import seed
        path = seed(os.path.abspath(args.data_dir))
        print(f"Seeded demo data in {path}")
        print(f"Now run:  python run.py --data-dir {args.data_dir}")
        return 0

    app = create_app(args.data_dir)
    shown = "127.0.0.1" if args.host in ("127.0.0.1", "localhost") else args.host
    print(f"EmberProof running at http://{shown}:{args.port}")
    print(f"Data directory: {os.path.abspath(args.data_dir)}")
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())