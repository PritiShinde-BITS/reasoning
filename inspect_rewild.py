#!/usr/bin/env python3
"""Inspect original ReWild JSON schemas without executing any trajectories.

Usage: python inspect_rewild.py --dir data/raw
"""
import argparse
from collections import Counter
import json
from pathlib import Path

FILES = (
    "standalone_train.json",
    "hybrid_train.json",
    "standalone_test.json",
    "hybrid_test.json",
)


def extract_records(obj, filename):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("data", "records", "examples", "items"):
            if isinstance(obj.get(key), list):
                return obj[key]
    raise TypeError(
        f"Unexpected JSON shape in {filename}. Expected a list of examples "
        "or an object containing a 'data'/'records'/'examples'/'items' list. "
        f"Found: {type(obj).__name__}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--preview-chars", type=int, default=260)
    args = parser.parse_args()

    found = 0
    for filename in FILES:
        path = args.dir / filename
        if not path.exists():
            continue
        found += 1
        with path.open("r", encoding="utf-8") as f:
            records = extract_records(json.load(f), filename)

        print(f"\n{'=' * 68}\n{filename}: {len(records):,} examples")
        if not records:
            continue
        if not isinstance(records[0], dict):
            raise TypeError(f"First record in {filename} is not a JSON object")
        keys = Counter(key for rec in records if isinstance(rec, dict) for key in rec)
        print("Fields:", ", ".join(sorted(keys)))
        print("Top dataset values:", Counter(str(r.get("dataset", "?")) for r in records).most_common(10))
        if filename.startswith("hybrid"):
            print("Hybrid qtype values:", Counter(str(r.get("qtype", "?")) for r in records).most_common(10))
        r = records[0]
        preview = r.get("input") or r.get("q") or ""
        print("First input preview:", repr(str(preview)[:args.preview_chars]))
        for name in ("gt_traj", "hyb_syn_traj", "orig_data", "qls"):
            if name in r:
                print(f"{name}: {type(r[name]).__name__}")
        del records
    if not found:
        raise SystemExit(f"No expected ReWild JSON files found in {args.dir}")


if __name__ == "__main__":
    main()
