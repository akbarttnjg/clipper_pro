"""Analyze once, review decisions, then execute an editable plan per selected clip."""
import re
import shutil
import time
from dataclasses import replace
from pathlib import Path
from .config import Config
from . import ffmpeg_util, transcribe, score, story, editorial, editplan, composition, render, captions_pro, qc
from .storage import source_key, read_json, write_json
from . import intelligence
from . import library_paths, placement, transcript_correction

RENDER_VERSION = '4.0.10'


def analyze(media_path, cfg, on_progress=lambda p, m: None):
    ffmpeg_util.ensure_ffmpeg()
    ffmpeg_util.filter_file_args('preflight')
    started = time.monotonic()
    work = Path(cfg.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    key = source_key(media_path, cfg)
    preparation_seconds = time.monotonic() - started
    asr_started = time.monotonic()
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
    asr_seconds = time.monotonic() - asr_started
    evidence_started = time.monotonic()
    if cfg.source_content_id:
        from . import evidence
        report = evidence.scan(media_path, cfg, transcript['duration'], on_progress, input_fingerprint=key)
        transcript['ocr_suggestions'] = evidence.suggestions(transcript['words'], report)
    evidence_seconds = time.monotonic() - evidence_started
    correction_started = time.monotonic()
    transcript = transcript_correction.refine(transcript, cfg)
    write_json(work / 'transcript-corrections.json', transcript['correction_report'])
    correction_seconds = time.monotonic() - correction_started
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
        'preparation_seconds': round(preparation_seconds, 2),
        'evidence_seconds': round(evidence_seconds, 2),
        'correction_seconds': round(correction_seconds, 2),
        'selection_seconds': round(time.monotonic() - selection_started, 2),
        'analysis_total_seconds': round(time.monotonic() - started, 2),
        'scope': 'analysis_only; rendering and editor export excluded',
        'cache_reused': bool(key and cached.get('key') == key)}
    write_json(work / 'transcript.json', transcript)
    on_progress(100, f'{len(clips)} kandidat siap diperiksa')
    return transcript, clips


def clip_name(clip, i):
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', clip['title']).strip('-').lower()[:40] or 'clip'
    return f'{i+1:02d}-{slug}'


def source_plan(media_path,words,clip,cfg,info,*,context_words=None):
    """Use the same evidence and pause policy for review, preview and final."""
    from .selected_alignment import prepare
    words,alignment_report=prepare(media_path,words,clip,cfg)
    words=intelligence.annotate_words(words,clip,cfg,context_words=context_words)
    preserve=cfg.source_kind in ('board','screen','chart','graphic') and cfg.preserve_material_pauses
    plan=editplan.build(words,clip,replace(cfg,trim_silence=False) if preserve else cfg)
    composition.analyze(media_path,plan,cfg,info)
    if cfg.source_kind=='auto' and cfg.trim_silence and cfg.preserve_material_pauses and any(s.get('has_material') for s in plan['shots']):
        plan=editplan.build(words,clip,replace(cfg,trim_silence=False))
        composition.analyze(media_path,plan,cfg,info)
        plan['warnings'].append('Jeda materi dipertahankan; waktu menulis tidak dipangkas otomatis.')
    plan['selected_alignment']=alignment_report
    return words,plan


