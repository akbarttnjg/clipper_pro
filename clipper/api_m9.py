"""M9 binary capture transport. Guest capabilities never become workspace sessions."""
from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from .api_m8 import error_response
from .m8_contract import AccessDenied, only
from .m9_contract import MAX_CHUNK, integer


def router(service):
    api=APIRouter(prefix='/m9',tags=['m9'])
    @api.get('/v1/clock')
    def clock(request:Request):
        service.integrations.workspaces.require(request.state.m8_actor)
        return {'server_time':service.integrations.db.clock()}

    @api.post('/v1/invites')
    def invite(request:Request,data:dict=Body(...)):
        try:return JSONResponse(service.lab.recording.invite(request.state.m8_actor,data),headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        except (ValueError,KeyError,OSError,TypeError) as exc:return error_response(exc)

    @api.post('/v1/tracks')
    def track(request:Request,data:dict=Body(...)):
        try:return service.lab.recording.add_track(request.state.m8_actor,data)
        except (ValueError,KeyError,OSError,TypeError) as exc:return error_response(exc)

    async def upload(request,key,seq,actor,participant=None):
        try:
            blocks=[];size=0
            async for block in request.stream():
                size+=len(block)
                if size>MAX_CHUNK:return JSONResponse({'error':'request_too_large','message':'Chunk maksimal 25 MiB'},status_code=413)
                blocks.append(block)
            return service.lab.recording.chunk(actor,key,seq,b''.join(blocks),request.headers.get('x-chunk-sha256'),float(request.headers.get('x-elapsed-seconds','nan')),participant)
        except (ValueError,KeyError,OSError,TypeError) as exc:return error_response(exc)

    @api.put('/v1/tracks/{key}/chunks/{seq}')
    async def chunk(request:Request,key:str,seq:int):return await upload(request,key,seq,request.state.m8_actor)

    def guest(request,key):
        value=request.state.m9_guest
        if value['session_id']!=key:raise AccessDenied('Capability room tidak cocok')
        return value

    @api.get('/guest/{key}/clock')
    def guest_clock(request:Request,key:str):
        g=guest(request,key)
        return {k:g[k] for k in ('session_id','participant','name','clock_origin','server_time')}

    @api.post('/guest/{key}/tracks')
    def guest_track(request:Request,key:str,data:dict=Body(...)):
        try:
            g=guest(request,key)
            if data.get('id')!=key:raise AccessDenied('Track harus di room undangan')
            return service.lab.recording.add_track(g['actor'],data,g['participant'])
        except (ValueError,KeyError,OSError,TypeError) as exc:return error_response(exc)

    @api.get('/guest/{key}/tracks/{track_id}')
    def guest_track_get(request:Request,key:str,track_id:str):
        try:
            g=guest(request,key);track=service.lab.recording.track(g['actor'],track_id,g['participant'])
            if track['session_id']!=key:raise AccessDenied('Track di luar room')
            return track
        except (ValueError,KeyError,OSError,TypeError) as exc:return error_response(exc)

    @api.put('/guest/{key}/tracks/{track_id}/chunks/{seq}')
    async def guest_chunk(request:Request,key:str,track_id:str,seq:int):
        g=guest(request,key)
        try:
            track=service.lab.recording.track(g['actor'],track_id,g['participant'])
            if track['session_id']!=key:raise AccessDenied('Track di luar room')
        except (ValueError,KeyError) as exc:return error_response(exc)
        return await upload(request,track_id,seq,g['actor'],g['participant'])

    @api.post('/guest/{key}/seal')
    def guest_seal(request:Request,key:str,data:dict=Body(...)):
        try:
            g=guest(request,key);track=service.lab.recording.track(g['actor'],data.get('track_id'),g['participant'])
            if track['session_id']!=key:raise AccessDenied('Track di luar room')
            return service.lab.recording.seal(g['actor'],data,g['participant'])
        except (ValueError,KeyError,OSError,TypeError) as exc:return error_response(exc)
    return api
