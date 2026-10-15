from fastapi import APIRouter,Body
from .audio6_service import snapshot

def router(service,guarded):
    api=APIRouter()
    @api.get('/projects/{pid}/audio6')
    @guarded
    def view(pid:str,clip_id:str,variant_id:str='portrait'):return snapshot(service,pid,clip_id,variant_id)
    @api.post('/projects/{pid}/audio6/diff')
    @guarded
    def diff(pid:str,data:dict=Body(...)):
        result=service.changes({**data,'project_id':pid},preview_only=True)
        from .audio6_contract import effective
        result['effective_audio']=effective(service.config(result['document'],data['clip_id'],data.get('variant_id','portrait')))
        return result
    @api.post('/audio6/assets')
    @guarded
    def register(data:dict=Body(...)):
        from .ffmpeg_util import probe
        from .finishing5_service import assets
        if not probe(data['path'])['has_audio']:raise ValueError('Aset tidak mempunyai suara')
        return assets(service).register(data['path'],data['metadata'])
    @api.get('/audio6/assets')
    @guarded
    def listing(q:str='',collection:str|None=None,min_seconds:float=0,max_seconds:float=86400):
        from .finishing5_service import assets
        if not 0<=min_seconds<=max_seconds<=86400:raise ValueError('Rentang durasi aset tidak valid')
        return {'assets':[r for r in assets(service).list(q,collection) if r['kind'] in ('audio','video') and min_seconds<=r['metadata']['duration']<=max_seconds]}
    return api
