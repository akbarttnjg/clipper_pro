"""Measured probes, GPU fallback and calibration executed outside the web UI."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time
from .catalog import get
from .state import read, write, digest
from .install import run, interpreter, api
from .gpu import GPULease
from .download import Canceled


def gpu_snapshot():
    if not shutil.which('nvidia-smi'):return []
    try:
        result=subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.total,memory.used,driver_version','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=6)
        if result.returncode:return []
        return [dict(index=int(parts[0]),name=parts[1].strip(),total_mb=int(parts[2]),used_mb=int(parts[3]),driver=parts[4].strip())
                for line in result.stdout.splitlines() if len(parts:=line.split(','))==5]
    except (OSError,ValueError,subprocess.SubprocessError):return []


class GPUMonitor:
    def __init__(self):self.stop=threading.Event();self.peak=[];self.thread=None;self.baseline=[]
    def __enter__(self):
        self.baseline=gpu_snapshot();self.peak=[r['used_mb'] for r in self.baseline]
        if self.baseline:
            self.thread=threading.Thread(target=self.sample,daemon=True);self.thread.start()
        return self
    def sample(self):
        while not self.stop.wait(.75):
            rows=gpu_snapshot()
            for i,row in enumerate(rows):
                if i<len(self.peak):self.peak[i]=max(self.peak[i],row['used_mb'])
    def __exit__(self,*exc):
        self.stop.set()
        if self.thread:self.thread.join(timeout=7)
    def result(self):
        return dict(baseline=self.baseline,peak_used_mb=self.peak,method='nvidia-smi sampling 0.75s; includes other processes',measured=bool(self.baseline))


def probe_generation(manager,job,directory,receipt,*,sample):
    key=job['component'];item=get(key);jid=job['id'];directory=Path(directory)
    if item['kind']=='node':return node_probe(manager,job,directory,sample=sample)
    py=interpreter(directory) if item['kind'] in ('pip','source') else Path(sys.executable)
    if not py.is_file():raise ValueError('Interpreter lingkungan komponen tidak tersedia')
    device=job['options'].get('device','cpu')
    if sample and device=='cuda' and not gpu_snapshot():device='cpu'
    request=dict(component=key,directory=str(directory),repo=str(manager.repo),sample=sample,device=device,source=job['options'].get('source'),resolution=job['options'].get('resolution',336))
    request_file=manager.root/'requests'/(jid+'.json');response_file=request_file.with_suffix('.result.json');write(request_file,request)
    environment={**os.environ,'PYTHONNOUSERSITE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false','OMP_NUM_THREADS':'4'}
    if key=='pyannote':environment['HF_HUB_CACHE']=str(directory/'hf-cache');environment['HUGGINGFACE_HUB_CACHE']=str(directory/'hf-cache')
    environment.pop('PYTHONPATH',None)
    # Keep DLL paths local to the isolated environment on Windows.
    if os.name=='nt':
        sites=directory/'env/Lib/site-packages/nvidia'
        dlls=[str(sites/name/'bin') for name in ('cublas','cudnn') if (sites/name/'bin').is_dir()]
        environment['PATH']=os.pathsep.join(dlls+[environment.get('PATH','')])
    attempts=[]
    with GPULease(manager.root,'komponen '+key,canceled=lambda:manager.canceled(jid),waiting=lambda:manager.update(jid,message='Menunggu GPU: model lain masih bekerja')):
        for selected in [device]+(['cpu'] if device=='cuda' else []):
            request['device']=selected;write(request_file,request);response_file.unlink(missing_ok=True)
            started=time.monotonic()
            with GPUMonitor() as monitor:
                try:run([py,manager.repo/'clipper/runtime/probe.py',request_file,response_file],manager,jid,env=environment,timeout=1200 if sample else 120)
                except (RuntimeError,TimeoutError) as exc:
                    if not response_file.exists():write(response_file,dict(passed=False,level='sample' if sample else 'import',detail=str(exc),device=selected))
            result=read(response_file,dict(passed=False,level='import',detail='Worker tidak menulis hasil'))
            result['memory']=monitor.result();result['elapsed_seconds']=round(time.monotonic()-started,3);attempts.append(result)
            if result.get('passed'):break
            # Retry only device/runtime failures, not a missing model or a faulty algorithm.
            if not any(s in result.get('detail','').lower() for s in ('cuda','out of memory','cudnn','cublas','gpu')):break
    if len(attempts)>1:result['fallback']={'from':'cuda','to':'cpu','reason':attempts[0].get('detail'),'failed_attempt_memory':attempts[0].get('memory')}
    result['tested_at']=time.time();return result


def node_probe(manager,job,directory,*,sample):
    receipt=read(directory/'receipt.json',{});versions=receipt.get('versions',{});node=versions.get('node') or shutil.which('node')
    if not node:raise ValueError('Node.js belum tersedia')
    folder=directory/'node';key=job['component'];jid=job['id'];started=time.monotonic()
    environment={**os.environ,'PATH':str(Path(node).parent)+os.pathsep+os.environ.get('PATH','')}
    run([node,'-e','const p=require("./node_modules/'+('remotion' if key=='remotion' else '@motion-canvas/core')+'/package.json"); console.log(p.version)'],manager,jid,cwd=folder,env=environment,timeout=60)
    result=dict(passed=True,level='import',detail='Versi paket Node berhasil dibaca; render belum diuji',duration_seconds=round(time.monotonic()-started,3),artifacts=[])
    if not sample:return result
    with GPULease(manager.root,'render '+key,canceled=lambda:manager.canceled(jid)):
        if key=='remotion':
            cli=folder/'node_modules/@remotion/cli/remotion-cli.js';out=folder/'output';out.mkdir(exist_ok=True)
            run([node,cli,'still','src/index.ts','ClipperSample','output/preview.png','--frame=12','--concurrency=1'],manager,jid,cwd=folder,env=environment,timeout=600)
            run([node,cli,'render','src/index.ts','ClipperSample','output/sample.mp4','--concurrency=1'],manager,jid,cwd=folder,env=environment,timeout=600)
            info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(out/'sample.mp4')],text=True,timeout=20))
            if not any(s.get('width')==320 and s.get('height')==180 for s in info['streams']):raise ValueError('Render Remotion bukan ukuran sampel')
            result.update(level='sample',detail='Preview PNG dan render MP4 24 frame berhasil',artifacts=['node/output/preview.png','node/output/sample.mp4'])
        else:
            run([node,folder/'node_modules/vite/bin/vite.js','build'],manager,jid,cwd=folder,env=environment,timeout=180)
            if not list((folder/'dist').rglob('*.js')):raise ValueError('Build Motion Canvas tidak menghasilkan JavaScript')
            result.update(level='build',detail='Proyek animasi Motion Canvas berhasil dikompilasi. Render browser belum diverifikasi; buka proyek melalui script preview.',artifacts=['node/dist/index.html'])
    result['duration_seconds']=round(time.monotonic()-started,3);return result


def ram_bytes():
    if os.name=='nt':
        import ctypes
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),*[(n,ctypes.c_ulonglong) for n in ('total_phys','avail_phys','total_page','avail_page','total_virtual','avail_virtual','avail_extended')]]
        value=Memory();value.length=ctypes.sizeof(value)
        return int(value.total_phys) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)) else None
    try:return os.sysconf('SC_PAGE_SIZE')*os.sysconf('SC_PHYS_PAGES')
    except (ValueError,OSError,AttributeError):return None


def calibrate(manager,job):
    manager.update(job['id'],progress=10,message='Membaca perangkat dan mengukur encode video pendek')
    output=manager.root/'calibration';output.mkdir(exist_ok=True);gpu=gpu_snapshot();benchmarks=[]
    with GPULease(manager.root,'kalibrasi',canceled=lambda:manager.canceled(job['id'])):
        for codec in ('libx264','h264_nvenc'):
            start=time.monotonic();target=output/(codec+'.mp4')
            cmd=['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=30:duration=2','-c:v',codec,'-threads','2',str(target)]
            with GPUMonitor() as monitor:
                try:
                    if manager.canceled(job['id']):raise Canceled('Kalibrasi dibatalkan')
                    result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
                    passed=result.returncode==0 and target.is_file() and target.stat().st_size>0
                    error=None if passed else result.stderr[-1200:]
                except (OSError,subprocess.SubprocessError) as exc:passed=False;error=str(exc)
            benchmarks.append(dict(codec=codec,passed=passed,seconds=round(time.monotonic()-start,3),frames=60,dimensions=[640,360],error=error,memory=monitor.result()))
    nvenc=next((b['passed'] for b in benchmarks if b['codec']=='h264_nvenc'),False)
    hardware=dict(measured_at=time.time(),os=platform.platform(),cpu=platform.processor() or platform.machine(),cpu_threads=os.cpu_count(),
                  ram_bytes=ram_bytes(),free_bytes=shutil.disk_usage(manager.root).free,gpus=gpu,benchmarks=benchmarks,
                  python=sys.version,component_measurements={r['id']:r['test'] for r in manager.snapshot()['components'] if r['test']},
                  scope='Encode pendek dan uji komponen tercatat; throughput video panjang/model yang belum diuji tidak diasumsikan.')
    write(manager.root/'hardware.json',hardware)
    # A short NVENC test cannot establish CUDA ASR memory safety.
    asr=manager.active('faster-whisper');test=(asr or {}).get('test',{})
    cuda_safe=bool(test.get('passed') and test.get('level')=='sample' and test.get('device')=='cuda' and not test.get('fallback'))
    profiles={name:dict(device='cuda' if cuda_safe else 'cpu',batch_size=1,concurrency=1,
                        sample_resolution=res,use_nvenc=nvenc,recommendation=why,measured_cuda_asr=cuda_safe)
              for name,res,why in [('fast',224,'Uji gambar kecil; satu worker GPU.'),('balanced',336,'Satu worker; CPU sampai uji CUDA ASR sendiri lulus.'),('detail',448,'Resolusi uji lebih besar; komponen berat tetap dijalankan bergantian.') ]}
    write(manager.root/'profiles.json',profiles);return hardware


def execute(manager,job):
    from .install import install
    action=job['action'];key=job['component']
    if action=='install':return install(manager,job)
    if action=='rollback':return manager.rollback(key)
    if action=='calibrate':return calibrate(manager,job)
    active=manager.active(key)
    if not active:raise ValueError('Pasang/daftarkan komponen terlebih dahulu')
    directory=Path(active['directory']);result=probe_generation(manager,job,directory,active,sample=action=='sample')
    receipt=read(directory/'receipt.json')
    if action=='probe':
        receipt['diagnostic']=result
        if not result.get('passed') or receipt.get('test',{}).get('level')!='sample':receipt['test']=result
    else:receipt['test']=result
    write(directory/'receipt.json',receipt)
    if not result.get('passed'):raise RuntimeError(result.get('detail','Uji komponen belum lulus'))
    return result
