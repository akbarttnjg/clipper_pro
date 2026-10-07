"""Persistent optional worker queue and immutable environment generations."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from . import VERSION
from .catalog import CATALOG, get, stock_status
from .state import read, write, runtime_root, safe_path, digest
from .gpu import owner
from ..job_queue import process_birth, terminate_owned

ACTIVE=('queued','running','cancel_requested')
ACTIONS=('install','probe','sample','calibrate','rollback')


class RuntimeManager:
    def __init__(self, repo, root=None, *, autostart=True, recover=True):
        self.repo=Path(repo).resolve();self.root=Path(root or runtime_root(repo)).resolve()
        self.root.mkdir(parents=True,exist_ok=True);self.db=self.root/'runtime.sqlite3'
        self.autostart=autostart;self.stop_event=threading.Event();self.thread=None;self.guard=threading.Lock()
        self.queue_owner=uuid.uuid4().hex
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,component TEXT,action TEXT,status TEXT,progress REAL,message TEXT,options TEXT,result TEXT,error TEXT,created REAL,updated REAL,pid INTEGER,birth TEXT,owner TEXT)')
            if recover:
                for row in db.execute("SELECT id,pid,birth FROM jobs WHERE status IN ('running','cancel_requested')").fetchall():
                    if not row['pid'] or process_birth(row['pid'])!=row['birth']:
                        db.execute("UPDATE jobs SET status='interrupted',message='Proses terhenti. Pilih Lanjutkan; rencana dan unduhan parsial tetap tersedia.',updated=? WHERE id=?",(time.time(),row['id']))
        if autostart:self.start()

    def connect(self):
        db=sqlite3.connect(self.db,timeout=15);db.row_factory=sqlite3.Row;return db

    def job(self,jid):
        with self.connect() as db:row=db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
        if not row:raise KeyError('Proses komponen tidak ditemukan')
        out=dict(row)
        for key in ('options','result'):out[key]=json.loads(out[key]) if out[key] else None
        return out

    def jobs(self):
        with self.connect() as db:rows=db.execute('SELECT id FROM jobs ORDER BY created DESC LIMIT 40').fetchall()
        return [self.job(row['id']) for row in rows]

    def update(self,jid,**values):
        allowed={'status','progress','message','result','error','pid','birth','owner'}
        if set(values)-allowed:raise ValueError('Atribut proses tidak dikenal')
        values['updated']=time.time()
        if 'result' in values:values['result']=json.dumps(values['result'],ensure_ascii=False,allow_nan=False)
        with self.connect() as db:
            db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),jid))

    def enqueue(self,component,action,options=None):
        if action not in ACTIONS:raise ValueError('Tindakan komponen tidak dikenal')
        if action!='calibrate':get(component)
        else:component='hardware'
        if options is not None and not isinstance(options,dict):raise ValueError('Pilihan proses harus berupa objek')
        options=dict(options or {})
        if set(options)-{'source','model','device'}:raise ValueError('Pilihan proses tidak dikenal')
        if options.get('model','small') not in ('small','medium'):raise ValueError('Model uji harus small atau medium')
        if options.get('device','cpu') not in ('cpu','cuda'):raise ValueError('Perangkat uji harus CPU atau CUDA')
        if options.get('source'):
            source=Path(options['source']).expanduser().resolve()
            if not source.is_file() or source.suffix.lower() not in ('.mp4','.mov','.mkv','.webm','.avi','.wav','.mp3','.flac','.m4a'):
                raise ValueError('Pilih sumber video atau audio lokal yang masih tersedia')
            options['source']=str(source)
        profile=read(self.root/'selected-profile.json',{'name':'balanced','device':'cpu','sample_resolution':336})
        options.setdefault('device',profile.get('device','cpu'))
        options.update(profile=profile.get('name','balanced'),resolution=profile.get('sample_resolution',336))
        jid='runtime-'+uuid.uuid4().hex;now=time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute("SELECT id FROM jobs WHERE component=? AND status IN ('queued','running','cancel_requested')",(component,)).fetchone()
            if prior:raise ValueError('Komponen ini masih mempunyai proses aktif')
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (jid,component,action,'queued',0,'Menunggu antrean',json.dumps(options),None,None,now,now,None,None,None))
        if self.autostart:self.start()
        return self.job(jid)

    def canceled(self,jid):return self.stop_event.is_set() or self.job(jid)['status']=='cancel_requested'

    def cancel(self,jid):
        row=self.job(jid)
        if row['status'] in ACTIVE:
            self.update(jid,status='canceled' if row['status']=='queued' else 'cancel_requested',message='Pembatalan diminta; unduhan parsial dipertahankan')
        return self.job(jid)

    def resume(self,jid):
        row=self.job(jid)
        if row['status'] not in ('interrupted','failed','canceled'):raise ValueError('Proses ini tidak perlu dilanjutkan')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT id FROM jobs WHERE component=? AND status IN ('queued','running','cancel_requested')",(row['component'],)).fetchone():raise ValueError('Komponen masih mempunyai proses aktif')
            db.execute("UPDATE jobs SET status='queued',error=NULL,pid=NULL,birth=NULL,owner=NULL,message='Melanjutkan rencana yang sama',updated=? WHERE id=?",(time.time(),jid))
        if self.autostart:self.start()
        return self.job(jid)

    def active(self,key):
        get(key);pointer=read(self.root/'components'/key/'active.json')
        if not pointer:return None
        generation=safe_path(self.root/'generations',pointer['generation'])
        receipt=read(generation/'receipt.json')
        if not receipt or receipt.get('component')!=key:raise ValueError('Receipt komponen tidak sesuai')
        return {**receipt,'generation':pointer['generation'],'directory':str(generation),'previous':pointer.get('previous')}

    def activate(self,key,generation,receipt):
        if receipt.get('component')!=key or not receipt.get('installed'):raise ValueError('Generasi belum selesai dipasang')
        pointer=self.root/'components'/key/'active.json';old=read(pointer,{})
        write(pointer,dict(generation=generation,previous=old.get('generation') if old.get('generation')!=generation else old.get('previous'),enabled=False))

    def rollback(self,key):
        pointer=self.root/'components'/key/'active.json';current=read(pointer,{})
        previous=current.get('previous')
        if not previous:raise ValueError('Belum ada generasi sebelumnya untuk dipulihkan')
        directory=safe_path(self.root/'generations',previous);receipt=read(directory/'receipt.json',{})
        if not receipt.get('installed') or receipt.get('component')!=key:raise ValueError('Generasi cadangan tidak valid')
        for entry in receipt.get('artifacts',[]):
            path=safe_path(directory,entry['path'])
            if not path.is_file() or digest(path,entry.get('algorithm','sha256'))!=entry['hash']:
                raise ValueError('Berkas generasi cadangan berubah; pemulihan ditolak')
        write(pointer,dict(generation=previous,previous=current.get('generation'),enabled=current.get('enabled',False)))
        return dict(generation=previous,message='Generasi sebelumnya dipulihkan; data proyek tetap tersedia')

    def enable(self,key,enabled):
        if key!='faster-whisper':raise ValueError('Backend produksi lain belum dihubungkan; gunakan Uji sampel')
        active=self.active(key)
        if enabled and (not active or active.get('test',{}).get('level')!='sample' or not active['test'].get('passed')):
            raise ValueError('Lakukan uji sampel pada transcriber terisolasi sebelum mengaktifkannya')
        pointer=self.root/'components'/key/'active.json';data=read(pointer)
        if not data:raise ValueError('Komponen belum dipasang')
        write(pointer,{**data,'enabled':bool(enabled)});return {'enabled':bool(enabled)}

    def snapshot(self):
        rows=[]
        for item in CATALOG:
            active=self.active(item['id']);test=(active or {}).get('test',{})
            pointer=read(self.root/'components'/item['id']/'active.json',{})
            detected=None
            if item['kind']=='system':detected=__import__('shutil').which('ffmpeg')
            elif item['packages']:
                import importlib.metadata
                try:detected=importlib.metadata.version(item['packages'][0].split('==')[0])
                except importlib.metadata.PackageNotFoundError:pass
            rows.append({**item,'installed':bool(active and active.get('installed')),'detected_existing':detected,
                         'test':test,'status':({'sample':'lolos sampel','import':'impor diperiksa','build':'build diperiksa','documents':'dokumen diperiksa'}.get(test.get('level'),'uji diperiksa') if test.get('passed') else
                                              'terpasang; belum lolos uji' if active else 'tersedia di lingkungan utama; belum diuji' if detected else 'belum dikelola'),
                         'version':(active or {}).get('versions',{}),'weights':(active or {}).get('weights',{}),
                         'generation':(active or {}).get('generation'),'previous':(active or {}).get('previous'),
                         'enabled':pointer.get('enabled',False), 'access_configured':bool(os.environ.get(item['access'])) if item['access'] else None})
        return dict(version=VERSION,components=rows,jobs=self.jobs(),gpu=owner(self.root),
                    hardware=read(self.root/'hardware.json'),profiles=read(self.root/'profiles.json'),
                    selected_profile=read(self.root/'selected-profile.json',{'name':'balanced','device':'cpu'}),
                    stock=stock_status(os.environ),free_bytes=__import__('shutil').disk_usage(self.root).free,
                    counts=dict(total=len(rows),installed=sum(r['installed'] for r in rows),
                                sample_passed=sum(bool(r['test'].get('passed') and r['test'].get('level')=='sample') for r in rows)))

    def select_profile(self,name):
        profiles=read(self.root/'profiles.json',{})
        if not isinstance(name,str) or name not in profiles:raise ValueError('Jalankan kalibrasi perangkat terlebih dahulu')
        write(self.root/'selected-profile.json',{'name':name,**profiles[name]})
        return read(self.root/'selected-profile.json')

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('running','cancel_requested')").fetchone():return None
            row=db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET status='running',owner=?,updated=? WHERE id=?",(self.queue_owner,time.time(),row['id']))
                return row['id']

    def start(self):
        with self.guard:
            if self.thread and self.thread.is_alive():return
            self.stop_event.clear();self.thread=threading.Thread(target=self.run,daemon=True,name='clipper-runtime');self.thread.start()

    def run(self):
        while not self.stop_event.is_set():
            jid=self.claim()
            if not jid:self.stop_event.wait(.25);continue
            log=self.root/'logs'/(jid+'.log');log.parent.mkdir(exist_ok=True)
            env=os.environ.copy();env['CLIPPER_RUNTIME_DIR']=str(self.root)
            env['PYTHONPATH']=str(self.repo)+os.pathsep+env.get('PYTHONPATH','')
            # A web server thread must not lend a core lease to another job.
            env.pop('CLIPPER_GPU_LEASE_TOKEN',None)
            try:
                with log.open('a',encoding='utf-8') as stream:
                    kwargs={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
                    proc=subprocess.Popen([sys.executable,'-m','clipper.runtime.cli','worker','--root',str(self.root),'--repo',str(self.repo),'--job',jid],cwd=self.repo,env=env,stdout=stream,stderr=subprocess.STDOUT,**kwargs)
                    birth=process_birth(proc.pid);self.update(jid,pid=proc.pid,birth=birth)
                    while proc.poll() is None:
                        if self.canceled(jid):
                            terminate_owned(proc.pid,birth)
                            try:proc.wait(timeout=8)
                            except subprocess.TimeoutExpired:
                                if process_birth(proc.pid)==birth:proc.kill()
                            break
                        self.stop_event.wait(.2)
                    proc.wait(timeout=10)
                row=self.job(jid)
                if row['status'] in ('running','cancel_requested'):
                    self.update(jid,status='interrupted' if self.stop_event.is_set() else 'canceled' if row['status']=='cancel_requested' else 'failed',
                                message='Worker berhenti; data parsial tersimpan. Lihat log komponen atau lanjutkan.',error='Worker exit '+str(proc.returncode))
            except Exception as exc:self.update(jid,status='failed',message='Worker tidak dapat dijalankan',error=redact(str(exc)))

    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=12)


def redact(text):
    for key,value in os.environ.items():
        if value and len(value)>=4 and any(word in key.upper() for word in ('TOKEN','KEY','PASSWORD','SECRET')):text=text.replace(value,'[disembunyikan]')
    return text[-3000:]
