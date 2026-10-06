"""Local review studio. Persistent jobs, separate analysis/render, explicit selected exports."""
from __future__ import annotations
import json
import math
import shutil
import threading
import time
import uuid
from dataclasses import asdict, replace, fields
from pathlib import Path
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
load_dotenv(ROOT / '.env.pro', override=True)
from clipper.config import Config, validate_overrides, validate_brand
from clipper import pipeline, boundaries, story, editorial, stock, illustrations, intelligence
from clipper import library_paths, transcript_correction
from clipper.storage import read_json, write_json
from clipper.looks import LOOKS, VISUAL_FIELDS
from clipper.font_catalog import FONTS

BRAND_FILE = ROOT / 'brand.json'
PRESETS_FILE = ROOT / 'style-presets.json'
base_cfg = replace(Config(), **validate_brand(read_json(BRAND_FILE, {})))
base_cfg = replace(base_cfg, work_dir=str((ROOT / base_cfg.work_dir).resolve()),
                   out_dir=str((ROOT / base_cfg.out_dir).resolve()))
app = FastAPI(title='Clipper Studio Local', version=pipeline.RENDER_VERSION)
STATIC = ROOT / 'static'
UPLOADS = ROOT / 'uploads'
UPLOADS.mkdir(exist_ok=True)
STATES = Path(base_cfg.work_dir) / 'studio-jobs'
STATES.mkdir(parents=True, exist_ok=True)
JOBS, JOB_STATE = {}, {}
PROCESS_LOCK = threading.Lock()
STATE_LOCK = threading.RLock()
ACTIVE = {'queued', 'analyzing', 'reviewing', 'rendering', 'previewing', 'exporting', 'illustrating', 'automatic', 'discovering', 'correcting'}


def persist(job_id):
    with STATE_LOCK:
        st = JOB_STATE[job_id]
        write_json(STATES / f'{job_id}.json', {'job': JOBS[job_id], 'state': {
            **st, 'cfg': {k:v for k,v in asdict(st['cfg']).items() if k != 'pexels_key'}, 'edits': {str(k): v for k, v in st.get('edits', {}).items()}}})


def restore():
    for file in STATES.glob('*.json'):
        data = read_json(file)
        if not data:
            continue
        try:
            st, job = data['state'], data['job']
            st['cfg'] = Config(**{k: v for k, v in st['cfg'].items() if k in {f.name for f in fields(Config)}})
            st['cfg'] = replace(st['cfg'], title_card=False)
            for settings in st.get('clip_settings', {}).values():
                settings['title_card'] = False
            st['edits'] = {int(k): v for k, v in st.get('edits', {}).items()}
            st['scored'] = [boundaries.annotate(c, st.get('edits', {}).get(i, st.get('transcript', {}).get('words', [])),
                                              st['cfg'].max_clip_s + st['cfg'].topic_grace_s) for i, c in enumerate(st.get('scored', []))]
            if job['status'] in ACTIVE:
                job.update(status='interrupted', message='Sesi terhenti. Kandidat dan koreksi yang tersimpan tetap ada.')
            JOB_STATE[file.stem], JOBS[file.stem] = st, job
        except (KeyError, ValueError, TypeError):
            continue


restore()


@app.middleware('http')
async def local_origin(request: Request, call_next):
    # Prevent unrelated web pages from submitting local paths or altering this local app.
    origin = request.headers.get('origin')
    if origin and origin not in {'http://127.0.0.1:8765', 'http://localhost:8765', 'http://testserver'}:
        return JSONResponse({'detail': 'Origin tidak diizinkan.'}, status_code=403)
    return await call_next(request)


def state(job_id, idx=None):
    st, job = JOB_STATE.get(job_id), JOBS.get(job_id)
    if st is None or job is None:
        raise HTTPException(404, 'Proyek tidak ditemukan.')
    if idx is not None and not 0 <= idx < len(st.get('scored', [])):
        raise HTTPException(404, 'Clip tidak ditemukan.')
    return st, job


def public(job_id):
    st, job = state(job_id)
    return {**job, 'id': job_id, 'candidates': st.get('scored', []),
            'selection_report': read_json(Path(st['cfg'].work_dir) / 'selection-report.json', {}),
            'correction_report': st.get('transcript', {}).get('correction_report', {}),
            'elapsed': round(time.time() - job.get('started', time.time())) if job['status'] in ACTIVE else job.get('elapsed', 0)}


