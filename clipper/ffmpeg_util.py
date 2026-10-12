"""Small wrappers around ffmpeg / ffprobe. No business logic here."""
from __future__ import annotations
import json
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def nvenc_diagnostic() -> dict:
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "color=s=1280x720:r=30:d=0.2", "-frames:v", "6", "-pix_fmt", "yuv420p", "-c:v",
                            "h264_nvenc", "-f", "null", "-"], capture_output=True, timeout=25)
        return {"available": r.returncode == 0, "ffmpeg": shutil.which("ffmpeg"),
                "detail": r.stderr.decode("utf-8", "replace")[-1600:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "ffmpeg": shutil.which("ffmpeg"), "detail": str(exc)}


def nvenc_available() -> bool:
    return nvenc_diagnostic()["available"]


def encoder_failure(message):
    """Only a hardware/encoder failure can benefit from switching codecs."""
    lower = message.lower()
    if any(s in lower for s in ('unrecognized option', 'option not found', 'no such filter',
                               'error parsing', 'error initializing complex filters')):
        return False
    return any(s in lower for s in ('nvenc', 'libcuda', 'cuda_error', 'cannot load nvcuda',
                                   'no capable devices', 'encoder error'))


def _encode_attempt(command, on_progress=None, duration=0):
    if on_progress is None:
        attempt = subprocess.run(command, capture_output=True)
        return attempt.returncode, attempt.stderr.decode('utf-8', 'replace')
    # stderr goes to disk: a long render must not fill a pipe and deadlock.
    with tempfile.TemporaryFile() as error:
        proc = subprocess.Popen([command[0], '-nostdin', '-progress', 'pipe:1', '-nostats',
                                 *command[1:]], stdout=subprocess.PIPE, stderr=error,
                                text=True, encoding='utf-8', errors='replace')
        try:
            for line in proc.stdout:
                key, _, value = line.strip().partition('=')
                if key == 'out_time_us' and duration > 0:
                    try:
                        on_progress(max(0., min(.99, int(value) / 1e6 / duration)))
                    except ValueError:
                        pass
            code = proc.wait()
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()
            proc.stdout.close()
        error.seek(0)
        return code, error.read().decode('utf-8', 'replace')


def encode(command, codec, log_path, on_progress=None, duration=0,*,allow_fallback=True):
    """Keep the diagnostic; never disguise a filter/argument error as GPU failure."""
    command = [str(x) for x in command]
    code, log = _encode_attempt(command, on_progress, duration)
    warnings = []
    if code and allow_fallback and codec == "h264_nvenc" and encoder_failure(log):
        warnings.append("NVENC gagal saat render; hasil ini menggunakan CPU. Lihat render.log.")
        pos = command.index("h264_nvenc")
        command[pos:pos + 1 + len(encoder_args(codec))] = ["libx264", *encoder_args("libx264")]
        code, retry_log = _encode_attempt(command, on_progress, duration)
        log += "\nCPU RETRY (encoder)\n" + retry_log
        codec = "libx264"
    Path(log_path).write_text(log, encoding="utf-8")
    if code:
        raise RuntimeError("Render FFmpeg gagal: " + log[-1600:])
    return codec, warnings


@lru_cache(maxsize=1)
def render_diagnostic():
    """Probe actual filter-file syntax + concat + libass before any long analysis.

    FFmpeg 9 removed filter_complex_script. Older installations may lack -/file
    syntax, so version strings alone are not sufficient for compatibility.
    """
    try:
        with tempfile.TemporaryDirectory(prefix='clipper-probe-') as tmp:
            folder = Path(tmp)
            ass = folder / 'probe.ass'
            ass.write_text('[Script Info]\nScriptType: v4.00+\nPlayResX: 320\nPlayResY: 180\n'
                '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
                'Style: Default,Arial,24,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1,1,2,10,10,10,1\n'
                '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
                'Dialogue: 0,0:00:00.00,0:00:00.30,Default,,0,0,0,,Clipper\n', encoding='utf-8')
            script = folder / 'probe.filter.txt'
            script.write_text('[0:v]split[a][b];[a]trim=end=0.1,setpts=PTS-STARTPTS[x];'
                '[b]trim=start=0.1:end=0.2,setpts=PTS-STARTPTS[y];'
                '[x][y]concat=n=2:v=1:a=0,ass=probe.ass[out]', encoding='utf-8')
            errors = []
            for option in ('-/filter_complex', '-filter_complex_script'):
                r = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-v', 'error',
                    '-f', 'lavfi', '-i', 'color=s=320x180:r=30:d=0.2',
                    option, str(script), '-map', '[out]', '-frames:v', '6',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-f', 'null', '-'],
                    cwd=tmp, capture_output=True, timeout=25)
                detail = r.stderr.decode('utf-8', 'replace')
                if r.returncode == 0:
                    return {'available': True, 'filter_option': option, 'detail': '',
                            'ffmpeg': shutil.which('ffmpeg')}
                errors.append(detail[-1200:])
                if 'Unrecognized option' not in detail and 'Option not found' not in detail:
                    break
            return {'available': False, 'filter_option': None, 'detail': '\n'.join(errors),
                    'ffmpeg': shutil.which('ffmpeg')}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'available': False, 'filter_option': None, 'detail': str(exc),
                'ffmpeg': shutil.which('ffmpeg')}


