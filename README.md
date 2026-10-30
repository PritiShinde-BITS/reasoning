# AVRS Step 2 — Generate strategy outcome data, without running ReWild

This project is the *independent* continuation of the previous ReWild data starter.
Only the official JSON **data** are used. No ReWild inference scripts, LoRA,
or Tiger model are needed.

## Scope

- `direct`: one LLM call returns a direct answer.
- `program`: one LLM call returns a *restricted expression program*; a local
  AST interpreter evaluates expressions without arbitrary `exec`/`eval`.
- `multi_path`: a planner generates 3 complementary plans in one call,
  the LLM attempts each, and an LLM aggregator selects a candidate.
- `collect.py` **never opens gold labels**. `score_results.py` evaluates saved
  predictions offline using the existing `*_train_labels.jsonl`.
- `build_controller_dataset.py` produces a first-pass training dataset for a
  controller. It excludes all-failed and incomplete examples.

**Important limitations**: This is a pilot, not a ReWild-equivalent executor or
MPPA reproduction. The expression DSL cannot fully encode arbitrary FOL, graph,
or commonsense tasks. It marks unsupported/invalid programs as failures, rather
than hallucinating executable results. Multi-path is prompting only (no LoRA
trained planner or aggregator). A runnable program can still be semantically
wrong. Exact scoring is a conservative proxy and does not reproduce all ReWild
metrics, e.g. program nontriviality or tactic recognition.

## macOS setup (Python 3.10–3.13 recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Set your key in the terminal (do not put it in source code or logs):

```bash
export OPENAI_API_KEY='YOUR_API_KEY'
```

### Reuse/download official ReWild TRAIN data

If already downloaded and prepared from Step 1, copy your existing `data/processed/`
folder into this project and skip downloading. Otherwise:

```bash
python download_rewild.py          # train only
python inspect_rewild.py
python prepare_rewild.py
```

Check `data/processed/standalone_train_problems.jsonl` and
`data/processed/hybrid_train_problems.jsonl` exist. The original raw ReWild
files have separate standalone and hybrid schemas; do not auto-concatenate them.

### Start small and limit API spend

```bash
python collect.py --mode standalone --limit 5 --model gpt-4o-mini
python score_results.py --mode standalone

python collect.py --mode hybrid --limit 5 --model gpt-4o-mini
python score_results.py --mode hybrid
```

For an isolated first check with **zero API calls**:

```bash
python collect.py --mode standalone --limit 2 --mock --out-dir mock_runs
python score_results.py --mode standalone --runs-dir mock_runs --out-dir mock_scored --allow-mock
```

Mock records are marked `mock:true` and **cannot be used for controller
training**. Results append to one JSONL per mode/strategy; re-running the same
command skips completed problem IDs. Use a **new `--out-dir`** when changing the
model, prompts, or experimental settings. Do not mix models in a run directory.
To retry errors, remove only their records or use a new directory.

To run strategies separately:

```bash
python collect.py --mode hybrid --limit 10 --strategies direct,program
python collect.py --mode hybrid --limit 10 --strategies multi_path
```

Outputs:

```text
runs/standalone_direct.jsonl
runs/standalone_program.jsonl
runs/standalone_multi_path.jsonl
runs/hybrid_*.jsonl
scored/*_*.scored.jsonl
scored/standalone_summary.json
scored/hybrid_summary.json
```

Generate **initial controller policy labels** after scoring all 3 strategies:

```bash
python build_controller_dataset.py --mode standalone
python build_controller_dataset.py --mode hybrid
```

These are *noisy provisional labels* from one trial per strategy, NOT a complete
fine-tuning dataset yet. Next iteration should repeat trials, estimate strategy
success probabilities, annotate program correctness, and learn fallback actions.
Ensure validation groups by underlying source problem/template before claiming
OOD generalization. Do not turn held-out test data into training records.

## Test the project

```bash
python -m unittest discover -s tests -v
```

## Important scoring note

The official hybrid dataset preview shows 1-based option labels, so the pilot
compares `Option 1` / `A` with reference `1`. For standalone the scorer permits
exact text or full-string numeric equivalence. Other formatting variants may
require a *dataset-specific verified* evaluation adapter. Manually audit ~20
predictions before treating these scores as paper-comparable.

## Security and cost

- There is NO `exec()` of model-generated Python. The program tool supports
  pure expressions only, with structural and value bounds. This limits coverage.
- OpenAI API calls are paid; `multi_path` makes **5 calls per example**
  (planner + 3 solutions + selector) versus **1** for each other strategy.
- Token counts use API usage fields when available. Failed API requests might
  still incur costs, and usage for failed retries is not collected.
- Results contain original problems and model outputs; follow the dataset's
  license and avoid publicly distributing data without appropriate permission.
