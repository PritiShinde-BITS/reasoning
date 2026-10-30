# Run AVRS Step 2 locally with Ollama

These files are a patch for an EXISTING `avrs_step2/` directory. They do not include or overwrite the `data/`, `runs/` or `scored/` folders.

## Apply patch

From inside your existing `avrs_step2` folder on the Mac:

```bash
# Adjust this filename if your browser added a number
unzip -o ~/Downloads/avrs_ollama_patch.zip -d .
```

This updates `avrs/backend.py`, `collect.py`, `score_results.py`, and `build_controller_dataset.py`, plus adds `tests/test_ollama.py` and this guide.

## Start/check Ollama (one-time)

```bash
ollama list
ollama run llama3.2:3b 'Return only JSON: {"answer":"42"}'
curl http://localhost:11434/api/tags
```

If `curl` returns connection refused, launch the Ollama app OR start `ollama serve` in a separate terminal. You can stop an interactive `ollama run` session with `/bye`.

No OpenAI API key required. The local backend uses Python standard-library HTTP requests.

## Test integration

```bash
python -m unittest discover -s tests -v
python collect.py --help
```

## Safe test (ONE real example, direct only)

```bash
python collect.py --backend ollama --model llama3.2:3b \
  --mode standalone --limit 1 --strategies direct \
  --out-dir runs_ollama_llama32_3b
```

## Re-run failed first five examples into NEW output folders

```bash
python collect.py --backend ollama --model llama3.2:3b --mode standalone --limit 5 \
  --out-dir runs_ollama_llama32_3b
python collect.py --backend ollama --model llama3.2:3b --mode hybrid --limit 5 \
  --out-dir runs_ollama_llama32_3b
python score_results.py --mode standalone --runs-dir runs_ollama_llama32_3b --out-dir scored_ollama_llama32_3b
python score_results.py --mode hybrid --runs-dir runs_ollama_llama32_3b --out-dir scored_ollama_llama32_3b
python build_controller_dataset.py --mode standalone --scored-dir scored_ollama_llama32_3b --out-dir data/controller_ollama_llama32_3b
python build_controller_dataset.py --mode hybrid --scored-dir scored_ollama_llama32_3b --out-dir data/controller_ollama_llama32_3b
```

Check results:

```bash
cat scored_ollama_llama32_3b/standalone_summary.json
cat scored_ollama_llama32_3b/hybrid_summary.json
wc -l data/controller_ollama_llama32_3b/*.jsonl
head -n 1 data/controller_ollama_llama32_3b/standalone_controller_train.jsonl | python -m json.tool
```

Important: a five-question sample may still produce zero controller labels if all strategies answer incorrectly. That is a model/performance or scoring issue, not an Ollama connection issue, **provided the new run records show `status: "ok"`**. The initial program strategy is limited to a small expression DSL and may not solve logic-heavy hybrid examples; the `multi_path` strategy takes 5 model calls per example. Run 1-2 problems first because local generation can take substantial time.

To try a stronger model (slower), change model and OUT DIRECTORY:

```bash
python collect.py --backend ollama --model qwen2.5:14b --mode standalone --limit 1 --strategies direct --out-dir runs_ollama_qwen14b
```

Never mix different model results in one run directory. Do not delete original failed runs: they can be kept for audit. Unlike original scoring, `status: "error"` is now marked unscorable rather than an incorrect reasoning answer. The controller dataset builder also excludes such records.
