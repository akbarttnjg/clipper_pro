"""M9 studio facade. Heavy work shares the existing durable serial queue."""
import copy
import json
import time
from dataclasses import asdict
from pathlib import Path
from .m8_contract import AccessDenied, canonical, only
from .m8_workspace import Actor
from .m8_store import ident
from .m9_contract import VERSION, artifact, safe_media, sha
from .m9_store import Store
from .project_store import Conflict, JobLeaseLost

READ = {'m9.status','m9.list','m9.get','m9.record.get','m9.job.get','m9.dub.plan'}
PERMISSIONS = {key:'edit' for key in ('m9.record.create','m9.record.stage','m9.record.revoke','m9.record.seal','m9.record.offset',
    'm9.record.finalize','m9.record.recover','m9.record.pause','m9.effects.submit','m9.lut.register','m9.creative.save','m9.creative.generate','m9.creative.propose',
    'm9.voice.register','m9.tts.submit','m9.provider.register','m9.provider.probe','m9.provider.reconcile','m9.generate.submit','m9.media.import','m9.podcast.submit',
    'm9.buffer.submit','m9.job.cancel','m9.job.resume','m9.preset.save','m9.preset.load','m9.preset.export','m9.preset.import','m9.dub.submit','m9.dub.accept')}
for _key in ('m9.voice.register','m9.provider.register','m9.provider.probe','m9.provider.reconcile','m9.lut.register'):PERMISSIONS[_key]='manage'


