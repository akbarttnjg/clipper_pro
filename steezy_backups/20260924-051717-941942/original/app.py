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
from clipper import pipeline
from clipper.storage import read_json, write_json

BRAND_FILE = ROOT / 'brand.json'
base_cfg = replace(Config(), **validate_brand(read_json(BRAND_FILE, {})))
base_cfg = replace(base_cfg, work_dir=str((ROOT / base_cfg.work_dir).resolve()),
                   out_dir=str((ROOT / base_cfg.out_dir).resolve()))
app = FastAPI(title='Clipper Studio Local', version='2.0.0')
STATIC = ROOT / 'static'
UPLOADS = ROOT / 'uploads'
UPLOADS.mkdir(exist_ok=True)
STATES = Path(base_cfg.work_dir) / 'studio-jobs'
STATES.mkdir(parents=True, exist_ok=True)
JOBS, JOB_STATE = {}, {}
PROCESS_LOCK = threading.Lock()
STATE_LOCK = threading.RLock()
ACTIVE = {'queued', 'analyzing', 'rendering', 'previewing', 'exporting'}


def persist(job_id):
    with STATE_LOCK:
        st = JOB_STATE[job_id]
        write_json(STATES / f'{job_id}.json', {'job': JOBS[job_id], 'state': {
            **st, 'cfg': asdict(st['cfg']), 'edits': {str(k): v for k, v in st.get('edits', {}).items()}}})


def restore():
    for file in STATES.glob('*.json'):
        data = read_json(file)
        if not data:
            continue
        try:
            st, job = data['state'], data['job']
            st['cfg'] = Config(**{k: v for k, v in st['cfg'].items() if k in {f.name for f in fields(Config)}})
            st['edits'] = {int(k): v for k, v in st.get('edits', {}).items()}
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
            'elapsed': round(time.time() - job.get('started', time.time())) if job['status'] in ACTIVE else job.get('elapsed', 0)}


def worker(job_id, action, indices=None):
    with PROCESS_LOCK:
        st, job = state(job_id)
        job.update(status=action, started=time.time(), error=None)
        persist(job_id)
        def progress(percent, message):
            with STATE_LOCK:
                job.update(percent=percent, message=message)
        try:
            if action == 'analyzing':
                transcript, clips = pipeline.analyze(st['media'], st['cfg'], progress)
                st.update(transcript=transcript, scored=clips, edits={})
                job.update(status='review', percent=100, message='Periksa pembuka, penutup, dan teks; pilih clip untuk render.')
            elif action == 'rendering':
                for n, idx in enumerate(indices):
                    c = st['scored'][idx]
                    progress(round(100 * n / len(indices)), f'Render {n+1}/{len(indices)} — {c["title"]}')
                    cfg = replace(st['cfg'], **st.get('clip_settings', {}).get(str(idx), {}))
                    res = pipeline.render_clip(st['media'], st.get('edits', {}).get(idx, st['transcript']['words']),
                        c, pipeline.clip_name(c, idx), cfg)
                    job['clips'] = [r for r in job['clips'] if r.get('index') != idx] + [{**res, 'index': idx}]
                    job['clips'].sort(key=lambda r: r['index'])
                    persist(job_id)
                job.update(status='done', percent=100, message=f'{len(indices)} clip selesai. Hasil tersimpan di folder clips.')
            elif action == 'previewing':
                idx = indices[0]
                c = dict(st['scored'][idx])
                cfg = replace(st['cfg'], **st.get('clip_settings', {}).get(str(idx), {}))
                cfg = replace(cfg, preview_seconds=12, target_w=640 if cfg.target_w > cfg.target_h else 360,
                              target_h=360 if cfg.target_w > cfg.target_h else 640)
                result = pipeline.render_clip(st['media'], st.get('edits', {}).get(idx, st['transcript']['words']),
                                              c, 'preview-' + str(idx), cfg)
                job.update(status='review', percent=100, message='Preview 12 detik siap. Pilih tab Preview.',
                           preview={**result, 'index': idx})
            elif action == 'exporting':
                from clipper.projects import export_bundle
                selected = [r for r in job['clips'] if r.get('index') in indices]
                progress(10, 'Menyusun media, subtitle, dan proyek editable')
                result = export_bundle(selected, st['cfg'], progress)
                job.update(status='done', percent=100, message='Paket proyek editable siap.', export=result)
        except Exception as exc:
            job.update(status='error', error=str(exc), message='Proses terhenti; hasil clip yang sudah selesai tetap tersimpan.')
        finally:
            job['elapsed'] = round(time.time() - job['started'], 1)
            persist(job_id)


