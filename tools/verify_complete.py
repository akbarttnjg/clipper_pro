"""Local acceptance and measured two-ratio benchmark. No model downloads.

Run in the existing app .venv. Default is a diagnostic; --alignment measures
saved corrections without publishing timing changes. --benchmark explicitly
renders selected clips and records resources, then measures cache reuse.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]


def save(path,report):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.replace(path)


def diagnostics(cfg):
    from clipper.runtime.state import runtime_root,read,safe_path
    from clipper.speech_jobs import alignment_availability
    from clipper.font_catalog import FONTS
    from clipper.caption_renderer import readiness
    components=[];root=Path(cfg.visual_runtime_root) if cfg.visual_runtime_root else runtime_root(ROOT,Path(cfg.work_dir))
    for pointer in sorted((root/'components').glob('*/active.json')):
        try:
            active=read(pointer,{}) or {};folder=safe_path(root/'generations',active['generation']);receipt=read(folder/'receipt.json',{}) or {}
            components.append({'component':pointer.parent.name,'generation':active['generation'],'installed':receipt.get('installed',False),
                'test':receipt.get('test',{}),'note':'Receipt uji sebelumnya; tidak dianggap pengukuran setelah pembaruan.'})
        except (ValueError,KeyError,OSError,TypeError) as exc:components.append({'component':pointer.parent.name,'error':str(exc)})
    modules={name:bool(importlib.util.find_spec(name)) for name in ('fastapi','requests','PIL','cv2','numpy','multipart','dotenv','pycapcut','faster_whisper')}
    disk=shutil.disk_usage(ROOT)
    fonts={name:(Path(cfg.fonts_dir)/item['file']).is_file() for name,item in FONTS.items()}
    hardware={'logical_cpus':os.cpu_count(),'free_disk_gib':round(disk.free/1024**3,2),'gpu':None}
    if shutil.which('nvidia-smi'):
        try:
            p=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],capture_output=True,text=True,timeout=8)
            if p.returncode==0:hardware['gpu']=p.stdout.strip()
        except (OSError,subprocess.SubprocessError):pass
    try:
        import psutil
        hardware['ram_gib']=round(psutil.virtual_memory().total/1024**3,2)
    except ImportError:hardware['ram_gib']=None
    return {'modules':modules,'ffmpeg':shutil.which('ffmpeg'),'ffprobe':shutil.which('ffprobe'),
            'fonts':fonts,'hardware':hardware,'components':components,'alignment':alignment_availability(cfg),
            'caption_renderer':readiness(cfg),'native_editors':{'capcut':'not_tested','resolve':'not_tested'},
            'note':'Ketersediaan komponen tidak membuktikan mutu atau keberhasilan render.'}


def choose_project(service,pid):
    if pid:return service.store.get(pid)
    for row in service.store.list():
        doc=service.store.get(row['project_id'])
        if doc.get('transcript_id'):return doc
    raise ValueError('Belum ada proyek bertanskrip. Analisis sumber dahulu, atau gunakan --project ID.')


def alignment_check(service,doc):
    from clipper import speech_jobs
    from clipper.transcript_correction import source_ids
    pid=doc['project_id'];reports=[]
    for cid in [None,*list(doc.get('clips',{}))]:
        transcript=service.transcript(doc,cid)
        rows=[w for w in transcript['words'] if (w.get('correction') or w.get('manually_edited') or len(w['word'].split())>1) and not w.get('aligned_words')]
        if cid:rows=[w for w in rows if w['end']>doc['clips'][cid]['start'] and w['start']<doc['clips'][cid]['end']]
        if not rows:continue
        cfg=service.config(doc,cid,'portrait' if cid else None)
        source=doc['source'].get('media_context',{}).get('payload',{}).get('working_path',doc['source']['path'])
        response=speech_jobs.run('alignment',source,transcript,cfg,{'limit':12,'origin_word_ids':source_ids(rows)[:80]})
        reports.append({'clip_id':cid,'report':response['report'],'patch_count':len(response['patches']),
            'published':False,'note':'Timing hasil uji tidak mengganti koreksi tersimpan.'})
        break
    return reports or [{'status':'no_candidates','aligned':0,'note':'Tidak ada koreksi yang memerlukan alignment; model belum diuji.'}]


def benchmark(service,doc):
    from clipper import batch7
    from clipper.studio_worker import execute
    from clipper.metrics6 import ResourceMeter
    pid=doc['project_id'];started=time.monotonic();meter=ResourceMeter(os.getpid());done=threading.Event()
    def sample():
        while not done.is_set():meter.sample();done.wait(.2)
    thread=threading.Thread(target=sample,daemon=True);thread.start();runs=[]
    try:
        for target in batch7.targets(doc):
            current=service.store.get(pid)
            job=service.enqueue(pid,'render',target['clip_id'],target['variant_id'],current['revision'],{'force':True})
            service.queue.update(job['id'],status='running')
            at=time.monotonic()
            try:
                result=execute(service,job)
                runs.append({**target,'wall_seconds':round(time.monotonic()-at,3),'duration':result.get('length'),
                    'output_content_id':result.get('output_content_id'),'warnings':result.get('warnings',[])})
            except Exception as exc:
                service.queue.update(job['id'],status='failed',error=str(exc));raise
        rendered=round(time.monotonic()-started,3);at=time.monotonic()
        current=service.store.get(pid);reuse=service.enqueue_batch(pid,current['revision'])
        return {'source_duration_seconds':doc['source']['info']['duration'],'render_seconds':rendered,'runs':runs,
            'cache_reuse_seconds':round(time.monotonic()-at,3),'reused_final_count':len(reuse['skipped']),
            'unexpected_render_jobs':len(reuse['jobs']),'resources':meter.report(),
            'measurement_scope':'Fresh video renders with existing transcript, models, and voice/vision caches. ASR/discovery and native import excluded.',
            'under_30_minutes':rendered<1800,'note':'Nilai ini untuk proyek dan klip yang diuji, bukan jaminan video lain atau pemrosesan penuh.'}
    finally:done.set();thread.join(timeout=2)


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--project');parser.add_argument('--alignment',action='store_true')
    parser.add_argument('--benchmark',action='store_true');parser.add_argument('--output',type=Path);args=parser.parse_args(argv)
    sys.path.insert(0,str(ROOT));os.chdir(ROOT)
    report={'version':'4.0.9','timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'python':sys.executable,'errors':[]}
    output=args.output or ROOT/'work'/'verification'/('complete-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT/'.env');load_dotenv(ROOT/'.env.pro',override=True)
        from clipper.config import Config
        cfg=Config();cfg.work_dir=str((ROOT/cfg.work_dir).resolve());cfg.out_dir=str((ROOT/cfg.out_dir).resolve())
        report['diagnostics']=diagnostics(cfg)
        if args.alignment or args.benchmark:
            # The GUI must release its GPU/process ownership before offline QA.
            try:
                with socket.create_connection(('127.0.0.1',8765),timeout=.3):raise ValueError('Tutup server Clipper dengan Ctrl+C sebelum uji offline.')
            except (ConnectionRefusedError,socket.timeout,OSError):pass
            from clipper.studio_service import StudioService
            service=StudioService(ROOT,cfg,autostart=False,recover=False);doc=choose_project(service,args.project)
            report['project_id']=doc['project_id']
            if args.alignment:report['alignment_test']=alignment_check(service,doc)
            if args.benchmark:report['benchmark']=benchmark(service,doc)
    except Exception as exc:report['errors'].append(str(exc))
    diagnostic=report.get('diagnostics',{})
    required=('fastapi','requests','PIL','cv2','numpy','multipart','dotenv')
    missing=[k for k in required if not diagnostic.get('modules',{}).get(k)]
    if diagnostic and missing:report['errors'].append('Modul aplikasi belum tersedia: '+', '.join(missing))
    if diagnostic and (not diagnostic.get('ffmpeg') or not diagnostic.get('ffprobe')):report['errors'].append('FFmpeg atau FFprobe tidak tersedia.')
    if args.alignment and any(r.get('report',{}).get('errors') for r in report.get('alignment_test',[])):
        report['errors'].append('Ada rentang alignment yang ditolak; periksa diagnosis setiap rentang.')
    report['status']='needs_attention' if report['errors'] else 'diagnostic_completed'
    save(output,report)
    print('Laporan: '+str(output));print('Status: '+report['status'])
    for error in report['errors']:print('Perlu diperiksa: '+error)
    return 1 if report['errors'] else 0


if __name__=='__main__':raise SystemExit(main())