def worker(job_id, action, indices=None):
    from clipper.runtime.gpu import GPULease
    from clipper.runtime.state import runtime_root
    with PROCESS_LOCK, GPULease(runtime_root(ROOT,Path(base_cfg.work_dir)),'pekerjaan '+action):
        st, job = state(job_id)
        job.update(status=action, started=time.time(), error=None)
        persist(job_id)
        def progress(percent, message):
            with STATE_LOCK:
                job.update(percent=percent, message=message)
        automatic = action == 'automatic' or (action == 'analyzing' and st['cfg'].workflow == 'automatic')
        if action == 'automatic':
            action = 'reviewing'
            job['status'] = action
        try:
            if action == 'analyzing':
                transcript, clips = pipeline.analyze(st['media'], st['cfg'], progress)
                st.update(transcript=transcript, scored=clips, edits={})
                job.update(status='review', percent=100, message='Periksa pembuka, penutup, dan teks; pilih clip untuk render.')
            elif action == 'discovering':
                cfg = replace(st['cfg'], search_depth='broad', num_clips=0)
                found = story.select(st['transcript'], cfg, progress)
                before = len(st['scored'])
                for candidate in found:
                    if candidate.get('selection_source') != 'manual-required' and not any(
                            story.duplicate(candidate, prior, st['transcript']['words']) for prior in st['scored']):
                        st['scored'].append(candidate)
                job.update(status='review', percent=100,
                    message=f'{len(st["scored"])-before} kandidat tambahan. Koreksi dan hasil clip sebelumnya tetap tersimpan.')
            elif action == 'correcting':
                progress(10,'Memperbarui istilah dari transkrip tersimpan')
                backup=Path(st['cfg'].work_dir)/'session-history'/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'-before-correction.json')
                write_json(backup,{'transcript':st['transcript'],'edits':st.get('edits',{}),'scored':st['scored']})
                transcript,edits=transcript_correction.refresh_saved(st['transcript'],st.get('edits',{}),st['cfg'],st.get('clip_settings',{}))
                st.update(transcript=transcript,edits=edits)
                for c in st['scored']:
                    c['revision']=c.get('revision',0)+1
                    c['intelligence']={'status':'stale','issues':['Istilah transkrip diperbarui. Jalankan Periksa AI untuk memeriksa cerita kembali.']}
                write_json(Path(st['cfg'].work_dir)/'transcript.json',transcript)
                write_json(Path(st['cfg'].work_dir)/'transcript-corrections.json',transcript['correction_report'])
                job.pop('export',None);job.pop('preview',None)
                job.update(status='review',percent=100,message='Koreksi istilah selesai tanpa Whisper ulang. Edit manual dipertahankan; periksa cerita lalu render ulang.')
            elif action == 'reviewing':
                try:
                    for n, idx in enumerate(indices):
                        progress(round(100 * n / len(indices)), f'Periksa batas {n+1}/{len(indices)} — transkrip tersimpan')
                        transcript = {**st['transcript'], 'words': st.get('edits', {}).get(idx, st['transcript']['words'])}
                        cfg = replace(st['cfg'], **st.get('clip_settings', {}).get(str(idx), {}))
                        if not (automatic and (intelligence.ready(st['scored'][idx], transcript['words'], cfg)
                                or st['scored'][idx].get('selection_source') == 'full')):
                            st['scored'][idx] = story.review_candidate(st['scored'][idx], transcript, cfg) if automatic else story.review_candidate(st['scored'][idx], transcript, cfg, refresh=True)
                        persist(job_id)
                finally:
                    editorial.release(st['cfg'])
                job.pop('export', None)
                job.update(status='review', percent=100, message='Pemeriksaan batas selesai. Kandidat bermasalah ditandai untuk review.')
            if automatic and action in ('analyzing', 'reviewing'):
                requested = list(range(len(st['scored']))) if indices is None else indices
                indices, skipped = [], []
                for idx in requested:
                    c = st['scored'][idx]
                    cfg = replace(st['cfg'], **st.get('clip_settings', {}).get(str(idx), {}))
                    words = st.get('edits', {}).get(idx, st['transcript']['words'])
                    if intelligence.ready(c, words, cfg) or c.get('selection_source') == 'full':
                        indices.append(idx)
                    else:
                        skipped.append({'index': idx, 'title': c['title'],
                            'issues': c.get('intelligence', {}).get('issues') or
                            c.get('boundary_review', {}).get('issues') or ['Perlu pemeriksaan cerita.']})
                job['automation'] = {'selected': indices, 'skipped': skipped}
                if not indices:
                    job.update(status='review', percent=100,
                        message='Belum ada cerita lolos pemeriksaan otomatis. Kandidat tersimpan untuk diperbaiki pada tab Cerita.')
                    return
                action = 'rendering'
                job.update(status=action, percent=0)
                persist(job_id)
            if action == 'illustrating':
                for n,idx in enumerate(indices):
                    cfg=replace(st['cfg'], **st.get('clip_settings',{}).get(str(idx),{}))
                    recipe=illustrations.prepare(st.get('edits',{}).get(idx,st['transcript']['words']),
                        st['scored'][idx],cfg,lambda p,m:progress(round((100*n+p)/len(indices)),m),refresh=True)
                    st['scored'][idx]['revision']=st['scored'][idx].get('revision',0)+1
                    job.setdefault('illustration_status',{})[str(idx)]={'count':len(recipe['scenes']),'notes':recipe['notes'],'status':recipe['status'],
                        'recipe':illustrations.recipe_path(st.get('edits',{}).get(idx,st['transcript']['words']),st['scored'][idx],cfg).name}
                    persist(job_id)
                job.pop('export',None)
                count=sum(job['illustration_status'][str(i)]['count'] for i in indices)
                notes=list(dict.fromkeys(note for i in indices for note in job['illustration_status'][str(i)]['notes']))
                message=f'{count} sisipan ilustrasi tersedia. Tinjau pada tab Visual.' if count else 'Tidak ada sisipan ilustrasi. '+ ' '.join(notes)
                job.update(status='review',percent=100,message=message)
            elif action == 'rendering':
                pipeline.ffmpeg_util.filter_file_args('preflight')
                job.pop('export', None)
                job.pop('export_error', None)
                job['failures'] = []
                completed = 0
                for n, idx in enumerate(indices):
                    c = st['scored'][idx]
                    prior = next((r for r in job['clips'] if r.get('index') == idx and
                        r.get('revision') == c.get('revision', 0) and r.get('render_version') == pipeline.RENDER_VERSION
                        and (Path(st['cfg'].out_dir) / r.get('file', '')).is_file()), None)
                    if prior:
                        completed += 1
                        continue
                    progress(round(100 * n / len(indices)), f'Render {n+1}/{len(indices)} — {c["title"]}')
                    cfg = replace(st['cfg'], **st.get('clip_settings', {}).get(str(idx), {}))
                    try:
                        res = pipeline.render_clip(st['media'], st.get('edits', {}).get(idx, st['transcript']['words']),
                            c, pipeline.clip_name(c, idx), cfg,
                            lambda p, m: progress(round((100*n+p)/len(indices)), f'Clip {n+1}/{len(indices)} · {m}'))
                    except Exception as exc:
                        job['failures'].append({'index': idx, 'title': c['title'], 'error': str(exc)})
                        persist(job_id)
                        continue
                    old_result = next((r for r in job['clips'] if r.get('index') == idx), None)
                    library_paths.archive_previous(cfg, old_result, res)
                    job['clips'] = [r for r in job['clips'] if r.get('index') != idx] + [{**res, 'index': idx}]
                    job['clips'].sort(key=lambda r: r['index'])
                    completed += 1
                    persist(job_id)
                failed = len(job['failures'])
                job.update(status='error' if failed else 'done', percent=100,
                    error=job['failures'][0]['error'] if failed else None,
                    message=f'{completed}/{len(indices)} clip selesai' + (f'; {failed} gagal. Render ulang hanya mengerjakan yang belum selesai.' if failed else '. Hasil tersimpan di folder clips.'))
                if automatic:
                    skipped_count = len(job.get('automation', {}).get('skipped', []))
                    job['message'] += f' {skipped_count} kandidat ditahan untuk review.'
                    completed_results = [r for r in job['clips'] if r.get('index') in indices
                        and r.get('revision') == st['scored'][r['index']].get('revision', 0)
                        and r.get('render_version') == pipeline.RENDER_VERSION
                        and (Path(st['cfg'].out_dir) / r.get('file', '')).is_file()]
                    if st['cfg'].auto_export and completed_results:
                        from clipper.projects import export_bundle
                        job['status'] = 'exporting'
                        persist(job_id)
                        summary = job['message']
                        try:
                            job['export'] = export_bundle(completed_results, st['cfg'], progress)
                            summary += ' Paket editor siap.' if not job['export'].get('capcut_error') else ' Paket DaVinci siap; ekspor CapCut perlu diperiksa.'
                        except Exception as exc:
                            job['export_error'] = str(exc)
                            summary += ' MP4 tersimpan; paket editor gagal, gunakan tombol ekspor untuk mencoba lagi.'
                        job.update(status='error' if failed else 'done', percent=100, message=summary)
            elif action == 'previewing':
                idx = indices[0]
                c = dict(st['scored'][idx])
                cfg = replace(st['cfg'], **st.get('clip_settings', {}).get(str(idx), {}))
                if cfg.broll_mode != 'off':
                    c['_broll_recipe'] = illustrations.prepare(st.get('edits', {}).get(idx, st['transcript']['words']), c, cfg, progress)
                preview_words = intelligence.annotate_words(st.get('edits', {}).get(idx, st['transcript']['words']), c, cfg)
                cursor = job.pop('preview_source_start', c['start'])
                if cursor > c['start'] + .05:
                    c['start'] = cursor
                    c['cold_open_span'] = None
                    cfg = replace(cfg, cold_open=False, title_card=False)
                cfg = replace(cfg, preview_seconds=12, target_w=640 if cfg.target_w > cfg.target_h else 360,
                              target_h=360 if cfg.target_w > cfg.target_h else 640)
                key = library_paths.fingerprint(st['media'], preview_words, c, cfg)
                cache = Path(st['cfg'].work_dir) / 'cache' / 'previews' / key
                result = read_json(cache / 'result.json')
                reused = bool(result and (cache / 'output' / result['file']).is_file())
                if not reused:
                    preview_cfg = replace(cfg, work_dir=str(cache / 'work'), out_dir=str(cache / 'output'))
                    result = pipeline.render_clip(st['media'], preview_words, c, 'preview-' + str(idx), preview_cfg, progress)
                    result['url'] = f'/api/preview-file/{job_id}/{key}/{result["file"]}'
                    write_json(cache / 'result.json', result)
                job.update(status='review', percent=100, message=f"Preview {result['length']:.1f} detik siap" + (' · cache dipakai kembali.' if reused else '. Pilih tab Preview.'),
                           preview={**result, 'index': idx, 'source_start': cursor})
            elif action == 'exporting':
                from clipper.projects import export_bundle
                selected = [r for r in job['clips'] if r.get('index') in indices]
                progress(10, 'Menyusun media, subtitle, dan proyek editable')
                result = export_bundle(selected, st['cfg'], progress)
                job.update(status='done', percent=100, message='Paket proyek editable siap.', export=result)
        except Exception as exc:
            job.update(status='error', error=str(exc), message=f'Proses terhenti. {len(job["clips"])} clip tersimpan; transkrip dan kandidat tetap tersedia.')
        finally:
            job['elapsed'] = round(time.time() - job['started'], 1)
            job.setdefault('timings', {})[action] = job['elapsed']
            persist(job_id)


