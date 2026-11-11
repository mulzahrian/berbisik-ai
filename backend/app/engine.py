"""Local voice-cloning engine. Models are read from backend/models/<name>/model.json (no API keys)."""
import gc
import io
import json
import os
import threading
from pathlib import Path

import truststore

truststore.inject_into_ssl()  # trust the corporate/Windows cert store if anything needs downloading

import lameenc
import librosa
import numpy as np
import soundfile as sf
import torch

from .adapters import ADAPTERS, BaseAdapter
from .tags import Chunk

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
REF_DIR = Path(os.getenv("TTS_REF_DIR", ROOT / "ref"))
MODELS_DIR = Path(os.getenv("TTS_MODELS_DIR", BACKEND / "models"))
CACHE_DIR = BACKEND / "cache"
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}
DEFAULT_MODEL_FILE = MODELS_DIR / "default.txt"


def list_voices() -> list[str]:
    return sorted(p.stem for p in REF_DIR.iterdir() if p.suffix.lower() in AUDIO_EXTS)


def list_models() -> dict[str, dict]:
    models = {}
    if MODELS_DIR.exists():
        for d in sorted(MODELS_DIR.iterdir()):
            cfg_file = d / "model.json"
            if d.is_dir() and cfg_file.exists():
                cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                if cfg.get("type") in ADAPTERS:
                    models[d.name] = cfg
    return models


def default_model() -> str | None:
    models = list_models()
    if DEFAULT_MODEL_FILE.exists():
        name = DEFAULT_MODEL_FILE.read_text(encoding="utf-8").strip()
        if name in models:
            return name
    return next(iter(models), None)


def _voice_file(voice: str) -> Path:
    for p in REF_DIR.iterdir():
        if p.stem == voice and p.suffix.lower() in AUDIO_EXTS:
            return p
    raise ValueError(f"Voice '{voice}' not found in {REF_DIR}")


def _load_audio(path: Path, sr: int) -> np.ndarray:
    try:
        wav, file_sr = sf.read(str(path), always_2d=True, dtype="float32")
        wav = wav.mean(axis=1)
        return librosa.resample(wav, orig_sr=file_sr, target_sr=sr) if file_sr != sr else wav
    except Exception:
        wav, _ = librosa.load(str(path), sr=sr, mono=True)
        return wav


def make_reference_clip(voice: str, sr: int, seconds: int) -> Path:
    """Pick the densest-speech window of the reference audio and save it as a clean wav."""
    src = _voice_file(voice)
    out = CACHE_DIR / f"{voice}.ref{seconds}s.wav"
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    wav = _load_audio(src, sr)
    hop = sr // 100
    rms = librosa.feature.rms(y=wav, frame_length=hop * 4, hop_length=hop)[0]
    voiced = rms > max(np.percentile(rms, 30), 1e-4)
    win = seconds * 100
    search = voiced[: min(len(voiced), 180 * 100)]  # look in the first 3 minutes
    start = 0
    if len(search) > win:
        start = int(np.argmax(np.convolve(search.astype(np.float32), np.ones(win), mode="valid")))
        while start > 0 and voiced[start]:  # back up to a pause so we don't cut a word
            start -= 1
    end = start * hop + seconds * sr
    end_frame = min(len(voiced) - 1, end // hop)
    while end_frame < len(voiced) - 1 and voiced[end_frame] and end_frame * hop < end + 3 * sr:
        end_frame += 1  # extend to the next pause so the last word is complete
    clip = wav[start * hop: end_frame * hop]
    clip, _ = librosa.effects.trim(clip, top_db=40)
    clip = clip / max(np.abs(clip).max(), 1e-6) * 0.9
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sf.write(out, clip, sr)
    return out


class Engine:
    def __init__(self):
        self.adapter: BaseAdapter | None = None
        self.model_name: str | None = None
        self.lock = threading.RLock()
        self.status = "not_loaded"
        self.error: str | None = None
        self.voice_info: dict[str, dict] = {}
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        torch.set_num_threads(max(1, os.cpu_count() or 1))

    @property
    def sr(self) -> int:
        return self.adapter.sr if self.adapter else 24000

    def load(self, name: str):
        with self.lock:
            if self.model_name == name and self.status == "ready":
                return
            models = list_models()
            if name not in models:
                raise ValueError(f"Model '{name}' tidak ada di {MODELS_DIR}")
            self.status, self.error, self.model_name = "loading", None, name
            self.adapter, self.voice_info = None, {}
            gc.collect()
            try:
                cfg = models[name]
                adapter = ADAPTERS[cfg["type"]](MODELS_DIR / name, cfg, self.device, CACHE_DIR / name)
                adapter.load()
                self.adapter = adapter
                for v in list_voices():
                    self._ensure_voice(v)
                DEFAULT_MODEL_FILE.write_text(name, encoding="utf-8")
                self.status = "ready"
            except Exception as e:
                self.adapter = None
                self.status, self.error = "error", repr(e)
                raise

    def _ensure_voice(self, voice: str):
        ref = make_reference_clip(voice, self.adapter.sr, self.adapter.ref_clip_seconds)
        self.voice_info[voice] = self.adapter.prepare_voice(voice, _voice_file(voice), ref)

    def synthesize_chunk(self, chunk: Chunk, voice: str, language: str, seed: int) -> np.ndarray:
        with self.lock:
            self._ensure_voice(voice)
            torch.manual_seed(seed)
            audio = self.adapter.synthesize(chunk.text, chunk.style, language, voice)
        audio, _ = librosa.effects.trim(audio, top_db=45)
        fade = min(len(audio) // 2, int(self.sr * 0.01))
        if fade:
            audio[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
        return audio

    def silence(self, ms: int) -> np.ndarray:
        return np.zeros(int(self.sr * ms / 1000), dtype=np.float32)


def finalize(parts: list[np.ndarray]) -> np.ndarray:
    audio = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
    peak = np.abs(audio).max()
    return audio / peak * 0.89 if peak > 0 else audio


def to_wav_bytes(audio: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def to_mp3_bytes(audio: np.ndarray, sr: int) -> bytes:
    enc = lameenc.Encoder()
    enc.set_bit_rate(192)
    enc.set_in_sample_rate(sr)
    enc.set_channels(1)
    enc.set_quality(2)
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
    return bytes(enc.encode(pcm) + enc.flush())


engine = Engine()
