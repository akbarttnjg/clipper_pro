"""Video comparisons: measured pixels and metadata, separate from human quality."""
import math
import json
import re
import subprocess
import time
from fractions import Fraction
from pathlib import Path
from .dependency_cache import content_id
from .storage import read_json
from .workflow6 import BRAND_FIELDS

CATEGORIES = ('talking_head','chart','board','multispeaker','graphics')


def media_info(path):
    path=Path(path).expanduser().resolve()
    if not path.is_file():raise ValueError('Video pembanding tidak ditemukan.')
    try:
        raw=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=30)
        p=json.loads(raw.stdout)
    except (subprocess.SubprocessError,ValueError) as exc:raise ValueError('Metadata video tidak dapat dibaca.') from exc
    v=next((s for s in p.get('streams',[]) if s.get('codec_type')=='video'),None)
    if not v:raise ValueError('Berkas pembanding tidak memiliki video.')
    duration=float(v.get('duration') or p.get('format',{}).get('duration',0))
    fps=str(v.get('avg_frame_rate') or v.get('r_frame_rate','0/1'))
    if not math.isfinite(duration) or duration<=0 or Fraction(fps)<=0:raise ValueError('Durasi/FPS video pembanding tidak valid.')
    return {'width':int(v['width']),'height':int(v['height']),'duration':duration,'fps':fps,
        'audio_tracks':sum(s.get('codec_type')=='audio' for s in p['streams'])}


def validate_record(row):
    for key in ('baseline','candidate'):
        if content_id(row[key]['path'],fresh=True)!=row[key]['content_id']:
            raise ValueError('Isi video pembanding berubah; ukur kembali sebelum memakai penilaiannya.')


def compare(baseline,candidate,*,category,label='',context=None,candidate_settings=None,progress=lambda p,m:None):
    if category not in CATEGORIES:raise ValueError('Kategori evaluasi tidak valid.')
    rows=[]
    for path in (baseline,candidate):
        path=Path(path).expanduser().resolve()
        rows.append({'path':str(path),'content_id':content_id(path,fresh=True),'media':media_info(path)})
    a,b=[r['media'] for r in rows]
    if [a['width'],a['height']]!=[b['width'],b['height']] or Fraction(a['fps'])!=Fraction(b['fps']):
        raise ValueError('Resolusi dan FPS pembanding harus sama; jangan menyamarkan perubahan layout dengan scaling.')
    tolerance=max(.05,1/float(Fraction(a['fps'])))
    if abs(a['duration']-b['duration'])>tolerance:raise ValueError('Durasi pembanding berbeda; gunakan potongan cerita yang sama.')
    seconds=min(a['duration'],b['duration'],60.)
    # Use the same time base/PTS and pixel format; no frame interpolation or resizing.
    base='[0:v]settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p,split=2[a][c];[1:v]settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p,split=2[b][d];[a][b]ssim=shortest=1[s];[c][d]psnr=shortest=1[p]'
    progress(10,'Membandingkan frame pada waktu, FPS dan ukuran yang sama')
    started=time.monotonic()
    proc=subprocess.run(['ffmpeg','-nostdin','-v','info','-threads','1','-i',rows[0]['path'],'-threads','1','-i',rows[1]['path'],
        '-filter_complex_threads','1','-filter_complex',base,'-map','[s]','-map','[p]','-t',str(seconds),'-f','null','-'],
        capture_output=True,text=True,timeout=240)
    if proc.returncode:raise ValueError('Perbandingan frame gagal: '+proc.stderr[-1600:])
    ssim=re.findall(r'All:([0-9.]+)',proc.stderr);psnr=re.findall(r'average:([0-9.]+|inf)',proc.stderr)
    if not ssim or not psnr:raise ValueError('FFmpeg tidak menghasilkan SSIM/PSNR.')
    value={'baseline':rows[0],'candidate':rows[1],'category':category,'label':str(label)[:160],
        'context':context or {},'candidate_settings':candidate_settings or {},
        'ssim':float(ssim[-1]),'psnr_db':None if psnr[-1]=='inf' else float(psnr[-1]),
        'psnr_infinite':psnr[-1]=='inf','sampled_seconds':seconds,'wall_seconds':time.monotonic()-started,
        'full_duration_compared':max(a['duration'],b['duration'])<=seconds+tolerance,
        'quality_status':'human_review_required','limitations':['SSIM/PSNR mengukur perbedaan piksel, bukan estetika, akurasi ASR atau kejelasan dialog.',
            'Pengukuran dibatasi 60 detik pertama; periksa akhir cerita dan audio secara manual.']}
    validate_record(value);progress(90,'Ukuran dan identitas video diperiksa; penilaian manusia belum diisi')
    return value


def artifact_pair(service,pid,options):
    ids=[options.get('baseline_id'),options.get('candidate_id')]
    if not all(isinstance(i,str) for i in ids) or ids[0]==ids[1]:raise ValueError('Pilih dua hasil tersimpan yang berbeda.')
    rows=service.store.artifacts(pid,limit=100);pair=[]
    for key in ids:
        row=next((r for r in rows if r['id']==key),None)
        if not row:raise ValueError('Hasil pembanding tidak ditemukan.')
        result=row['data'];context=result.get('evaluation_context')
        if not context:raise ValueError('Hasil lama belum memiliki konteks evaluasi; buat dua preview baru pada Tahap 6.')
        path=Path(result.get('absolute_file',''))
        if content_id(path,fresh=True)!=result.get('output_content_id'):raise ValueError('Berkas pembanding berubah.')
        pair.append((row,result,context))
    if pair[0][2]!=pair[1][2]:raise ValueError('Pembanding harus memakai sumber, transkrip, potongan, kata, audio dan rasio yang sama.')
    settings={k:v for k,v in pair[1][1].get('evaluation_settings',{}).items() if k in BRAND_FIELDS}
    return pair,settings


def evaluate_artifacts(service,pid,options,progress=lambda p,m:None):
    pair,settings=artifact_pair(service,pid,options)
    value=compare(pair[0][1]['absolute_file'],pair[1][1]['absolute_file'],category=options.get('category'),
        label=options.get('label',''),context=pair[0][2],candidate_settings=settings,progress=progress)
    value.update(baseline_artifact=pair[0][0]['id'],candidate_artifact=pair[1][0]['id'])
    return value


def quality_summary(service,pid):
    doc=service.store.get(pid);evaluations=service.workspace.rows('evaluations6',pid);feedback=service.workspace.rows('feedback6',pid)
    rows=[]
    for category in CATEGORIES:
        matches=[r for r in evaluations if r['category']==category]
        rows.append({'category':category,'comparisons':len(matches),'human_reviews':sum(f['evaluation_id'] in {e['id'] for e in matches} for f in feedback)})
    return {'categories':rows,'human_feedback':feedback,
        'correction_patches':len(doc.get('shared_corrections',{}))+sum(len(c) for c in doc.get('clip_corrections',{}).values()),
        'readability_issues':[{'clip_id':c,'variant_id':v,'issues':x.get('style_report',{}).get('issue_count'),
            'stale':x.get('style_dependency')!=service.dependency(doc,c,v)} for c,clip in doc['clips'].items() for v,x in clip['variants'].items()],
        'jobs':[{'id':j['id'],'kind':j['kind'],'status':j['status'],'resources':(j.get('result') or {}).get('resource_metrics')}
            for j in service.queue.list(pid)],
        'note':'Jumlah kandidat bukan keberagaman makna; isi kolom cerita unik setelah meninjau sumber. RAM/VRAM kosong berarti belum terukur.'}