def enqueue(job_id, action, indices=None):
    _, job = state(job_id)
    if job['status'] in ACTIVE:
        raise HTTPException(409, 'Proyek ini masih diproses.')
    job.update(status='queued', percent=0, message='Menunggu giliran proses lokal', error=None, started=time.time())
    persist(job_id)
    threading.Thread(target=worker, args=(job_id, action, indices), daemon=True).start()


def new_job(path, options, music='', sfx='', original_name=None):
    from clipper.ffmpeg_util import probe
    info = probe(str(path))
    if not info['has_audio']:
        raise HTTPException(400, 'File tidak mempunyai track suara.')
    job_id = uuid.uuid4().hex[:12]
    preset = next((p['settings'] for p in LOOKS if p['id'] == options.get('style_preset')), {})
    options = {'num_clips': '0', **options}
    cfg = replace(base_cfg, job_id=job_id, music_path=music, sfx_path=sfx,
                  work_dir=str(Path(base_cfg.work_dir) / job_id), **{**preset, **validate_overrides(options)})
    JOB_STATE[job_id] = {'cfg': cfg, 'media': str(Path(path).resolve()), 'transcript': {},
                         'scored': [], 'edits': {}, 'clip_settings': {}, 'source_info': info}
    JOBS[job_id] = {'status': 'new', 'percent': 0, 'message': '', 'clips': [], 'error': None,
                    'name': original_name or Path(path).name, 'created': time.time(), 'elapsed': 0}
    enqueue(job_id, 'analyzing')
    return {'job': job_id}