def render_clip(media_path, words, clip, name, cfg, on_progress=lambda p, m: None, *, context_words=None):
    started = time.monotonic()
    name = name + f"-r{clip.get('revision', 0)}-v40"
    work = Path(cfg.work_dir) / 'renders' / name
    locations = library_paths.destinations(cfg, name)
    video_base, text_base, report_base = locations['video'], locations['text'], locations['report']
    work.mkdir(parents=True, exist_ok=True)
    info = ffmpeg_util.probe(media_path)
    if not 0 <= clip['start'] < clip['end'] <= info['duration'] + .05:
        raise ValueError('Batas clip melebihi durasi sumber.')
    clip = {**clip, 'end': min(clip['end'], info['duration'])}
    if not info['has_audio']:
        raise ValueError('Sumber tidak mempunyai track audio.')
    ffmpeg_util.filter_file_args('preflight')
    on_progress(3, 'Menyusun potongan dan komposisi')
    words,plan=source_plan(media_path,words,clip,cfg,info,context_words=context_words)
    if not plan['shots']:
        raise ValueError('Tidak ada frame yang dapat dirender. Periksa batas clip.')
    from . import illustrations
    recipe={'scenes':[],'notes':[]}
    if cfg.broll_mode != 'off':
        recipe = clip.get('_broll_recipe') or illustrations.prepare(words, clip, cfg, lambda p,m: on_progress(7+p//8,m))
    if cfg.illustration_mode!='off':
        from . import explanation5
        explanation=explanation5.prepare(words,clip,cfg)
        recipe={**recipe,'scenes':[*recipe.get('scenes',[]),*explanation['scenes']],'notes':[*recipe.get('notes',[]),*explanation['notes']]}
        plan['explanation_assets']=[s['asset'] for s in explanation['scenes']]
    if recipe.get('scenes') or recipe.get('notes'):
        illustrations.attach(plan, recipe, replace(cfg,broll_mode='local') if cfg.illustration_mode!='off' and cfg.broll_mode=='off' else cfg)
        placement.protect_broll(plan, cfg)
    write_json(report_base.with_suffix('.credits.json'), illustrations.credits(plan))
    report_base.with_suffix('.credits.txt').write_text('\n'.join(c['credit'] for c in illustrations.credits(plan)), encoding='utf-8')
    from .subtitle_edit import clean
    display, changes, notices = clean(plan['words'], cfg.caption_cleanup, cfg.caption_punctuation, cfg)
    plan['display_words'] = display
    if cfg.visual_enabled:
        from .visual4 import caption_envelopes
        caption_envelopes(plan,cfg)
    plan['subtitle_cleanup'] = {'mode': cfg.caption_cleanup, 'changes': changes, 'review': notices}
    if notices:
        plan['warnings'].append('Ada angka atau waktu kata yang perlu didengarkan kembali; lihat laporan subtitle.')
    write_json(report_base.with_suffix('.subtitle-review.json'), plan['subtitle_cleanup'])
    from .typography import make_plan
    anchors=placement.caption_anchors(plan,cfg)
    on_progress(20,'Menyiapkan suara dan memeriksa penekanan ucapan')
    voice=render.voice_stem(media_path,plan,cfg,work)
    from .style5 import annotate_prosody,readability
    display=annotate_prosody(display,voice)
    plan['display_words']=display
    ass = captions_pro.write_ass(display, work / 'captions.ass', cfg,
        keywords=clip.get('keywords', []),
        anchors=placement.caption_anchors(plan, cfg))
    plan['captions'] = read_json(Path(ass).with_suffix('.caption-plan.json'))
    # SFX cues now follow the final acoustic/semantic caption decisions.
    mix=render.audio_stems(media_path,plan,cfg,work)
    plan['style_report']=readability(plan['captions'],cfg)
    plan['style_report']['selected_alignment']=plan.get('selected_alignment')
    write_json(report_base.with_suffix('.readability.json'),plan['style_report'])
    if plan['style_report']['issue_count']:plan['warnings'].append('Keterbacaan perlu ditinjau; lihat masalah per frasa di panel Gaya Tahap 5.')
    from . import caption_renderer
    plan['caption_renderer']=caption_renderer.render(plan['captions'],cfg,work,plan['duration'])
    plan['style_report']['renderer']={k:plan['caption_renderer'].get(k) for k in ('engine','status','reason','generation')}
    plan['style_report']['explanations']=[{'quote':a['origin']['quote'],'renderer':a['renderer'],
        'motion_canvas':a['motion_canvas'],'preview_path':a['path']} for a in plan.get('explanation_assets',[])]
    for phrase in plan['style_report']['phrases']:
        span=next((s for s in plan['spans'] if s['start']<=phrase['start']<s['end']),None)
        if span:phrase['source_start']=span['source_start']+phrase['start']-span['start']
    write_json(report_base.with_suffix('.readability.json'),plan['style_report'])
    if plan['caption_renderer'].get('status')=='fallback':plan['warnings'].append(plan['caption_renderer']['reason'])
    plan['caption_checks'] = qc.inspect_caption_plan(plan['captions'], cfg, expected_words=display)
    for event in plan.get('broll', []):
        event['image_height'] = min(s.get('image_height') or cfg.target_h for s in plan['shots']
            if s['start'] < event['end'] and s['end'] > event['start'])
    render.broll_plates(plan, cfg, work)
    plan['style'] = {'accent': cfg.accent_hex, 'base': cfg.base_hex, 'caption_style': cfg.caption_style,
                     'preset':cfg.style_preset,'seed':cfg.caption_seed,'renderer':plan['caption_renderer']['engine'],
                     'motion_intensity': cfg.motion_intensity, 'font_main': cfg.font_main,
                     'font_accent': cfg.font_accent, 'contrast': cfg.caption_backdrop, 'caption_position': cfg.caption_position,
                     'caption_align': cfg.caption_align, 'safe_placement': cfg.safe_placement}
    plan['subtitle_path'] = str(Path(ass).resolve())
    plan['render_config'] = {'zoom_amount': cfg.zoom_amount}
    plan_path = work / 'edit-plan.json'
    plan['status'] = 'preparing'
    write_json(plan_path, plan)
    shutil.copy2(ass, text_base.with_suffix('.ass'))
    from .projects import write_srt
    write_srt(plan, text_base.with_suffix('.srt'))
    on_progress(25, 'Menyiapkan suara dan musik')
    from . import audio_quality
    plan['audio_quality'] = audio_quality.inspect(mix, cfg)
    plan['warnings'].extend(plan['audio_quality'].get('issues', []))
    plan['status'] = 'rendering'
    write_json(plan_path, plan)
    try:
        # Logs and intermediate files remain with the editable plan.
        rendered = render.video(media_path, plan, cfg, ass, work / (name + '.mp4'), mix,
            lambda p: on_progress(40 + round(p * 54), 'Encoding video'))
        on_progress(96, 'Memeriksa durasi, gambar, dan suara')
        checked = qc.inspect(rendered, cfg, plan['duration'])
        checked['caption_layout'] = plan['caption_checks']
        plan['audio_quality'] = audio_quality.inspect(rendered, cfg)
        checked['audio_quality'] = plan['audio_quality']
        plan['warnings'].extend(plan['audio_quality'].get('issues', []))
        checked['editorial'] = {'status': 'needs_review' if notices or clip.get('boundary_review', {}).get('status') == 'needs_review' else 'not_human_verified',
            'subtitle_flags': len(notices), 'boundary': clip.get('boundary_review', {}),
            'intelligence': clip.get('intelligence', {}),
            'note': 'QC teknis bukan penilaian kelengkapan cerita atau prediksi retensi.'}
        write_json(report_base.with_suffix('.qc.json'), checked)
        # Publish only a validated result; a failed retry leaves the prior MP4 intact.
        final = video_base.with_suffix('.mp4')
        shutil.move(rendered, final)
    except Exception as exc:
        plan.update(status='error', error=str(exc))
        write_json(plan_path, plan)
        raise
    plan['render_seconds'] = round(time.monotonic() - started, 2)
    plan['status'] = 'done'
    write_json(plan_path, plan)
    on_progress(100, 'Clip selesai')
    return {'file': library_paths.relative(cfg, final), 'url': library_paths.url(library_paths.relative(cfg, final)),
        'ass_url': library_paths.url(library_paths.relative(cfg, text_base.with_suffix('.ass'))),
        'srt_url': library_paths.url(library_paths.relative(cfg, text_base.with_suffix('.srt'))),
        'credits_url': library_paths.url(library_paths.relative(cfg, report_base.with_suffix('.credits.txt'))),
        'title': clip['title'], 'reason': clip.get('reason', ''),
        'start': clip['start'], 'end': clip['end'], 'length': round(checked['duration'], 2),
        'width': cfg.target_w, 'height': cfg.target_h, 'fps': cfg.output_fps, 'encoder': plan['encoder'],
        'revision': clip.get('revision', 0), 'plan_path': str(plan_path.resolve()),
        'render_version': RENDER_VERSION, 'broll_count': len(plan.get('broll', [])), 'subtitle_flags': len(notices),
        'render_seconds': plan['render_seconds'], 'selection_source': clip.get('selection_source'),
        'placement': plan.get('placement_summary', {}),
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
