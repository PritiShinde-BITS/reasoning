#!/usr/bin/env python3
"""Download the original ReWild JSON files from the authors' Hugging Face dataset.

This downloads DATA only. It does not clone or execute the ReWild repository,
run any LLM, or create synthetic training examples.

Usage:
    python download_rewild.py
    python download_rewild.py --include-test
    python download_rewild.py --out data/raw --include-test
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

REPO_ID = "yuan-yang/ReWild"
TRAIN_FILES = ("standalone_train.json", "hybrid_train.json")
TEST_FILES = ("standalone_test.json", "hybrid_test.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--include-test", action="store_true",
        help="Also download the held-out test sets (keep these out of training).",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    # Pin one exact dataset revision so all files are from the same snapshot.
    revision = HfApi().dataset_info(REPO_ID).sha
    files = TRAIN_FILES + (TEST_FILES if args.include_test else ())
    manifest = {
        "repo_id": REPO_ID,
        "repo_type": "dataset",
        "revision": revision,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "license": "cc-by-nc-4.0 (per dataset card)",
        "files": {},
    }

    print(f"Dataset: {REPO_ID}")
    print(f"Pinned revision: {revision}")
    for filename in files:
        print(f"\nDownloading {filename} ...", flush=True)
        local_path = Path(
            hf_hub_download(
                repo_id=REPO_ID,
                repo_type="dataset",
                filename=filename,
                revision=revision,
                local_dir=str(args.out),
            )
        )
        if not local_path.is_file() or local_path.stat().st_size == 0:
            raise RuntimeError(f"Download missing or empty: {local_path}")
        manifest["files"][filename] = {
            "bytes": local_path.stat().st_size,
            "sha256": sha256_file(local_path),
            "split": "test" if "_test" in filename else "train",
        }
        print(f"Saved: {local_path} ({local_path.stat().st_size:,} bytes)")

    manifest_path = args.out / "download_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nDownload complete. Manifest: {manifest_path}")
    print("No ReWild code or model inference was run.")


if __name__ == "__main__":
    main()