@app.get('/api/stock-settings')
def get_stock_settings():
    return stock.public_settings()


@app.post('/api/stock-settings')
def set_stock_settings(data: dict = Body(...)):
    try:
        return stock.save_settings(data)
    except (TypeError,ValueError,OSError) as exc:
        raise HTTPException(400,str(exc)) from exc


def clip_recipe(job_id,idx):
    st,job=state(job_id,idx)
    cfg=replace(st['cfg'],**st.get('clip_settings',{}).get(str(idx),{}))
    words=st.get('edits',{}).get(idx,st['transcript']['words'])
    path=illustrations.recipe_path(words,st['scored'][idx],cfg)
    last=job.get('illustration_status',{}).get(str(idx),{})
    notes=last['notes'] if last.get('recipe')==path.name else ['Tekan Siapkan ilustrasi, atau langsung render untuk menyiapkannya otomatis.']
    return st,job,cfg,path,read_json(path,{'scenes':[],'notes':notes})


@app.get('/api/illustrations/{job_id}/{idx}')
def get_illustrations(job_id: str,idx: int):
    st,job,cfg,path,recipe=clip_recipe(job_id,idx)
    return {**recipe,'scenes':[{**e,'asset':{k:v for k,v in e['asset'].items() if k not in ('path','url')},
        'preview':f'/api/illustration-media/{job_id}/{idx}/{e["id"]}'} for e in recipe['scenes']]}


@app.post('/api/illustrations/{job_id}/{idx}')
def edit_illustration(job_id: str,idx: int,data: dict=Body(...)):
    st,job,cfg,path,recipe=clip_recipe(job_id,idx)
    if job['status'] in ACTIVE: raise HTTPException(409,'Tunggu proses selesai.')
    item=next((e for e in recipe['scenes'] if e['id']==data.get('id')),None)
    if item is None: raise HTTPException(404,'Ilustrasi tidak ditemukan.')
    if type(data.get('enabled')) is not bool: raise HTTPException(400,'Pilihan aktif tidak valid.')
    item['enabled']=data['enabled'];write_json(path,recipe)
    st['scored'][idx]['revision']=st['scored'][idx].get('revision',0)+1
    job.pop('export',None);persist(job_id)
    return {'ok':True}


@app.get('/api/illustration-media/{job_id}/{idx}/{scene_id}')
def illustration_media(job_id: str,idx: int,scene_id: str):
    *_,recipe=clip_recipe(job_id,idx)
    item=next((e for e in recipe['scenes'] if e['id']==scene_id),None)
    if item is None or not Path(item['asset']['path']).is_file(): raise HTTPException(404,'Aset tidak ditemukan.')
    return FileResponse(item['asset']['path'])


@app.post('/api/prepare-illustrations/{job_id}')
def prepare_illustrations(job_id: str,data: dict=Body(...)):
    st,_=state(job_id)
    indices=selected_indices(data,st)
    enqueue(job_id,'illustrating',indices)
    return {'ok':True}


@app.get('/', response_class=HTMLResponse)
def index():
    return (STATIC / 'index.html').read_text(encoding='utf-8')


@app.get('/assets/{name}')
def static_asset(name: str):
    if name not in ('studio.css', 'studio.js'):
        raise HTTPException(404, 'Aset tidak ditemukan.')
    return FileResponse(STATIC / name, headers={'Cache-Control': 'no-cache'})


@app.get('/api/jobs')
def jobs():
    return [{'id': j, 'name': v.get('name', j), 'status': v['status'], 'created': v.get('created', 0)}
            for j, v in sorted(JOBS.items(), key=lambda row: row[1].get('created', 0), reverse=True)]


@app.get('/api/templates')
def typography_templates():
    return [{**t, 'preview': '/api/template-preview/' + t['id'],
             'poster': '/api/template-poster/' + t['id']} for t in LOOKS]


@app.get('/api/template-poster/{template_id}')
def template_poster(template_id: str):
    if template_id not in {t['id'] for t in LOOKS}:
        raise HTTPException(404, 'Template tidak ditemukan.')
    path = STATIC / 'templates' / (template_id + '.jpg')
    if not path.is_file():
        raise HTTPException(404, 'Gambar contoh belum terpasang.')
    return FileResponse(path, media_type='image/jpeg')


@app.get('/api/template-preview/{template_id}')
def template_preview(template_id: str):
    from clipper.motion import IDS
    if template_id not in (*IDS, *(t['id'] for t in LOOKS)):
        raise HTTPException(404, 'Template tidak ditemukan.')
    path = STATIC / 'templates' / (template_id + '.mp4')
    if not path.is_file():
        raise HTTPException(404, 'Preview template belum terpasang. Pasang paket upgrade lengkap.')
    return FileResponse(path, media_type='video/mp4')


@app.get('/api/fonts')
def fonts():
    return [{'id': k, **v, 'url': '/api/font/' + k} for k, v in FONTS.items()]


@app.get('/api/font/{font_id}')
def font_file(font_id: str):
    if font_id not in FONTS:
        raise HTTPException(404, 'Font tidak tersedia.')
    return FileResponse(Path(base_cfg.fonts_dir) / FONTS[font_id]['file'], media_type='font/ttf')


