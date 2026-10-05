"""Final-file validation; failures stop publication of the result in the UI."""
import json
import subprocess
from pathlib import Path


from .caption_checks import inspect_caption_plan


def inspect(path, cfg, expected_duration):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    data = json.loads(r.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    duration = float(data["format"].get("duration", 0))
    issues = []
    if not video or (video["width"], video["height"]) != (cfg.target_w, cfg.target_h):
        issues.append("Resolusi output tidak sesuai pilihan.")
    if not audio:
        issues.append("Output tidak mempunyai audio.")
    if duration <= 0 or abs(duration - expected_duration) > max(.35, expected_duration * .015):
        issues.append("Durasi output berbeda dari timeline pemotongan.")
    for stream in (video, audio):
        if stream and 'duration' in stream and abs(float(stream['duration']) - expected_duration) > .20:
            issues.append('Durasi track ' + stream['codec_type'] + ' tidak sesuai rencana edit.')
    report = {"passed": not issues, "issues": issues, "duration": duration,
              "width": video.get("width") if video else 0,
              "height": video.get("height") if video else 0,
              "checks": ["streams", "dimensions", "duration"],
              "note": "Pemeriksaan teknis; kualitas isi dan akurasi transkrip perlu preview."}
    Path(path).with_suffix(".qc.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if issues:
        raise RuntimeError("Pemeriksaan hasil gagal: " + " ".join(issues))
    return report
