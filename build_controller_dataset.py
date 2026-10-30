#!/usr/bin/env python3
"""Turn scored TRAIN experiments into strategy-policy supervision (no test data)."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random


def read_jsonl(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip(): yield json.loads(line)


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows: f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["standalone", "hybrid"], required=True)
    p.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    p.add_argument("--scored-dir", type=Path, default=Path("scored"))
    p.add_argument("--out-dir", type=Path, default=Path("data/controller"))
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--validation-fraction", type=float, default=0.2)
    args = p.parse_args()
    if not 0 <= args.validation_fraction < 1: p.error("Validation fraction must be in [0,1)")
    problems = {r["id"]: r for r in read_jsonl(
        args.processed_dir / f"{args.mode}_train_problems.jsonl")}
    trials = defaultdict(dict)
    for strategy in ("direct", "program", "multi_path"):
        path = args.scored_dir / f"{args.mode}_{strategy}.scored.jsonl"
        if not path.exists(): p.error(f"Missing {path}; score all 3 strategies first")
        for row in read_jsonl(path):
            if row.get("mock"):
                raise ValueError("Mock data cannot be used to train a controller")
            if row["problem_id"] in trials and strategy in trials[row["problem_id"]]:
                raise ValueError("Duplicate scored record")
            trials[row["problem_id"]][strategy] = row

    ready = []
    skipped_incomplete = skipped_no_success = skipped_unscorable = 0
    for pid, outcomes in trials.items():
        if set(outcomes) != {"direct", "program", "multi_path"}:
            skipped_incomplete += 1
            continue
        if pid not in problems: raise ValueError(f"No problem for {pid}")
        if any(not row["grade"]["scorable"] for row in outcomes.values()):
            skipped_unscorable += 1
            continue
        winners = [(strategy, row) for strategy, row in outcomes.items()
                   if row["grade"]["correct"] is True]
        if not winners:
            skipped_no_success += 1
            continue
        # Choose cheapest successful strategy if reliable token usage is available.
        # If usage missing: fixed deterministic strategy order rather than made-up costs.
        order = {"direct": 0, "program": 1, "multi_path": 2}
        best = min(winners, key=lambda pair: (
            pair[1]["tokens"] if isinstance(pair[1]["tokens"], int) and pair[1]["tokens"] > 0
            else float("inf"), order[pair[0]]))[0]
        meta = problems[pid]
        ready.append({
            "id": pid, "question": meta["prompt"], "mode": meta["mode"],
            "source_dataset": meta.get("source_dataset"), "qtype": meta.get("qtype"),
            "target_strategy": best,
            "outcomes": {
                s: {"correct": outcomes[s]["grade"]["correct"],
                    "tokens": outcomes[s]["tokens"],
                    "status": outcomes[s]["status"]}
                for s in ("direct", "program", "multi_path")
            },
        })

    random.Random(args.seed).shuffle(ready)
    n_val = round(len(ready) * args.validation_fraction)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out_dir / f"{args.mode}_controller_train.jsonl", ready[n_val:])
    write_jsonl(args.out_dir / f"{args.mode}_controller_val.jsonl", ready[:n_val])
    print(f"Prepared {len(ready)} strategy labels; {len(ready)-n_val} train, {n_val} val")
    print(f"Skipped incomplete={skipped_incomplete}, "
          f"trial errors/unscorable={skipped_unscorable}, "
          f"all strategies incorrect={skipped_no_success}")
    print("CAUTION: One trial per strategy yields noisy preferences; repeat runs for a robust policy.")
    print("A random ID split does not guarantee source-problem or template independence.")


if __name__ == "__main__": main()
