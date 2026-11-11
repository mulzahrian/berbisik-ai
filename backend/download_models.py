"""Download the supported models into backend/models/<name>/.

Usage:  .venv\\Scripts\\python.exe download_models.py [omnivoice] [chatterbox-id]
"""
import json
import shutil
import sys
from pathlib import Path

import truststore

truststore.inject_into_ssl()

from huggingface_hub import hf_hub_download, snapshot_download  # noqa: E402

MODELS_DIR = Path(__file__).resolve().parent / "models"


def write_config(folder: Path, config: dict):
    (folder / "model.json").write_text(json.dumps(config, indent=2), encoding="utf-8")


def omnivoice():
    dest = MODELS_DIR / "omnivoice"
    snapshot_download("k2-fsa/OmniVoice", local_dir=dest)
    snapshot_download(
        "openai/whisper-large-v3-turbo",
        local_dir=dest / "asr",
        allow_patterns=["*.json", "*.safetensors", "*.txt", "*.tiktoken"],
    )
    write_config(dest, {
        "type": "omnivoice",
        "label": "OmniVoice (Indonesia native, paling mirip) - non-komersial",
        "languages": {"id": "Bahasa Indonesia", "en": "English"},
        "license": "CC-BY-NC 4.0 (non-commercial)",
        "num_step": 32,
        "chunk_chars": 500,
        "ref_seconds": 16,
    })


def chatterbox_id():
    dest = MODELS_DIR / "chatterbox-id"
    snapshot_download(
        "ResembleAI/chatterbox",
        local_dir=dest,
        allow_patterns=["ve.safetensors", "s3gen.safetensors", "tokenizer.json", "conds.pt"],
    )
    t3 = hf_hub_download("grandhigh/Chatterbox-TTS-Indonesian", "t3_cfg.safetensors", local_dir=dest / "_dl")
    shutil.move(t3, dest / "t3_cfg.safetensors")
    shutil.rmtree(dest / "_dl", ignore_errors=True)
    write_config(dest, {
        "type": "chatterbox",
        "label": "Chatterbox Indonesian (tag emosi penuh) - boleh komersial",
        "languages": {"id": "Bahasa Indonesia"},
        "license": "Apache 2.0",
    })


TARGETS = {"omnivoice": omnivoice, "chatterbox-id": chatterbox_id}

if __name__ == "__main__":
    for name in sys.argv[1:] or TARGETS:
        print(f"== Downloading {name} ...", flush=True)
        TARGETS[name]()
        shutil.rmtree(MODELS_DIR / name / ".cache", ignore_errors=True)
        print(f"== {name} done", flush=True)
