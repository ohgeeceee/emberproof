#!/usr/bin/env python3
"""Entry point.

    python run.py                          # serve on 127.0.0.1:8787
    python run.py --data-dir ~/inventory
    python run.py --demo                   # seed a sample house
    python run.py --inspect backup.zip     # what is in a backup?
    python run.py --restore backup.zip     # put a backup back

Restoring into a directory that already holds a database is refused unless you
pass --overwrite. Losing an inventory to a careless restore would be worse than
losing it to the fire.
"""

from __future__ import annotations

import argparse
import os
import sys

from emberproof.app import create_app


def _print_counts(counts: dict) -> None:
    for key, value in counts.items():
        if key == "items_value_cents":
            print(f"  {'total value':<16} ${value / 100:,.2f}")
        else:
            print(f"  {key:<16} {value}")


def main() -> int:
    ap = argparse.ArgumentParser(description="EmberProof — local-first home inventory")
    ap.add_argument("--data-dir", default=os.environ.get("EMBERPROOF_DATA", "./data"),
                    help="where the database and photos live (default: ./data)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("EMBERPROOF_PORT", 8787)))
    ap.add_argument("--demo", action="store_true", help="seed a sample property and exit")
    ap.add_argument("--inspect", metavar="ARCHIVE",
                    help="show what a backup archive contains, then exit")
    ap.add_argument("--restore", metavar="ARCHIVE",
                    help="restore a backup archive into --data-dir, then exit")
    ap.add_argument("--overwrite", action="store_true",
                    help="with --restore: replace an existing database")
    args = ap.parse_args()

    if args.inspect:
        from emberproof import backup
        try:
            info = backup.inspect(args.inspect)
        except backup.RestoreError as exc:
            print(f"Not a usable backup: {exc}", file=sys.stderr)
            return 2
        manifest = info["manifest"]
        print(f"Archive:   {args.inspect}")
        print(f"Files:     {info['members']}")
        print(f"Database:  {info['db_bytes']:,} bytes")
        if manifest:
            prop = manifest.get("property") or {}
            print(f"Property:  {prop.get('name', '?')}")
            print(f"Generated: {manifest.get('generated_at', '?')}")
        print("Contents:")
        _print_counts(info["counts"])
        return 0

    if args.restore:
        from emberproof import backup
        target = os.path.abspath(args.data_dir)
        try:
            result = backup.restore(args.restore, target, overwrite=args.overwrite)
        except backup.RestoreError as exc:
            print(f"Restore refused: {exc}", file=sys.stderr)
            return 2
        print(f"Restored into {result['data_dir']}")
        _print_counts(result["counts"])
        print(f"\nNow run:  python run.py --data-dir {args.data_dir}")
        return 0

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
    if args.host not in ("127.0.0.1", "localhost"):
        print("")
        print("  WARNING: bound to a non-loopback address with no authentication.")
        print("  Anyone who can reach this port can read and delete your inventory.")
        print("  Put it behind a reverse proxy with auth, or use a private network.")
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())