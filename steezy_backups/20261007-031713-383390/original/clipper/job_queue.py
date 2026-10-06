"""Persistent serial queue. Each heavy job owns a cancellable process tree."""
import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from .project_store import dumps
from .contracts import fingerprint

ACTIVE=('queued','running','cancel_requested')


def process_birth(pid):
    try:
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            ctypes.windll.kernel32.OpenProcess.restype=wintypes.HANDLE
            ctypes.windll.kernel32.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.c_void_p]*4
            ctypes.windll.kernel32.CloseHandle.argtypes=[wintypes.HANDLE]
            handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,int(pid))
            if not handle:return None
            values=[ctypes.c_ulonglong() for _ in range(4)]
            try:
                if not ctypes.windll.kernel32.GetProcessTimes(handle,*[ctypes.byref(v) for v in values]):return None
                return str(values[0].value)
            finally:ctypes.windll.kernel32.CloseHandle(handle)
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
    except (OSError,IndexError,ValueError):return None


def terminate_owned(pid,birth):
    if not pid or not birth or process_birth(pid)!=birth:return False
    try:
        if os.name=='nt':subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],capture_output=True,timeout=10)
        else:os.killpg(pid,signal.SIGTERM)
        return True
    except (OSError,subprocess.SubprocessError):return False


class JobQueue:
    def __init__(self,store,work_root,resource_lock=None,*,autostart=True,recover=True):
        self.store=store;self.work=Path(work_root);self.lock=resource_lock or threading.Lock()
        self.guard=threading.Lock();self.thread=None;self.owner=uuid.uuid4().hex;self.stop_event=threading.Event();self.autostart=autostart;self.on_idle=None
        with store.connect() as db:
            if 'pid_birth' not in {r['name'] for r in db.execute('PRAGMA table_info(jobs)')}:db.execute('ALTER TABLE jobs ADD COLUMN pid_birth TEXT')
            for row in db.execute("SELECT id,pid,pid_birth,updated FROM jobs WHERE status IN ('running','cancel_requested')").fetchall() if recover else []:
                if not row['pid'] or process_birth(row['pid'])!=row['pid_birth']:
                    db.execute("UPDATE jobs SET status='interrupted',message=?,updated=? WHERE id=?",('Proses terhenti; tahap tersimpan dapat dilanjutkan.',time.time(),row['id']))

    def get(self,job_id):
        with self.store.connect() as db:row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if row is None:raise KeyError('Proses tidak ditemukan')
        out=dict(row)
        for key in ('target','request','result'):out[key]=json.loads(out[key]) if out[key] else None
        return out

    def list(self,project_id=None):
        with self.store.connect() as db:
            rows=db.execute('SELECT id FROM jobs '+('WHERE project_id=? ' if project_id else '')+'ORDER BY created DESC LIMIT 100',([project_id] if project_id else [])).fetchall()
        return [self.get(r['id']) for r in rows]

    def enqueue(self,project_id,kind,target,request):
        request={**request,'queue_key':fingerprint([project_id,kind,target,request])}
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute("SELECT id,request FROM jobs WHERE project_id=? AND kind=? AND status IN ('queued','running')",(project_id,kind)):
                if json.loads(row['request'])['queue_key']==request['queue_key']:
                    db.commit();self.start();return self.get(row['id'])
            ident='job-'+uuid.uuid4().hex;now=time.time()
            db.execute('INSERT INTO jobs(id,project_id,kind,target,status,request,created,updated,message) VALUES(?,?,?,?,?,?,?,?,?)',
                (ident,project_id,kind,dumps(target),'queued',dumps(request),now,now,'Menunggu giliran; satu proses berat pada satu waktu.'))
            db.commit()
        self.start();return self.get(ident)

    def start(self):
        if not self.autostart:return
        with self.guard:
            if self.thread and self.thread.is_alive():return
            self.stop_event.clear();self.thread=threading.Thread(target=self.run,daemon=True,name='clipper-resource-queue');self.thread.start()

    def update(self,ident,**values):
        allowed={'status','progress','message','error','result','pid','pid_birth','owner'}
        if set(values)-allowed:raise ValueError('Field proses tidak valid')
        if 'result' in values:values['result']=dumps(values['result'])
        values['updated']=time.time()
        with self.store.connect() as db:db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',[*values.values(),ident])

    def cancel(self,ident):
        job=self.get(ident)
        if job['status']=='queued':self.update(ident,status='canceled',message='Dibatalkan sebelum dimulai.')
        elif job['status']=='running':self.update(ident,status='cancel_requested',message='Menghentikan proses milik tugas ini…')
        return self.get(ident)

    def resume(self,ident,request=None):
        job=self.get(ident)
        if job['status'] not in ('interrupted','failed','canceled','stale'):raise ValueError('Proses ini tidak perlu dilanjutkan')
        return self.enqueue(job['project_id'],job['kind'],job['target'],request or {k:v for k,v in job['request'].items() if k!='queue_key'})

    def claim(self):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('running','cancel_requested') LIMIT 1").fetchone():db.commit();return None
            row=db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:db.execute("UPDATE jobs SET status='running',owner=?,updated=? WHERE id=?",(self.owner,time.time(),row['id']))
            db.commit()
        return self.get(row['id']) if row else None

    def run(self):
        maintenance_at=0
        while not self.stop_event.is_set():
            if not any(j['status']=='queued' for j in self.list()):
                if self.on_idle and time.monotonic()>=maintenance_at:
                    try:self.on_idle()
                    except (ValueError,OSError):pass
                    maintenance_at=time.monotonic()+30
                self.stop_event.wait(.5);continue
            with self.lock:
                job=self.claim()
                if job is None:continue
                folder=self.work/job['project_id']/'tasks';folder.mkdir(parents=True,exist_ok=True)
                try:
                    with (folder/(job['id']+'.log')).open('ab') as log:
                        options={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
                        proc=subprocess.Popen([sys.executable,'-m','clipper.studio_worker','--db',str(self.store.path),'--job',job['id']],
                            cwd=Path(__file__).resolve().parent.parent,stdout=log,stderr=log,**options)
                        birth=process_birth(proc.pid);self.update(job['id'],pid=proc.pid,pid_birth=birth)
                        cancel_time=None
                        while proc.poll() is None:
                            current=self.get(job['id'])
                            if current['status']=='cancel_requested' or self.stop_event.is_set() and current['status']=='running':
                                if cancel_time is None:
                                    terminate_owned(proc.pid,birth);cancel_time=time.monotonic()
                                elif time.monotonic()-cancel_time>4 and process_birth(proc.pid)==birth:
                                    if os.name!='nt':os.killpg(proc.pid,signal.SIGKILL)
                                    else:terminate_owned(proc.pid,birth)
                            self.stop_event.wait(.2)
                        current=self.get(job['id'])
                        if cancel_time is not None and current['status'] not in ('completed','failed','stale'):
                            self.update(job['id'],status='canceled',message='Proses dihentikan. Hasil sah sebelumnya tetap ada.')
                            try:
                                from .config import Config
                                from .editorial import release
                                doc=self.store.get(job['project_id']);release(Config(**doc['settings']))
                            except Exception:pass
                        elif current['status']=='running':
                            self.update(job['id'],status='failed',error='Worker berakhir sebelum mengesahkan hasil.',message='Lihat log proses; tahap yang sah dapat digunakan kembali.')
                except Exception as exc:self.update(job['id'],status='failed',error=str(exc),message='Proses belum selesai; dapat dicoba lagi.')

    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=6)
