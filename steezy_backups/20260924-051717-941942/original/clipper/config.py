"""Central configuration. Everything tunable lives here or in env vars."""
from __future__ import annotations
import os
import re
from dataclasses import dataclass
from pathlib import Path

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ[key])
    except (KeyError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ[key])
    except (KeyError, ValueError):
        return default


@dataclass
class Config:
    # --- Ollama (the "editor" that picks clips) ---
    ollama_url: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model: str = os.environ.get("CLIPPER_MODEL", "qwen3:8b")  # 8b = fast; qwen3:14b = better taste, more VRAM

    # --- Whisper (the "listener") ---
    # base.en = fast, small.en = better, medium.en / large-v3 = best (needs more VRAM).
    whisper_model: str = os.environ.get("WHISPER_MODEL", "medium")
    whisper_compute: str = os.environ.get("WHISPER_COMPUTE", "int8_float16")
    whisper_device: str = os.environ.get("WHISPER_DEVICE", "auto")  # auto|cuda|cpu

    # --- Clip selection ---
    num_clips: int = _env_int("NUM_CLIPS", 10)
    min_clip_s: float = _env_float("MIN_CLIP_S", 30.0)
    max_clip_s: float = _env_float("MAX_CLIP_S", 120.0)

    # --- Auto B-roll (Pexels stock video) ---
    broll: bool = os.environ.get("BROLL", "0") == "1"
    pexels_key: str = os.environ.get("PEXELS_API_KEY", "")
    broll_max: int = _env_int("BROLL_MAX", 3)          # max cutaways per clip
    broll_dur: float = _env_float("BROLL_DUR", 2.5)    # seconds per cutaway
    broll_gap: float = _env_float("BROLL_GAP", 5.0)    # min seconds between cutaways

    # --- Silence trimming ---
    trim_silence: bool = os.environ.get("TRIM_SILENCE", "1") == "1"
    silence_max: float = _env_float("SILENCE_MAX", 1.2)
    silence_keep: float = _env_float("SILENCE_KEEP", 0.25)

    # --- Layout ---
    layout: str = os.environ.get("LAYOUT", "auto")
    split_ratio: float = _env_float("SPLIT_RATIO", 0.5)   # top (talking-head) fraction
    background_path: str = ""   # set per-job when layout=split; path to the gameplay/B-roll clip

    # --- Reframe / face tracking ---
    target_w: int = _env_int("TARGET_W", 1080)   # output width  (9:16)
    target_h: int = _env_int("TARGET_H", 1920)   # output height
    detect_every: int = _env_int("DETECT_EVERY", 6)   # run face detect every N frames
    smooth_alpha: float = _env_float("SMOOTH_ALPHA", 0.12)  # lower = smoother/laggier

    # --- Punch-in zoom (subtle motion on emphasis) ---
    punch_zoom: bool = os.environ.get("PUNCH_ZOOM", "1") == "1"
    zoom_amount: float = _env_float("ZOOM_AMOUNT", 0.08)   # max extra zoom at a punch (8%)
    zoom_gap: float = _env_float("ZOOM_GAP", 10.0)

    # --- Captions ---
    accent_hex: str = os.environ.get("ACCENT_HEX", "#F6CF69")  # active word color
    base_hex: str = os.environ.get("BASE_HEX", "#FFFFFF")      # inactive words
    words_per_caption: int = _env_int("WORDS_PER_CAPTION", 3)
    caption_gap_s: float = _env_float("CAPTION_GAP_S", 0.6)    # break line on pauses
    font_name: str = os.environ.get("FONT_NAME", "Arial")
    font_size: int = _env_int("FONT_SIZE", 120)
    caption_style: str = os.environ.get("CAPTION_STYLE", "editorial")

    # --- Encoding ---
    use_nvenc: bool = os.environ.get("USE_NVENC", "1") == "1"

    # --- Paths ---
    work_dir: str = os.environ.get("WORK_DIR", "work")
    out_dir: str = os.environ.get("OUT_DIR", "clips")

    # Pro Local: stable typography and a sequential 4 GB VRAM profile.
    language: str = os.environ.get("TRANSCRIPT_LANGUAGE", "id")
    processing_mode: str = "auto"
    job_id: str = ""
    caption_position: str = os.environ.get("CAPTION_POSITION", "auto")
    caption_scale: float = _env_float("CAPTION_SCALE", 1.0)
    audio_normalize: bool = os.environ.get("AUDIO_NORMALIZE", "1") == "1"
    ollama_num_gpu: int = _env_int("OLLAMA_NUM_GPU", 16)
    ollama_num_ctx: int = _env_int("OLLAMA_NUM_CTX", 4096)
    ollama_timeout: int = _env_int("OLLAMA_TIMEOUT", 1200)
    whisper_isolate: bool = os.environ.get("WHISPER_ISOLATE", "1") == "1"
    editorial_words: int = _env_int("EDITORIAL_WORDS", 6)
    editorial_phrase_s: float = _env_float("EDITORIAL_PHRASE_S", 2.6)
    fonts_dir: str = str(Path(__file__).parent / "fonts")
    # Studio: one resource-heavy stage at a time on a 4 GB GPU.
    adaptive_clips: bool = True
    topic_grace_s: float = 20.0
    output_fps: int = 30
    music_path: str = ""
    music_db: float = -24.0
    sfx_path: str = ""
    sfx_db: float = -25.0
    cold_open: bool = True
    title_card: bool = True
    accent_font: bool = True
    framing_x: float = -1.0  # -1 = detected; otherwise normalized horizontal focus
    analysis_window_s: float = 240.0
    analysis_overlap_s: float = 130.0
    selection_floor: int = 3
    preview_seconds: float = 0.0

    @property
    def video_codec(self) -> str:
        from .ffmpeg_util import nvenc_available
        return "h264_nvenc" if self.use_nvenc and nvenc_available() else "libx264"