@app.get('/api/style-presets')
def style_presets():
    return [{**p, 'settings': {k:v for k,v in p.get('settings', {}).items() if k in VISUAL_FIELDS}}
            for p in read_json(PRESETS_FILE, [])]


@app.post('/api/style-presets')
def save_style_preset(data: dict = Body(...)):
    name = str(data.get('name', '')).strip()[:60]
    values = data.get('settings')
    if not name or not isinstance(values, dict):
        raise HTTPException(400, 'Isi nama dan pengaturan preset.')
    try:
        settings = validate_overrides({k:v for k,v in values.items() if k in VISUAL_FIELDS})
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if not {'caption_style', 'font_main', 'font_accent'} <= settings.keys():
        raise HTTPException(400, 'Pilih gaya dan pasangan font yang tersedia.')
    with STATE_LOCK:
        presets = read_json(PRESETS_FILE, [])
        if len(presets) >= 30:
            raise HTTPException(400, 'Maksimal 30 preset; hapus preset lama dahulu.')
        saved = {'id': uuid.uuid4().hex[:12], 'name': name, 'settings': settings}
        write_json(PRESETS_FILE, [*presets, saved])
    return saved


@app.delete('/api/style-presets/{preset_id}')
def delete_style_preset(preset_id: str):
    with STATE_LOCK:
        presets = read_json(PRESETS_FILE, [])
        write_json(PRESETS_FILE, [p for p in presets if p.get('id') != preset_id])
    return {'ok': True}


@app.post('/api/upload')
async def upload(request: Request):
    form = await request.form(max_part_size=8 * 1024 * 1024)
    f = form.get('file')
    if f is None or not getattr(f, 'filename', ''):
        raise HTTPException(400, 'Pilih file video.')
    suffix = Path(f.filename).suffix.lower()
    if suffix not in ('.mp4', '.mkv', '.mov', '.webm', '.m4v'):
        raise HTTPException(400, 'Gunakan MP4, MKV, MOV, M4V, atau WebM.')
    dest = UPLOADS / (uuid.uuid4().hex[:12] + suffix)
    with dest.open('wb') as out:
        shutil.copyfileobj(f.file, out)
    options = {k: v for k, v in form.items() if isinstance(v, str)}
    music, sfx = '', ''
    for kind in ('music', 'sfx'):
        asset = form.get(kind)
        if asset and getattr(asset, 'filename', ''):
            ext = Path(asset.filename).suffix.lower()
            if ext not in ('.mp3', '.wav', '.m4a', '.flac', '.ogg'):
                raise HTTPException(400, 'Format audio tidak didukung.')
            p = UPLOADS / (uuid.uuid4().hex[:12] + '-' + kind + ext)
            with p.open('wb') as out:
                shutil.copyfileobj(asset.file, out)
            if kind == 'music':
                music = str(p.resolve())
            else:
                sfx = str(p.resolve())
    try:
        return new_job(dest, options, music, sfx, Path(f.filename).name)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post('/api/local')
def local_file(data: dict = Body(...)):
    # User-selected disk path avoids duplicating a multi-GB downloaded source.
    p = Path(str(data.get('path', '')).strip().strip('"'))
    if not p.is_file() or p.suffix.lower() not in ('.mp4', '.mkv', '.mov', '.webm', '.m4v'):
        raise HTTPException(400, 'Path video lokal tidak ditemukan.')
    assets = []
    for key in ('music_path', 'sfx_path'):
        value = str(data.get(key, '')).strip().strip('"')
        if value and (not Path(value).is_file() or Path(value).suffix.lower() not in ('.mp3', '.wav', '.m4a', '.flac', '.ogg')):
            raise HTTPException(400, f'Path {key} tidak valid.')
        assets.append(value)
    try:
        return new_job(p, data, *assets)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get('/api/status/{job_id}')
def status(job_id: str):
    return public(job_id)


@app.post('/api/resume/{job_id}')
def resume(job_id: str):
    st, job = state(job_id)
    if job['status'] in ACTIVE:
        raise HTTPException(409, 'Proyek masih diproses.')
    if st.get('scored'):
        job.update(status='review', error=None, message='Kandidat dipulihkan. Render ulang pilihan yang belum selesai.')
        persist(job_id)
    else:
        enqueue(job_id, 'analyzing')
    return public(job_id)


@app.get('/api/source/{job_id}')
def source(job_id: str):
    st, _ = state(job_id)
    if not Path(st['media']).is_file():
        raise HTTPException(404, 'Video sumber dipindah atau dihapus.')
    return FileResponse(st['media'])


@app.get('/api/transcript/{job_id}')
def transcript(job_id: str, q: str = '', offset: int = 0):
    st, _ = state(job_id)
    words = st.get('transcript', {}).get('words', [])
    if q:
        words = [w for w in words if q.lower() in w['word'].lower()]
    return {'words': words[max(0, offset):max(0, offset) + 500], 'total': len(words)}


@app.get('/api/editor/{job_id}/{idx}')
def editor_get(job_id: str, idx: int, start: float | None = None, end: float | None = None):
    st, _ = state(job_id, idx)
    c = st['scored'][idx]
    a, b = start if start is not None else c['start'] - 10, end if end is not None else c['end'] + 10
    words = st.get('edits', {}).get(idx, st['transcript']['words'])
    cfg = replace(st['cfg'], **st.get('clip_settings', {}).get(str(idx), {}))
    settings = {k: v for k, v in asdict(cfg).items() if k not in ('pexels_key',)}
    return {'clip': c, 'duration': st['transcript']['duration'], 'settings': settings,
            'words': [w for w in words if w['end'] > a and w['start'] < b]}