def enqueue(job_id, action, indices=None):
    _, job = state(job_id)
    if job['status'] in ACTIVE:
        raise HTTPException(409, 'Proyek ini masih diproses.')
    job.update(status='queued', percent=0, message='Menunggu giliran proses lokal', error=None, started=time.time())
    persist(job_id)
    threading.Thread(target=worker, args=(job_id, action, indices), daemon=True).start()


def new_job(path, options, music='', sfx=''):
    from clipper.ffmpeg_util import probe
    info = probe(str(path))
    if not info['has_audio']:
        raise HTTPException(400, 'File tidak mempunyai track suara.')
    job_id = uuid.uuid4().hex[:12]
    cfg = replace(base_cfg, job_id=job_id, music_path=music, sfx_path=sfx,
                  work_dir=str(Path(base_cfg.work_dir) / job_id), **validate_overrides(options))
    JOB_STATE[job_id] = {'cfg': cfg, 'media': str(Path(path).resolve()), 'transcript': {},
                         'scored': [], 'edits': {}, 'clip_settings': {}, 'source_info': info}
    JOBS[job_id] = {'status': 'new', 'percent': 0, 'message': '', 'clips': [], 'error': None,
                    'name': Path(path).name, 'created': time.time(), 'elapsed': 0}
    enqueue(job_id, 'analyzing')
    return {'job': job_id}


@app.get('/', response_class=HTMLResponse)
def index():
    return (STATIC / 'index.html').read_text(encoding='utf-8')


@app.get('/api/jobs')
def jobs():
    return [{'id': j, 'name': v.get('name', j), 'status': v['status'], 'created': v.get('created', 0)}
            for j, v in sorted(JOBS.items(), key=lambda row: row[1].get('created', 0), reverse=True)]


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
        return new_job(dest, options, music, sfx)
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
    return {'clip': c, 'duration': st['transcript']['duration'], 'settings': asdict(cfg),
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
        lo, hi = min(w['start'] for w in words), max(w['end'] for w in words)
        outside = [w for w in existing if w['end'] <= lo or w['start'] >= hi]
        combined = sorted(outside + words, key=lambda w: w['start'])
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
        overrides = validate_overrides(settings)
        st.setdefault('edits', {})[idx] = combined
        st['scored'][idx] = c
        st.setdefault('clip_settings', {})[str(idx)] = overrides
        job.pop('export', None)
        persist(job_id)
        return {'ok': True, 'revision': c['revision']}
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


@app.post('/api/render/{job_id}')
def render_selected(job_id: str, data: dict = Body(...)):
    st, _ = state(job_id)
    indices = selected_indices(data, st)
    for i in indices:
        st['scored'][i]['approved'] = True
    enqueue(job_id, 'rendering', indices)
    return {'ok': True}


@app.post('/api/preview/{job_id}/{idx}')
def preview(job_id: str, idx: int):
    state(job_id, idx)
    enqueue(job_id, 'previewing', [idx])
    return {'ok': True}


@app.post('/api/export/{job_id}')
def export_selected(job_id: str, data: dict = Body(...)):
    st, job = state(job_id)
    indices = selected_indices(data, st)
    for i in indices:
        if not any(r.get('index') == i and r.get('revision') == st['scored'][i].get('revision', 0) for r in job['clips']):
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
    from clipper.ffmpeg_util import nvenc_diagnostic
    return {'nvenc': nvenc_diagnostic(), 'model': base_cfg.model, 'whisper': base_cfg.whisper_model,
            'version': '2.0.0', 'exports': {'resolve': 'XML + Lua, perlu uji di Resolve', 'capcut': 'multi-timeline + draft per clip, eksperimental'}}


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


@app.get('/clips/{name}')
def clip(name: str):
    p = Path(base_cfg.out_dir) / Path(name).name
    if not p.is_file() or p.suffix != '.mp4':
        raise HTTPException(404, 'Clip tidak ditemukan.')
    return FileResponse(p, media_type='video/mp4')


if __name__ == '__main__':
    print('Clipper Studio Local 2.0 -> http://localhost:8765')
    uvicorn.run(app, host='127.0.0.1', port=8765, log_level='warning')
