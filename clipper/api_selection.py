"""M3 endpoints use the existing revision service and supervised job queue."""
from fastapi import APIRouter,Body
from . import selection_service


def router(service,guarded):
    api=APIRouter(tags=['M3'])
    @api.get('/projects/{pid}/selection')
    @guarded
    def snapshot(pid:str,offset:int=0,limit:int=25):return selection_service.snapshot(service,pid,offset=offset,limit=limit)
    @api.post('/projects/{pid}/selection')
    @guarded
    def analyze(pid:str,data:dict=Body(...)):
        return service.enqueue(pid,'selection_m3',expected_revision=data['expected_revision'],options=data.get('constraints',{}))
    @api.post('/projects/{pid}/selection/decision')
    @guarded
    def decision(pid:str,data:dict=Body(...)):
        op={k:data[k] for k in ('analysis_id','candidate_id','status','reason','reviewed') if k in data}
        return service.changes({'project_id':pid,'expected_revision':data['expected_revision'],
            'operation_id':data['operation_id'],'operations':[{'op':'m3_decide',**op}]})
    @api.post('/projects/{pid}/selection/story')
    @guarded
    def story(pid:str,data:dict=Body(...)):
        op={k:data[k] for k in ('analysis_id','candidate_ids','source_spans','title') if k in data}
        return service.changes({'project_id':pid,'expected_revision':data['expected_revision'],
            'operation_id':data['operation_id'],'operations':[{'op':'m3_story',**op}]})
    @api.post('/projects/{pid}/selection/marker')
    @guarded
    def marker(pid:str,data:dict=Body(...)):
        return service.changes({'project_id':pid,'expected_revision':data['expected_revision'],
            'operation_id':data['operation_id'],'operations':[{'op':'m3_marker','time':data['time'],'label':data.get('label','Penanda pengguna')}]})
    @api.post('/projects/{pid}/selection/render-set')
    @guarded
    def render_set(pid:str,data:dict=Body(...)):
        op={'op':'m3_select_set','analysis_id':data['analysis_id']}
        if 'candidate_ids' in data:op['candidate_ids']=data['candidate_ids']
        return service.changes({'project_id':pid,'expected_revision':data['expected_revision'],
            'operation_id':data['operation_id'],'operations':[op]})
    return api