ASPECTS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}
CAPTION_STYLES: tuple[str, ...] = ("editorial", "clean", "karaoke", "boxed", "bold")
LAYOUTS: tuple[str, ...] = ("auto", "fill", "fit", "stream", "split")
# length preset -> (min_clip_s, max_clip_s)
LENGTHS: dict[str, tuple[float, float]] = {
    "auto": (30.0, 120.0),
    "60to120": (60.0, 120.0),
    "under30": (8.0, 30.0),
    "30to60": (30.0, 60.0),
    "60to90": (60.0, 90.0),
}


def validate_overrides(form: dict) -> dict:
    """Whitelist + clamp UI form fields into Config overrides. Bad values are dropped."""
    out: dict = {}
    if form.get("aspect") in ASPECTS:
        out["target_w"], out["target_h"] = ASPECTS[form["aspect"]]
    if form.get("caption_style") in CAPTION_STYLES:
        out["caption_style"] = form["caption_style"]
    if form.get("layout") in LAYOUTS:
        out["layout"] = form["layout"]
    if form.get("processing_mode") in ("auto", "full"):
        out["processing_mode"] = form["processing_mode"]
    if form.get("caption_position") in ("auto", "left", "right", "bottom"):
        out["caption_position"] = form["caption_position"]
    if form.get("language") in ("id", "en", "auto"):
        out["language"] = form["language"]
    if form.get("length") in LENGTHS:
        out["min_clip_s"], out["max_clip_s"] = LENGTHS[form["length"]]
    if form.get("trim") is not None:
        out["trim_silence"] = form["trim"] == "1"
    if form.get("broll") is not None:
        out["broll"] = form["broll"] == "1"
    n = form.get("num_clips")
    if n is not None:
        try:
            out["num_clips"] = max(1, min(10, int(n)))
        except (TypeError, ValueError):
            pass
    for key in ("punch_zoom", "cold_open", "title_card", "accent_font", "adaptive_clips"):
        if key in form:
            out[key] = str(form[key]).lower() in ("1", "true")
    for key, lo, hi in (("music_db", -40, -10), ("sfx_db", -40, -12),
                        ("caption_scale", .7, 1.3), ("framing_x", -1, 1)):
        if key in form:
            try:
                value = float(form[key])
                if __import__('math').isfinite(value):
                    out[key] = max(lo, min(hi, value))
            except (TypeError, ValueError):
                pass
    if form.get("accent_hex") and _HEX.match(str(form["accent_hex"])):
        out["accent_hex"] = form["accent_hex"]
    return out


def validate_brand(form: dict) -> dict:
    """Whitelist the brand-kit fields into Config overrides (accent color, caption style, font)."""
    out: dict = {}
    a = form.get("accent_hex")
    if isinstance(a, str) and _HEX.match(a):
        out["accent_hex"] = a.upper()
    if form.get("caption_style") in CAPTION_STYLES:
        out["caption_style"] = form["caption_style"]
    f = form.get("font_name")
    if isinstance(f, str) and f.strip():
        out["font_name"] = f.strip()[:64]
    return out
