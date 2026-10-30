#!/usr/bin/env python3
"""Run direct/program/multi-path reasoning on processed TRAIN problems only.

Does NOT read labels. Outputs inference trajectories for separate offline scoring.
"""
import argparse
import json
import os
from pathlib import Path
import time

from avrs.backend import OpenAIBackend, OllamaBackend, MockBackend
from avrs.strategies import generate_strategy

STRATEGIES = ("direct", "program", "multi_path")


def iter_jsonl(path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip(): yield json.loads(line)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["standalone", "hybrid"], required=True)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--strategies", default=",".join(STRATEGIES))
    p.add_argument("--backend", choices=["openai", "ollama"], default="openai")
    p.add_argument("--model", default=None, help="Model tag; default follows backend")
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    p.add_argument("--out-dir", type=Path, default=Path("runs"))
    p.add_argument("--mock", action="store_true", help="No API calls; smoke tests only")
    args = p.parse_args()
    if args.limit < 1 or args.start < 0: p.error("--limit must be positive and --start nonnegative")
    requested = [s.strip() for s in args.strategies.split(",") if s.strip()]
    if not requested or any(s not in STRATEGIES for s in requested):
        p.error(f"--strategies must be comma-separated from {STRATEGIES}")
    if len(set(requested)) != len(requested): p.error("Duplicate strategies not allowed")
    src = args.processed_dir / f"{args.mode}_train_problems.jsonl"
    if not src.is_file(): p.error(f"Missing {src}. Run prepare_rewild.py first")
    if args.mock:
        backend = MockBackend()
    elif args.backend == "ollama":
        backend = OllamaBackend(
            model=args.model or "llama3.2:3b",
            base_url=args.ollama_url,
        )
    else:
        backend = OpenAIBackend(args.model or "gpt-4o-mini")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    names = {s: args.out_dir / f"{args.mode}_{s}.jsonl" for s in requested}
    # Resume by ID, per strategy. Append-only to preserve prior paid work.
    seen = {s: {r["problem_id"] for r in iter_jsonl(path)} if path.exists() else set()
            for s, path in names.items()}
    selected = list(iter_jsonl(src))[args.start:args.start + args.limit]
    print(f"Running {len(selected)} {args.mode} problems; model={backend.model}; mock={backend.is_mock}")
    for position, problem in enumerate(selected, 1):
        problem_id = problem["id"]
        question = problem["prompt"]
        for strategy in requested:
            if problem_id in seen[strategy]:
                print(f"[{position}/{len(selected)}] {problem_id} {strategy}: SKIP (resume)")
                continue
            started = time.monotonic()
            try:
                output = generate_strategy(backend, question, strategy)
                record = {"problem_id": problem_id, "mode": args.mode,
                          "strategy": strategy, "model": backend.model,
                          "mock": backend.is_mock, "answer": output["answer"],
                          "result": output, "status": "ok", "error": None}
            except Exception as exc:
                record = {"problem_id": problem_id, "mode": args.mode,
                          "strategy": strategy, "model": backend.model,
                          "mock": backend.is_mock, "answer": None,
                          "result": None, "status": "error", "error": str(exc)[:1200]}
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            with names[strategy].open("a", encoding="utf-8") as out:
                out.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            seen[strategy].add(problem_id)
            print(f"[{position}/{len(selected)}] {problem_id} {strategy}: {record['status']} "
                  f"answer={str(record['answer'])[:45]!r}")
    print("Done. These are model-generated trials, not training labels. Score separately.")


if __name__ == "__main__": main()
