"""Adapters that wrap each model family behind one interface.

A model lives in backend/models/<name>/ with a model.json whose "type" picks the adapter:
  - "chatterbox": Chatterbox (English/Indonesian fine-tune) or Chatterbox Multilingual
  - "omnivoice":  OmniVoice (600+ languages, incl. Indonesian)
"""
import gc
import json
from pathlib import Path

import librosa
import numpy as np
import torch

from .tags import Style


def median_pause_ms(y: np.ndarray, sr: int) -> int:
    """Median length of the natural pauses (>=150 ms) in a recording."""
    hop = sr // 100
    db = 20 * np.log10(librosa.feature.rms(y=y, frame_length=hop * 4, hop_length=hop)[0] + 1e-9)
    voiced = db > np.percentile(db, 95) - 30
    runs, count = [], 0
    for v in voiced:
        if not v:
            count += 1
        else:
            if count >= 15:
                runs.append(count * 10)
            count = 0
    return int(np.clip(np.median(runs), 200, 800)) if runs else 350


class BaseAdapter:
    sr = 24000
    ref_clip_seconds = 20
    inline_tags: frozenset[str] = frozenset()
    supports_emotion = False
    max_chars = 260  # hard limit per model call
    merge_chars = 130  # merge short same-style sentences up to this length
    split_on_style = True

    def __init__(self, model_dir: Path, config: dict, device: str, cache_dir: Path):
        self.dir = model_dir
        self.config = config
        self.device = device
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load(self): ...

    def prepare_voice(self, voice: str, source: Path, ref_clip: Path) -> dict:
        """Prepare (and cache) voice conditioning. Returns info shown in the UI."""
        raise NotImplementedError

    def parse_options(self, voice: str) -> dict:
        return dict(inline_tags=self.inline_tags, max_chars=self.max_chars, merge_chars=self.merge_chars,
                    split_on_style=self.split_on_style)

    def synthesize(self, text: str, style: Style, language: str, voice: str) -> np.ndarray:
        raise NotImplementedError


class ChatterboxAdapter(BaseAdapter):
    supports_emotion = True

    def load(self):
        if (self.dir / "t3_mtl23ls_v2.safetensors").exists():
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS as Cls
            self.multilingual = True
        else:
            from chatterbox.tts import ChatterboxTTS as Cls
            self.multilingual = False
        self.model = Cls.from_local(self.dir, self.device)
        self.sr = self.model.sr
        self._conds = {}

    def prepare_voice(self, voice, source, ref_clip):
        if voice not in self._conds:
            if self.multilingual:
                from chatterbox.mtl_tts import Conditionals
            else:
                from chatterbox.tts import Conditionals
            cache = self.cache_dir / f"{voice}.conds.pt"
            if cache.exists() and cache.stat().st_mtime >= ref_clip.stat().st_mtime:
                self._conds[voice] = Conditionals.load(cache).to(self.device)
            else:
                self.model.prepare_conditionals(str(ref_clip), exaggeration=0.5)
                self.model.conds.save(cache)
                self._conds[voice] = self.model.conds
        self.model.conds = self._conds[voice]
        return {}

    def synthesize(self, text, style, language, voice):
        kwargs = dict(exaggeration=style.exaggeration, cfg_weight=style.cfg_weight, temperature=style.temperature)
        if self.multilingual:
            kwargs["language_id"] = {"id": "ms"}.get(language, language)
        wav = self.model.generate(text, **kwargs)
        return wav.squeeze(0).numpy().astype(np.float32)


