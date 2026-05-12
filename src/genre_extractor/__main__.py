"""CLI entry for the genre extractor.

Usage:
  python3 -m src.genre_extractor --to-preset <id> --sources a.txt,b.txt [--with-trial]
  python3 -m src.genre_extractor --fill-preset <id>
  python3 -m src.genre_extractor --audit-preset <id>
  python3 -m src.genre_extractor --extract-only <id>
  python3 -m src.genre_extractor --merge-only <id>
  python3 -m src.genre_extractor --draft-only <id>
  python3 -m src.genre_extractor --validate-only <id> [--with-trial]
"""
from __future__ import annotations

import argparse
import json
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Novelforge Genre Extractor")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--to-preset", metavar="ID")
    grp.add_argument("--fill-preset", metavar="ID")
    grp.add_argument("--audit-preset", metavar="ID")
    grp.add_argument("--extract-only", metavar="ID")
    grp.add_argument("--merge-only", metavar="ID")
    grp.add_argument("--draft-only", metavar="ID")
    grp.add_argument("--validate-only", metavar="ID")
    parser.add_argument("--sources", default="")
    parser.add_argument("--with-trial", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    from src.genre_extractor import to_preset as to_preset_mod
    from src.genre_extractor import pipeline

    if args.to_preset:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        if not sources:
            print("error: --to-preset requires --sources a.txt,b.txt", file=sys.stderr)
            return 2
        out = to_preset_mod.extract_to_preset(
            args.to_preset, sources=sources, with_trial=args.with_trial,
        )
    elif args.fill_preset:
        out = pipeline.fill_preset(args.fill_preset)
    elif args.audit_preset:
        out = pipeline.audit_preset(args.audit_preset)
    elif args.extract_only:
        out = pipeline.run_phase(args.extract_only, phase="extract")
    elif args.merge_only:
        out = pipeline.run_phase(args.merge_only, phase="merge")
    elif args.draft_only:
        out = pipeline.run_phase(args.draft_only, phase="draft")
    elif args.validate_only:
        out = pipeline.run_phase(
            args.validate_only, phase="validate", with_trial=args.with_trial,
        )
    else:
        parser.print_help()
        return 2

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
