"""Optional A router. B mounts create_router(services) after C0 review.

Services are injected: get_snapshot(target), submit_changes(request),
run_stage(request). No access to app globals, project files or legacy edit route.
"""
import inspect
from dataclasses import dataclass
from typing import Callable
from fastapi import APIRouter,Body,HTTPException
from .analysis_options import validate_settings,SETTINGS,DEPENDENCIES


@dataclass(frozen=True)
class AnalysisHost:
    """Public C0 injection point retained from B's extraction."""
    snapshot: Callable
    submit_changes: Callable
    get_words_page: Callable
    run_stage: Callable


def mount(app,host,router_factory=None):
    if router_factory is not None:
        router=router_factory(host)
        app.include_router(router,prefix='' if router.prefix=='/api/analysis' else '/api/analysis')


def target_ids(data):
    target={k:data.get(k) for k in ('project_id','clip_id','variant_id')}
    if any(not isinstance(v,str) or not v.strip() or len(v)>160 for v in target.values()):
        raise ValueError('project_id, clip_id, variant_id harus ID stabil')
    return target


async def invoke(fn,value):
    result=fn(value)
    return await result if inspect.isawaitable(result) else result


def create_router(services):
    if isinstance(services,AnalysisHost):
        services=dict(get_snapshot=services.snapshot,submit_changes=services.submit_changes,
                      run_stage=services.run_stage,get_words_page=services.get_words_page)
    for name in ('get_snapshot','submit_changes','run_stage'):
        if not callable(services.get(name)):raise ValueError('Layanan B belum tersedia: '+name)
    router=APIRouter(prefix='/api/analysis',tags=['analysis-A'])

    @router.get('/capabilities')
    async def capabilities():
        return {'schema_version':1,'producer_version':'A-01-22.1','settings':SETTINGS,'dependencies':DEPENDENCIES,
                'mutation_owner':'B revision service','shared_c0_status':'validated_against_f67b032',
                'production_services_status':'provided_by_host_not_verified_by_module_tests'}

    @router.get('/snapshot')
    async def snapshot(project_id:str,clip_id:str,variant_id:str):
        try:target=target_ids(dict(project_id=project_id,clip_id=clip_id,variant_id=variant_id))
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        result=await invoke(services['get_snapshot'],target)
        if result.get('schema_version')!=1:raise HTTPException(409,'Versi snapshot belum didukung; data asli dipertahankan')
        return result

    @router.post('/changes')
    async def changes(data:dict=Body(...)):
        try:
            target=target_ids(data)
            revision=data.get('expected_revision');operation_id=data.get('operation_id')
            if type(revision) is not int or revision<0 or not isinstance(operation_id,str) or not 8<=len(operation_id)<=160:
                raise ValueError('expected_revision dan operation_id wajib untuk penyimpanan aman')
            operations=data.get('operations')
            if not isinstance(operations,list) or not 1<=len(operations)<=100:raise ValueError('Daftar perubahan tidak valid')
            for op in operations:
                if not isinstance(op,dict) or op.get('op') not in ('correct_token','alias_upsert','alias_remove','asset_enabled','asset_metadata','analysis_settings'):
                    raise ValueError('Operasi bukan milik komponen analisis A')
                if op['op']=='analysis_settings':validate_settings(op.get('values',{}))
        except (ValueError,TypeError) as exc:raise HTTPException(400,str(exc)) from exc
        result=await invoke(services['submit_changes'],{**target,'expected_revision':revision,'operation_id':operation_id,'operations':operations})
        if result.get('status')=='conflict':
            from fastapi.responses import JSONResponse
            return JSONResponse(result,status_code=409)
        return result

    @router.post('/stage')
    async def stage(data:dict=Body(...)):
        try:
            target=target_ids(data)
            if data.get('stage_id') not in ('source_evidence','correction','discovery','boundary_review','asset_proposals','asset_visual_review'):
                raise ValueError('Tahap analisis tidak dikenal')
            if type(data.get('expected_revision')) is not int or data['expected_revision']<0:
                raise ValueError('Revisi snapshot harus disertakan')
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        # B owns dependency fingerprint, queue, cancellation and artifact commit.
        return await invoke(services['run_stage'],{**target,'stage_id':data['stage_id'],
                                                'expected_revision':data['expected_revision']})
    return router