class OmniVoiceAdapter(BaseAdapter):
    """OmniVoice copies timbre *and* rhythm from the reference, so we:
    - use a reference cut exactly at sentence boundaries with its exact transcript,
    - feed long continuous passages (style tags don't split the text; the model handles
      sentence flow itself), and
    - join passages with the reference speaker's own median pause length."""

    PROMPT_VERSION = 2
    split_on_style = False
    inline_tags = frozenset({
        "laughter", "sigh", "confirmation-en", "question-en", "question-ah", "question-oh",
        "question-ei", "question-yi", "surprise-ah", "surprise-oh", "surprise-wa", "surprise-yo",
        "dissatisfaction-hnn",
    })

    def load(self):
        from omnivoice import OmniVoice

        asr = self.dir / "asr"
        self.model = OmniVoice.from_pretrained(
            str(self.dir),
            device_map=self.device,
            dtype=torch.float16 if self.device == "cuda" else torch.float32,
            asr_model_name=str(asr) if asr.exists() else None,
            asr_device=self.device,
        )
        self.sr = self.model.sampling_rate
        self.num_step = int(self.config.get("num_step", 32))
        self.ref_target_s = float(self.config.get("ref_seconds", 16))
        self.max_chars = self.merge_chars = int(self.config.get("chunk_chars", 500))
        self._prompts, self._info = {}, {}

    def _sentence_segments(self, y16: np.ndarray) -> list[dict]:
        if self.model._asr_pipe is None:
            self.model.load_asr_model()
        res = self.model._asr_pipe({"raw": y16, "sampling_rate": 16000}, return_timestamps=True)
        segs = []
        for c in res.get("chunks", []):
            start, end = c["timestamp"]
            text = c["text"].strip()
            # Whisper sometimes returns broken timestamps; keep only plausible ones.
            if text and start is not None and end is not None and end - start >= len(text) / 25:
                segs.append({"start": start, "end": end, "text": text})
        return segs

    def _pick_segments(self, segs: list[dict]) -> tuple[float, float, str] | None:
        best = None
        for i in range(len(segs)):
            for j in range(i, len(segs)):
                if j > i and segs[j]["start"] - segs[j - 1]["end"] > 2:
                    break
                dur = segs[j]["end"] - segs[i]["start"]
                if dur > 20:
                    break
                if dur >= 6:
                    score = abs(dur - self.ref_target_s)
                    if best is None or score < best[0]:
                        best = (score, i, j)
        if best is None:
            return None
        _, i, j = best
        return segs[i]["start"], segs[j]["end"], " ".join(s["text"] for s in segs[i:j + 1])

    def _build_prompt(self, source: Path, ref_clip: Path):
        window_s = 30  # one Whisper window -> reliable timestamps
        y, _ = librosa.load(str(source), sr=self.sr, mono=True, duration=window_s)
        y16 = librosa.resample(y, orig_sr=self.sr, target_sr=16000)
        picked = self._pick_segments(self._sentence_segments(y16))
        if picked:
            start, end, text = picked
            clip = y[max(0, int((start - 0.05) * self.sr)): int((end + 0.15) * self.sr)]
            prompt = self.model.create_voice_clone_prompt((torch.from_numpy(clip), self.sr), ref_text=text)
        else:
            prompt = self.model.create_voice_clone_prompt(str(ref_clip))
            start = end = None
        self.model._asr_pipe = None  # free Whisper memory
        gc.collect()
        info = {"version": self.PROMPT_VERSION, "ref_text": prompt.ref_text, "pause_ms": median_pause_ms(y, self.sr),
                "ref_start": start, "ref_end": end}
        return prompt, info

    def prepare_voice(self, voice, source, ref_clip):
        from omnivoice.models.omnivoice import VoiceClonePrompt

        cache = self.cache_dir / f"{voice}.prompt.pt"
        meta = self.cache_dir / f"{voice}.ref.json"
        if voice not in self._prompts:
            info = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
            fresh = cache.exists() and cache.stat().st_mtime >= source.stat().st_mtime
            if fresh and info.get("version") == self.PROMPT_VERSION:
                self._prompts[voice] = VoiceClonePrompt.load(str(cache))
            else:
                prompt, info = self._build_prompt(source, ref_clip)
                prompt.save(str(cache))
                meta.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
                self._prompts[voice] = prompt
            self._info[voice] = info
        return {"ref_text": self._info[voice].get("ref_text")}

    def parse_options(self, voice):
        opts = super().parse_options(voice)
        opts["sentence_pause_ms"] = self._info.get(voice, {}).get("pause_ms", 350)
        return opts

    def synthesize(self, text, style, language, voice):
        audio = self.model.generate(
            text=text,
            language=language,
            voice_clone_prompt=self._prompts[voice],
            num_step=self.num_step,
        )
        return np.asarray(audio[0], dtype=np.float32).reshape(-1)


ADAPTERS = {"chatterbox": ChatterboxAdapter, "omnivoice": OmniVoiceAdapter}
