"""Owned cache inventory, selected cleanup, portable project backups and relink."""
import copy
import json
import shutil
import time
import zipfile
from pathlib import Path
from .contracts import fingerprint
from .dependency_cache import content_id
from .project_store import Conflict,dumps
from .storage import write_json
from .studio_service import identifier
from .job_queue import ACTIVE


def inventory(service):
    entries=[];seen=set();protected=set();documents=[service.store.get(p['project_id']) for p in service.store.list()]
    for doc in documents:
        paths=[doc['source'].get('path'),doc['source'].get('media_context',{}).get('payload',{}).get('working_path')]
        for c in doc['clips'].values():
            for v in c['variants'].values():paths.extend(s.get('asset',{}).get('path') for s in v.get('recipe',{}).get('scenes',[]))
        paths.extend(doc['settings'].get(k) for k in ('music_path','sfx_path'))
        protected.update(str(Path(p).resolve()) for p in paths if p)
    # Only preview subtrees and their temporary renders can be deleted here.
    for project in documents:
        pid=project['project_id'];work=service.work/pid;roots=[('preview',work/'cache'/'previews',True),
            ('canonical',work/'cache'/'canonical',False),('analysis',work,False),('results',Path(service.base.out_dir)/pid,False)]
        for category,root,deletable in roots:
            if not root.is_dir() or root.is_symlink():continue
            for path in sorted(root.rglob('*')):
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()) or path in seen:continue
                seen.add(path);stat=path.stat()
                entries.append({'id':fingerprint([str(path.resolve()),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]),'project_id':pid,
                    'category':category,'name':str(path.relative_to(root)),'bytes':stat.st_size,'modified':stat.st_mtime,
                    'last_used':stat.st_atime,'deletable':deletable and str(path.resolve()) not in protected,'path':str(path.resolve()),'project_name':project['name']})
        source=Path(project['source']['path'])
        if source.is_file() and source not in seen:
            seen.add(source);stat=source.stat();entries.append({'id':fingerprint([str(source.resolve()),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]),
                'project_id':pid,'project_name':project['name'],'category':'source','name':source.name,'bytes':stat.st_size,
                'modified':stat.st_mtime,'deletable':False,'path':str(source.resolve())})
    # Recognizable 2.x/3.x preview files are also owned cache, including orphan sessions.
    from .library_paths import disposable_files
    for path in disposable_files(service.work,service.base.out_dir):
        if path in seen or str(path.resolve()) in protected:continue
        stat=path.stat();entries.append({'id':fingerprint([str(path.resolve()),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]),
            'project_id':'legacy','project_name':'Preview sesi lama','category':'preview','name':path.name,'bytes':stat.st_size,
            'modified':stat.st_mtime,'deletable':True,'path':str(path.resolve())})
    return {'entries':entries,'bytes':sum(e['bytes'] for e in entries),'cache_bytes':sum(e['bytes'] for e in entries if e['deletable']),
        'etag':fingerprint([(e['id'],e['bytes']) for e in entries]),'protection':'Sumber, transkrip, koreksi, hasil final, proyek editor, dan model tidak termasuk cache yang dihapus.'}


def cleanup(service,ids,etag):
    if any(j['status'] in ACTIVE for j in service.queue.list()):raise ValueError('Tunggu atau batalkan antrean sebelum membersihkan cache')
    if not service.queue.lock.acquire(blocking=False):raise ValueError('Sumber daya sedang digunakan')
    try:
        listing=inventory(service)
        if listing['etag']!=etag:raise Conflict(0,'Daftar berkas berubah; periksa daftar baru sebelum menghapus cache')
        selected=set(ids);matches=[e for e in listing['entries'] if e['id'] in selected]
        if len(matches)!=len(selected) or any(not e['deletable'] for e in matches):raise ValueError('Pilihan berkas bukan cache preview milik aplikasi')
        for entry in matches:Path(entry['path']).unlink(missing_ok=True)
        return {'deleted':len(matches),'bytes':sum(e['bytes'] for e in matches)}
    finally:service.queue.lock.release()


def enforce_limit(service):
    listing=inventory(service)
    limits=[float(service.store.get(p['project_id'])['settings'].get('cache_limit_gb',0)) for p in service.store.list()]
    limit=min((v for v in limits if v>0),default=0)*1024**3
    if not limit or listing['cache_bytes']<=limit:return {'deleted':0}
    remaining=listing['cache_bytes'];selected=[]
    for entry in sorted((e for e in listing['entries'] if e['deletable']),key=lambda e:e.get('last_used',e['modified'])):
        if remaining<=limit:break
        selected.append(entry['id']);remaining-=entry['bytes']
    return cleanup(service,selected,listing['etag'])


