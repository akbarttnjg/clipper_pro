"""Explicit local Piper/ComfyUI adapters and labelled external asset intake.

No weights/downloads or paid/cloud nodes are installed by this module. A
reachable endpoint is transport availability, never a model-quality probe.
"""
import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
import requests
from .m8_contract import AccessDenied, canonical, integer, only, text
from .m9_contract import artifact, atomic_bytes, checksum, number, sha
from .m9_media import verify_media
from .dependency_cache import content_id
from .project_store import Conflict

COMFY_NODES={'CheckpointLoaderSimple','CLIPTextEncode','EmptyLatentImage','KSampler','VAEDecode','SaveImage','CLIPSetLastLayer'}
ASSET_KINDS={'tts','dubbing','lip_sync','speech_repair','gaze','avatar','ugc','image','video','extend','fill','object_edit','music','sfx','image_animation'}


def local_url(value):
    value=text(value,'URL lokal',200);url=urlsplit(value)
    if url.scheme!='http' or url.hostname not in ('127.0.0.1','::1') or url.username or url.password or url.path not in ('','/') or url.query or url.fragment:
        raise ValueError('Provider harus HTTP 127.0.0.1/[::1], tanpa path, proxy atau kredensial')
    return value.rstrip('/')


def local_file(value, suffixes, cap=8*1024**3):
    p=Path(value).expanduser()
    if p.is_symlink() or not p.is_file() or p.suffix.lower() not in suffixes or p.stat().st_size>cap:raise ValueError('Berkas runtime/model tidak valid')
    return p.resolve()


