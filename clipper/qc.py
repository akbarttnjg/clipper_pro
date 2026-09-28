"""Final-file validation; failures stop publication of the result in the UI."""
import json
import subprocess
from pathlib import Path


def inspect_caption_plan(plan, cfg):
    """Check settled positions and line edges against the requested placement."""
    issues = []
    if plan.get('title'):
        issues.append('Judul pembuka seharusnya tidak dirender.')
    for phrase in plan.get('phrases', []):
        if cfg.caption_position != 'auto' and phrase['position'] != cfg.caption_position:
            issues.append('Posisi subtitle berbeda dari pilihan manual.')
        align = cfg.caption_align
        if align == 'auto':
            align = phrase['position'] if phrase['position'] in ('left', 'right') else 'center'
        if phrase.get('alignment') != align:
            issues.append('Perataan subtitle berbeda dari pengaturan.')
        x, y, width, height = phrase['panel']
        lines = {}
        for word in phrase['words']:
            lines.setdefault(word['baseline'], []).append(word)
            if not (0 <= word['x']-word['width']/2 < word['x']+word['width']/2 <= cfg.target_w):
                issues.append('Subtitle keluar dari lebar gambar.')
        for row in lines.values():
            left = min(w['x']-w['width']/2 for w in row)
            right = max(w['x']+w['width']/2 for w in row)
            observed = left if align == 'left' else right if align == 'right' else (left+right)/2
            expected = x if align == 'left' else x+width if align == 'right' else x+width/2
            if abs(observed-expected) > 1:
                issues.append('Tepi baris subtitle belum sejajar.')
    if issues:
        raise ValueError('Pemeriksaan posisi subtitle gagal: ' + ' '.join(dict.fromkeys(issues)))
    return {'passed': True, 'phrases': len(plan.get('phrases', [])),
            'requested_position': cfg.caption_position, 'requested_alignment': cfg.caption_align,
            'checks': ['manual_position', 'line_alignment', 'horizontal_bounds', 'no_title_overlay']}


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
