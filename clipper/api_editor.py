"""M1 HTTP commands: revision-aware diff, snapshots, attributes and time mapping."""
import copy
from fastapi import APIRouter, Body

from . import editor_service as editor
from .project_store import Conflict


def router(service, guarded):
    api=APIRouter(prefix='/editor',tags=['editor-m1'])

    @api.get('/projects/{pid}')
    @guarded
    def state(pid:str,clip_id:str,variant_id:str='portrait'):
        return editor.state(service,service.store.get(pid),clip_id,variant_id)

    @api.get('/projects/{pid}/revisions/{revision}')
    @guarded
    def revision(pid:str,revision:int,clip_id:str,variant_id:str='portrait'):
        return editor.state(service,service.store.revision_document(pid,revision),clip_id,variant_id)

    @api.post('/diff')
    @guarded
    def diff(data:dict=Body(...)):
        result=service.changes(data,preview_only=True)
        return {k:result[k] for k in ('status','project_id','revision','base_revision','changes')}

    @api.post('/projects/{pid}/draft-commands')
    @guarded
    def draft_commands(pid:str,data:dict=Body(...)):
        doc=service.store.get(pid)
        if data.get('expected_revision')!=doc['revision']:raise Conflict(doc['revision'])
        from .editor_drafts import request
        return request(service,doc,data)

    @api.post('/drafts')
    @guarded
    def draft(data:dict=Body(...)):
        result=editor.make_draft(service,data)
        return {k:result[k] for k in ('id','project_id','base_revision','diff','reviews','created')}

    @api.get('/projects/{pid}/drafts/{draft_id}')
    @guarded
    def read_draft(pid:str,draft_id:str):
        result=service.store.editor_draft(pid,draft_id)
        return {k:result[k] for k in ('id','project_id','base_revision','diff','reviews','created')}

    @api.get('/projects/{pid}/drafts')
    @guarded
    def saved_drafts(pid:str):
        service.store.get(pid)
        return service.store.editor_drafts(pid)

    @api.post('/projects/{pid}/drafts/{draft_id}/commit')
    @guarded
    def commit(pid:str,draft_id:str,data:dict=Body(...)):
        return editor.commit_draft(service,pid,draft_id,data['expected_revision'],data['operation_id'],rebase=data.get('rebase',False))

    @api.post('/projects/{pid}/drafts/{draft_id}/preview')
    @guarded
    def preview(pid:str,draft_id:str,data:dict=Body(...)):
        doc=service.store.get(pid)
        if type(data.get('expected_revision')) is not int or data['expected_revision']!=doc['revision']:
            raise Conflict(doc['revision'])
        snapshot=service.store.editor_draft(pid,draft_id)
        if snapshot['document']['source']['source_id']!=doc['source']['source_id']:
            raise ValueError('Sumber draf berbeda dari sumber aktif; buat snapshot baru')
        cid,vid=data['clip_id'],data.get('variant_id','portrait')
        frozen=snapshot['document']
        service.variant(frozen,cid,vid)
        if not frozen.get('transcript_id'):
            raise ValueError('Transkripsi belum tersedia')
        summary=editor.render_summary(service,frozen,[{'clip_id':cid,'variant_id':vid}])
        request={'dependency':service.dependency(frozen,cid,vid,fresh=True),'input_revision':snapshot['base_revision'],
            'snapshot':copy.deepcopy(frozen),'draft_id':draft_id,'snapshot_digest':editor.fingerprint(frozen),
            'render_summary':summary,'options':{'quality':data.get('quality','draft')}}
        if request['options']['quality'] not in ('draft','detail'):
            raise ValueError('Pilih kualitas draft atau detail')
        return service.queue.enqueue_many(pid,[('preview',{'clip_id':cid,'variant_id':vid},request)],doc['revision'])[0]

    @api.post('/projects/{pid}/copy-attributes')
    @guarded
    def copy_attributes(pid:str,data:dict=Body(...)):
        doc=service.store.get(pid)
        if data.get('expected_revision')!=doc['revision']:
            raise Conflict(doc['revision'])
        return editor.copy_attributes(service,doc,data['clip_id'],data.get('variant_id','portrait'),data['keys'])

    @api.post('/projects/{pid}/replace-proposal')
    @guarded
    def replace(pid:str,data:dict=Body(...)):
        doc=service.store.get(pid)
        if data.get('expected_revision')!=doc['revision']:
            raise Conflict(doc['revision'])
        return editor.replace_proposal(service,doc,data)

    @api.post('/projects/{pid}/summary')
    @guarded
    def summary(pid:str,data:dict=Body(...)):
        doc=service.store.get(pid)
        if data.get('expected_revision')!=doc['revision']:
            raise Conflict(doc['revision'])
        return editor.render_summary(service,doc,data['targets'])

    @api.post('/projects/{pid}/camera-sync')
    @guarded
    def camera_sync(pid:str,data:dict=Body(...)):
        doc=service.store.get(pid)
        if data.get('expected_revision')!=doc['revision']:
            raise Conflict(doc['revision'])
        from .editor_media import sync_evidence
        return sync_evidence(service,doc,data['path'])

    @api.get('/brand-kits/{kit_id}/export')
    @guarded
    def export_kit(kit_id:str):
        kit=service.workspace.kit(kit_id)
        from .font_catalog import FONTS
        from .dependency_cache import asset_id
        from pathlib import Path
        fonts={}
        for key in ('font_main','font_accent'):
            font=kit['settings'].get(key)
            if font in FONTS:
                path=Path(service.base.fonts_dir)/FONTS[font]['file']
                fonts[key]={'id':font,'file':path.name,'content_id':asset_id(path) if path.is_file() else None,'license':'bundled_or_user_supplied; inspect font license before redistribution'}
        record={'schema_version':1,'kind':'ClipperBrandKit','name':kit['name'],'settings':kit['settings'],
            'source_revision':kit['revision'],'fonts':fonts,'assets':[],
            'limitations':['Metadata round-trip; font/media bytes are not included in this JSON.']}
        return {**record,'digest':editor.fingerprint(record)}

    @api.post('/brand-kits/import')
    @guarded
    def import_kit(data:dict=Body(...)):
        if data.get('schema_version')!=1 or data.get('kind')!='ClipperBrandKit':raise ValueError('Schema brand kit tidak didukung')
        record={k:v for k,v in data.items() if k!='digest'}
        if data.get('digest')!=editor.fingerprint(record):raise ValueError('Checksum brand kit tidak cocok')
        if data.get('assets'):raise ValueError('Aset kit memerlukan pack portable M5; JSON ini tidak menyalin aset diam-diam')
        from .font_catalog import FONTS
        from .dependency_cache import asset_id
        from pathlib import Path
        warnings=[]
        for row in data.get('fonts',{}).values():
            if row.get('id') not in FONTS:raise ValueError('Identitas font kit tidak dikenal')
            path=Path(service.base.fonts_dir)/FONTS[row['id']]['file']
            actual=asset_id(path) if path.is_file() else None
            if actual!=row.get('content_id'):warnings.append('Font '+row['id']+' belum cocok dengan digest sumber; periksa sebelum render.')
        result=service.workspace.save_kit({'name':data['name'],'settings':data['settings']})
        return {'kit':result,'warnings':warnings,'source_revision':data.get('source_revision'),'template_policy':result['settings'].get('caption_template_policy')}

    @api.get('/projects/{pid}/filmstrip')
    @guarded
    def filmstrip(pid:str,clip_id:str,variant_id:str='portrait',count:int=8):
        from .editor_media import filmstrip as frames
        return frames(service,service.store.get(pid),clip_id,variant_id,count)

    return api