def filter_file_args(path):
    check = render_diagnostic()
    if not check['available']:
        raise RuntimeError('Pemeriksaan render gagal sebelum proses video: ' + check['detail'])
    return [check['filter_option'], str(path)]


def encoder_args(codec):
    return (["-preset", "p4", "-rc", "vbr", "-cq", "19", "-b:v", "0"]
            if codec == "h264_nvenc" else ["-preset", "fast", "-crf", "18"])


def ass_filter(path, cfg):
    def esc(p):
        return str(Path(p).resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "'\\\\\\''")
    return f"ass=filename='{esc(path)}':fontsdir='{esc(cfg.fonts_dir)}'"


def final_audio_args(cfg, source_path):
    if not cfg.audio_normalize:
        return []
    duration = probe(str(source_path))["duration"]
    # Short, completely silent inputs can produce NaN samples in loudnorm.
    # Analyze with a silent tail, then remove it and fix the output sample rate.
    filters = ("apad=pad_dur=3,loudnorm=I=-16:TP=-1.5:LRA=11,"
               f"aresample=48000,atrim=duration={duration:.6f}")
    return ["-af", filters]


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError(
            "ffmpeg/ffprobe not found on PATH. Install ffmpeg and reopen your shell.\n"
            "  Windows : winget install Gyan.FFmpeg\n"
            "  macOS   : brew install ffmpeg\n"
            "  Linux   : sudo apt install ffmpeg"
        )


def probe(path: str) -> dict:
    """Return {width, height, fps, duration} for the first video stream."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    vstream = next(s for s in data["streams"] if s["codec_type"] == "video")
    num, den = (vstream.get("r_frame_rate", "30/1").split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    return {
        "width": int(vstream["width"]),
        "height": int(vstream["height"]),
        "fps": fps if fps > 0 else 30.0,
        "duration": float(data["format"]["duration"]),
        "has_audio": any(s["codec_type"] == "audio" for s in data["streams"]),
    }


def cut(src: str, start: float, end: float, dst: str, codec: str = "libx264") -> str:
    """Cut [start, end] into its own file, re-encoding so the timeline is clean.

    Pass the GPU codec (h264_nvenc) to keep this off the CPU when a GPU is present.
    """
    preset = encoder_args(codec)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src,
         "-c:v", codec, *preset, "-c:a", "aac", "-movflags", "+faststart", dst],
        capture_output=True, check=True,
    )
    return dst


def cut_spans(src: str, start: float, end: float, rel_spans: list[tuple[float, float]],
              dst: str, codec: str = "libx264") -> str:
    """Cut [start, end] keeping only rel_spans (clip-relative), concatenated - used to drop
    silence. Fast input seek to the clip window first, so only the clip is decoded; trim +
    concat keep audio and video sample-accurate.
    """
    preset = encoder_args(codec)
    parts = []
    for i, (a, b) in enumerate(rel_spans):
        parts.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{i}]")
    n = len(rel_spans)
    parts.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", src, "-t", f"{end - start:.3f}",
         "-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]",
         "-c:v", codec, *preset, "-c:a", "aac", "-movflags", "+faststart", dst],
        capture_output=True, check=True,
    )
    return dst


def even(n: int) -> int:
    """h264 needs even dimensions."""
    n = int(round(n))
    return n if n % 2 == 0 else n + 1
