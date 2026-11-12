import queue
import threading
import time
import uuid
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import tags
from .engine import MODELS_DIR, _voice_file, default_model, engine, finalize, list_models, list_voices, to_mp3_bytes, to_wav_bytes

MAX_CHARS = 4000
MAX_FINISHED_JOBS = 20

app = FastAPI(title="Local Voice Clone TTS")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@dataclass
class Job:
    id: str
    text: str
    voice: str
    language: str
    seed: int
    model: str
    status: str = "queued"  # queued | running | done | error | cancelled
    done_chunks: int = 0
    total_chunks: int = 0
    current_text: str = ""
    error: str | None = None
    unknown_tags: list[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    duration_sec: float = 0.0
    wav: bytes | None = None
    mp3: bytes | None = None
    cancel: bool = False

    def public(self):
        elapsed = (self.finished or time.time()) - self.started if self.started else 0
        eta = None
        if self.status == "running" and self.done_chunks:
            eta = elapsed / self.done_chunks * (self.total_chunks - self.done_chunks)
        return {
            "id": self.id,
            "model": self.model,
            "status": self.status,
            "done_chunks": self.done_chunks,
            "total_chunks": self.total_chunks,
            "current_text": self.current_text,
            "error": self.error,
            "unknown_tags": self.unknown_tags,
            "elapsed_sec": round(elapsed, 1),
            "eta_sec": round(eta, 1) if eta is not None else None,
            "duration_sec": round(self.duration_sec, 1),
            "queue_position": _queue_position(self.id),
        }


jobs: dict[str, Job] = {}
job_queue: "queue.Queue[str]" = queue.Queue()


def _queue_position(job_id: str) -> int:
    pending = [j for j in jobs.values() if j.status == "queued"]
    pending.sort(key=lambda j: j.created)
    ids = [j.id for j in pending]
    return ids.index(job_id) + 1 if job_id in ids else 0


def _run_job(job: Job):
    engine.load(job.model)
    with engine.lock:
        engine._ensure_voice(job.voice)
        options = engine.adapter.parse_options(job.voice)
    parsed = tags.parse(job.text, **options)
    job.unknown_tags = parsed.unknown_tags
    job.total_chunks = len(parsed.chunks)
    if not parsed.chunks:
        raise ValueError("Tidak ada teks yang bisa dibacakan.")
    parts = []
    for i, chunk in enumerate(parsed.chunks):
        if job.cancel:
            job.status = "cancelled"
            return
        job.current_text = f"[{chunk.style_name}] {chunk.text}"
        parts.append(engine.synthesize_chunk(chunk, job.voice, job.language, job.seed + i))
        parts.append(engine.silence(chunk.pause_after_ms))
        job.done_chunks = i + 1
    audio = finalize(parts[:-1])
    job.duration_sec = len(audio) / engine.sr
    job.wav = to_wav_bytes(audio, engine.sr)
    job.mp3 = to_mp3_bytes(audio, engine.sr)
    job.status = "done"


def _load_safely(name: str | None):
    if name:
        try:
            engine.load(name)
        except Exception:
            pass  # error is exposed through /api/status


def _worker():
    _load_safely(default_model())
    while True:
        job = jobs.get(job_queue.get())
        if not job or job.cancel:
            if job:
                job.status = "cancelled"
            continue
        job.status, job.started = "running", time.time()
        try:
            _run_job(job)
        except Exception as e:
            job.status, job.error = "error", str(e)
        finally:
            job.finished = time.time()
            job.current_text = ""
            _prune()


def _prune():
    finished = sorted((j for j in jobs.values() if j.finished), key=lambda j: j.finished)
    for j in finished[:-MAX_FINISHED_JOBS]:
        jobs.pop(j.id, None)


@app.on_event("startup")
def _start_worker():
    threading.Thread(target=_worker, daemon=True).start()


class JobRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHARS)
    voice: str | None = None
    language: str = "id"
    model: str | None = None
    seed: int = 42


class ModelRequest(BaseModel):
    model: str


@app.get("/api/status")
def status():
    models = list_models()
    active = engine.model_name if engine.model_name in models else default_model()
    adapter = engine.adapter
    return {
        "model": engine.status,
        "error": engine.error,
        "device": engine.device,
        "active_model": active,
        "models": {
            k: {"label": v.get("label", k), "languages": v.get("languages", {}), "license": v.get("license")}
            for k, v in models.items()
        },
        "models_dir": str(MODELS_DIR),
        "supports_emotion": bool(adapter and adapter.supports_emotion),
        "voices": list_voices(),
        "voice_info": engine.voice_info,
        "styles": sorted(tags.STYLES),
        "pause_tags": sorted(tags.PAUSE_TAGS),
        "inline_tags": sorted(adapter.inline_tags) if adapter else [],
        "max_chars": MAX_CHARS,
    }


@app.get("/api/voices/{voice}/audio")
def get_voice_audio(voice: str):
    """Serve a reference recording for the local voice library preview."""
    try:
        path = _voice_file(voice)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    media_types = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac", ".ogg": "audio/ogg", ".m4a": "audio/mp4"}
    return Response(path.read_bytes(), media_type=media_types.get(path.suffix.lower(), "application/octet-stream"))


@app.post("/api/model")
def switch_model(req: ModelRequest):
    if req.model not in list_models():
        raise HTTPException(400, f"Model tidak ditemukan di {MODELS_DIR}")
    if any(j.status in ("queued", "running") for j in jobs.values()):
        raise HTTPException(409, "Tunggu proses generate selesai sebelum ganti model.")
    engine.status, engine.model_name = "loading", req.model
    threading.Thread(target=_load_safely, args=(req.model,), daemon=True).start()
    return {"ok": True}


@app.post("/api/jobs")
def create_job(req: JobRequest):
    voices = list_voices()
    voice = req.voice or (voices[0] if voices else None)
    if voice not in voices:
        raise HTTPException(400, f"Voice tidak ditemukan. Tersedia: {voices}")
    models = list_models()
    model = req.model or engine.model_name or default_model()
    if model not in models:
        raise HTTPException(400, f"Model tidak ditemukan. Tersedia: {list(models)}")
    languages = models[model].get("languages", {})
    if req.language not in languages:
        raise HTTPException(400, f"Bahasa '{req.language}' tidak didukung model ini. Tersedia: {list(languages)}")
    job = Job(id=uuid.uuid4().hex[:12], text=req.text, voice=voice, language=req.language, seed=req.seed, model=model)
    job.total_chunks = len(tags.parse(req.text).chunks)
    jobs[job.id] = job
    job_queue.put(job.id)
    return job.public()


def _get(job_id: str) -> Job:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job tidak ditemukan")
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return _get(job_id).public()


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str):
    job = _get(job_id)
    job.cancel = True
    if job.status == "queued":
        job.status = "cancelled"
    return job.public()


@app.get("/api/jobs/{job_id}/audio")
def get_audio(job_id: str, format: str = "wav", download: bool = False):
    job = _get(job_id)
    if job.status != "done":
        raise HTTPException(409, "Audio belum siap")
    data, media = (job.mp3, "audio/mpeg") if format == "mp3" else (job.wav, "audio/wav")
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="tts-{job.id}.{"mp3" if format == "mp3" else "wav"}"'
    return Response(data, media_type=media, headers=headers)
