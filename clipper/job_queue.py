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
from .project_store import dumps,JobLeaseLost
from .contracts import fingerprint

ACTIVE=('queued','running','cancel_requested')


def process_birth(pid,*,visible=False):
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
        target=Path(f'/proc/{pid}')
        if not visible:
            # /proc can expose outer PIDs while getpid/Popen report namespace
            # PIDs (containers with a host procfs mount). Match the namespace,
            # never borrow a different process's start time for cancellation.
            current_namespace=os.readlink('/proc/self/ns/pid')
            if int(pid)==os.getpid():target=Path('/proc/self')
            else:
                try:same_namespace=os.readlink(target/'ns/pid')==current_namespace
                except OSError:same_namespace=False
                if not same_namespace:
                    target=None
                    for candidate in Path('/proc').iterdir():
                        if not candidate.name.isdigit():continue
                        try:
                            if os.readlink(candidate/'ns/pid')!=current_namespace:continue
                            line=next(row for row in (candidate/'status').read_text().splitlines() if row.startswith('NSpid:'))
                            if int(line.split()[-1])==int(pid):target=candidate;break
                        except (OSError,ValueError,StopIteration):continue
                    if target is None:return None
        fields=(target/'stat').read_text().rsplit(')',1)[1].split()
        return None if fields[0]=='Z' else fields[19]
    except (OSError,IndexError,ValueError):return None


def process_group_alive(group):
    if os.name=='nt':return False
    try:namespace=os.readlink('/proc/self/ns/pid')
    except OSError:return False
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            if os.readlink(path/'ns/pid')!=namespace:continue
            fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in (path/'status').read_text().splitlines() if ':' in line}
            if fields.get('State','').startswith('Z'):continue
            if fields.get('NSpgid') and int(fields['NSpgid'].split()[-1])==group:return True
        except (OSError,ValueError):continue
    return False


def terminate_owned(pid,birth,*,force=False):
    if not pid or not birth or process_birth(pid)!=birth:return False
    try:
        if os.name=='nt':
            return subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],capture_output=True,timeout=10).returncode==0
        else:os.killpg(pid,signal.SIGKILL if force else signal.SIGTERM)
        return True
    except (OSError,subprocess.SubprocessError):return False


