#!/usr/bin/env python3
"""Inspect AVRS training-time model outputs for one or more ReWild problems.

Examples:
 python inspect_avrs_reasoning.py --mode hybrid --scored-dir scored_llama31_8b --problem-id hybrid_train_000000
 python inspect_avrs_reasoning.py --mode hybrid --scored-dir scored_llama31_8b --count 5 --save-md reasoning_report.md

Reads training questions and scored runs only; no API calls, no changes to data.
"""
import argparse
import json
from pathlib import Path


def rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def format_item(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False)
    return str(value)


def problem_report(pid, prompts, scored):
    lines = [f"# {pid}", "", "## Original question", "", prompts.get(pid, "[question unavailable]"), ""]
    for strategy in ("direct", "program", "multi_path"):
        lines += [f"## Strategy: {strategy}", ""]
        r = scored.get(strategy, {}).get(pid)
        if r is None:
            lines += ["No trial found.", ""]
            continue
        grade = r.get("grade") or {}
        lines += [
            f"- Status: **{r.get('status')}**",
            f"- Final answer: **{r.get('answer')}**",
            f"- Scorable: **{grade.get('scorable')}**",
            f"- Correct: **{grade.get('correct')}** ({grade.get('method')})",
            f"- Tokens: {r.get('tokens')}",
            "",
        ]
        if r.get("error"):
            lines += ["**Error:**", "", "```text", str(r["error"]), "```", ""]
        result = r.get("result") or {}
        plans = result.get("plans") or []
        if plans:
            lines += ["### Jointly generated plans", ""]
            for plan in plans:
                lines += [f"- **{plan.get('id')} ({plan.get('tactic')})**: {plan.get('instructions')}"]
            lines.append("")
        candidates = result.get("candidates") or []
        for idx, c in enumerate(candidates, 1):
            label = c.get("id") or f"{idx}"
            lines += [f"### Candidate {label}", "", f"- Tactic: {c.get('tactic', strategy)}", f"- Answer: {c.get('answer')}", f"- Execution status: {c.get('execution_status')}", ""]
            if c.get("plan"):
                lines += ["**Plan followed:**", "", str(c["plan"]), ""]
            if c.get("explanation"):
                lines += ["**Model-generated explanation (not an internal reasoning trace):**", "", str(c["explanation"]), ""]
            if c.get("program"):
                lines += ["**Generated expression program:**", "", "```json", format_item(c["program"]), "```", ""]
            if c.get("execution_trace"):
                lines += ["**Actually executed expression trace:**", "", "```json", format_item(c["execution_trace"]), "```", ""]
            if c.get("execution_error"):
                lines += [f"**Execution error:** {c['execution_error']}", ""]
        selection = result.get("selection")
        if isinstance(selection, dict):
            lines += ["### Aggregator decision", "", f"- Selected candidate: **{selection.get('id')}**", f"- Reason: {selection.get('reason')}", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["standalone", "hybrid"], required=True)
    parser.add_argument("--scored-dir", type=Path, default=Path("scored"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--problem-id", help="Inspect one ID, e.g. hybrid_train_000000")
    parser.add_argument("--count", type=int, default=1, help="Number of problems if no ID specified")
    parser.add_argument("--save-md", type=Path, help="Optional path for a readable Markdown report")
    args = parser.parse_args()
    questions_file = args.processed_dir / f"{args.mode}_train_problems.jsonl"
    if not questions_file.exists():
        parser.error(f"Cannot find {questions_file}")
    prompts = {r["id"]: r["prompt"] for r in rows(questions_file)}
    scored = {}
    for strategy in ("direct", "program", "multi_path"):
        file = args.scored_dir / f"{args.mode}_{strategy}.scored.jsonl"
        scored[strategy] = {r["problem_id"]: r for r in rows(file)}
    present = set().union(*(set(v) for v in scored.values()))
    if args.problem_id:
        ids = [args.problem_id]
        if args.problem_id not in present:
            parser.error(f"No scored results for {args.problem_id}")
    else:
        ids = sorted(present)[: max(1, args.count)]
    if not ids:
        parser.error(f"No scored results in {args.scored_dir}")
    content = "\n\n---\n\n".join(problem_report(pid, prompts, scored) for pid in ids)
    if args.save_md:
        args.save_md.parent.mkdir(parents=True, exist_ok=True)
        args.save_md.write_text(content + "\n", encoding="utf-8")
        print(f"Saved {len(ids)} problem reports to {args.save_md}")
    else:
        print(content)


if __name__ == "__main__":
    main()