@app.post('/api/editor/{job_id}/{idx}')
def editor_save(job_id: str, idx: int, data: dict = Body(...)):
    st, job = state(job_id, idx)
    if job['status'] in ACTIVE:
        raise HTTPException(409, 'Tunggu proses proyek selesai sebelum mengedit.')
    try:
        duration = st['transcript']['duration']
        start, end = float(data['start']), float(data['end'])
        if not all(math.isfinite(x) for x in (start, end)) or not 0 <= start < end <= duration + .05:
            raise ValueError('Batas clip di luar durasi video.')
        raw = data['words']
        if not isinstance(raw, list) or not raw or len(raw) > 10000:
            raise ValueError('Daftar kata tidak valid.')
        words, previous = [], -1.
        for w in raw:
            a, b, text = float(w['start']), float(w['end']), str(w['word']).strip()
            if not text or len(text) > 120 or not all(math.isfinite(v) for v in (a, b)) or not 0 <= a < b <= duration + .05 or a < previous:
                raise ValueError('Periksa urutan waktu dan teks setiap kata.')
            words.append({**w, 'word': text, 'start': a, 'end': b})
            previous = a
        keys = data.get('keywords', [])
        if not isinstance(keys, list):
            raise ValueError('Keywords harus berupa daftar.')
        old = st['scored'][idx]
        existing = st.get('edits', {}).get(idx, st['transcript']['words'])
        old_words = {w.get('word_id'): w for w in existing if w.get('word_id') is not None}
        for word in words:
            prior = old_words.get(word.get('word_id'))
            if prior and word['word'] != prior['word']:
                word['manually_edited'] = True
        lo, hi = min(w['start'] for w in words), max(w['end'] for w in words)
        outside = [w for w in existing if w['end'] <= lo or w['start'] >= hi]
        combined = sorted(outside + words, key=lambda w: w['start'])
        start, end = boundaries.snap_words(start, end, combined, duration)
        c = {**old, 'start': start, 'end': end, 'keywords': [str(k)[:80] for k in keys[:20]],
             'title': str(data.get('title', old['title'])).strip()[:120] or old['title'],
             'selection_source': 'reviewed', 'approved': True, 'revision': old.get('revision', 0) + 1}
        cold = data.get('cold_open_span', old.get('cold_open_span'))
        if cold is not None:
            if not isinstance(cold, list) or len(cold) != 2:
                raise ValueError('Hook harus dua waktu sumber atau kosong.')
            ca, cb = map(float, cold)
            if not start <= ca < cb <= end or cb - ca > 6:
                raise ValueError('Hook harus kutipan 1–6 detik dari dalam clip.')
            cold = [ca, cb]
        c['cold_open_span'] = cold
        settings = data.get('settings', {})
        if not isinstance(settings, dict):
            raise ValueError('Pengaturan clip harus berupa objek.')
        overrides = {**st.get('clip_settings', {}).get(str(idx), {}), **validate_overrides(settings)}
        c = boundaries.annotate(c, combined, st['cfg'].max_clip_s + st['cfg'].topic_grace_s)
        review_cfg = replace(st['cfg'], **overrides)
        decision = c.get('intelligence')
        if decision and decision.get('signature') != intelligence.signature(c, combined, review_cfg.audience):
            c['intelligence'] = {**decision, 'status': 'stale',
                'issues': ['Isi, sasaran atau batas clip berubah. Jalankan Periksa AI untuk memperbarui keputusan.']}
        st.setdefault('edits', {})[idx] = combined
        st['scored'][idx] = c
        st.setdefault('clip_settings', {})[str(idx)] = overrides
        job.pop('export', None)
        persist(job_id)
        canonical = asdict(replace(st['cfg'], **overrides))
        canonical.pop('pexels_key', None)
        return {'ok': True, 'revision': c['revision'], 'clip': c, 'settings': canonical}
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post('/api/add-clip/{job_id}')
def add_clip(job_id: str, data: dict = Body(...)):
    st, job = state(job_id)
    if job['status'] in ACTIVE or not st.get('transcript'):
        raise HTTPException(409, 'Transkripsi belum siap.')
    if len(st['scored']) >= 20:
        raise HTTPException(400, 'Maksimal 20 kandidat termasuk tambahan manual.')
    try:
        a, b = float(data['start']), float(data['end'])
        if not 0 <= a < b <= st['transcript']['duration']:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, 'Batas waktu tidak valid.')
    st['scored'].append({'start': a, 'end': b, 'title': 'Pembahasan pilihan', 'reason': 'Dipilih manual',
        'keywords': [], 'warnings': [], 'selection_source': 'manual', 'approved': False, 'revision': 0})
    persist(job_id)
    return {'index': len(st['scored']) - 1}


def selected_indices(data, st):
    raw = data.get('indices', [])
    if not isinstance(raw, list) or not raw or any(type(i) is not int or not 0 <= i < len(st['scored']) for i in raw):
        raise HTTPException(400, 'Pilih kandidat clip yang valid.')
    return sorted(set(raw))


@app.post('/api/apply-template/{job_id}')
def apply_template(job_id: str, data: dict = Body(...)):
    from clipper.motion import IDS
    st, job = state(job_id)
    if job['status'] in ACTIVE:
        raise HTTPException(409, 'Tunggu proses selesai sebelum mengganti template.')
    indices = selected_indices(data, st)
    settings = data.get('settings', {})
    if not isinstance(settings, dict) or settings.get('caption_style') not in (*IDS, 'editorial', 'clean'):
        raise HTTPException(400, 'Pilih template yang tersedia.')
    try:
        allowed = VISUAL_FIELDS
        overrides = validate_overrides({k: v for k, v in settings.items() if k in allowed})
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    for i in indices:
        st.setdefault('clip_settings', {})[str(i)] = {**st.get('clip_settings', {}).get(str(i), {}), **overrides}
        st['scored'][i]['revision'] = st['scored'][i].get('revision', 0) + 1
    job.pop('export', None)
    if job.get('preview', {}).get('index') in indices:
        job.pop('preview', None)
    persist(job_id)
    return {'ok': True, 'count': len(indices)}


