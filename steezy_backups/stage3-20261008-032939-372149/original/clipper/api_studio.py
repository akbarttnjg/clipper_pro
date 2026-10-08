"""HTTP boundary for Studio 4. All mutations carry revisions or queue ownership."""
import functools
import uuid
from pathlib import Path
from fastapi import APIRouter,Body,File,UploadFile,HTTPException
from fastapi.responses import FileResponse,JSONResponse
from .project_store import Conflict
from . import studio_storage


def guarded(fn):
    @functools.wraps(fn)
    def call(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except Conflict as exc:return JSONResponse({'status':'conflict','revision':exc.revision,'message':str(exc),'paths':exc.paths},status_code=409)
        except KeyError as exc:raise HTTPException(404,str(exc)) from exc
        except (ValueError,OSError) as exc:raise HTTPException(400,str(exc)) from exc
    return call


def create_router(service):
    router=APIRouter(prefix='/api/studio',tags=['studio4'])
    from .api_runtime import router as runtime_router
    router.include_router(runtime_router(service))
    @router.get('/projects')
    def projects():return service.store.list()

    @router.post('/projects')
    @guarded
    def create(data:dict=Body(...)):return service.create(data['path'],data.get('settings'),data.get('name'))

    @router.post('/upload')
    async def upload(file:UploadFile=File(...)):
        suffix=Path(file.filename or '').suffix.lower()
        if suffix not in ('.mp4','.mkv','.mov','.webm','.avi','.m4v'):raise HTTPException(400,'Pilih berkas video')
        folder=service.root/'uploads';folder.mkdir(parents=True,exist_ok=True);target=folder/(uuid.uuid4().hex+suffix)
        try:
            with target.open('wb') as stream:
                while block:=await file.read(4*1024*1024):stream.write(block)
            return {'path':str(target),'name':Path(file.filename or 'Video').stem}
        except BaseException:target.unlink(missing_ok=True);raise
        finally:await file.close()

    @router.get('/projects/{pid}')
    @guarded
    def project(pid:str):return service.public(pid)

    @router.get('/projects/{pid}/words')
    @guarded
    def words(pid:str,clip_id:str|None=None,offset:int=0,limit:int=150,q:str='',whole:bool=False):return service.page(pid,clip_id,offset=offset,limit=limit,q=q,whole=whole)

    @router.post('/changes')
    @guarded
    def changes(data:dict=Body(...)):return service.changes(data)

    @router.get('/projects/{pid}/history')
    @guarded
    def history(pid:str):return service.store.history(pid)

    @router.post('/projects/{pid}/undo')
    @guarded
    def undo(pid:str,data:dict=Body(...)):return service.store.undo(pid,data['expected_revision'],data['operation_id'],data['revision'])

    @router.post('/projects/{pid}/jobs')
    @guarded
    def enqueue(pid:str,data:dict=Body(...)):
        if type(data.get('expected_revision')) is not int:raise ValueError('Revisi proyek diperlukan')
        return service.enqueue(pid,data['kind'],data.get('clip_id'),data.get('variant_id','portrait'),data.get('expected_revision'),data.get('options'))

    @router.post('/jobs/{jid}/cancel')
    @guarded
    def cancel(jid:str):return service.queue.cancel(jid)

    @router.post('/jobs/{jid}/resume')
    @guarded
    def resume(jid:str):
        job=service.queue.get(jid)
        if job['status'] not in ('interrupted','failed','canceled','stale'):raise ValueError('Proses ini tidak perlu dilanjutkan')
        return service.enqueue(job['project_id'],job['kind'],job['target'].get('clip_id'),job['target'].get('variant_id','portrait'),options=job['request'].get('options'))

    @router.get('/files/{fid}')
    @guarded
    def file(fid:str):
        path=service.file(fid)
        return FileResponse(path,filename=path.name if path.suffix in ('.zip','.svg','.json','.srt','.ass') else None)

    @router.get('/styles')
    def styles():
        from .edit_styles import STYLES
        return STYLES

    @router.get('/storage')
    @guarded
    def storage():return studio_storage.inventory(service)

    @router.post('/storage/cleanup')
    @guarded
    def cleanup(data:dict=Body(...)):return studio_storage.cleanup(service,data['ids'],data['etag'])

    @router.post('/storage/enforce-limit')
    @guarded
    def limit():return studio_storage.enforce_limit(service)

    @router.post('/projects/{pid}/backup')
    @guarded
    def backup(pid:str,data:dict=Body(...)):return studio_storage.backup(service,pid,data.get('include_source',False))

    @router.post('/restore')
    @guarded
    def restore(data:dict=Body(...)):return studio_storage.restore(service,data['path'])

    @router.post('/projects/{pid}/relink')
    @guarded
    def relink(pid:str,data:dict=Body(...)):return studio_storage.relink(service,pid,data['path'],data['expected_revision'],data['operation_id'])

    @router.get('/projects/{pid}/artifacts')
    @guarded
    def artifacts(pid:str,clip_id:str|None=None,variant_id:str|None=None):
        results=service.store.artifacts(pid,clip_id,variant_id)
        for row in results:row['data']['url']=service.register_file(pid,row['data'].get('absolute_file'))
        return results

    @router.post('/benchmark')
    @guarded
    def benchmark(data:dict=Body(...)):
        from .benchmark import evaluate
        return evaluate(data['reference'],data['hypothesis'])
    return router


def install(app,root,base,states,resource_lock):
    from .studio_service import StudioService
    from .api_analysis import create_router as analysis_router
    from fastapi.staticfiles import StaticFiles
    service=StudioService(root,base,resource_lock=resource_lock)
    service.migrate(states)
    app.include_router(create_router(service))
    def analysis_changes(data):
        try:return service.changes(data)
        except Conflict as exc:return {'status':'conflict','revision':exc.revision,'message':str(exc)}
        except (ValueError,KeyError) as exc:raise HTTPException(400,str(exc)) from exc
    app.include_router(analysis_router({'get_snapshot':guarded(service.analysis_snapshot),'submit_changes':analysis_changes,
        'run_stage':guarded(service.run_stage),'get_words_page':service.page}))
    app.mount('/static',StaticFiles(directory=Path(root)/'static'),name='studio4-static')
    # Migrated projects can no longer be overwritten by a pre-4.0 browser tab.
    @app.middleware('http')
    async def legacy_guard(request,call_next):
        if request.method in ('POST','PUT','PATCH','DELETE') and request.url.path.startswith('/api/') and not request.url.path.startswith(('/api/studio/','/api/analysis/')):
            known={p['project_id'] for p in service.store.list()}
            if known.intersection(request.url.path.split('/')):return JSONResponse({'detail':'Proyek telah memakai revisi Studio 4. Muat ulang editor; draf tab lama jangan ditutup sebelum disalin.'},status_code=409)
        return await call_next(request)
    @app.on_event('startup')
    def start():service.queue.start()
    @app.on_event('shutdown')
    def stop():
        service.queue.close()
        if 'runtime' in service.__dict__:service.runtime.close()
    app.state.studio=service
    return service
