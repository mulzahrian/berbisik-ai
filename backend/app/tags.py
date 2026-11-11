"""Parse inline style tags like [intense] or [pause] and split text into synthesizable chunks."""
import re
from dataclasses import dataclass, field

MAX_CHUNK_CHARS = 260


@dataclass(frozen=True)
class Style:
    exaggeration: float = 0.5  # Chatterbox emotion intensity
    cfg_weight: float = 0.5  # Chatterbox pacing (lower = more dynamic)
    temperature: float = 0.8
    pause_ms: int = 280  # silence appended after each sentence chunk



STYLES: dict[str, Style] = {
    "neutral": Style(),
    "normal": Style(),
    "calm": Style(0.35, 0.55, 0.7, 380),
    "soft": Style(0.3, 0.55, 0.7, 380),
    "whisper": Style(0.25, 0.6, 0.65, 400),
    "sad": Style(0.4, 0.6, 0.7, 450),
    "serious": Style(0.5, 0.6, 0.7, 350),
    "mysterious": Style(0.55, 0.5, 0.75, 450),
    "curious": Style(0.6, 0.5, 0.85, 300),
    "happy": Style(0.7, 0.4, 0.85, 250),
    "excited": Style(0.85, 0.35, 0.85, 220),
    "energetic": Style(0.85, 0.35, 0.85, 200),
    "intense": Style(0.95, 0.3, 0.8, 260),
    "angry": Style(1.1, 0.3, 0.8, 220),
    "dramatic": Style(1.0, 0.3, 0.8, 500),
    "powerful": Style(1.15, 0.25, 0.8, 320),
    "epic": Style(1.15, 0.25, 0.8, 400),
}

ALIASES = {
    "default": "neutral",
    "whispering": "whisper",
    "whispers": "whisper",
    "excitedly": "excited",
    "seriously": "serious",
    "dramatically": "dramatic",
    "intensely": "intense",
    "curiously": "curious",
    "angrily": "angry",
    "sadly": "sad",
    "calmly": "calm",
    "softly": "soft",
}

# Tags that only insert silence (milliseconds).
PAUSE_TAGS = {"pause": 600, "short pause": 300, "long pause": 1200, "breath": 350, "beat": 500}

# Sound-effect tags that some models (OmniVoice) can voice directly, with friendly aliases.
INLINE_ALIASES = {"laugh": "laughter", "laughs": "laughter", "sighs": "sigh"}

TAG_RE = re.compile(r"\[([^\[\]]{1,40})\]")
SENTENCE_RE = re.compile(r"[^.!?…]+(?:[.!?…]+[\"')\]]*|$)")
PARAGRAPH_RE = re.compile(r"\n\s*\n")


@dataclass
class Chunk:
    text: str
    style: Style
    style_name: str
    pause_after_ms: int


@dataclass
class ParseResult:
    chunks: list[Chunk] = field(default_factory=list)
    unknown_tags: list[str] = field(default_factory=list)


def resolve_style(tag: str) -> tuple[str, Style] | None:
    key = ALIASES.get(tag, tag)
    if key in STYLES:
        return key, STYLES[key]
    return None


def _split_long(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    parts, current = [], ""
    for piece in sentence.split():
        candidate = f"{current} {piece}".strip()
        if len(candidate) > max_chars and current:
            parts.append(current)
            current = piece
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def _fix_shouting(text: str) -> str:
    """ALL-CAPS sentences get read as acronyms by TTS models; convert them to sentence case."""
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 12 or sum(c.isupper() for c in letters) / len(letters) < 0.8:
        return text
    lowered = text.lower()
    return re.sub(r"(^|[.!?…]\s+)(\w)", lambda m: m.group(1) + m.group(2).upper(), lowered)


def _sentences(text: str, max_chars: int) -> list[str]:
    out = []
    for m in SENTENCE_RE.finditer(text):
        s = _fix_shouting(m.group(0).strip())
        if re.search(r"\w", s):
            out.extend(_split_long(s, max_chars))
    return out


def parse(
    text: str,
    inline_tags: frozenset[str] = frozenset(),
    max_chars: int = MAX_CHUNK_CHARS,
    merge_chars: int = MAX_CHUNK_CHARS // 2,
    split_on_style: bool = True,
    sentence_pause_ms: int | None = None,
) -> ParseResult:
    """A style tag stays active until the next style tag. Tags in `inline_tags` stay in the
    text (the model voices them); other unknown tags are skipped. Consecutive sentences with
    the same style are merged while the result stays within `merge_chars`.
    With split_on_style=False, style tags don't break the text (models that follow the
    reference's own prosody sound more natural on long, continuous passages)."""
    result = ParseResult()
    style_name, style = "neutral", STYLES["neutral"]
    buffer: list[str] = []

    def flush():
        segment = "".join(buffer)
        buffer.clear()
        paras = PARAGRAPH_RE.split(segment)
        for pi, para in enumerate(paras):
            merged: list[str] = []
            for s in _sentences(" ".join(para.split()), max_chars):
                # Merge short consecutive sentences for smoother prosody (and fewer model calls).
                if merged and len(merged[-1]) + len(s) + 1 <= merge_chars:
                    merged[-1] = f"{merged[-1]} {s}"
                else:
                    merged.append(s)
            for s in merged:
                pause = style.pause_ms if sentence_pause_ms is None else sentence_pause_ms
                result.chunks.append(Chunk(s, style, style_name, pause))
            if pi < len(paras) - 1 and result.chunks:
                result.chunks[-1].pause_after_ms += 400

    pos = 0
    for m in TAG_RE.finditer(text):
        buffer.append(text[pos:m.start()])
        pos = m.end()
        tag = " ".join(m.group(1).lower().split())
        inline = INLINE_ALIASES.get(tag, tag)
        if inline in inline_tags:
            buffer.append(f"[{inline}] ")
            continue
        if tag in PAUSE_TAGS:
            flush()
            if result.chunks:
                result.chunks[-1].pause_after_ms += PAUSE_TAGS[tag]
            continue
        resolved = resolve_style(tag)
        if resolved:
            if split_on_style:
                flush()
            style_name, style = resolved
        elif tag not in result.unknown_tags:
            result.unknown_tags.append(tag)
    buffer.append(text[pos:])
    flush()
    return result
