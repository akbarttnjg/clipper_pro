"""Final-file validation; failures stop publication of the result in the UI."""
import json
import subprocess
import math
from fractions import Fraction
from pathlib import Path


from .caption_checks import inspect_caption_plan


def inspect(path, cfg, expected_duration):
    try:return _inspect(path,cfg,expected_duration)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired,ValueError,KeyError,TypeError) as exc:
        from .dependency_cache import asset_id
        report={'passed':False,'inspection_state':'failed','status':'fail','validator_version':'media-qc-m0-1',
                'inspected_content_id':asset_id(path,fresh=True),'full_decode':'not_completed',
                'issues':['Pemeriksaan media tidak selesai: '+str(exc)[-1200:]],'checks':['probe_or_decode_failed']}
        Path(path).with_suffix('.qc.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        raise RuntimeError('Pemeriksaan hasil gagal: '+report['issues'][0]) from exc


def _inspect(path,cfg,expected_duration):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True,timeout=30)
    data = json.loads(r.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    duration = float(data["format"].get("duration", 0))
    issues = []
    if not math.isfinite(duration) or not math.isfinite(expected_duration) or expected_duration<=0:
        issues.append('Durasi media/timeline tidak valid.')
    if not video or (video["width"], video["height"]) != (cfg.target_w, cfg.target_h):
        issues.append("Resolusi output tidak sesuai pilihan.")
    if not audio:
        issues.append("Output tidak mempunyai audio.")
    rate=video.get('avg_frame_rate') or video.get('r_frame_rate') if video else None
    try:
        fps=Fraction(rate)
        if fps<=0 or abs(float(fps)-cfg.output_fps)>.001:issues.append('FPS output tidak sesuai rencana.')
    except (ValueError,TypeError,ZeroDivisionError):issues.append('FPS output belum dapat diverifikasi.')
    if video and audio:
        try:
            offset=abs(float(video.get('start_time',0))-float(audio.get('start_time',0)))
            if not math.isfinite(offset) or offset>max(.05,2/cfg.output_fps):issues.append('Awal track audio/video tidak sinkron.')
        except (ValueError,TypeError):issues.append('Offset audio/video tidak valid.')
    if duration <= 0 or abs(duration - expected_duration) > max(.35, expected_duration * .015):
        issues.append("Durasi output berbeda dari timeline pemotongan.")
    for stream in (video, audio):
        if stream and 'duration' in stream and abs(float(stream['duration']) - expected_duration) > .20:
            issues.append('Durasi track ' + stream['codec_type'] + ' tidak sesuai rencana edit.')
    decode=subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-err_detect','explode','-threads','1','-i',str(path),
                           '-map','0:v:0','-map','0:a:0','-f','null','-'],capture_output=True,text=True,
                          timeout=max(120,expected_duration*6) if math.isfinite(expected_duration) else 120)
    if decode.returncode or decode.stderr.strip():issues.append('Full decode video/audio gagal: '+decode.stderr[-1200:])
    from .dependency_cache import content_id
    report = {"passed": not issues,'inspection_state':'completed','status':'fail' if issues else 'pass',
              'validator_version':'media-qc-m0-1','inspected_content_id':content_id(path,fresh=True),
              'full_decode':'failed' if decode.returncode or decode.stderr.strip() else 'passed',
              'fps':rate,"issues": issues, "duration": duration,
              "width": video.get("width") if video else 0,
              "height": video.get("height") if video else 0,
              "checks": ["streams", "dimensions", "duration",'fps','av_start_offset','full_decode'],
              "note": "Pemeriksaan teknis; kualitas isi dan akurasi transkrip perlu preview."}
    Path(path).with_suffix(".qc.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if issues:
        raise RuntimeError("Pemeriksaan hasil gagal: " + " ".join(issues))
    return report
