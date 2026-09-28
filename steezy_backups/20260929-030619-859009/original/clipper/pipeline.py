"""Analyze once, review decisions, then execute an editable plan per selected clip."""
import re
import shutil
import time
from pathlib import Path
from .config import Config
from . import ffmpeg_util, transcribe, score, story, editorial, editplan, composition, render, captions_pro, qc
from .storage import source_key, read_json, write_json


def analyze(media_path, cfg, on_progress=lambda p, m: None):
    ffmpeg_util.ensure_ffmpeg()
    ffmpeg_util.filter_file_args('preflight')
    started = time.monotonic()
    work = Path(cfg.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    key = source_key(media_path, cfg)
    cached = read_json(work / 'asr-cache.json', {})
    if key and cached.get('key') == key:
        transcript = cached['transcript']
        on_progress(30, 'Transkrip tersimpan dipakai kembali')
    else:
        if cfg.processing_mode == 'auto':
            editorial.release(cfg)
        on_progress(8, 'Transkripsi lokal; model dilepas sebelum tahap pemilihan topik')
        transcript = transcribe.transcribe(media_path, cfg)
        if key:
            write_json(work / 'asr-cache.json', {'key': key, 'transcript': transcript})
    if not transcript['words']:
        raise RuntimeError('Tidak ada percakapan yang terdeteksi.')
    asr_seconds = time.monotonic() - started
    selection_started = time.monotonic()
    if cfg.processing_mode == 'full':
        clips = [{'start': 0., 'end': transcript['duration'], 'title': Path(media_path).stem,
                  'reason': 'Video utuh dengan tipografi.', 'keywords': [], 'hook': '',
                  'selection_source': 'full', 'approved': False, 'revision': 0, 'warnings': []}]
    else:
        clips = story.select(transcript, cfg, on_progress)
    for c in clips:
        c['warnings'] = list(c.get('warnings', [])) + transcript.get('warnings', [])
    write_json(work / 'clip-decisions.json', clips)
    transcript['timings'] = {'transcription_seconds': round(asr_seconds, 2),
        'selection_seconds': round(time.monotonic() - selection_started, 2),
        'cache_reused': bool(key and cached.get('key') == key)}
    write_json(work / 'transcript.json', transcript)
    on_progress(100, f'{len(clips)} kandidat siap diperiksa')
    return transcript, clips


def clip_name(clip, i):
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', clip['title']).strip('-').lower()[:40] or 'clip'
    return f'{i+1:02d}-{slug}'


def render_clip(media_path, words, clip, name, cfg, on_progress=lambda p, m: None):
    started = time.monotonic()
    name = (cfg.job_id + '-' if cfg.job_id else '') + name + f"-r{clip.get('revision', 0)}-v231"
    work, out = Path(cfg.work_dir) / name, Path(cfg.out_dir)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    info = ffmpeg_util.probe(media_path)
    if not 0 <= clip['start'] < clip['end'] <= info['duration'] + .05:
        raise ValueError('Batas clip melebihi durasi sumber.')
    clip = {**clip, 'end': min(clip['end'], info['duration'])}
    if not info['has_audio']:
        raise ValueError('Sumber tidak mempunyai track audio.')
    ffmpeg_util.filter_file_args('preflight')
    on_progress(3, 'Menyusun potongan dan komposisi')
    plan = editplan.build(words, clip, cfg)
    composition.analyze(media_path, plan, cfg, info)
    if not plan['shots']:
        raise ValueError('Tidak ada frame yang dapat dirender. Periksa batas clip.')
    from .subtitle_edit import clean
    display, changes, notices = clean(plan['words'], cfg.caption_cleanup)
    plan['display_words'] = display
    plan['subtitle_cleanup'] = {'mode': cfg.caption_cleanup, 'changes': changes, 'review': notices}
    if notices:
        plan['warnings'].append('Ada angka atau waktu kata yang perlu didengarkan kembali; lihat laporan subtitle.')
    write_json(out / (name + '.subtitle-review.json'), plan['subtitle_cleanup'])
    ass = captions_pro.write_ass(display, work / 'captions.ass', cfg,
        keywords=clip.get('keywords', []),
        anchors=[{'time': (s['start'] + s['end']) / 2, 'start': s['start'], 'end': s['end'],
                  'position': s['position'], 'panel': s.get('caption_panel')} for s in plan['shots']])
    plan['captions'] = read_json(Path(ass).with_suffix('.caption-plan.json'))
    plan['caption_checks'] = qc.inspect_caption_plan(plan['captions'], cfg)
    plan['style'] = {'accent': cfg.accent_hex, 'base': cfg.base_hex, 'caption_style': cfg.caption_style,
                     'motion_intensity': cfg.motion_intensity, 'font_main': cfg.font_main,
                     'font_accent': cfg.font_accent, 'contrast': cfg.caption_backdrop, 'caption_position': cfg.caption_position,
                     'caption_align': cfg.caption_align, 'safe_placement': cfg.safe_placement}
    plan['subtitle_path'] = str(Path(ass).resolve())
    plan['render_config'] = {'zoom_amount': cfg.zoom_amount}
    plan_path = work / 'edit-plan.json'
    plan['status'] = 'preparing'
    write_json(plan_path, plan)
    shutil.copy2(ass, out / (name + '.ass'))
    from .projects import write_srt
    write_srt(plan, out / (name + '.srt'))
    on_progress(25, 'Menyiapkan suara dan musik')
    mix = render.audio_stems(media_path, plan, cfg, work)
    plan['status'] = 'rendering'
    write_json(plan_path, plan)
    try:
        final = render.video(media_path, plan, cfg, ass, out / (name + '.mp4'), mix,
            lambda p: on_progress(40 + round(p * 54), 'Encoding video'))
        on_progress(96, 'Memeriksa durasi, gambar, dan suara')
        checked = qc.inspect(final, cfg, plan['duration'])
        checked['caption_layout'] = plan['caption_checks']
        write_json(Path(final).with_suffix('.qc.json'), checked)
    except Exception as exc:
        plan.update(status='error', error=str(exc))
        write_json(plan_path, plan)
        raise
    plan['render_seconds'] = round(time.monotonic() - started, 2)
    plan['status'] = 'done'
    write_json(plan_path, plan)
    on_progress(100, 'Clip selesai')
    return {'file': Path(final).name, 'title': clip['title'], 'reason': clip.get('reason', ''),
        'start': clip['start'], 'end': clip['end'], 'length': round(checked['duration'], 2),
        'width': cfg.target_w, 'height': cfg.target_h, 'fps': cfg.output_fps, 'encoder': plan['encoder'],
        'revision': clip.get('revision', 0), 'plan_path': str(plan_path.resolve()),
        'render_version': '2.3.1',
        'render_seconds': plan['render_seconds'], 'selection_source': clip.get('selection_source'),
        'warnings': list(dict.fromkeys(clip.get('warnings', []) + plan['warnings'])), 'qc': checked}


def render_all(media_path, transcript, clips, cfg, on_progress=lambda p, m: None, on_clip=lambda c: None):
    results = []
    for i, clip in enumerate(clips):
        on_progress(round(100 * i / max(1, len(clips))), f'Render clip {i+1}/{len(clips)}')
        result = render_clip(media_path, transcript['words'], clip, clip_name(clip, i), cfg)
        results.append(result)
        on_clip(result)
    on_progress(100, f'{len(results)} clip siap')
    return results


def process(media_path, cfg, on_progress=lambda p, m: None):
    transcript, clips = analyze(media_path, cfg, on_progress)
    return render_all(media_path, transcript, clips, cfg, on_progress)