class JobQueue:
    def __init__(self,store,work_root,resource_lock=None,*,autostart=True,recover=True,lease_seconds=30,installation_root=None):
        from .installation_lock import InstallationLease
        self.installation_lease=InstallationLease(installation_root) if installation_root else None
        self.closed=False
        self.store=store;self.work=Path(work_root);self.lock=resource_lock or threading.Lock()
        self.guard=threading.Lock();self.thread=None;self.owner=uuid.uuid4().hex;self.stop_event=threading.Event();self.autostart=autostart;self.on_idle=None
        self.lease_seconds=max(5,float(lease_seconds))
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            columns={r['name'] for r in db.execute('PRAGMA table_info(jobs)')}
            for name,type_ in [('pid_birth','TEXT'),('lease_token','INTEGER DEFAULT 0'),('lease_expires','REAL'),('recovery_state','TEXT'),('stop_requested_at','REAL')]:
                if name not in columns:db.execute('ALTER TABLE jobs ADD COLUMN '+name+' '+type_)
            db.commit()
        if recover:self.recover()

    def recover(self):
        stop=[]
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT id,pid,pid_birth,lease_expires,status,recovery_state,stop_requested_at FROM jobs WHERE status IN ('running','cancel_requested')").fetchall()
            for row in rows:
                # A fresh claim without a PID is a valid launch window.
                expired=not row['lease_expires'] or row['lease_expires']<=time.time()
                dead=bool(row['pid'] and process_birth(row['pid'])!=row['pid_birth'] and not process_group_alive(row['pid']))
                if not expired and not dead:continue
                if expired and row['pid'] and not dead:
                    # Fence first, keep the global serial slot occupied, then
                    # stop the exact process tree. A later pass acknowledges exit.
                    if not row['recovery_state']:
                        db.execute("UPDATE jobs SET status='cancel_requested',lease_token=lease_token+1,lease_expires=NULL,recovery_state='lease_expired',stop_requested_at=?,message=?,updated=? WHERE id=?",
                            (time.time(),'Lease berakhir; menunggu pohon proses lama berhenti.',time.time(),row['id']))
                    stop.append((row['pid'],row['pid_birth'],bool(row['stop_requested_at'] and time.time()-row['stop_requested_at']>=4)))
                    continue
                status='canceled' if row['status']=='cancel_requested' and dead and not row['recovery_state'] else 'interrupted'
                db.execute('UPDATE jobs SET status=?,lease_token=lease_token+1,lease_expires=NULL,message=?,updated=? WHERE id=?',
                    (status,'Proses terhenti; tahap sah dapat dilanjutkan.',time.time(),row['id']))
            db.commit()
        for pid,birth,force in stop:terminate_owned(pid,birth,force=force)

    def get(self,job_id):
        with self.store.connect() as db:row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if row is None:raise KeyError('Proses tidak ditemukan')
        out=dict(row)
        for key in ('target','request','result'):out[key]=json.loads(out[key]) if out[key] else None
        return out

    def list(self,project_id=None):
        with self.store.connect() as db:
            where='WHERE project_id=? AND ' if project_id else 'WHERE '
            args=[project_id] if project_id else []
            active=db.execute('SELECT id,created,status FROM jobs '+where+"status IN ('queued','running','cancel_requested')",args).fetchall()
            history=db.execute('SELECT id,created,status FROM jobs '+where+"status NOT IN ('queued','running','cancel_requested') ORDER BY created DESC LIMIT 100",args).fetchall()
            rows=sorted(active,key=lambda row:(row['status']=='queued',row['created']))+history
        return [self.get(r['id']) for r in rows]

    def has_queued(self):
        with self.store.connect() as db:
            return db.execute("SELECT 1 FROM jobs WHERE status='queued' LIMIT 1").fetchone() is not None

    def enqueue(self,project_id,kind,target,request):
        if self.closed:raise ValueError('Antrean sudah ditutup; buka ulang mesin sebelum menjalankan tugas')
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
        if self.closed:raise ValueError('Antrean sudah ditutup; buka ulang mesin sebelum menjalankan tugas')
        if not self.autostart:return
        with self.guard:
            if self.thread and self.thread.is_alive():return
            self.stop_event.clear();self.thread=threading.Thread(target=self.run,daemon=True,name='clipper-resource-queue');self.thread.start()

    def enqueue_many(self,project_id,entries,expected_revision):
        if self.closed:raise ValueError('Antrean sudah ditutup; buka ulang mesin sebelum menjalankan tugas')
        """Validate the snapshot and add a whole batch in one SQLite transaction."""
        from .project_store import Conflict
        ids=[]
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT revision FROM projects WHERE id=?',(project_id,)).fetchone()
            if row is None:raise KeyError('Proyek tidak ditemukan')
            if row['revision']!=expected_revision:raise Conflict(row['revision'])
            for kind,target,request in entries:
                request={**request,'queue_key':fingerprint([project_id,kind,target,request])}
                existing=next((r['id'] for r in db.execute("SELECT id,request FROM jobs WHERE project_id=? AND kind=? AND status IN ('queued','running')",(project_id,kind)) if json.loads(r['request'])['queue_key']==request['queue_key']),None)
                if existing:ids.append(existing);continue
                ident='job-'+uuid.uuid4().hex;now=time.time()
                db.execute('INSERT INTO jobs(id,project_id,kind,target,status,request,created,updated,message) VALUES(?,?,?,?,?,?,?,?,?)',
                    (ident,project_id,kind,dumps(target),'queued',dumps(request),now,now,'Batch dua rasio · menunggu giliran.'))
                ids.append(ident)
            db.commit()
        self.start();return [self.get(i) for i in ids]

    def update(self,ident,**values):
        allowed={'status','progress','message','error','result','pid','pid_birth','owner'}
        if set(values)-allowed:raise ValueError('Field proses tidak valid')
        if 'result' in values:values['result']=dumps(values['result'])
        values['updated']=time.time()
        with self.store.connect() as db:db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',[*values.values(),ident])

    def cancel(self,ident):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status FROM jobs WHERE id=?',(ident,)).fetchone()
            if row is None:raise KeyError('Proses tidak ditemukan')
            if row['status']=='queued':db.execute("UPDATE jobs SET status='canceled',message=?,updated=? WHERE id=? AND status='queued'",
                ('Dibatalkan sebelum dimulai.',time.time(),ident))
            elif row['status']=='running':db.execute("UPDATE jobs SET status='cancel_requested',message=?,updated=? WHERE id=? AND status='running'",
                ('Menunggu pengakuan worker setelah proses dihentikan.',time.time(),ident))
            db.commit()
        return self.get(ident)

    def update_owned(self,job,**values):
        allowed={'status','progress','message','error','result','pid','pid_birth'}
        if set(values)-allowed:raise ValueError('Field proses tidak valid')
        if 'result' in values:values['result']=dumps(values['result'])
        values.update(updated=time.time())
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT owner,lease_token,status,lease_expires,result FROM jobs WHERE id=?',(job['id'],)).fetchone()
            if not current or current['owner']!=job['owner'] or current['lease_token']!=job['lease_token']:
                raise JobLeaseLost('Worker lama tidak lagi memiliki tugas ini.')
            if 'status' in values:
                if current['status'] not in ('running','cancel_requested'):
                    raise JobLeaseLost('Status terminal tugas tidak dapat ditulis ulang oleh worker.')
                if current['status']=='cancel_requested' and values['status'] not in ('canceled','interrupted'):
                    raise JobLeaseLost('Pembatalan harus diakui sebelum status terminal lain.')
                if not current['lease_expires'] or current['lease_expires']<=time.time():
                    raise JobLeaseLost('Lease worker telah berakhir.')
            elif current['status'] in ('running','cancel_requested') and (not current['lease_expires'] or current['lease_expires']<=time.time()):
                raise JobLeaseLost('Lease worker telah berakhir.')
            if current['status'] not in ('running','cancel_requested'):
                if set(values)-{'message','result','updated'}:raise JobLeaseLost('Data terminal tugas tidak dapat ditulis ulang.')
                if 'result' in values:
                    old=json.loads(current['result']) if current['result'] else {}
                    new=json.loads(values['result'])
                    if {k:v for k,v in new.items() if k!='resource_metrics'}!={k:v for k,v in old.items() if k!='resource_metrics'}:
                        raise JobLeaseLost('Hasil terminal hanya dapat ditambah telemetry supervisor.')
            updated=db.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=? AND owner=? AND lease_token=?',
                [*values.values(),job['id'],job['owner'],job['lease_token']]).rowcount
            if updated!=1:raise JobLeaseLost('Worker lama tidak lagi memiliki tugas ini.')
            db.commit()

    def heartbeat(self,job):
        with self.store.connect() as db:
            changed=db.execute("UPDATE jobs SET lease_expires=?,updated=? WHERE id=? AND owner=? AND lease_token=? AND lease_expires>? AND status IN ('running','cancel_requested')",
                (time.time()+self.lease_seconds,time.time(),job['id'],job['owner'],job['lease_token'],time.time())).rowcount
        return changed==1

    def resume(self,ident,request=None):
        job=self.get(ident)
        if job['status'] not in ('interrupted','failed','canceled','stale'):raise ValueError('Proses ini tidak perlu dilanjutkan')
        return self.enqueue(job['project_id'],job['kind'],job['target'],request or {k:v for k,v in job['request'].items() if k!='queue_key'})

    def claim(self,ident=None):
        if self.closed:raise ValueError('Antrean sudah ditutup; buka ulang mesin sebelum menjalankan tugas')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('running','cancel_requested') LIMIT 1").fetchone():db.commit();return None
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m9_resource_holds'").fetchone() and db.execute("SELECT 1 FROM m9_resource_holds WHERE state!='released' LIMIT 1").fetchone():
                db.commit();return None
            row=db.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row and ident and row['id']!=ident:db.commit();return None
            if row:db.execute("UPDATE jobs SET status='running',owner=?,lease_token=lease_token+1,lease_expires=?,updated=? WHERE id=? AND status='queued'",
                             (self.owner,time.time()+self.lease_seconds,time.time(),row['id']))
            db.commit()
        return self.get(row['id']) if row else None

    def run(self):
        maintenance_at=0
        while not self.stop_event.is_set():
            self.recover()
            if not self.has_queued():
                if self.on_idle and time.monotonic()>=maintenance_at:
                    try:self.on_idle()
                    except (ValueError,OSError):pass
                    maintenance_at=time.monotonic()+30
                self.stop_event.wait(.5);continue
            with self.lock:
                job=self.claim()
                if job is not None:self.run_claimed(job)
            # Another server may own SQLite's serial resource. Release the
            # local lock before the cancellable backoff.
            if job is None:self.stop_event.wait(.5)

    def run_claimed(self,job):
        # The caller holds its local resource lock; SQLite owns global order.
        folder=self.work/job['project_id']/'tasks';folder.mkdir(parents=True,exist_ok=True)
        proc=None;birth=None
        def child_running():
            if os.name!='nt' and hasattr(os,'waitid') and hasattr(os,'WNOWAIT'):
                # Leave an exited leader unreaped until its group is empty:
                # its PID cannot be reused while we finish stopping descendants.
                return os.waitid(os.P_PID,proc.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is None
            return proc.poll() is None
        def stop_process(force=False):
            # An unreaped Popen child cannot reuse its PID. This also works when
            # namespace/procfs metadata are unavailable; recovery uses birth tokens.
            if proc is None or proc.returncode is not None:return
            if os.name=='nt':
                if proc.poll() is not None:return
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,timeout=10)
            else:
                try:os.killpg(proc.pid,signal.SIGKILL if force else signal.SIGTERM)
                except ProcessLookupError:pass
        try:
            current=self.get(job['id'])
            if current['owner']!=job['owner'] or current['lease_token']!=job['lease_token']:return
            if current['status']=='cancel_requested':
                self.update_owned(job,status='canceled',message='Dibatalkan sebelum worker dimulai.');return
            if current['status']!='running':return
            with (folder/(job['id']+'.log')).open('ab') as log:
                options={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
                proc=subprocess.Popen([sys.executable,'-m','clipper.studio_worker','--db',str(self.store.path),'--job',job['id']],
                    cwd=Path(__file__).resolve().parent.parent,stdout=log,stderr=log,**options)
                birth=process_birth(proc.pid);self.update_owned(job,pid=proc.pid,pid_birth=birth)
                from .metrics6 import ResourceMeter
                meter=ResourceMeter(proc.pid)
                cancel_time=None
                while child_running():
                    alive=self.heartbeat(job)
                    meter.sample()
                    current=self.get(job['id'])
                    if not alive and current['status'] not in ('completed','failed','stale','canceled'):
                        stop_process(force=True);proc.wait(timeout=5)
                        raise JobLeaseLost('Lease worker berakhir sebelum pekerjaan selesai.')
                    if current['status']=='cancel_requested' or self.stop_event.is_set() and current['status']=='running':
                        if cancel_time is None:
                            stop_process();cancel_time=time.monotonic()
                        elif time.monotonic()-cancel_time>4:stop_process(force=True)
                    time.sleep(.2)
                if os.name!='nt' and proc.returncode is None:
                    stop_process(force=True)
                    while process_group_alive(proc.pid):
                        self.heartbeat(job);stop_process(force=True);time.sleep(.05)
                proc.wait()
                current=self.get(job['id'])
                self.update_owned(job,result={**(current.get('result') or {}),'resource_metrics':meter.report()})
                if cancel_time is not None and current['status'] not in ('completed','failed','stale'):
                    self.update_owned(job,status='canceled',message='Proses dihentikan. Hasil sah sebelumnya tetap ada.')
                    try:
                        from .config import Config
                        from .editorial import release
                        doc=self.store.get(job['project_id']);release(Config(**doc['settings']))
                    except Exception:pass
                elif current['status']=='running':
                    self.update_owned(job,status='failed',error='Worker berakhir sebelum mengesahkan hasil.',message='Lihat log proses; tahap yang sah dapat digunakan kembali.')
        except JobLeaseLost:pass
        except Exception as exc:
            try:self.update_owned(job,status='failed',error=str(exc),message='Proses belum selesai; dapat dicoba lagi.')
            except JobLeaseLost:pass
        finally:
            if proc is not None and proc.returncode is None:
                stop_process(force=True)
                try:proc.wait(timeout=5)
                except subprocess.TimeoutExpired:pass

    def close(self):
        self.closed=True
        for job in self.list():
            if job.get('owner')==self.owner and job['status']=='running':self.cancel(job['id'])
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=6)
        if self.installation_lease and not (self.thread and self.thread.is_alive()):
            self.installation_lease.close();self.installation_lease=None
