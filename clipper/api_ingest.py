"""M2 import and reviewed transcript boundary. Provider work is queued."""
import subprocess
from fastapi import APIRouter,Body
from .source_imports import inspect_playlist


def router(service,guarded):
    api=APIRouter(tags=['M2'])
    @api.get('/imports')
    @guarded
    def imports():return service.imports.list()
    @api.post('/imports')
    @guarded
    def submit(data:dict=Body(...)):return service.imports.submit(data)
    @api.post('/imports/playlist')
    @guarded
    def playlist(data:dict=Body(...)):return inspect_playlist(data['url'],data.get('limit',50))
    @api.post('/imports/{iid}/cancel')
    @guarded
    def cancel(iid:str):return service.imports.cancel(iid)
    @api.post('/imports/{iid}/resume')
    @guarded
    def resume(iid:str):return service.imports.resume(iid)
    @api.post('/monitors')
    @guarded
    def monitor(data:dict=Body(...)):return service.imports.save_monitor(data)
    @api.post('/monitors/{mid}/scan')
    @guarded
    def scan(mid:str):return service.imports.scan(mid)
    @api.post('/source-assembly')
    @guarded
    def assembly(data:dict=Body(...)):
        return service.imports.submit({'items':[{'kind':'assembly','segments':data['segments'],'name':data.get('name','Sumber gabungan')}],
            'operation_id':data['operation_id'],'settings':data.get('settings',{}),'auto_analyze':data.get('auto_analyze',False)})
    @api.get('/projects/{pid}/source-origins')
    @guarded
    def origins(pid:str):
        doc=service.store.get(pid)
        return {'source_id':doc['source']['source_id'],'origins':[{**r,'url':service.register_file(pid,r['source_path'])} for r in doc['source'].get('lineage',[])]}
    @api.get('/projects/{pid}/transcript-tracks')
    @guarded
    def tracks(pid:str):return service.transcripts.snapshot(pid)
    @api.post('/projects/{pid}/transcript-import/review')
    @guarded
    def import_review(pid:str,data:dict=Body(...)):return service.transcripts.import_review(pid,data)
    @api.post('/projects/{pid}/transcript-import/commit')
    @guarded
    def import_commit(pid:str,data:dict=Body(...)):return service.transcripts.commit_import(pid,data)
    @api.post('/projects/{pid}/embedded-subtitle/review')
    @guarded
    def embedded(pid:str,data:dict=Body(...)):
        doc=service.transcripts._doc(pid,data['expected_revision']);index=data['stream_index']
        if type(index) is not int:raise ValueError('Pilih track subtitle sumber')
        track=next((r for r in doc['source']['info'].get('subtitle_tracks',[]) if r['index']==index),None)
        if not track or track['codec'] not in ('subrip','webvtt','mov_text','ass','ssa','text'):raise ValueError('Subtitle gambar memerlukan OCR tersendiri; pilih track teks')
        text=subprocess.run(['ffmpeg','-v','error','-nostdin','-i',doc['source']['path'],'-map','0:'+str(index),'-f','srt','pipe:1'],capture_output=True,text=True,check=True,timeout=60).stdout
        return service.transcripts.import_review(pid,{**data,'format':'srt','text':text,'language':track['language'],'provider':'embedded_creator_subtitle'})
    @api.post('/projects/{pid}/translation/review')
    @guarded
    def translation(pid:str,data:dict=Body(...)):
        if data.get('provider')=='ollama':
            options={k:v for k,v in data.items() if k in ('provider','target_language','expected_revision')}
            return {'queued':True,'job':service.enqueue(pid,'translation',expected_revision=data['expected_revision'],options=options)}
        return service.transcripts.translation_review(pid,data)
    @api.post('/projects/{pid}/translation/commit')
    @guarded
    def translation_commit(pid:str,data:dict=Body(...)):return service.transcripts.commit_translation(pid,data)
    @api.post('/projects/{pid}/transcript-export')
    @guarded
    def export(pid:str,data:dict=Body(...)):return service.transcripts.export(pid,data)
    return api