def backup(service,project_id,include_source=False):
    doc=service.store.get(project_id);folder=Path(service.base.out_dir)/project_id/'backups';folder.mkdir(parents=True,exist_ok=True)
    path=folder/('backup-'+str(time.time_ns())+'.zip');pending=path.with_suffix('.partial.zip');files={};mapping={}
    # Pack exact assets referenced by the project; cache/preview/video outputs can be rebuilt.
    asset_paths=[]
    for clip in doc['clips'].values():
        for variant in clip['variants'].values():
            for scene in variant.get('recipe',{}).get('scenes',[]):asset_paths.append(scene.get('asset',{}).get('path'))
    for settings in [doc['settings'],*[v.get('settings',{}) for c in doc['clips'].values() for v in c['variants'].values()]]:
        asset_paths += [settings.get('music_path'),settings.get('sfx_path')]
    if include_source:asset_paths.append(doc['source']['path'])
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
        for item in dict.fromkeys(p for p in asset_paths if p):
            p=Path(item)
            if not p.is_file():continue
            digest=content_id(p,fresh=True);name='media/'+digest[7:23]+p.suffix.lower();archive.write(p,name)
            files[name]=digest;mapping[str(p.resolve())]=name
        archive.writestr('project.json',dumps(doc))
        takes={doc.get('transcript_id')}|{p['transcript_id'] for g in [doc.get('shared_corrections',{}),*doc.get('clip_corrections',{}).values()] for p in g.values()}
        transcripts={take:service.store.transcript(take) for take in takes if take}
        archive.writestr('transcripts.json',dumps(transcripts));archive.writestr('history.json',dumps(service.store.history(project_id,100)))
        for name,value in [('project.json',dumps(doc)),('transcripts.json',dumps(transcripts))]:
            import hashlib
            files[name]='sha256:'+hashlib.sha256(value.encode()).hexdigest()
        archive.writestr('manifest.json',dumps({'version':1,'project_id':project_id,'files':files,'path_map':mapping,
            'source_included':include_source,'note':'Hasil render dapat dibuat kembali. Riwayat lama disertakan sebagai arsip.'}))
    pending.replace(path)
    return {'file':str(path),'url':service.register_file(project_id,path),'source_included':include_source}


def restore(service,path):
    import hashlib
    destination=service.work/identifier('restore');destination.mkdir(parents=True,exist_ok=False);created_id=None
    try:
        with zipfile.ZipFile(path) as archive:
            infos=archive.infolist()
            if len(infos)>10000 or sum(i.file_size for i in infos)>100*1024**3:raise ValueError('Paket backup melebihi batas')
            if len({i.filename for i in infos})!=len(infos):raise ValueError('Nama ganda dalam paket backup')
            for info in infos:
                target=(destination/info.filename).resolve()
                if not target.is_relative_to(destination.resolve()) or '\\' in info.filename or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Path tidak aman dalam backup')
            manifest=json.loads(archive.read('manifest.json'))
            if manifest.get('version')!=1:raise ValueError('Versi backup belum didukung')
            for name,expected in manifest['files'].items():
                if name not in {i.filename for i in infos} or not (destination/name).resolve().is_relative_to(destination.resolve()):raise ValueError('Manifest backup tidak valid')
                target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(name) as src,target.open('wb') as dst:shutil.copyfileobj(src,dst,4*1024*1024)
                if content_id(target,fresh=True)!=expected:raise ValueError('Checksum backup tidak cocok: '+name)
            doc=json.loads((destination/'project.json').read_text(encoding='utf-8'))
            transcripts=json.loads((destination/'transcripts.json').read_text(encoding='utf-8'))
        mapping={old:str(destination/packed) for old,packed in manifest['path_map'].items()}
        def rewrite(value):
            if isinstance(value,dict):return {k:rewrite(v) for k,v in value.items()}
            if isinstance(value,list):return [rewrite(v) for v in value]
            return mapping.get(value,value) if isinstance(value,str) else value
        doc=rewrite(doc);old_id=doc['project_id'];doc.pop('revision',None);doc.pop('updated',None);doc['name']+=' (dipulihkan)';doc['exports']=[]
        doc['source'].pop('media_context',None)
        for clip in doc['clips'].values():
            for variant in clip['variants'].values():
                for key in ('result','preview','schedule','schedule_dependency','asset_proposals','timeline_summary','shot_summary'):variant.pop(key,None)
        created=service.store.create(doc);pid=created['project_id'];created_id=pid;take_map={}
        for take,transcript in transcripts.items():take_map[take]=service.store.save_transcript(pid,transcript)
        def change(current):
            if current.get('transcript_id'):current['transcript_id']=take_map[current['transcript_id']]
            for group in [current.get('shared_corrections',{}),*current.get('clip_corrections',{}).values()]:
                for patch in group.values():patch['transcript_id']=take_map[patch['transcript_id']]
            current['restored_from']=old_id
        service.store.mutate(pid,0,identifier('restore'),{'restore':old_id},change,'Pulihkan sebagai proyek baru')
        return service.public(pid)
    except BaseException:
        if created_id:
            with service.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM words WHERE take_id IN (SELECT id FROM transcripts WHERE project_id=?)',(created_id,))
                for table in ('transcripts','operations','history','files'):db.execute('DELETE FROM '+table+' WHERE project_id=?',(created_id,))
                db.execute('DELETE FROM projects WHERE id=?',(created_id,));db.commit()
        shutil.rmtree(destination,ignore_errors=True);raise


def relink(service,project_id,path,expected_revision,operation_id):
    path=Path(path).expanduser().resolve();digest=content_id(path,fresh=True);doc=service.store.get(project_id)
    unverified=doc['source']['source_id'].startswith('legacy-unverified:')
    if not unverified and digest!=doc['source']['source_id']:raise ValueError('Isi berkas berbeda. Buat proyek baru atau pilih sumber asli agar koreksi tidak berpindah ke ucapan lain.')
    info=None
    if unverified:
        from .media_context import inspect
        info=inspect(path)
    def change(current):
        current['source']['path']=str(path)
        if unverified:
            current['source'].update(info=info,requires_analysis=True)
            current['source']['relink_note']='Sesi 3.3 belum memiliki checksum sumber. Analisis ulang wajib; transkrip dan koreksi lama diarsipkan.'
        media=current['source'].get('media_context')
        if media:
            payload=media['payload'];payload['source_path']=str(path)
            if not payload.get('normalized'):payload['working_path']=str(path)
    return service.store.mutate(project_id,expected_revision,operation_id,{'relink':str(path),'content_id':digest},change,'Tautkan berkas sumber yang sama')
