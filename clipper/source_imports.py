"""Durable M2 import queue. Complete, probed media precedes project/ASR creation."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse
import uuid
from dataclasses import asdict
from .contracts import fingerprint
from .dependency_cache import content_id
from .project_store import dumps
from .storage import read_json,write_json
from .media_context import inspect
from .job_queue import process_birth,terminate_owned

MEDIA_SUFFIXES={'.mp4','.mkv','.mov','.webm','.avi','.m4v','.wav','.mp3','.flac','.m4a','.aac','.ogg','.opus'}
DEFAULT_MAX_BYTES=20*1024**3


def url(value):
    if not isinstance(value,str) or not 1<=len(value)<=4000:raise ValueError('URL sumber tidak valid')
    parsed=urlparse(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:raise ValueError('URL harus HTTP/HTTPS tanpa kredensial tertanam')
    return value


def limit_bytes(value):
    if type(value) is not int or not 1024<=value<=100*1024**3:raise ValueError('Batas unduhan harus 1 KB–100 GB')
    return value


def safe_error(exc):
    message=str(exc)[-2000:]
    for name in ('CLIPPER_DRIVE_ACCESS_TOKEN','CLIPPER_ZOOM_ACCESS_TOKEN','CLIPPER_ASR_API_KEY'):
        secret=os.environ.get(name)
        if secret:message=message.replace(secret,'[redacted]')
    return re.sub(r'([?&](?:access_token|token|key|signature)=)[^&\s]+',r'\1[redacted]',message,flags=re.I)


def _complete(path,request):
    if not Path(path).is_file() or Path(path).stat().st_size>limit_bytes(request.get('max_bytes',DEFAULT_MAX_BYTES)):raise ValueError('Media tidak ada atau melebihi batas ukuran')
    identity=content_id(path,fresh=True);expected=request.get('sha256')
    if expected and identity!='sha256:'+expected:raise ValueError('SHA-256 unduhan berbeda dari yang diharapkan')
    info=inspect(path)
    if content_id(path,fresh=True)!=identity:raise ValueError('Media berubah ketika diperiksa')
    return identity,info


def direct_download(request,folder,*,headers=None):
    import requests
    address=url(request['url']);cap=limit_bytes(request.get('max_bytes',DEFAULT_MAX_BYTES));folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    suffix=Path(urlparse(address).path).suffix.lower();suffix=suffix if suffix in MEDIA_SUFFIXES else '.bin'
    output=folder/('source'+suffix);part=folder/(output.name+'.part');state=folder/'transfer.json';old=read_json(state,{})
    if output.is_file() and old.get('complete') and old.get('url_hash')==fingerprint(address):
        identity,info=_complete(output,request)
        if identity==old.get('content_id'):return {'path':str(output),'content_id':identity,'info':info,'receipt':old['receipt']}
    base=dict(headers or {});head=requests.head(address,headers=base,allow_redirects=True,timeout=30)
    if head.status_code not in (405,501):head.raise_for_status()
    etag=head.headers.get('ETag');validator=etag if etag and not etag.startswith('W/') else head.headers.get('Last-Modified')
    length=int(head.headers['Content-Length']) if head.headers.get('Content-Length','').isdigit() else None
    if length and length>cap:raise ValueError('Sumber melebihi batas ukuran unduhan')
    resume=0
    committed=old.get('committed_bytes',0)
    if part.is_file() and validator and old.get('validator')==validator and old.get('url_hash')==fingerprint(address) and type(committed) is int and 0<committed<=part.stat().st_size:
        with part.open('rb') as prefix:
            digest=hashlib.sha256();remaining=committed
            while remaining:
                block=prefix.read(min(1024*1024,remaining));digest.update(block);remaining-=len(block)
        if digest.hexdigest()==old.get('partial_sha256'):
            resume=committed
            with part.open('r+b') as stream:stream.truncate(resume)
    if resume>cap:raise ValueError('Berkas parsial melebihi batas ukuran')
    incoming={**base}
    if resume:incoming.update(Range='bytes='+str(resume)+'-',**{'If-Range':validator})
    with requests.get(address,headers=incoming,stream=True,allow_redirects=True,timeout=(30,60)) as response:
        response.raise_for_status();total=length;get_etag=response.headers.get('ETag');actual=get_etag if get_etag and not get_etag.startswith('W/') else response.headers.get('Last-Modified')
        if resume and response.status_code==206:
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
            if not match or int(match[1])!=resume or int(match[2])<resume or (length and int(match[3])!=length):raise ValueError('Content-Range resume tidak sesuai')
            if actual and actual!=validator:raise ValueError('Identitas sumber berubah ketika resume')
            total=int(match[3])
        elif response.status_code==206:raise ValueError('Range tak diminta; unduhan ditolak')
        else:resume=0;total=int(response.headers['Content-Length']) if response.headers.get('Content-Length','').isdigit() else length
        if total and total>cap:raise ValueError('Sumber melebihi batas ukuran unduhan')
        state_value={'complete':False,'url_hash':fingerprint(address),'validator':validator,'expected_bytes':total}
        write_json(state,state_value);received=resume;hasher=hashlib.sha256()
        if resume:
            with part.open('rb') as prefix:
                for block in iter(lambda:prefix.read(1024*1024),b''):hasher.update(block)
        checkpoint=time.monotonic();checkpoint_bytes=resume
        try:
            with part.open('ab' if resume else 'wb') as stream:
                for block in response.iter_content(1024*1024):
                    if not block:continue
                    if received+len(block)>cap:raise ValueError('Unduhan melewati batas ukuran')
                    stream.write(block);hasher.update(block);received+=len(block)
                    if received-checkpoint_bytes>=64*1024**2 or time.monotonic()-checkpoint>1:
                        stream.flush();os.fsync(stream.fileno());write_json(state,{**state_value,'committed_bytes':received,'partial_sha256':hasher.hexdigest()})
                        checkpoint=time.monotonic();checkpoint_bytes=received
                stream.flush();os.fsync(stream.fileno())
        finally:
            write_json(state,{**state_value,'committed_bytes':received,'partial_sha256':hasher.hexdigest()})
        if total is not None and received!=total:raise ValueError('Unduhan terputus; resume mempertahankan berkas parsial')
    identity,info=_complete(part,request)
    receipt={'provider':'direct_http','bytes':received,'resumed_bytes':resume,'validator':validator,'range_validated':bool(resume),
        'complete_media_probed':True,'source_content_id':identity}
    part.replace(output);write_json(state,{**state_value,'complete':True,'content_id':identity,'receipt':receipt})
    return {'path':str(output),'content_id':identity,'info':info,'receipt':receipt}


def yt_command():
    executable=shutil.which('yt-dlp')
    if executable:return [executable]
    if importlib.util.find_spec('yt_dlp'):return [sys.executable,'-m','yt_dlp']
    raise ValueError('yt-dlp belum terpasang. Impor lokal tetap tersedia; pasang yt-dlp untuk URL platform')


def cookies():
    path=os.environ.get('CLIPPER_YTDLP_COOKIE_FILE','')
    if path and not Path(path).is_file():raise ValueError('Cookie file platform tidak ditemukan')
    return ['--cookies',path] if path else []


def inspect_playlist(address,limit=50,*,detailed=False):
    if type(limit) is not int or not 1<=limit<=50:raise ValueError('Pilih 1–50 sumber')
    command=yt_command()+['--ignore-config','--skip-download','--dump-single-json','--playlist-end',str(limit),*cookies()]
    if not detailed:command+=['--flat-playlist']
    r=subprocess.run(command+[url(address)],capture_output=True,text=True,timeout=180,check=True);data=json.loads(r.stdout)
    rows=data.get('entries') or [data]
    return {'items':[{'url':url(row.get('webpage_url') or row.get('url') or 'https://www.youtube.com/watch?v='+row['id']),
        'title':row.get('title',''),'duration':row.get('duration'),'id':row.get('id'),'upload_date':row.get('upload_date'),
        'channel_id':row.get('channel_id')} for row in rows if row][:limit],'provider':'yt-dlp','account_ownership_verified':False}


def platform_download(request,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);state=folder/'platform.json';old=read_json(state,{})
    if old.get('path'):
        p=Path(old['path'])
        if p.is_file():
            identity,info=_complete(p,request)
            if identity==old.get('content_id'):return {**old,'info':info}
    cap=limit_bytes(request.get('max_bytes',DEFAULT_MAX_BYTES));command=yt_command()+['--ignore-config','--no-playlist','--continue','--part',
        '--max-filesize',str(cap),'--retries','3','--socket-timeout','30','--write-info-json','--write-subs','--sub-langs','id,en','--sub-format','vtt',
        '--merge-output-format','mp4','--no-progress',*cookies(),'-o',str(folder/'source.%(ext)s'),url(request['url'])]
    with tempfile_log(folder/'download.log') as log:
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT);start=time.monotonic()
        try:
            while proc.poll() is None:
                if time.monotonic()-start>3600:raise ValueError('Batas waktu unduhan platform tercapai')
                if sum(p.stat().st_size for p in folder.glob('source*') if p.is_file())>3*cap+10*1024**2:raise ValueError('Unduhan platform melebihi batas ukuran')
                time.sleep(.1)
            if proc.returncode:raise ValueError('Impor URL platform gagal. Periksa URL/akses/cookie; transkripsi belum dijalankan')
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
    files=[p for p in folder.glob('source.*') if p.suffix.lower() in MEDIA_SUFFIXES and not p.name.endswith('.part')]
    if len(files)!=1:raise ValueError('Platform tidak menghasilkan satu media lengkap')
    identity,info=_complete(files[0],request);details=read_json(folder/'source.info.json',{})
    result={'path':str(files[0]),'content_id':identity,'info':info,'receipt':{'provider':'yt-dlp','extractor':details.get('extractor_key'),
        'platform_id':details.get('id'),'duration':info['duration'],'complete_media_probed':True,'source_content_id':identity,
        'access':'user_cookie' if cookies() else 'public','creator_subtitles':[str(p) for p in folder.glob('source*.vtt')]}}
    write_json(state,result);return result


def tempfile_log(path):return Path(path).open('ab')


def connector_download(request,folder):
    import requests
    kind=request['kind']
    if kind=='drive':
        token=os.environ.get('CLIPPER_DRIVE_ACCESS_TOKEN','')
        if not token:raise ValueError('Isi CLIPPER_DRIVE_ACCESS_TOKEN dengan akses akun Google Drive pilihan')
        headers={'Authorization':'Bearer '+token};account=requests.get('https://www.googleapis.com/drive/v3/about',params={'fields':'user'},headers=headers,timeout=30)
        account.raise_for_status();user=account.json()['user'];file_id=request['file_id']
        if not re.fullmatch(r'[\w-]{5,200}',file_id):raise ValueError('File ID Drive tidak valid')
        metadata=requests.get('https://www.googleapis.com/drive/v3/files/'+file_id,params={'fields':'id,name,size,capabilities(canDownload)'},headers=headers,timeout=30)
        metadata.raise_for_status();meta=metadata.json()
        if not meta.get('capabilities',{}).get('canDownload'):raise ValueError('Akun Drive tidak dapat mengunduh media ini')
        download='https://www.googleapis.com/drive/v3/files/'+file_id+'?alt=media';verified={'permission_id':user.get('permissionId'),'email':user.get('emailAddress')}
    elif kind=='zoom':
        token=os.environ.get('CLIPPER_ZOOM_ACCESS_TOKEN','')
        if not token:raise ValueError('Isi CLIPPER_ZOOM_ACCESS_TOKEN dengan akses rekaman akun Zoom pilihan')
        headers={'Authorization':'Bearer '+token};account=requests.get('https://api.zoom.us/v2/users/me',headers=headers,timeout=30);account.raise_for_status();user=account.json()
        meeting=request['meeting_id']
        if not re.fullmatch(r'[\w-]{5,100}',str(meeting)):raise ValueError('Meeting ID Zoom tidak valid')
        response=requests.get('https://api.zoom.us/v2/meetings/'+str(meeting)+'/recordings',headers=headers,timeout=30);response.raise_for_status()
        candidates=[r for r in response.json().get('recording_files',[]) if r.get('status')=='completed' and r.get('file_type') in ('MP4','M4A')]
        if request.get('recording_id'):candidates=[r for r in candidates if r['id']==request['recording_id']]
        if not candidates:raise ValueError('Rekaman Zoom lengkap belum tersedia untuk akun ini')
        download=candidates[0]['download_url'];verified={'id':user.get('id'),'email':user.get('email')}
    else:raise ValueError('Connector tidak valid')
    result=direct_download({**request,'url':download},folder,headers=headers)
    result['receipt'].update(provider=kind,account_identity=verified,access_verified_by_provider=True)
    return result


class SourceImports:
    def __init__(self,service):
        self.service=service;self.stop=threading.Event();self.thread=None;self.owner=uuid.uuid4().hex
        with service.store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS m2_imports(id TEXT PRIMARY KEY,batch_id TEXT,identity TEXT UNIQUE,status TEXT,request TEXT,result TEXT,error TEXT,created REAL,updated REAL,pid INTEGER,birth TEXT,lease TEXT);
                CREATE TABLE IF NOT EXISTS m2_import_operations(id TEXT PRIMARY KEY,digest TEXT,items TEXT);
                CREATE TABLE IF NOT EXISTS m2_monitors(id TEXT PRIMARY KEY,config TEXT,observed TEXT,error TEXT,updated REAL);
                CREATE TABLE IF NOT EXISTS m2_seen(monitor_id TEXT,identity TEXT,item_id TEXT,PRIMARY KEY(monitor_id,identity));''')
        if service.queue.autostart:self.recover()

    def recover(self):
        with self.service.store.connect() as db:
            for row in db.execute("SELECT id,pid,birth,updated FROM m2_imports WHERE status='running'").fetchall():
                dead=row['pid'] and process_birth(row['pid'])!=row['birth']
                not_launched=not row['pid'] and time.time()-row['updated']>15
                if dead or not_launched:
                    db.execute("UPDATE m2_imports SET status='interrupted',error='Proses impor sebelumnya terputus',updated=? WHERE id=? AND status='running'",(time.time(),row['id']))

    def get(self,iid):
        with self.service.store.connect() as db:r=db.execute('SELECT * FROM m2_imports WHERE id=?',(iid,)).fetchone()
        if not r:raise KeyError('Impor tidak ditemukan')
        return {**dict(r),'request':json.loads(r['request']),'result':json.loads(r['result']) if r['result'] else None}

    def list(self):
        with self.service.store.connect() as db:ids=[r[0] for r in db.execute('SELECT id FROM m2_imports ORDER BY created DESC LIMIT 200')]
        return {'items':[self.get(i) for i in ids],'monitors':self.monitors(),'queue_status':'import_only; ASR is a separate job'}

    def submit(self,data):
        items=data.get('items');operation=data.get('operation_id')
        if not isinstance(items,list) or not 1<=len(items)<=50 or any(not isinstance(r,dict) for r in items):raise ValueError('Kirim 1–50 sumber')
        if not isinstance(operation,str) or not 8<=len(operation)<=160:raise ValueError('ID operasi batch diperlukan')
        for flag in ('auto_analyze','force_new'):
            if flag in data and type(data[flag]) is not bool:raise ValueError(flag+' harus boolean')
        from .config import validate_overrides
        settings=validate_overrides(data.get('settings',{}));normalized=[]
        for item in items:
            kind=item.get('kind','platform');req={**item,'kind':kind,'max_bytes':limit_bytes(item.get('max_bytes',DEFAULT_MAX_BYTES)),
                'settings':settings,'auto_analyze':data.get('auto_analyze',False)}
            if item.get('sha256') and (not isinstance(item['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',item['sha256'])):raise ValueError('SHA-256 tidak valid')
            if kind=='local':
                path=Path(item['path']).expanduser().resolve()
                if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:raise ValueError('Sumber lokal video/audio tidak tersedia')
                req.update(path=str(path),expected_content_id=content_id(path,fresh=True))
            elif kind in ('direct','platform'):req['url']=url(item['url'])
            elif kind=='assembly':
                from .source_assembly import validate_segments
                req['segments']=validate_segments(self.service,item['segments'])
            elif kind not in ('drive','zoom'):raise ValueError('Jenis impor tidak dikenal')
            normalized.append(req)
        digest=fingerprint(data);batch='batch-'+uuid.uuid4().hex[:20];ids=[]
        with self.service.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                old=db.execute('SELECT * FROM m2_import_operations WHERE id=?',(operation,)).fetchone()
                if old:
                    if old['digest']!=digest:raise ValueError('ID operasi dipakai untuk batch berbeda')
                    ids=json.loads(old['items'])
                else:
                    for request in normalized:
                        identity=fingerprint(request)+(':'+uuid.uuid4().hex if data.get('force_new') else '')
                        prior=db.execute('SELECT id FROM m2_imports WHERE identity=?',(identity,)).fetchone()
                        iid=prior[0] if prior else 'import-'+uuid.uuid4().hex[:20]
                        if not prior:db.execute('INSERT INTO m2_imports VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(iid,batch,identity,'queued',dumps(request),None,None,time.time(),time.time(),None,None,None))
                        ids.append(iid)
                    db.execute('INSERT INTO m2_import_operations VALUES(?,?,?)',(operation,digest,dumps(ids)))
                db.commit()
            except BaseException:db.rollback();raise
        self.start();return {'items':[self.get(i) for i in ids],'batch_id':batch}

    def process(self,iid,lease=None):
        lease=lease or self.owner+':'+uuid.uuid4().hex
        with self.service.store.connect() as db:
            if lease and db.execute("UPDATE m2_imports SET status='running',lease=?,updated=? WHERE id=? AND status='queued'",(lease,time.time(),iid)).rowcount!=1:
                existing=self.get(iid)
                if existing['status']!='running' or existing['lease']!=lease:raise ValueError('Impor tidak lagi dimiliki worker')
        item=self.get(iid);request=item['request'];folder=self.service.work/'source-imports'/fingerprint({k:v for k,v in request.items() if k not in ('settings','auto_analyze')})[:32]
        def check():
            current=self.get(iid)
            if current['status']!='running' or current['lease']!=lease:raise ValueError('Impor dibatalkan atau worker berubah')
        try:
            check();kind=request['kind']
            if kind=='local':
                identity=content_id(request['path'],fresh=True)
                if identity!=request['expected_content_id']:raise ValueError('Sumber lokal berubah sejak ditambahkan ke antrean')
                identity,info=_complete(request['path'],request)
                result={'path':request['path'],'content_id':identity,'info':info,'receipt':{'provider':'local','complete_media_probed':True,'source_content_id':identity}}
            elif kind=='assembly':
                from .source_assembly import assemble
                result=assemble(self.service,request,folder,check)
            elif kind=='direct':result=direct_download(request,folder)
            elif kind=='platform':result=platform_download(request,folder)
            else:result=connector_download(request,folder)
            check();project=self.service.create(result['path'],request.get('settings'),request.get('name'));pid=project['project_id']
            if project['source']['source_id']!=result['content_id']:raise ValueError('Sumber berubah sebelum pembuatan proyek')
            def attach(doc):
                doc['source']['import_receipt']=result['receipt'];doc['source']['import_id']=iid
                if result.get('lineage'):doc['source']['lineage']=result['lineage']
                if result.get('transcript_id'):
                    raise ValueError('Assembly transcript tidak boleh merujuk proyek lain')
            check();self.service.store.mutate(pid,project['revision'],iid+'-attach',{'import_id':iid,'receipt':result['receipt']},attach,'M2 identitas sumber impor')
            if result.get('transcript'):
                take=self.service.store.save_transcript(pid,result['transcript']);current=self.service.store.get(pid)
                self.service.store.mutate(pid,current['revision'],iid+'-transcript',{'take':take},lambda d:d.update(transcript_id=take,transcript_revision=1),'M2 lineage transkrip gabungan')
            result={k:v for k,v in result.items() if k!='transcript'};result['project_id']=pid
            check()
            with self.service.store.connect() as db:
                if db.execute("UPDATE m2_imports SET status='completed',result=?,error=NULL,updated=? WHERE id=? AND status='running' AND lease=?",(dumps(result),time.time(),iid,lease)).rowcount!=1:raise ValueError('Impor tidak lagi aktif')
            if request.get('auto_analyze'):
                try:self.service.enqueue(pid,'analyze')
                except Exception as exc:result['asr_enqueue_error']=safe_error(exc)
            return result
        except Exception as exc:
            with self.service.store.connect() as db:db.execute("UPDATE m2_imports SET status='failed',error=?,updated=? WHERE id=? AND status='running' AND lease=?",(safe_error(exc),time.time(),iid,lease))
            raise

    def cancel(self,iid):
        item=self.get(iid)
        with self.service.store.connect() as db:db.execute("UPDATE m2_imports SET status='canceled',updated=? WHERE id=? AND status IN ('queued','running')",(time.time(),iid))
        terminate_owned(item['pid'],item['birth']);return self.get(iid)

    def resume(self,iid):
        with self.service.store.connect() as db:
            if db.execute("UPDATE m2_imports SET status='queued',error=NULL,pid=NULL,birth=NULL,lease=NULL,updated=? WHERE id=? AND status IN ('failed','interrupted','canceled')",(time.time(),iid)).rowcount!=1:raise ValueError('Impor ini tidak perlu dilanjutkan')
        self.start();return self.get(iid)

    def start(self):
        if not self.service.queue.autostart or self.stop.is_set() or self.thread and self.thread.is_alive():return
        self.thread=threading.Thread(target=self._loop,daemon=True);self.thread.start()

    def _loop(self):
        scanned=0
        while not self.stop.wait(.2):
            self.recover()
            if time.monotonic()-scanned>5:
                for monitor in self.monitors():
                    if monitor['config'].get('enabled') and (monitor['config']['kind']=='folder' or time.time()-monitor['updated']>300):
                        try:self.scan(monitor['id'])
                        except Exception as exc:
                            with self.service.store.connect() as db:db.execute('UPDATE m2_monitors SET error=?,updated=? WHERE id=?',(safe_error(exc),time.time(),monitor['id']))
                scanned=time.monotonic()
            with self.service.store.connect() as db:
                row=db.execute("SELECT id FROM m2_imports WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
                if not row:continue
                iid=row['id'];lease=self.owner+':'+uuid.uuid4().hex
                if db.execute("UPDATE m2_imports SET status='running',lease=?,updated=? WHERE id=? AND status='queued'",(lease,time.time(),iid)).rowcount!=1:continue
            env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
            kwargs={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
            log=self.service.work/'source-imports'/('worker-'+iid+'.log');log.parent.mkdir(parents=True,exist_ok=True)
            try:
                with log.open('ab') as stream:
                    proc=subprocess.Popen([sys.executable,'-m','clipper.source_imports','--db',str(self.service.store.path),'--root',str(self.service.root),
                        '--job',iid,'--lease',lease,'--base',dumps({k:v for k,v in asdict(self.service.base).items() if k!='pexels_key'})],cwd=self.service.root,env=env,stdout=stream,stderr=subprocess.STDOUT,**kwargs)
                    birth=process_birth(proc.pid)
                    with self.service.store.connect() as db:db.execute('UPDATE m2_imports SET pid=?,birth=? WHERE id=? AND lease=?',(proc.pid,birth,iid,lease))
                    while proc.poll() is None:
                        if self.stop.wait(.1) or self.get(iid)['status']!='running':
                            terminate_owned(proc.pid,birth)
                            if proc.poll() is None:proc.terminate()
                            try:proc.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                terminate_owned(proc.pid,birth,force=True);proc.kill();proc.wait()
                            break
                if self.get(iid)['status']=='running':
                    with self.service.store.connect() as db:db.execute("UPDATE m2_imports SET status='interrupted',error='Worker impor berakhir sebelum publikasi',updated=? WHERE id=? AND lease=?",(time.time(),iid,lease))
                self.service.queue.start()
            except Exception as exc:
                with self.service.store.connect() as db:db.execute("UPDATE m2_imports SET status='failed',error=?,updated=? WHERE id=? AND status='running' AND lease=?",(safe_error(exc),time.time(),iid,lease))

    def close(self):
        self.stop.set()
        with self.service.store.connect() as db:rows=db.execute("SELECT id,pid,birth FROM m2_imports WHERE status='running' AND lease LIKE ?",(self.owner+':%',)).fetchall()
        for row in rows:
            terminate_owned(row['pid'],row['birth'])
            with self.service.store.connect() as db:db.execute("UPDATE m2_imports SET status='interrupted',updated=? WHERE id=? AND status='running'",(time.time(),row['id']))
        if self.thread:self.thread.join(4)

    def monitors(self):
        with self.service.store.connect() as db:rows=db.execute('SELECT * FROM m2_monitors ORDER BY id').fetchall()
        return [{**dict(r),'config':json.loads(r['config']),'observed':json.loads(r['observed'])} for r in rows]

    def save_monitor(self,data):
        cfg=dict(data);kind=cfg.get('kind');mid=cfg.pop('id',None) or 'monitor-'+uuid.uuid4().hex[:20]
        if type(cfg.get('enabled',True)) is not bool:raise ValueError('Pilihan monitor harus boolean')
        cfg.setdefault('enabled',True)
        if kind=='folder':
            path=Path(cfg['path']).expanduser().resolve()
            if not path.is_dir():raise ValueError('Folder monitor tidak ditemukan')
            cfg['path']=str(path)
        elif kind=='channel':
            cfg['url']=url(cfg['url'])
            if cfg.get('own_channel_confirmed') is not True:raise ValueError('Konfirmasi channel milik Anda untuk monitor ini')
            cfg['ownership_status']='user_declared; OAuth_ownership_pending'
            for k in ('date_after','date_before'):
                if cfg.get(k) and not re.fullmatch(r'\d{8}',cfg[k]):raise ValueError('Filter tanggal harus YYYYMMDD')
        else:raise ValueError('Jenis monitor tidak valid')
        from .config import validate_overrides
        cfg['settings']=validate_overrides(cfg.get('settings',{}))
        if type(cfg.get('auto_analyze',False)) is not bool:raise ValueError('auto_analyze harus boolean')
        with self.service.store.connect() as db:
            db.execute('INSERT INTO m2_monitors VALUES(?,?,?,NULL,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config,error=NULL',
                (mid,dumps(cfg),'{}',0))
        self.start();return next(r for r in self.monitors() if r['id']==mid)

    def scan(self,mid,*,now=None):
        monitor=next((m for m in self.monitors() if m['id']==mid),None)
        if not monitor:raise KeyError('Monitor tidak ditemukan')
        cfg=monitor['config'];observed={};candidates=[];now=time.time() if now is None else now
        if cfg['kind']=='folder':
            for path in sorted(Path(cfg['path']).iterdir()):
                if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:continue
                stat=path.stat();sig=[stat.st_size,stat.st_mtime_ns];old=monitor['observed'].get(str(path),{})
                stable=old.get('signature')==sig;since=old.get('since',now) if stable else now
                observed[str(path)]={'signature':sig,'since':since}
                if stable and now-since>=2:candidates.append(('local',{'kind':'local','path':str(path)},content_id(path,fresh=True)))
        else:
            inspected=inspect_playlist(cfg['url'],50,detailed=True)
            for row in inspected['items']:
                date=row.get('upload_date') or ''
                if cfg.get('date_after') and date<cfg['date_after'] or cfg.get('date_before') and date>cfg['date_before']:continue
                if cfg.get('title_contains') and cfg['title_contains'].casefold() not in row['title'].casefold():continue
                if cfg.get('channel_id') and row.get('channel_id')!=cfg['channel_id']:continue
                candidates.append(('platform',{'kind':'platform','url':row['url'],'name':row['title']},fingerprint([row['id'],row['url']])))
        added=[]
        for _,item,identity in candidates:
            identity=fingerprint([identity,cfg.get('settings'),cfg.get('auto_analyze',False)])
            with self.service.store.connect() as db:seen=db.execute('SELECT 1 FROM m2_seen WHERE monitor_id=? AND identity=?',(mid,identity)).fetchone()
            if seen:continue
            batch=self.submit({'items':[item],'settings':cfg.get('settings',{}),'auto_analyze':cfg.get('auto_analyze',False),'operation_id':'monitor-'+fingerprint([mid,identity])})
            iid=batch['items'][0]['id']
            with self.service.store.connect() as db:db.execute('INSERT OR IGNORE INTO m2_seen VALUES(?,?,?)',(mid,identity,iid))
            added.append(iid)
        with self.service.store.connect() as db:db.execute('UPDATE m2_monitors SET observed=?,error=NULL,updated=? WHERE id=?',(dumps(observed),now,mid))
        return {'added':added,'monitor_id':mid,'ownership_status':cfg.get('ownership_status')}


def main():
    import argparse
    from .config import Config
    from .studio_service import StudioService
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True);parser.add_argument('--root',required=True);parser.add_argument('--job',required=True);parser.add_argument('--lease',required=True);parser.add_argument('--base',required=True);args=parser.parse_args()
    service=StudioService(args.root,Config(**json.loads(args.base)),db_path=args.db,autostart=False,recover=False);imports=service.imports
    deadline=time.monotonic()+3
    while imports.get(args.job).get('pid') is None and time.monotonic()<deadline:time.sleep(.05)
    if imports.get(args.job).get('pid')!=os.getpid():raise ValueError('Worker impor belum terdaftar; hentikan orphan')
    imports.process(args.job,args.lease)


if __name__=='__main__':main()