@app.post('/api/render/{job_id}')
def render_selected(job_id: str, data: dict = Body(...)):
    st, _ = state(job_id)
    indices = selected_indices(data, st)
    enqueue(job_id, 'rendering', indices)
    return {'ok': True}


@app.post('/api/automatic/{job_id}')
def automatic_selected(job_id: str, data: dict = Body(...)):
    st, _ = state(job_id)
    indices = selected_indices(data, st)
    enqueue(job_id, 'automatic', indices)
    return {'ok': True}


@app.post('/api/refresh-transcript/{job_id}')
def refresh_transcript(job_id: str):
    st,job=state(job_id)
    if job['status'] in ACTIVE:
        raise HTTPException(409,'Tunggu proses selesai.')
    if not st.get('transcript'):
        raise HTTPException(400,'Transkrip belum tersedia.')
    enqueue(job_id,'correcting')
    return {'ok':True}


@app.post('/api/review-boundaries/{job_id}')
def review_boundaries(job_id: str, data: dict = Body(...)):
    st, _ = state(job_id)
    indices = selected_indices(data, st)
    enqueue(job_id, 'reviewing', indices)
    return {'ok': True}


@app.post('/api/audio/{job_id}')
async def update_audio(job_id: str, request: Request):
    st, job = state(job_id)
    if job['status'] in ACTIVE:
        raise HTTPException(409, 'Tunggu proses selesai sebelum mengganti audio.')
    form = await request.form()
    values = {}
    for kind in ('music', 'sfx'):
        asset = form.get(kind)
        if asset and getattr(asset, 'filename', ''):
            ext = Path(asset.filename).suffix.lower()
            if ext not in ('.mp3', '.wav', '.m4a', '.flac', '.ogg'):
                raise HTTPException(400, 'Format audio tidak didukung.')
            path = UPLOADS / (uuid.uuid4().hex[:12] + '-' + kind + ext)
            with path.open('wb') as out:
                shutil.copyfileobj(asset.file, out)
            values[kind + '_path'] = str(path.resolve())
        elif form.get('remove_' + kind) == '1':
            values[kind + '_path'] = ''
    st['cfg'] = replace(st['cfg'], **values)
    if values:
        for c in st['scored']:
            c['revision'] = c.get('revision', 0) + 1
        job.pop('export', None)
        persist(job_id)
    return {'ok': True}


@app.get('/api/subtitle-review/{job_id}/{idx}')
def subtitle_review(job_id: str, idx: int):
    from clipper.subtitle_edit import clean
    st, _ = state(job_id, idx)
    c = st['scored'][idx]
    cfg = replace(st['cfg'], **st.get('clip_settings', {}).get(str(idx), {}))
    words = st.get('edits', {}).get(idx, st['transcript']['words'])
    words = [w for w in words if w['start'] < c['end'] and w['end'] > c['start']]
    display, changes, warnings = clean(words, cfg.caption_cleanup, cfg.caption_punctuation, cfg)
    changes = [r for r in st['transcript'].get('correction_report', {}).get('changes', [])
               if c['start'] <= r.get('start', -1) < c['end']] + changes
    return {'original': words, 'display': display, 'changes': changes, 'warnings': warnings}


@app.post('/api/preview/{job_id}/{idx}')
def preview(job_id: str, idx: int, data: dict = Body(default={})):
    st, job = state(job_id, idx)
    if job['status'] in ACTIVE:
        raise HTTPException(409, 'Tunggu proses selesai.')
    c = st['scored'][idx]
    try:
        cursor = float(data.get('source_start', c['start']))
        if not math.isfinite(cursor) or not c['start'] <= cursor < c['end']:
            raise ValueError('Posisi preview harus di dalam clip.')
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    job['preview_source_start'] = cursor
    enqueue(job_id, 'previewing', [idx])
    return {'ok': True}


@app.post('/api/export/{job_id}')
def export_selected(job_id: str, data: dict = Body(...)):
    st, job = state(job_id)
    indices = selected_indices(data, st)
    for i in indices:
        if not any(r.get('index') == i and r.get('revision') == st['scored'][i].get('revision', 0) and r.get('render_version') == pipeline.RENDER_VERSION for r in job['clips']):
            raise HTTPException(409, 'Render ulang clip yang berubah sebelum membuat paket proyek.')
    enqueue(job_id, 'exporting', indices)
    return {'ok': True}


@app.get('/api/download/{job_id}')
def download_export(job_id: str):
    _, job = state(job_id)
    p = Path(job.get('export', {}).get('zip', ''))
    if not p.is_file():
        raise HTTPException(404, 'Paket belum siap.')
    return FileResponse(p, filename=p.name, media_type='application/zip')


@app.post('/api/regenerate/{job_id}/{idx}')
def regenerate(job_id: str, idx: int, aspect: str = Form('9:16'), caption_style: str = Form('editorial'),
               caption_position: str = Form('auto'), layout: str = Form('auto'), trim: str = Form('0')):
    st, job = state(job_id, idx)
    if not PROCESS_LOCK.acquire(blocking=False):
        raise HTTPException(409, 'Tunggu proses video yang sedang berjalan.')
    try:
        options = validate_overrides({'aspect': aspect, 'caption_style': caption_style, 'caption_position': caption_position,
                                      'layout': layout, 'trim': trim})
        cfg = replace(st['cfg'], **options)
        c = st['scored'][idx]
        c['revision'] = c.get('revision', 0) + 1
        res = pipeline.render_clip(st['media'], st.get('edits', {}).get(idx, st['transcript']['words']), c, pipeline.clip_name(c, idx), cfg)
        st.setdefault('clip_settings', {})[str(idx)] = options
        job['clips'] = [r for r in job['clips'] if r.get('index') != idx] + [{**res, 'index': idx}]
        job.pop('export', None)
        persist(job_id)
        return res
    finally:
        PROCESS_LOCK.release()


