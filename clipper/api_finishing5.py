from fastapi import APIRouter,Body
from .finishing5_service import snapshot,assets
def router(service,guarded):
    api=APIRouter()
    @api.get('/projects/{pid}/finishing5')
    @guarded
    def view(pid:str,clip_id:str,variant_id:str='portrait'):return snapshot(service,pid,clip_id,variant_id)
    @api.post('/projects/{pid}/finishing5/diff')
    @guarded
    def diff(pid:str,data:dict=Body(...)):
        from .finishing5_contract import effective
        request={**data,'project_id':pid};result=service.changes(request,preview_only=True)
        result['effective_style']=effective(service.config(result['document'],data['clip_id'],data.get('variant_id','portrait')))
        return result
    @api.post('/finishing5/assets')
    @guarded
    def register(data:dict=Body(...)):return assets(service).register(data['path'],data['metadata'])
    @api.get('/finishing5/assets')
    @guarded
    def listing(q:str='',collection:str|None=None):return {'assets':assets(service).list(q,collection)}
    @api.post('/finishing5/assets/metadata')
    @guarded
    def metadata(data:dict=Body(...)):return assets(service).update_metadata(data['asset_id'],data['expected_revision'],data['values'])
    @api.post('/finishing5/kits')
    @guarded
    def save(data:dict=Body(...)):return assets(service).save_kit(data)
    @api.post('/finishing5/kits/export')
    @guarded
    def export(data:dict=Body(...)):
        import uuid
        pid=data['project_id'];service.store.get(pid);target=service.work/pid/'finishing5'/('kit-'+uuid.uuid4().hex+'.zip');target.parent.mkdir(parents=True,exist_ok=True);assets(service).export(data['kit_id'],target);return {'url':service.register_file(pid,target)}
    @api.post('/finishing5/kits/import')
    @guarded
    def import_kit(data:dict=Body(...)):return assets(service).import_pack(data['path'])
    return api
