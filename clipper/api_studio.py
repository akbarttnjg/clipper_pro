"""HTTP boundary for Studio 4. All mutations carry revisions or queue ownership."""
import functools
import subprocess
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
        except (ValueError,OSError,TypeError,subprocess.SubprocessError) as exc:raise HTTPException(400,str(exc)) from exc
    return call


def create_router(service):
    router=APIRouter(prefix='/api/studio',tags=['studio4'])
    from .api_m8 import router as m8_router
    router.include_router(m8_router(service))
    from .api_m9 import router as m9_router
    router.include_router(m9_router(service))
    from .api_delivery7 import router as delivery_router
    router.include_router(delivery_router(service,guarded))
    from .api_audio6 import router as audio_router
    router.include_router(audio_router(service,guarded))
    from .api_finishing5 import router as finishing_router
    router.include_router(finishing_router(service,guarded))
    from .api_runtime import router as runtime_router
    router.include_router(runtime_router(service))
    from .api_editor import router as editor_router
    router.include_router(editor_router(service,guarded))
    from .api_ingest import router as ingest_router
    router.include_router(ingest_router(service,guarded))
    from .api_selection import router as selection_router
    router.include_router(selection_router(service,guarded))
    from .api_camera4 import router as camera_router
    router.include_router(camera_router(service,guarded))
    @router.get('/style-presets')
    def style_presets():
        from .style5 import PRESETS,VERSION
        return {'version':VERSION,'presets':PRESETS}
    @router.get('/projects')
    def projects():return service.store.list()

    @router.post('/projects')
    @guarded
    def create(data:dict=Body(...)):return service.create(data['path'],data.get('settings'),data.get('name'))

    @router.post('/upload')
    async def upload(file:UploadFile=File(...)):
        suffix=Path(file.filename or '').suffix.lower()
        from .source_imports import MEDIA_SUFFIXES,DEFAULT_MAX_BYTES
        if suffix not in MEDIA_SUFFIXES:raise HTTPException(400,'Pilih berkas video atau audio')
        folder=service.root/'uploads';folder.mkdir(parents=True,exist_ok=True);target=folder/(uuid.uuid4().hex+suffix)
        try:
            received=0
            with target.open('wb') as stream:
                while block:=await file.read(4*1024*1024):
                    received+=len(block)
                    if received>DEFAULT_MAX_BYTES:raise HTTPException(400,'Berkas melebihi batas 20 GB')
                    stream.write(block)
            from .media_context import inspect
            try:inspect(target)
            except (ValueError,subprocess.SubprocessError) as exc:raise HTTPException(400,'Media tidak dapat dibaca') from exc
            return {'path':str(target),'name':Path(file.filename or 'Video').stem}
        except BaseException:target.unlink(missing_ok=True);raise
        finally:await file.close()

    @router.get('/projects/{pid}')
    @guarded
    def project(pid:str):return service.public(pid)

    @router.get('/projects/{pid}/words')
    @guarded
    def words(pid:str,clip_id:str|None=None,offset:int=0,limit:int=150,q:str='',whole:bool=False,search_mode:str='display',variant_id:str|None=None):return service.page(pid,clip_id,offset=offset,limit=limit,q=q,whole=whole,search_mode=search_mode,variant_id=variant_id)

    @router.post('/changes')
    @guarded
    def changes(data:dict=Body(...)):return service.changes(data)

    @router.post('/correction-review')
    @guarded
    def correction_review(data:dict=Body(...)):return service.correction_review(data)

    @router.get('/projects/{pid}/stage3')
    @guarded
    def stage3(pid:str,clip_id:str|None=None,offset:int=0,limit:int=40):return service.stage3_status(pid,clip_id,offset,limit)

    @router.get('/projects/{pid}/history')
    @guarded
    def history(pid:str):return service.store.history(pid)

    @router.post('/projects/{pid}/undo')
    @guarded
    def undo(pid:str,data:dict=Body(...)):return service.store.undo(pid,data['expected_revision'],data['operation_id'],data['revision'])

    @router.post('/projects/{pid}/redo')
    @guarded
    def redo(pid:str,data:dict=Body(...)):return service.store.redo(pid,data['expected_revision'],data['operation_id'],data['revision'])

    @router.post('/projects/{pid}/jobs')
    @guarded
    def enqueue(pid:str,data:dict=Body(...)):
        if type(data.get('expected_revision')) is not int:raise ValueError('Revisi proyek diperlukan')
        return service.enqueue(pid,data['kind'],data.get('clip_id'),data.get('variant_id','portrait'),data.get('expected_revision'),data.get('options'))

    @router.post('/jobs/{jid}/cancel')
    @guarded
    def cancel(jid:str):return service.queue.cancel(jid)

    @router.post('/projects/{pid}/batch-render')
    @guarded
    def batch_render(pid:str,data:dict=Body(...)):
        return service.enqueue_batch(pid,data.get('expected_revision'))

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

    @router.get('/brand-kits')
    @guarded
    def brand_kits():return {'kits':service.workspace.kits(),'preference':service.workspace.preference()}

    @router.post('/brand-kits')
    @guarded
    def save_brand_kit(data:dict=Body(...)):return service.workspace.save_kit(data)

    @router.get('/projects/{pid}/workspace')
    @guarded
    def workspace(pid:str):return service.workspace.summary(pid)

    @router.get('/projects/{pid}/manifest')
    @guarded
    def project_manifest(pid:str):
        from .storage import write_json
        path=service.work/pid/'project-manifest.json'
        write_json(path,service.workspace.manifest(pid))
        return {'url':service.register_file(pid,path)}

    @router.get('/projects/{pid}/quality')
    @guarded
    def quality(pid:str):
        from .evaluation6 import quality_summary
        return quality_summary(service,pid)

    @router.post('/projects/{pid}/feedback')
    @guarded
    def feedback(pid:str,data:dict=Body(...)):return service.workspace.feedback(pid,data)

    @router.post('/projects/{pid}/preferences')
    @guarded
    def preferences(pid:str,data:dict=Body(...)):return service.workspace.promote(pid,data)

    @router.post('/projects/{pid}/native-evidence')
    @guarded
    def native_evidence(pid:str,data:dict=Body(...)):return service.workspace.native_evidence(pid,data)

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
    from .api_m8 import install_security
    install_security(app,service)
    @app.get('/m8',include_in_schema=False)
    def m8_console():return FileResponse(Path(root)/'static/m8.html',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"})
    @app.get('/m9',include_in_schema=False)
    def m9_console():return FileResponse(Path(root)/'static/m9.html',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"})
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
    def start():service.queue.start();service.imports.start();service.integrations.start()
    @app.on_event('shutdown')
    def stop():
        service.integrations.close()
        service.queue.close()
        if 'imports' in service.__dict__:service.imports.close()
        if 'runtime' in service.__dict__:service.runtime.close()
    app.state.studio=service
    return service
