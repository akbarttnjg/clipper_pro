"""Bounded CPU sampling of source frames, OCR and audio energy.

    OCR coordinates are in decoded-source pixels, never caption/output pixels.
    Samples are evidence, not a claim that every frame has been inspected.
"""
import difflib
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from .storage import read_json, write_json

VERSION = 'evidence-1'


def cache_path(cfg):
    return Path(cfg.work_dir) / 'source-evidence.json'


def load(cfg):
    return read_json(cache_path(cfg), {}) or {}


def frame_rows(frame, engine):
    import cv2
    h, w = frame.shape[:2]
    scale = min(1., 1100/max(w,h))
    small = cv2.resize(frame, (round(w*scale), round(h*scale))) if scale < 1 else frame
    result, _ = engine(small)
    rows = []
    for polygon, text, confidence in result or []:
        if confidence < .72 or not str(text).strip():
            continue
        xs, ys = [p[0]/scale for p in polygon], [p[1]/scale for p in polygon]
        rows.append({'text': str(text)[:240], 'confidence': round(float(confidence),3),
                     'box': [max(0., min(xs)), max(0., min(ys)), min(float(w),max(xs))-max(0.,min(xs)),
                             min(float(h),max(ys))-max(0.,min(ys))]})
    return rows


def audio_cues(media, duration):
    import numpy as np
    # Streaming RMS uses a constant amount of RAM, even for long recordings.
    command = ['ffmpeg','-nostdin','-v','error','-i',str(media),'-vn','-ac','1','-ar','8000','-f','s16le','-']
    levels = []
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        while True:
            block = proc.stdout.read(32000)
            if not block:
                break
            values = np.frombuffer(block[:len(block)//2*2], dtype='<i2').astype(float)/32768
            levels.append(float(np.sqrt(np.mean(values**2))) if len(values) else 0.)
    if not levels:
        return []
    typical = float(np.median([x for x in levels if x > .0001])) if max(levels) > .0001 else 0
    rows = []
    for i in range(1,len(levels)):
        if typical and levels[i] > typical*1.65 and levels[i] > levels[i-1]*1.5:
            rows.append({'time': i*2., 'kind': 'audio_emphasis', 'strength': round(levels[i]/typical,2)})
        elif levels[i-1] < max(.002,typical*.15) and levels[i] > max(.006,typical*.5):
            rows.append({'time': i*2., 'kind': 'speech_restart', 'strength': 1.})
    return rows[:240]


def scan(media, cfg, duration, progress=lambda p,m: None, *, input_fingerprint=None,cancellation_token=None):
    from .analysis_options import configured
    cfg=configured(cfg) if cfg is not None else None
    import cv2
    import numpy as np
    p = Path(media)
    if not p.is_file():
        return {'version':VERSION,'frames':[],'cues':[],'ocr_status':'unavailable',
                'warnings':['Sumber tidak tersedia untuk pembacaan materi.'],'coverage':'unavailable'}
    stat = p.stat()
    key = hashlib.sha256(json.dumps([str(p.resolve()),stat.st_size,stat.st_mtime_ns,
        cfg.ocr_enabled,cfg.visual_cues,cfg.ocr_max_frames,cfg.ocr_interval_s,VERSION,input_fingerprint]).encode()).hexdigest()
    cached = load(cfg)
    if cached.get('key') == key:
        return {**cached, 'cache_reused': True}
    started = time.monotonic()
    data = {'version':VERSION,'key':key,'source':str(p.resolve()),'duration':duration,'frames':[],
            'cues':[],'warnings':[],'ocr_status':'disabled','coordinate_space':'decoded_source_pixels'}
    engine = None
    if cfg.ocr_enabled:
        try:
            from rapidocr_onnxruntime import RapidOCR
            engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
            data['ocr_status'] = 'ready'
        except (ImportError, RuntimeError, OSError) as exc:
            data['ocr_status'] = 'unavailable'
            data['warnings'].append('OCR belum tersedia: '+str(exc)[:200])
    if cfg.ocr_enabled or cfg.visual_cues:
        count = max(1,min(cfg.ocr_max_frames, int(duration/max(1.,cfg.ocr_interval_s))+1))
        sample_times = np.linspace(min(.25,duration/2),max(0,duration-.25), count)
        cap = cv2.VideoCapture(str(media))
        previous, previous_text = None, set()
        try:
            for index, t in enumerate(sample_times):
                from .analysis_options import checkpoint
                checkpoint(cancellation_token)
                cap.set(cv2.CAP_PROP_POS_MSEC,float(t)*1000)
                ok, frame = cap.read()
                if not ok:
                    continue
                h,w = frame.shape[:2]
                try:
                    rows = frame_rows(frame,engine) if engine else []
                except (RuntimeError,ValueError,OSError) as exc:
                    rows = []
                    data['ocr_status'] = 'partial'
                    data['warnings'].append(f'OCR sampel {index+1} gagal: {str(exc)[:120]}')
                gray = cv2.cvtColor(cv2.resize(frame,(128,72)),cv2.COLOR_BGR2GRAY)
                tokens = set(re.findall(r'\w+', ' '.join(r['text'] for r in rows).lower()))
                delta = float(np.mean(cv2.absdiff(gray,previous)))/255 if previous is not None else 0
                if cfg.visual_cues and previous is not None:
                    changed = len(tokens ^ previous_text)/max(1,len(tokens|previous_text))
                    if delta > .13 or (len(tokens) > 2 and changed > .6):
                        data['cues'].append({'time':round(float(t),3),'kind':'slide_or_scene_change',
                                             'strength':round(max(delta,changed),3),'sample_interval_s':round(duration/max(1,count-1),2)})
                data['frames'].append({'time':round(float(t),3),'width':w,'height':h,'texts':rows})
                previous, previous_text = gray, tokens
                progress(round(32+index/max(1,count)*8),f'Membaca materi: sampel {index+1}/{count}')
        finally:
            cap.release()
        if cfg.visual_cues:
            try:
                data['cues'] += audio_cues(media,duration)
            except (OSError, subprocess.SubprocessError) as exc:
                data['warnings'].append('Petunjuk audio tidak tersedia: '+str(exc)[:160])
    data.update(seconds=round(time.monotonic()-started,2),sample_count=len(data['frames']),
                coverage='sampled',cache_reused=False,input_fingerprint=input_fingerprint,
                identity_status='provided_by_media_service' if input_fingerprint else 'legacy_metadata_only')
    write_json(cache_path(cfg),data)
    return data


def suggestions(words, evidence):
    from .transcript_correction import norm, PROTECTED, BUILTINS
    found = {}
    for frame in evidence.get('frames',[]):
        terms = [(term,row) for row in frame['texts'] for term in re.findall(r'[\w-]+',row['text']) if len(term)>2]
        for word in words:
            if abs((word['start']+word['end'])/2-frame['time']) > 8 or word.get('manually_edited'):
                continue
            token = norm(word['word'])
            if re.search(r'\d',token) or token in PROTECTED:
                continue
            for term, row in terms:
                normalized = norm(term)
                if normalized == token or re.search(r'\d',term) or normalized in PROTECTED:
                    continue
                known = any(normalized == norm(c) and token in [norm(a) for a in aliases] for c,aliases in BUILTINS.items())
                similarity = difflib.SequenceMatcher(None,token,normalized).ratio()
                if not known and similarity < .70:
                    continue
                key = (word.get('word_id'),normalized)
                found[key] = {'word_id':word.get('word_id'),'text':word['word'],'start':word['start'],'end':word['end'],
                    'suggestions':[term],'reason':'Tulisan slide berbeda; cocokkan dengan audio sebelum menerima',
                    'evidence':'ocr','ocr':{'text':row['text'],'time':frame['time'],'box':row['box'],
                    'width':frame['width'],'height':frame['height'],'confidence':row['confidence']},
                    'listen_start':max(0,word['start']-2),'listen_end':word['end']+2}
    return sorted(found.values(),key=lambda r:r['start'])


def protected_boxes(evidence, start, end, width, height):
    """Use nearby observations only; don't carry the old slide across a cut."""
    rows = [f for f in evidence.get('frames',[]) if start-.4 <= f['time'] <= end+.4
            and f['width'] == width and f['height'] == height]
    return [r['box'] for f in rows for r in f['texts'] if r['confidence'] >= .8]
