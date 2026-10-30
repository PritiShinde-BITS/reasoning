#!/usr/bin/env python3
"""Make problem-only JSONL and separate gold-label JSONL from raw ReWild JSON.

No LLM calls are made. The original raw data, including trajectories, are kept
unchanged. NEVER use labels_* files as input to a test-time reasoning model.

Usage: python prepare_rewild.py --raw data/raw --out data/processed
"""
import argparse
import json
from pathlib import Path
from inspect_rewild import extract_records

FILES = ("standalone_train.json", "hybrid_train.json",
         "standalone_test.json", "hybrid_test.json")


def write_jsonl(path, items):
    with path.open("w", encoding="utf-8") as out:
        for item in items:
            out.write(json.dumps(item, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    prepared = 0

    for filename in FILES:
        src = args.raw / filename
        if not src.exists():
            continue
        mode = "hybrid" if filename.startswith("hybrid") else "standalone"
        split = "test" if "_test" in filename else "train"
        with src.open("r", encoding="utf-8") as f:
            raw = extract_records(json.load(f), filename)

        problems, labels = [], []
        for i, rec in enumerate(raw):
            if not isinstance(rec, dict):
                raise TypeError(f"{filename}[{i}]: expected an object")
            prompt = rec.get("input") or rec.get("q")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"{filename}[{i}]: missing input/q; inspect raw schema")
            if "label" not in rec:
                raise ValueError(f"{filename}[{i}]: missing label; inspect raw schema")
            identifier = f"{mode}_{split}_{i:06d}"
            problems.append({
                "id": identifier,
                "prompt": prompt,
                "mode": mode,
                "source_dataset": rec.get("dataset"),
                "qtype": rec.get("qtype"),
            })
            labels.append({"id": identifier, "label": rec["label"]})

        stem = f"{mode}_{split}"
        write_jsonl(args.out / f"{stem}_problems.jsonl", problems)
        write_jsonl(args.out / f"{stem}_labels.jsonl", labels)
        print(f"Prepared {stem}: {len(problems):,} problem/label pairs")
        prepared += 1
    if not prepared:
        raise SystemExit(f"No ReWild files found in {args.raw}")
    print("Raw trajectories remain unchanged in the raw directory.")
    print("Use *_problems.jsonl for model input; *_labels.jsonl ONLY for offline evaluation.")


if __name__ == "__main__":
    main()
