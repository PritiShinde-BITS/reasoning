#!/usr/bin/env python3
"""Offline scoring of TRAIN runs against separate ReWild reference labels."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from avrs.scoring import score


def load_jsonl(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip(): yield json.loads(line)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["standalone", "hybrid"], required=True)
    p.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--out-dir", type=Path, default=Path("scored"))
    p.add_argument("--allow-mock", action="store_true", help="Score mock demos for smoke tests only")
    args = p.parse_args()
    gold_path = args.processed_dir / f"{args.mode}_train_labels.jsonl"
    if not gold_path.is_file(): p.error(f"Missing {gold_path}")
    labels = {x["id"]: x["label"] for x in load_jsonl(gold_path)}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    found = False
    for name in ("direct", "program", "multi_path"):
        run_path = args.runs_dir / f"{args.mode}_{name}.jsonl"
        if not run_path.exists(): continue
        found = True
        seen = set()
        records = []
        for rec in load_jsonl(run_path):
            pid = rec["problem_id"]
            if pid in seen: raise ValueError(f"Duplicate {pid} in {run_path}")
            if pid not in labels: raise ValueError(f"Unknown ID {pid} in {run_path}")
            if rec.get("mock") and not args.allow_mock:
                raise ValueError(f"Found mock records in {run_path}; cannot treat as real experiments")
            seen.add(pid)
            # Errors such as API quota, connection failures or invalid model JSON
            # are not evidence that the reasoning strategy answered incorrectly.
            if rec.get("status") == "error":
                grade = {"correct": None, "scorable": False, "method": "trial_error"}
            else:
                grade = score(rec.get("answer"), labels[pid], args.mode)
            usage = (rec.get("result") or {}).get("usage", {})
            enriched = {**rec, "grade": grade, "tokens": usage.get("total_tokens")}
            records.append(enriched)
        target = args.out_dir / f"{args.mode}_{name}.scored.jsonl"
        with target.open("w", encoding="utf-8") as f:
            for rec in records: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        scorable = [r for r in records if r["grade"]["scorable"]]
        successes = sum(r["grade"]["correct"] is True for r in scorable)
        token_rows = [r["tokens"] for r in records if isinstance(r["tokens"], int) and not r.get("mock")]
        summary[name] = {
            "n_total": len(records),
            "n_scorable": len(scorable),
            "n_correct": successes,
            "accuracy": round(successes / len(scorable), 4) if scorable else None,
            "n_errors": sum(r["status"] != "ok" for r in records),
            "mean_total_tokens": round(sum(token_rows) / len(token_rows), 2) if token_rows else None,
            "is_mock": any(r.get("mock") for r in records),
        }
        print(f"{name}: {summary[name]}")
    if not found: p.error(f"No {args.mode} result files in {args.runs_dir}")
    out = args.out_dir / f"{args.mode}_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__": main()
