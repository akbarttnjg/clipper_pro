"""Local component administration API; all long operations are queued workers."""
from pathlib import Path
from fastapi import APIRouter,Body,HTTPException
from fastapi.responses import FileResponse,JSONResponse,PlainTextResponse
from .runtime.catalog import get
from .runtime.manager import redact
from .runtime.state import safe_path


def router(service):
    api=APIRouter(prefix='/runtime',tags=['components'])
    def guarded(fn):
        def call(*args,**kwargs):
            try:return fn(*args,**kwargs)
            except (ValueError,OSError,KeyError) as exc:raise HTTPException(400,redact(str(exc))) from exc
        return call

    @api.get('')
    def status():return service.runtime.snapshot()

    @api.get('/report')
    def report():return JSONResponse(service.runtime.snapshot(),headers={'Content-Disposition':'attachment; filename="Laporan_Komponen_Clipper_Studio_4_0_2a.json"'})

    @api.post('/jobs')
    def enqueue(data:dict=Body(...)):
        return guarded(service.runtime.enqueue)(data.get('component'),data.get('action'),data.get('options'))

    @api.post('/jobs/cancel-queued')
    def cancel_queued():return guarded(service.runtime.cancel_queued)()

    @api.post('/jobs/{jid}/cancel')
    def cancel(jid:str):return guarded(service.runtime.cancel)(jid)

    @api.post('/jobs/{jid}/resume')
    def resume(jid:str):return guarded(service.runtime.resume)(jid)

    def read_log(jid):
        guarded(service.runtime.job)(jid)
        path=service.runtime.root/'logs'/(jid+'.log')
        if not path.exists():return {'text':'Log belum tersedia','truncated':False}
        with path.open('rb') as stream:
            stream.seek(0,2);length=stream.tell();stream.seek(max(0,length-100000))
            text=stream.read(100000).decode('utf-8',errors='replace')
        return {'text':redact(text,limit=None),'truncated':length>100000}

    @api.get('/jobs/{jid}/log')
    def log(jid:str):return read_log(jid)

    @api.get('/jobs/{jid}/log/download')
    def download_log(jid:str):
        data=read_log(jid)
        prefix='[Bagian akhir log; dibatasi 100.000 byte]\n' if data['truncated'] else ''
        return PlainTextResponse(prefix+data['text'],headers={'Content-Disposition':'attachment; filename="'+jid+'.log"'})

    @api.post('/profile')
    def profile(data:dict=Body(...)):return guarded(service.runtime.select_profile)(data.get('name'))

    @api.post('/components/{key}/enabled')
    def enable(key:str,data:dict=Body(...)):
        if type(data.get('enabled')) is not bool:raise HTTPException(400,'Nilai enabled harus boolean')
        return guarded(service.runtime.enable)(key,data['enabled'])

    @api.get('/components/{key}/artifact')
    def artifact(key:str,path:str):
        active=guarded(service.runtime.active)(key)
        if not active:raise HTTPException(404,'Komponen belum dipasang')
        if path not in active.get('test',{}).get('artifacts',[]):raise HTTPException(404,'Berkas bukan hasil uji terdaftar')
        target=guarded(safe_path)(active['directory'],path)
        if not target.is_file():raise HTTPException(404,'Hasil uji tidak tersedia')
        return FileResponse(target,filename=target.name)
    return api