class Providers:
    def __init__(self,lab):self.lab=lab;self.m8=lab.m8;self.service=lab.service

    def listing(self,actor):
        return [{'id':i['id'],'kind':i['kind'],'name':i['data']['name'],'status':i['data'].get('status','registered_not_probed'),
            'last_probe':i['data'].get('last_probe'),'inference_acceptance':i['data'].get('inference_acceptance','not_run'),
            'language':i['data'].get('language'),'capability':i['data'].get('capability')} for i in self.lab.store.listing(actor) if i['kind'] in ('voice','provider')]

    def voice_register(self,actor,data):
        only(data,('name','executable','model_path','config_path','language','license','permission','sample_path'),('name','executable','model_path','config_path','language','license','permission'))
        self.m8.workspaces.require(actor,'manage')
        if not actor.local:raise AccessDenied('Runtime lokal hanya didaftarkan operator lokal')
        if data['permission'] not in ('own','authorized','licensed'):raise ValueError('Izin suara harus dinyatakan')
        exe=local_file(data['executable'],{'.exe',''},200*1024**2);model=local_file(data['model_path'],{'.onnx'});cfg=local_file(data['config_path'],{'.json'},4*1024**2)
        if cfg!=Path(str(model)+'.json').resolve():raise ValueError('Konfigurasi Piper harus berdampingan sebagai nama-model.onnx.json agar sama dengan file yang dipakai CLI')
        config=json.loads(cfg.read_text());language=text(data['language'],'Bahasa model',40)
        actual=config.get('language',{}).get('code')
        if actual!=language:raise ValueError('Bahasa yang dinyatakan berbeda dari konfigurasi model')
        value={'name':text(data['name'],'Nama suara',100),'executable':str(exe),'model_path':str(model),'config_path':str(cfg),
            'executable_content_id':content_id(exe,fresh=True),'model_content_id':content_id(model,fresh=True),'config_content_id':content_id(cfg,fresh=True),
            'language':language,'license':text(data['license'],'Lisensi',2000),'permission':data['permission'],'engine':'piper_cli','status':'registered_not_probed',
            'sample_provenance':None,'inference_acceptance':'not_run','capability':'tts; voice cloning not implemented'}
        if data.get('sample_path'):
            sample=local_file(data['sample_path'],{'.wav','.flac','.mp3','.m4a'},100*1024**2)
            info=verify_media(sample)
            value['sample_provenance']={'content_id':content_id(sample,fresh=True),'duration':info['duration'],'permission':data['permission']}
        return self.lab.store.create(actor,'voice',value)

    def tts_submit(self,actor,data):
        only(data,('id','expected_version','voice_id','text_sha256','reviewed','max_seconds'),('id','expected_version','voice_id','text_sha256','reviewed'))
        item=self.lab.store.get(actor,data['id'],'edit');voice=self.lab.store.get(actor,data['voice_id'])
        if item['kind']!='creative' or voice['kind']!='voice':raise ValueError('Pilih tulisan dan model suara terdaftar')
        if item['version']!=data['expected_version']:raise Conflict(item['version'])
        if data['reviewed'] is not True or checksum(data['text_sha256'])!=sha(item['data']['text'].encode()):raise ValueError('Persetujuan harus terikat teks yang sudah diperiksa')
        if len(item['data']['text'])>12000:raise ValueError('TTS dibatasi 12.000 karakter per tugas')
        # No implicit cross-language fallback.
        if item['data']['language'].replace('-','_').split('_')[0] != voice['data']['language'].split('_')[0]:raise ValueError('Bahasa tulisan berbeda dari model TTS')
        snap={'creative_id':item['id'],'creative_version':item['version'],'text':item['data']['text'],'text_sha256':data['text_sha256'],
            'voice':voice['data'],'voice_id':voice['id'],'voice_version':voice['version'],'max_seconds':number(data.get('max_seconds',600),'Batas detik TTS',1,900),
            'project_id':item['data'].get('project_id'),'source':item['data'].get('source',{}),'name':item['data']['name']+' — narasi sintetis'}
        if snap['project_id']:
            from .source_guard import verify
            verify(self.service,snap['source'])
        return self.lab.enqueue(actor,'tts_m9',snap,item_id=item['id'])

    def register(self,actor,data):
        only(data,('name','url','workflow_path','model_path','license','prompt_node','seed_node','memory_budget_mib'),('name','url','workflow_path','model_path','license','prompt_node','seed_node','memory_budget_mib'))
        self.m8.workspaces.require(actor,'manage')
        if not actor.local:raise AccessDenied('Workflow model lokal memerlukan operator lokal')
        address=local_url(data['url']);path=local_file(data['workflow_path'],{'.json'},2*1024**2);model=local_file(data['model_path'],{'.safetensors'})
        workflow=json.loads(path.read_text())
        if not isinstance(workflow,dict) or not 1<=len(workflow)<=60:raise ValueError('Pilih workflow ComfyUI API format')
        for key,node in workflow.items():
            if not re.fullmatch(r'\d{1,6}',key) or not isinstance(node,dict):raise ValueError('Node workflow tidak valid')
            only(node,('class_type','inputs','_meta'),('class_type','inputs'))
            if not isinstance(node['inputs'],dict):raise ValueError('Inputs node harus object')
            if node['class_type'] not in COMFY_NODES:raise ValueError('Custom/API node belum diizinkan: '+str(node['class_type']))
        pnode=str(data['prompt_node']);snode=str(data['seed_node'])
        if pnode not in workflow or workflow[pnode]['class_type']!='CLIPTextEncode' or snode not in workflow or workflow[snode]['class_type']!='KSampler':raise ValueError('Binding prompt/seed tidak cocok')
        loaders=[n for n in workflow.values() if n['class_type']=='CheckpointLoaderSimple']
        if len(loaders)!=1 or loaders[0]['inputs'].get('ckpt_name')!=model.name:raise ValueError('Nama checkpoint harus cocok dengan model yang diverifikasi')
        # Keep text-to-image deliberately bounded for a 4 GiB GPU. Other GN
        # modes require their own adapters and quality acceptance, not a label.
        latent=[n for n in workflow.values() if n['class_type']=='EmptyLatentImage']
        if len(latent)!=1:raise ValueError('Workflow memerlukan satu latent gambar')
        integer(latent[0]['inputs'].get('width'),'Lebar',64,768);integer(latent[0]['inputs'].get('height'),'Tinggi',64,768)
        if latent[0]['inputs'].get('batch_size')!=1:raise ValueError('Batch gambar harus 1')
        integer(workflow[snode]['inputs'].get('steps'),'Langkah',1,50)
        budget=integer(data['memory_budget_mib'],'Anggaran VRAM MiB',256,4096)
        key='m9provider-'+sha(os.urandom(32))[:24];saved=self.lab.root/'providers'/(key+'.json');atomic_bytes(saved,(canonical(workflow)+'\n').encode())
        return self.lab.store.create(actor,'provider',{'name':text(data['name'],'Nama',100),'url':address,'workflow_path':str(saved),'workflow_content_id':content_id(saved,fresh=True),
            'model_path':str(model),'declared_model_content_id':content_id(model,fresh=True),'actual_server_model_identity':'operator_configured_not_attested','license':text(data['license'],'Lisensi',2000),'prompt_node':pnode,'seed_node':snode,
            'memory_budget_mib':budget,'status':'registered_not_probed','capability':'text_to_image','inference_acceptance':'not_run'},key)

    def request(self,address,path,*,body=None,cap=2*1024**2):
        client=requests.Session();client.trust_env=False
        try:
            with client.request('POST' if body is not None else 'GET',local_url(address)+path,json=body,timeout=(4,20),stream=True,allow_redirects=False) as r:
                if r.status_code!=200:raise ValueError('Provider lokal belum memberikan respons 200')
                data=bytearray()
                for block in r.iter_content(65536):
                    data.extend(block)
                    if len(data)>cap:raise ValueError('Respons provider terlalu besar')
                return bytes(data)
        finally:client.close()

    def probe(self,actor,data):
        only(data,('id',),('id',));item=self.lab.store.get(actor,data['id'],'edit');value=item['data']
        self.m8.workspaces.require(actor,'manage')
        if item['kind']=='provider':
            stats=json.loads(self.request(value['url'],'/system_stats'));defs=json.loads(self.request(value['url'],'/object_info',cap=16*1024**2))
            workflow=json.loads(Path(value['workflow_path']).read_text())
            if any(n['class_type'] not in defs for n in workflow.values()):raise ValueError('Server tidak mempunyai semua node yang diperlukan')
            devices=stats.get('devices',[]);free=max((int(d.get('vram_free',0)) for d in devices),default=0)
            result={'status':'transport_and_nodes_available','free_vram_bytes_reported':free,'inference_acceptance':'not_run','last_probe':self.m8.db.clock()}
        elif item['kind']=='voice':
            for p,h in [('executable','executable_content_id'),('model_path','model_content_id'),('config_path','config_content_id')]:
                if content_id(value[p],fresh=True)!=value[h]:raise ValueError('Runtime/model suara berubah')
            result={'status':'files_verified_not_inferred','inference_acceptance':'not_run','last_probe':self.m8.db.clock()}
        else:raise ValueError('Item bukan provider/suara')
        return self.lab.store.change(actor,item['id'],item['version'],lambda v,db:v.update(result))

    def submit(self,actor,data):
        only(data,('provider_id','prompt','seed','reviewed','max_seconds'),('provider_id','prompt','seed','reviewed'))
        item=self.lab.store.get(actor,data['provider_id'],'edit')
        if item['kind']!='provider' or item['data'].get('capability')!='text_to_image':raise ValueError('Provider gambar lokal belum terdaftar')
        if data['reviewed'] is not True:raise ValueError('Periksa prompt dan lisensi dahulu')
        if item['data'].get('status')!='transport_and_nodes_available':raise ValueError('Periksa runtime/node provider dahulu')
        return self.lab.enqueue(actor,'generate_m9',{'provider':item['data'],'provider_id':item['id'],'provider_version':item['version'],
            'prompt':text(data['prompt'],'Prompt',6000),'seed':integer(data['seed'],'Seed',0,2**63-1),'max_seconds':number(data.get('max_seconds',300),'Batas waktu',10,600)},item_id=item['id'])

    def reconcile(self,actor,data):
        only(data,('job_id',),('job_id',));self.m8.workspaces.require(actor,'manage')
        with self.service.store.connect() as db:hold=db.execute("SELECT * FROM m9_resource_holds WHERE job_id=? AND workspace=?",(data['job_id'],actor.workspace)).fetchone()
        if not hold:raise KeyError('Reservasi inference tidak ditemukan')
        job=self.service.queue.get(hold['job_id'])
        if job['status'] in ('queued','running','cancel_requested'):raise ValueError('Tunggu proses Clipper berhenti sebelum rekonsiliasi provider')
        provider=self.lab.store.get(actor,hold['provider_id'])['data']
        for _ in range(2):
            queue=json.loads(self.request(provider['url'],'/queue'))
            if queue.get('queue_running') or queue.get('queue_pending'):raise ValueError('Provider masih bekerja; antrean berat tetap ditahan untuk melindungi GPU')
            time.sleep(.15)
        with self.m8.db.transaction() as db:db.execute("UPDATE m9_resource_holds SET state='released' WHERE job_id=? AND workspace=?",(hold['job_id'],actor.workspace))
        self.service.queue.start()
        return {'released':True,'job_id':hold['job_id'],'provider_idle_confirmed':True,'automatic_regeneration':False}

    def media_import(self,actor,data):
        only(data,('path','kind','name','model','prompt','seed','license','permission','reviewed','source_project_id','source_revision'),('path','kind','name','model','prompt','license','permission','reviewed'))
        if not actor.local:raise AccessDenied('Impor hasil luar dari path memerlukan operator lokal')
        if data['kind'] not in ASSET_KINDS or data['reviewed'] is not True or data['permission'] not in ('own','authorized','licensed'):raise ValueError('Periksa jenis, izin dan hasil media generatif')
        path=local_file(data['path'],{'.mp4','.webm','.mov','.mkv','.wav','.flac','.mp3','.m4a','.png','.jpg','.webp'},2*1024**3)
        source={}
        if data.get('source_project_id'):
            self.m8.workspaces.require(actor,'edit',data['source_project_id']);doc=self.service.store.get(data['source_project_id'])
            if doc['revision']!=data.get('source_revision'):raise Conflict(doc['revision'])
            source={'project_id':doc['project_id'],'revision':doc['revision'],'source_content_id':doc['source']['source_id']}
        if path.suffix.lower() in ('.png','.jpg','.webp'):
            from PIL import Image
            with Image.open(path) as im:
                if im.width*im.height>40_000_000:raise ValueError('Gambar melebihi 40 megapiksel')
                im.verify()
        else:verify_media(path)
        key='m9media-'+sha(os.urandom(32))[:24];target=self.lab.root/'assets'/(key+path.suffix.lower())
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        value={'name':text(data['name'],'Nama',160),'path':str(target),'artifact':artifact(target),'synthetic':True,'kind':data['kind'],
            'model':text(data['model'],'Model/provenance',300),'prompt':text(data['prompt'],'Prompt/provenance',6000),'seed':data.get('seed'),
            'license':text(data['license'],'Lisensi',2000),'permission':data['permission'],'source':source,'project_id':source.get('project_id'),
            'status':'imported_external_result','inference_performed_by_clipper':False,'quality_reviewed_by_user':True,'is_original_source_evidence':False}
        return self.lab.store.create(actor,'media',value,key)

    def execute(self,job):
        return self.execute_tts(job) if job['kind']=='tts_m9' else self.execute_image(job)

    def execute_tts(self,job):
        snap=job['request']['m9'];actor=self.lab.operator(snap['workspace']);voice=snap['voice'];self.lab.check_job(job)
        creative=self.lab.store.get(actor,snap['creative_id']);registered=self.lab.store.get(actor,snap['voice_id'])
        if creative['version']!=snap['creative_version'] or registered['version']!=snap['voice_version']:raise ValueError('Tulisan/model TTS berubah')
        if snap.get('project_id'):
            from .source_guard import verify
            verify(self.service,snap['source'])
        folder=self.lab.root/'tts'/job['id'];folder.mkdir(parents=True,exist_ok=True);output=folder/'narration.wav'
        started=time.monotonic()
        self.verify_voice(voice)
        info=self.synthesize(job,voice,snap['text'],output,snap['max_seconds'])
        self.verify_voice(voice)
        if self.lab.store.get(actor,snap['voice_id'])['version']!=snap['voice_version'] or self.lab.store.get(actor,snap['creative_id'])['version']!=snap['creative_version']:
            raise ValueError('Tulisan/model TTS berubah saat proses berjalan')
        if snap.get('project_id'):verify(self.service,snap['source'])
        manifest={'schema_version':1,'kind':'tts9','synthetic':True,'text':snap['text'],'text_sha256':snap['text_sha256'],'voice_id':snap['voice_id'],
            'model_content_id':voice['model_content_id'],'language':voice['language'],'license':voice['license'],'permission':voice['permission'],'source':snap['source'],
            'output':artifact(output),'inference_performed':True,'quality_acceptance':'listen for pronunciation, names, numbers and negation before use',
            'wall_seconds':round(time.monotonic()-started,3),'paid_api_cost_usd':0}
        manifest_path=folder/'tts9.json';atomic_bytes(manifest_path,(canonical(manifest)+'\n').encode())
        return self.lab.publish_derivative(job,actor,output,snap['name'],{'kind':'synthetic_tts9','manifest':str(manifest_path),'voice_id':snap['voice_id'],'source':snap['source']},manifest_path,source_guard=snap['source'] if snap.get('project_id') else None)

    @staticmethod
    def verify_voice(voice):
        for p,h in [('executable','executable_content_id'),('model_path','model_content_id'),('config_path','config_content_id')]:
            if content_id(voice[p],fresh=True)!=voice[h]:raise ValueError('Runtime/model TTS berubah')

    def synthesize(self,job,voice,utterance,output,max_seconds,timeout=600):
        """Pinned local CLI; shared by narration and reviewed cue dubbing."""
        self.lab.check_job(job);output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.unlink(missing_ok=True)
        args=[voice['executable'],'--model',voice['model_path'],'--config',voice['config_path'],'--output_file',str(output)]
        started=time.monotonic()
        with tempfile.TemporaryFile() as errors, tempfile.TemporaryFile() as input_text:
            input_text.write((utterance+'\n').encode());input_text.seek(0)
            process=subprocess.Popen(args,stdin=input_text,stdout=subprocess.DEVNULL,stderr=errors,env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','OMP_NUM_THREADS':'2'})
            try:
                while process.poll() is None:
                    self.lab.check_job(job)
                    if time.monotonic()-started>timeout:raise ValueError('Batas waktu TTS terlampaui')
                    if errors.tell()>2*1024**2 or output.exists() and output.stat().st_size>max_seconds*192000+1024**2:
                        raise ValueError('Runtime TTS melebihi anggaran berkas')
                    time.sleep(.08)
                if process.returncode:raise ValueError('Piper gagal; periksa runtime/model lokal')
            finally:
                if process.poll() is None:process.kill();process.wait(timeout=10)
        info=verify_media(output,check=lambda:self.lab.check_job(job))
        if info['duration']>max_seconds:raise ValueError('Hasil TTS melebihi anggaran durasi')
        return info

    def execute_image(self,job):
        from PIL import Image
        from urllib.parse import urlencode
        snap=job['request']['m9'];actor=self.lab.operator(snap['workspace']);provider=snap['provider'];self.lab.check_job(job)
        for p,h in [('workflow_path','workflow_content_id'),('model_path','declared_model_content_id')]:
            if content_id(provider[p],fresh=True)!=provider[h]:raise ValueError('Workflow/model gambar berubah')
        workflow=json.loads(Path(provider['workflow_path']).read_text());workflow[provider['prompt_node']]['inputs']['text']=snap['prompt'];workflow[provider['seed_node']]['inputs']['seed']=snap['seed']
        # Require an idle dedicated server. Queue sharing outside Clipper is not
        # a GPU lease; operator must reserve this instance for Clipper.
        queue=json.loads(self.request(provider['url'],'/queue'))
        if queue.get('queue_running') or queue.get('queue_pending'):raise ValueError('ComfyUI sedang dipakai; tunggu agar anggaran GPU tidak bertumpuk')
        stats=json.loads(self.request(provider['url'],'/system_stats'))
        devices=stats.get('devices',[]);free=max((int(d.get('vram_free',0)) for d in devices),default=0)
        if free and free<provider['memory_budget_mib']*1024**2:raise ValueError('VRAM bebas di bawah anggaran workflow')
        folder=self.lab.root/'generated'/job['id'];folder.mkdir(parents=True,exist_ok=True)
        # A persisted submission receipt prevents an automatic second inference
        # after a lost HTTP response. Unknown outcome requires reconciliation.
        receipt=folder/'submission.json'
        if receipt.exists():raise ValueError('Pengajuan generatif pernah dimulai; periksa ComfyUI sebelum membuat tugas baru')
        with self.m8.db.transaction() as db:
            self.lab.check_job(job,db)
            if db.execute("SELECT 1 FROM m9_resource_holds WHERE state!='released' LIMIT 1").fetchone():raise ValueError('Inference lama belum direkonsiliasi')
            db.execute('INSERT INTO m9_resource_holds VALUES(?,?,?,?,NULL,?)',(job['id'],actor.workspace,snap['provider_id'],'submission_unknown',self.m8.db.clock()))
        atomic_bytes(receipt,(canonical({'status':'submission_started','job_id':job['id']})+'\n').encode())
        result=json.loads(self.request(provider['url'],'/prompt',body={'prompt':workflow,'client_id':'clipper-'+job['id']}))
        prompt_id=text(result.get('prompt_id'),'ID inference',100)
        if not re.fullmatch('[a-zA-Z0-9-]+',prompt_id):raise ValueError('ID inference tidak aman')
        atomic_bytes(receipt,(canonical({'status':'submitted','prompt_id':prompt_id})+'\n').encode());started=time.monotonic()
        with self.m8.db.transaction() as db:db.execute("UPDATE m9_resource_holds SET state='submitted',prompt_id=? WHERE job_id=?",(prompt_id,job['id']))
        while True:
            self.lab.check_job(job)
            history=json.loads(self.request(provider['url'],'/history/'+prompt_id)).get(prompt_id)
            if history:
                status=history.get('status',{})
                if status.get('status_str')=='error':raise ValueError('Inference lokal gagal; lihat ComfyUI')
                if status.get('completed'):break
            if time.monotonic()-started>snap['max_seconds']:raise ValueError('Batas waktu inference; tugas provider mungkin masih berjalan, rekonsiliasi sebelum ulang')
            time.sleep(.5)
        images=[r for node in history.get('outputs',{}).values() for r in node.get('images',[])]
        if len(images)!=1:raise ValueError('Workflow harus menghasilkan tepat satu gambar')
        image=images[0];filename=image.get('filename','');subfolder=image.get('subfolder','')
        if Path(filename).name!=filename or not re.fullmatch('[a-zA-Z0-9_.-]{1,200}',filename) or subfolder or image.get('type')!='output':raise ValueError('Lokasi keluaran workflow tidak didukung')
        raw=self.request(provider['url'],'/view?'+urlencode({'filename':filename,'type':'output'}),cap=32*1024**2)
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('SaveImage harus menghasilkan PNG')
        output=folder/'image.png';atomic_bytes(output,raw)
        with Image.open(output) as im:
            if im.width>768 or im.height>768:raise ValueError('Gambar hasil melewati anggaran dimensi')
            metadata=im.info.get('prompt')
            if metadata:
                reported=json.loads(metadata)
                for node_id,node in workflow.items():
                    actual=reported.get(node_id,{})
                    if actual.get('class_type')!=node['class_type'] or actual.get('inputs')!=node['inputs']:raise ValueError('Metadata gambar berbeda dari workflow/prompt/seed yang dikirim')
            im.verify()
        value={'name':'Gambar lokal M9','path':str(output),'artifact':artifact(output),'synthetic':True,'kind':'image','status':'requires_visual_review',
            'declared_model_content_id':provider['declared_model_content_id'],'actual_server_model_identity':'operator_configured_not_attested',
            'image_prompt_metadata':'matches_request' if metadata else 'not_available','workflow_content_id':provider['workflow_content_id'],'prompt':snap['prompt'],'seed':snap['seed'],
            'license':provider['license'],'inference_performed':True,'provider_prompt_id':prompt_id,'paid_api_cost_usd':0,'wall_seconds':round(time.monotonic()-started,3)}
        manifest=folder/'generation9.json';atomic_bytes(manifest,(canonical(value)+'\n').encode());key='m9media-'+sha(job['id'].encode())[:24];now=self.m8.db.clock()
        with self.m8.db.transaction() as db:
            self.lab.check_job(job,db);db.execute('INSERT INTO m9_items VALUES(?,?,?,0,?,?,?)',(key,actor.workspace,'media',canonical(value),now,now))
            self.lab.finish(db,job,{'item_id':key,'manifest_path':str(manifest),'inference_performed':True,'requires_visual_review':True})
            db.execute("UPDATE m9_resource_holds SET state='released' WHERE job_id=?",(job['id'],))
        return {'item_id':key,'manifest_path':str(manifest),'inference_performed':True}
