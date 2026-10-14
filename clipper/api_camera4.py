from fastapi import APIRouter,Body
from .camera4_service import snapshot


def router(service,guarded):
    api=APIRouter()
    @api.get('/projects/{pid}/camera4')
    @guarded
    def view(pid:str,clip_id:str,variant_id:str='portrait'):return snapshot(service,pid,clip_id,variant_id)
    @api.post('/projects/{pid}/camera4/analyze')
    @guarded
    def analyze(pid:str,data:dict=Body(...)):return service.enqueue(pid,'camera_m4',data['clip_id'],data.get('variant_id','portrait'),data['expected_revision'])
    @api.post('/projects/{pid}/camera4/changes')
    @guarded
    def changes(pid:str,data:dict=Body(...)):
        return service.changes({'project_id':pid,'clip_id':data['clip_id'],'variant_id':data.get('variant_id','portrait'),
            'expected_revision':data['expected_revision'],'operation_id':data['operation_id'],'operations':data['operations']})
    return api