@app.get('/api/health')
def health():
    from clipper.ffmpeg_util import nvenc_diagnostic, render_diagnostic
    return {'nvenc': nvenc_diagnostic(), 'render': render_diagnostic(), 'model': base_cfg.model, 'whisper': base_cfg.whisper_model,
            'version': pipeline.RENDER_VERSION, 'exports': {'resolve': 'XML + Lua, perlu uji di Resolve', 'capcut': 'multi-timeline + draft per clip, eksperimental'}}


@app.get('/api/brand')
def get_brand():
    return {k: getattr(base_cfg, k) for k in ('accent_hex', 'caption_style', 'font_name')}


@app.post('/api/brand')
def set_brand(accent_hex: str = Form(...), caption_style: str = Form(...), font_name: str = Form(...)):
    global base_cfg
    values = validate_brand(locals())
    write_json(BRAND_FILE, values)
    base_cfg = replace(base_cfg, **values)
    return {'ok': True, **values}


@app.get('/api/storage')
def storage_status():
    return {**library_paths.cache_summary(base_cfg.work_dir, base_cfg.out_dir),
            'busy': any(j.get('status') in ACTIVE for j in JOBS.values()),
            'output_folder': str(base_cfg.out_dir)}


@app.post('/api/storage/clear-cache')
def clear_cache():
    if not PROCESS_LOCK.acquire(blocking=False):
        raise HTTPException(409, 'Tunggu proses video selesai sebelum membersihkan cache.')
    try:
        with STATE_LOCK:
            if any(j.get('status') in ACTIVE for j in JOBS.values()):
                raise HTTPException(409, 'Masih ada proyek dalam antrean/proses.')
            result = library_paths.clear_previews(base_cfg.work_dir, base_cfg.out_dir)
            for ident, job in JOBS.items():
                if job.pop('preview', None):
                    persist(ident)
            return result
    finally:
        PROCESS_LOCK.release()


@app.post('/api/storage/organize')
def organize_outputs():
    if not PROCESS_LOCK.acquire(blocking=False):
        raise HTTPException(409, 'Tunggu proses video selesai dahulu.')
    try:
        with STATE_LOCK:
            if any(j.get('status') in ACTIVE for j in JOBS.values()):
                raise HTTPException(409, 'Masih ada proyek dalam antrean/proses.')
            count = 0
            for ident, st in JOB_STATE.items():
                moved = library_paths.organize_legacy(st['cfg'])
                count += len(moved)
                for result in JOBS[ident].get('clips', []):
                    old = result.get('file', '')
                    if old in moved:
                        result['file'] = moved[old]
                        result['url'] = library_paths.url(moved[old])
                        for field, ext in [('ass_url', '.ass'), ('srt_url', '.srt'), ('credits_url', '.credits.txt')]:
                            target = moved.get(str(Path(old).with_suffix(ext)))
                            if target:
                                result[field] = library_paths.url(target)
                if moved:
                    persist(ident)
            return {'moved_files': count}
    finally:
        PROCESS_LOCK.release()


@app.get('/api/preview-file/{job_id}/{key}/{name}')
def preview_file(job_id: str, key: str, name: str):
    import re
    st, _ = state(job_id)
    if not re.fullmatch('[a-f0-9]{24}', key) or Path(name).name != name or Path(name).suffix != '.mp4':
        raise HTTPException(404, 'Preview tidak ditemukan.')
    p = library_paths.contained(Path(st['cfg'].work_dir) / 'cache' / 'previews', f'{key}/output/{name}')
    if not p.is_file():
        raise HTTPException(404, 'Cache preview sudah dibersihkan. Buat preview kembali.')
    return FileResponse(p, media_type='video/mp4')


@app.post('/api/discover/{job_id}')
def discover_more(job_id: str):
    st, _ = state(job_id)
    if not st.get('transcript', {}).get('words'):
        raise HTTPException(409, 'Transkripsi belum tersedia. Pulihkan sesi dahulu.')
    enqueue(job_id, 'discovering')
    return {'ok': True}


@app.get('/clips/{name:path}')
def clip(name: str):
    try:
        p = library_paths.contained(base_cfg.out_dir, name)
    except ValueError:
        raise HTTPException(404, 'File tidak ditemukan.')
    # Saved 3.1 download links remain valid after organizing old outputs.
    if not p.is_file() and '/' not in name and len(name.split('-')[0]) == 12:
        ident = name.split('-')[0]
        for folder in ('video', 'subtitles', 'reports'):
            candidate = library_paths.contained(base_cfg.out_dir, f'{ident}/{folder}/{name}')
            if candidate.is_file():
                p = candidate
                break
    if not p.is_file() or (p.suffix not in ('.mp4', '.ass', '.srt') and not p.name.endswith('.credits.txt')):
        raise HTTPException(404, 'Clip tidak ditemukan.')
    if p.suffix == '.mp4':
        return FileResponse(p, media_type='video/mp4')
    return FileResponse(p, media_type='text/plain; charset=utf-8', filename=p.name)


from clipper.api_studio import install as install_studio4
studio4 = install_studio4(app, ROOT, base_cfg, JOB_STATE, PROCESS_LOCK)


if __name__ == '__main__':
    print('Clipper Studio Local 4.0 -> http://localhost:8765')
    uvicorn.run(app, host='127.0.0.1', port=8765, log_level='warning')