class Lab:
    def __init__(self, service):
        self.service=service;self.m8=service.integrations;self.root=service.work/'m9';self.root.mkdir(parents=True,exist_ok=True)
        self.store=Store(self)
        from .m9_recording import Recording
        from .m9_effects import Effects
        self.recording=Recording(self);self.effects=Effects(self)
        from .m9_creative import Creative
        from .m9_providers import Providers
        from .m9_delivery import Delivery
        from .m9_dubbing import Dubbing
        self.creative=Creative(self);self.providers=Providers(self);self.delivery=Delivery(self);self.dubbing=Dubbing(self)

    def operator(self, workspace):
        with self.service.store.connect() as db:row=db.execute("SELECT user_id FROM m8_members WHERE workspace=? AND role='owner' ORDER BY user_id LIMIT 1",(workspace,)).fetchone()
        if not row:raise AccessDenied('Workspace tidak memiliki operator pemilik')
        return Actor(workspace,row['user_id'],local=True)

    def check_job(self, job, db=None):
        if db is None:
            with self.service.store.connect() as connection:return self.check_job(job,connection)
        row=db.execute('SELECT status,owner,lease_token,lease_expires FROM jobs WHERE id=?',(job['id'],)).fetchone()
        if not row or row['status']!='running' or row['owner']!=job['owner'] or row['lease_token']!=job['lease_token'] or not row['lease_expires'] or row['lease_expires']<=time.time():
            raise JobLeaseLost('Tugas M9 dibatalkan atau lease tidak berlaku')

    def finish(self, db, job, result, message='Hasil M9 tersimpan; periksa sebelum dipakai'):
        self.check_job(job,db)
        db.execute("UPDATE jobs SET status='completed',progress=100,result=?,message=?,updated=?,lease_expires=NULL WHERE id=?",
                   (canonical(result),message,time.time(),job['id']))

    def enqueue(self, actor, kind, snapshot, item_id=None):
        self.m8.workspaces.require(actor,'edit',snapshot.get('project_id'))
        snapshot={**copy.deepcopy(snapshot),'workspace':actor.workspace,'audit_release':'4.0.22'}
        snapshot['config']={k:v for k,v in asdict(self.service.base).items() if k!='pexels_key'}
        item_id=item_id or snapshot.get('project_id') or ident('m9task')
        with self.m8.db.transaction() as db:
            reference='m9-'+sha(canonical([kind,snapshot,item_id]).encode())
            self.m8.workspaces.reserve(db,actor,'job',reference)
        return self.service.queue.enqueue(item_id,kind,{}, {'m9':snapshot})

    def publish_derivative(self, job, actor, path, name, lineage, manifest_path, source_guard=None, *, item_id=None, extra=None):
        from .media_context import inspect
        from .dependency_cache import content_id
        path=safe_media(path,self.root);info=inspect(path)
        if not info['audio_tracks']:raise ValueError('Media baru untuk editor memerlukan track audio')
        key=sha(('m9-project-'+job['id']).encode())[:12];now=time.time()
        cfg={k:v for k,v in asdict(self.service.base).items() if k!='pexels_key'}
        if source_guard:
            parent=self.service.store.get(source_guard['project_id'])
            cfg.update({k:v for k,v in parent.get('settings',{}).items() if k!='pexels_key'})
        cfg.update(punch_zoom=False,cold_open=False,title_card=False,audio_stream_index=-1)
        if lineage.get('capture_primary_kind') in ('screen','slides'):
            cfg.update(source_kind='screen',layout='fit',preserve_material_pauses=True,trim_silence=False)
        doc={'project_id':key,'schema_version':4,'name':name[:160],'settings':cfg,'source':{'path':str(path),'source_id':content_id(path,fresh=True),'info':info,'lineage':lineage},
            'clips':{},'aliases':[],'shared_corrections':{},'clip_corrections':{},'transcript_revision':0,'exports':[]}
        result={'project_id':key,'content_id':doc['source']['source_id'],'manifest_path':str(manifest_path),**(extra or {})}
        with self.m8.db.transaction() as db:
            self.check_job(job,db)
            if source_guard:
                row=db.execute('SELECT revision,document FROM projects WHERE id=?',(source_guard['project_id'],)).fetchone()
                if not row:
                    raise ValueError('Proyek sumber tidak ditemukan')
                from .source_guard import verify
                verify(self.service,source_guard,json.loads(row['document']),row['revision'])
            db.execute('INSERT INTO projects VALUES(?,0,?,?,?)',(key,canonical(doc),now,now))
            db.execute('INSERT INTO m8_projects(project_id,workspace) VALUES(?,?)',(key,actor.workspace))
            if item_id:
                item=self.store.get(actor,item_id,db=db);value=item['data']
                if item['kind']=='recording' and (item['version']!=(extra or {}).get('recording_version') or value['status']!='finalizing'):
                    from .studio_worker import StaleJob
                    raise StaleJob('Finalisasi rekaman telah diganti; proyek tidak diterbitkan')
                if item['kind']=='dubbing' and (item['version']!=(extra or {}).get('dubbing_version') or value['status']!='awaiting_listening'):
                    from .studio_worker import StaleJob
                    raise StaleJob('Kandidat dubbing telah berubah atau diterima; proyek tidak diterbitkan ulang')
                value.update(status='ready',project_id=key,manifest_path=str(manifest_path),program_path=str(path),program_content_id=doc['source']['source_id'],**(extra or {}))
                db.execute('UPDATE m9_items SET data=?,version=version+1,updated=? WHERE id=?',(canonical(value),now,item_id))
            self.finish(db,job,result)
            self.m8.db.event(db,actor.workspace,'m9.derivative.ready',key,0,{'job_id':job['id'],'content_id':result['content_id']})
        return result

    def public_item(self, actor, item):
        result=copy.deepcopy(item)
        for key in ('path','program_path','manifest_path','archive_path','original_path','dubbed_path','sample_path','executable','model_path','config_path','workflow_path'):
            value=result['data'].pop(key,None)
            if value and key in ('path','program_path','manifest_path','archive_path','original_path','dubbed_path') and Path(value).is_file():
                result['data'][key.replace('_path','')+'_url']=self.m8.register_file(actor,value,result['data'].get('project_id'))
        return result

    def dispatch(self, actor, action, data, command_id=None):
        if action=='m9.status':
            only(data,());from .m9_media import available_filters
            with self.service.store.connect() as db:holds=[dict(r) for r in db.execute("SELECT job_id,provider_id,state,prompt_id FROM m9_resource_holds WHERE workspace=? AND state!='released'",(actor.workspace,))]
            trace_path=Path(__file__).resolve().parents[1]/'docs/M9_REQUIREMENTS.json'
            return {'version':VERSION,'recording':'browser_capture_progressive_upload','live_monitoring':False,'multistream':'not_implemented',
                'filters':sorted(available_filters()),'paid_api_required':False,'default_no_pan':True,'default_hook':False,
                'capabilities':json.loads(trace_path.read_text()) if trace_path.is_file() else {},'providers':self.providers.listing(actor),'resource_holds':holds}
        if action=='m9.list':
            only(data,('kind',));return {'items':[self.public_item(actor,r) for r in self.store.listing(actor,data.get('kind'))]}
        if action=='m9.get':
            only(data,('id',),('id',));return self.public_item(actor,self.store.get(actor,data['id']))
        if action=='m9.record.create':return self.recording.create(actor,data)
        if action=='m9.record.get':
            only(data,('id',),('id',));row=self.recording.view(actor,data['id']);row=self.public_item(actor,row)
            for job in row['jobs']:job.pop('request',None)
            return row
        for name,method in [('stage',self.recording.stage),('revoke',self.recording.revoke),('seal',self.recording.seal),('offset',self.recording.offset),('finalize',self.recording.finalize)]:
            if action=='m9.record.'+name:return method(actor,data)
        if action=='m9.record.recover':
            only(data,('id','expected_version'),('id','expected_version'))
            row=self.recording.view(actor,data['id'])
            if any(j['status'] in ('queued','running','cancel_requested') for j in row['jobs']):raise ValueError('Antrean rekaman masih aktif')
            if row['data']['status']=='ready':raise ValueError('Rekaman sudah siap; buka hasilnya')
            def change(v,db):
                v['status']='capturing';p=v['participants']['host']
                if not p['onstage']:p['intervals'].append([max(0.,self.m8.db.clock()-v['clock_origin']),None]);p['onstage']=True
            return self.store.change(actor,row['id'],data['expected_version'],change)
        if action=='m9.record.pause':
            only(data,('id','expected_version'),('id','expected_version'))
            def change(v,db):
                if v['status']!='capturing':raise ValueError('Rekaman tidak sedang capture')
                v['status']='paused';now=max(0.,self.m8.db.clock()-v['clock_origin'])
                for p in v['participants'].values():
                    if p['onstage']:p['intervals'][-1][1]=now;p['onstage']=False
                db.execute('UPDATE m9_invites SET revoked=1 WHERE session_id=?',(data['id'],))
            return self.store.change(actor,data['id'],data['expected_version'],change)
        if action=='m9.effects.submit':return self.enqueue(actor,'effects_m9',self.effects.prepare(actor,data))
        if action=='m9.lut.register':return self.effects.register_lut(actor,data)
        if action=='m9.creative.save':return self.creative.save(actor,data)
        if action=='m9.creative.generate':return self.creative.generate(actor,data)
        if action=='m9.creative.propose':return self.creative.propose(actor,data,command_id)
        if action=='m9.voice.register':return self.providers.voice_register(actor,data)
        if action=='m9.tts.submit':return self.providers.tts_submit(actor,data)
        if action=='m9.dub.plan':return self.dubbing.plan(actor,data)
        if action=='m9.dub.submit':return self.dubbing.submit(actor,data)
        if action=='m9.dub.accept':return self.dubbing.accept(actor,data)
        if action=='m9.provider.register':return self.providers.register(actor,data)
        if action=='m9.provider.probe':return self.providers.probe(actor,data)
        if action=='m9.provider.reconcile':return self.providers.reconcile(actor,data)
        if action=='m9.generate.submit':return self.providers.submit(actor,data)
        if action=='m9.media.import':return self.providers.media_import(actor,data)
        if action=='m9.podcast.submit':return self.delivery.podcast(actor,data)
        if action=='m9.buffer.submit':return self.delivery.buffer(actor,data)
        if action in ('m9.job.get','m9.job.cancel','m9.job.resume'):
            only(data,('job_id',),('job_id',));job=self.service.queue.get(data['job_id'])
            if not job['kind'].endswith('_m9'):raise ValueError('Bukan tugas M9')
            snapshot=job['request']['m9']
            if snapshot['workspace']!=actor.workspace:raise AccessDenied('Tugas di luar workspace')
            self.m8.workspaces.require(actor,'read' if action=='m9.job.get' else 'edit',snapshot.get('project_id'))
            if action=='m9.job.cancel':job=self.service.queue.cancel(job['id'])
            if action=='m9.job.resume':
                if job['kind']=='recording_m9':raise ValueError('Gunakan pulihkan rekaman lalu finalisasi ulang')
                if job['kind']=='generate_m9':raise ValueError('Rekonsiliasi provider dahulu; inference generatif tidak diulang otomatis')
                job=self.service.queue.resume(job['id'])
            value={k:v for k,v in job.items() if k!='request'}
            if job.get('result'):
                value['result']=dict(job['result'])
                for key in ('manifest_path','archive_path','path'):
                    path=value['result'].pop(key,None)
                    if path and Path(path).is_file():value['result'][key.replace('_path','')+'_url']=self.m8.register_file(actor,path,value['result'].get('project_id'))
            return value
        if action=='m9.preset.save':
            from .m9_effects import recipe
            only(data,('name','recipe','duration','size','license'),('name','recipe','duration','size','license'))
            from .m8_contract import text
            from .m9_contract import number
            size=data['size']
            if not isinstance(size,list) or len(size)!=2:raise ValueError('Ukuran sumber tidak valid')
            from .m8_contract import integer
            size=[integer(n,'Ukuran',2,7680) for n in size]
            normalized=recipe(data['recipe'],number(data['duration'],'Durasi',.04,3600),size)
            return self.store.create(actor,'preset',{'name':text(data['name'],'Nama',100),'recipe':normalized,'size':size,'duration':data['duration'],
                'license':text(data['license'],'Lisensi',2000),'schema_version':1,'proprietary_assets_included':False})
        if action=='m9.preset.load':
            only(data,('id',),('id',));row=self.store.get(actor,data['id'])
            if row['kind']!='preset':raise ValueError('Bukan preset M9')
            return row
        if action=='m9.preset.export':
            only(data,('id',),('id',));row=self.store.get(actor,data['id'])
            if row['kind']!='preset':raise ValueError('Bukan preset M9')
            if any(o['kind'] in ('lut','overlay') for o in row['data']['recipe']['operations']):raise ValueError('Pack dengan aset eksternal memerlukan distribusi aset/lisensi terpisah; ekspor resep tanpa aset dahulu')
            from .m9_contract import atomic_bytes
            value={'schema_version':1,'kind':'clipper-m9-effect-pack','version':row['version']+1,'preset':row['data']}
            path=self.root/'packs'/(row['id']+'-v'+str(row['version']+1)+'.json');atomic_bytes(path,(canonical(value)+'\n').encode())
            return {'url':self.m8.register_file(actor,path),'content_id':artifact(path)['content_id'],'schema_version':1,'pack_version':row['version']+1}
        if action=='m9.preset.import':
            only(data,('file_id',),('file_id',));path=self.m8.file(actor,data['file_id'])
            if path.stat().st_size>1024**2:raise ValueError('Pack maksimal 1 MiB')
            value=json.loads(path.read_text());only(value,('schema_version','kind','version','preset'),('schema_version','kind','version','preset'))
            if type(value['schema_version']) is not int or value['schema_version']!=1 or value['kind']!='clipper-m9-effect-pack':raise ValueError('Schema pack belum didukung')
            if not isinstance(value['preset'],dict) or not isinstance(value['preset'].get('recipe'),dict) or not isinstance(value['preset']['recipe'].get('operations'),list) or any(not isinstance(o,dict) for o in value['preset']['recipe']['operations']):raise ValueError('Struktur resep pack tidak valid')
            if any(o.get('kind') in ('lut','overlay') for o in value['preset'].get('recipe',{}).get('operations',[])):raise ValueError('Pack tidak boleh membawa referensi aset lintas workspace')
            entry=value['preset'];only(entry,('name','recipe','size','duration','license','schema_version','proprietary_assets_included'),('name','recipe','size','duration','license'))
            return self.dispatch(actor,'m9.preset.save',{k:entry[k] for k in ('name','recipe','size','duration','license')},command_id)
        raise ValueError('Aksi M9 tidak dikenal')

    def execute(self, job):
        if job['kind'] in ('dubbing_m9','dubbing_accept_m9'):return self.dubbing.execute(job)
        if job['kind']=='recording_m9':return self.recording.execute(job)
        if job['kind']=='effects_m9':return self.effects.execute(job)
        if job['kind']=='creative_m9':return self.creative.execute(job)
        if job['kind'] in ('tts_m9','generate_m9'):return self.providers.execute(job)
        if job['kind'] in ('podcast_m9','buffer_m9'):return self.delivery.execute(job)
        raise ValueError('Tahap M9 tidak dikenal')
