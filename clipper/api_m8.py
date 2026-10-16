"""Authenticated M8 boundary and local-only protection for legacy Studio routes."""
import asyncio
import json
import os
from urllib.parse import urlsplit
from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from .m8_contract import AccessDenied, Busy, canonical, integer, only
from .m8_youtube import NetworkFailure, RemoteFailure
from .project_store import Conflict


def error_response(exc):
    if isinstance(exc, AccessDenied):
        return JSONResponse({'error': 'access_denied', 'message': str(exc)}, status_code=403)
    if isinstance(exc, Conflict):
        return JSONResponse({'error': 'revision_conflict', 'message': str(exc), 'revision': exc.revision, 'paths': exc.paths}, status_code=409)
    if isinstance(exc, Busy):
        return JSONResponse({'error': 'needs_reconcile', 'message': str(exc)}, status_code=409)
    if isinstance(exc, NetworkFailure):
        return JSONResponse({'error': 'network_unavailable', 'message': str(exc)}, status_code=503)
    if isinstance(exc, RemoteFailure):
        return JSONResponse({'error': 'platform_error', 'message': str(exc)}, status_code=502)
    return JSONResponse({'error': 'not_found' if isinstance(exc, KeyError) else 'invalid_request', 'message': str(exc)}, status_code=404 if isinstance(exc, KeyError) else 400)


def router(service):
    m8 = service.integrations
    api = APIRouter(prefix='/m8/v1', tags=['m8-v1'])
    @api.post('/command')
    def command(request: Request, data: dict = Body(...)):
        try:
            return m8.command(request.state.m8_actor, data)
        except (ValueError, KeyError, OSError, TypeError) as exc:
            return error_response(exc)

    @api.post('/sessions')
    def sessions(request: Request, data: dict = Body(...)):
        try:
            return JSONResponse(m8.workspaces.issue_session(request.state.m8_actor, data), headers={'Cache-Control': 'no-store'})
        except (ValueError, KeyError, OSError, TypeError) as exc:
            return error_response(exc)

    @api.post('/reviews')
    def create_review(request: Request, data: dict = Body(...)):
        try:
            from .delivery7_review import Reviews
            actor=request.state.m8_actor
            only(data,('project_id','expected_revision','package_content_id','permission','expires_minutes'),('project_id','expected_revision','package_content_id'))
            m8.workspaces.require(actor,'review',data['project_id'])
            if data.get('permission')=='download':m8.workspaces.require(actor,'publish',data['project_id'])
            value=Reviews(service).create(data['project_id'],{k:v for k,v in data.items() if k!='project_id'})
            return JSONResponse(value,headers={'Cache-Control':'no-store'})
        except (ValueError, KeyError, OSError, TypeError) as exc:
            return error_response(exc)

    @api.post('/oauth/start')
    def oauth_start(request: Request, data: dict = Body(...)):
        try:
            return JSONResponse(m8.accounts.oauth_start(request.state.m8_actor, data), headers={'Cache-Control': 'no-store'})
        except (ValueError, KeyError, OSError, TypeError) as exc:
            return error_response(exc)

    @api.get('/oauth/{flow_id}')
    def oauth_status(request: Request, flow_id: str):
        try:
            return JSONResponse(m8.accounts.oauth_status(request.state.m8_actor, flow_id), headers={'Cache-Control': 'no-store'})
        except (ValueError, KeyError, OSError, TypeError) as exc:
            return error_response(exc)

    @api.post('/webhooks/{webhook_id}/signing-key')
    def webhook_key(request: Request, webhook_id: str):
        try:
            return JSONResponse(m8.webhooks.signing_key(request.state.m8_actor, webhook_id), headers={'Cache-Control': 'no-store'})
        except (ValueError, KeyError, OSError, TypeError) as exc:
            return error_response(exc)

    @api.get('/files/{file_id}')
    def file(request: Request, file_id: str):
        try:
            path = m8.file(request.state.m8_actor, file_id)
            return FileResponse(path, filename=path.name, headers={'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer'})
        except (ValueError, KeyError, OSError, TypeError) as exc:
            return error_response(exc)

    @api.get('/events')
    async def events(request: Request, after: int = 0):
        actor = request.state.m8_actor
        try:
            m8.workspaces.require(actor)
            cursor = integer(int(request.headers.get('last-event-id', after)), 'Event cursor')
        except (ValueError, KeyError) as exc:
            return error_response(exc)
        async def generate():
            nonlocal cursor
            # Finite stream permits frequent membership/expiry revalidation and simple resume.
            for _ in range(10):
                if await request.is_disconnected():
                    break
                try:
                    m8.workspaces.require(actor)
                except AccessDenied:
                    break
                rows = m8.db.events(actor.workspace, cursor)
                for row in rows:
                    cursor = row['seq']
                    yield 'id: '+str(cursor)+'\nevent: m8\ndata: '+canonical(row)+'\n\n'
                yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(generate(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
    return api


def install_security(app, service):
    m8 = service.integrations
    @app.middleware('http')
    async def m8_boundary(request, call_next):
        path = request.url.path
        if not path.startswith('/api/'):
            return await call_next(request)
        # Existing review capability URLs keep their explicit token, expiry and permissions.
        if path.startswith('/api/studio/delivery7/review/') and request.method in ('GET', 'HEAD'):
            return await call_next(request)
        try:
            peer = request.client.host if request.client else ''
            local = peer in ('127.0.0.1', '::1')
            host = urlsplit('http://'+request.headers.get('host', '')).hostname
            allowed = {'127.0.0.1', 'localhost', '::1'}
            if m8.server_mode:
                allowed |= {v.strip().lower() for v in os.environ.get('CLIPPER_M8_ALLOWED_HOSTS', '').split(',') if v.strip()}
            if host not in allowed:
                raise AccessDenied('Host tidak diizinkan')
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                raise AccessDenied('Origin berbeda; gunakan halaman Clipper pada host yang sama')
            authorization = request.headers.get('authorization', '')
            guest_prefix='/api/studio/m9/guest/'
            scoped_prefixes=('/api/studio/m8/v1/','/api/studio/m9/v1/')
            if path.startswith(guest_prefix):
                if not local and (not m8.server_mode or request.url.scheme!='https'):
                    raise AccessDenied('Tamu jaringan memerlukan mode server dan HTTPS eksplisit')
                if not authorization.startswith('Bearer '):raise AccessDenied('Undangan room diperlukan')
                session_id=path[len(guest_prefix):].split('/')[0]
                request.state.m9_guest=service.lab.recording.guest(authorization[7:],session_id)
                if request.method=='POST':
                    body=bytearray()
                    async for block in request.stream():
                        body.extend(block)
                        if len(body)>1024**2:return JSONResponse({'error':'request_too_large'},status_code=413)
                    request._body=bytes(body)
                response=await call_next(request)
                response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer'
                return response
            if m8.server_mode:
                if not path.startswith(scoped_prefixes):
                    raise AccessDenied('Mode server memakai API M8 dengan workspace; endpoint lokal lama tidak tersedia dari jaringan')
                if not authorization.startswith('Bearer '):
                    raise AccessDenied('Sesi bearer diperlukan pada mode server')
                actor = m8.workspaces.authenticate(authorization[7:])
            else:
                if not local:
                    raise AccessDenied('Mode lokal hanya menerima koneksi loopback. Mode server memerlukan konfigurasi dan sesi eksplisit.')
                actor = m8.workspaces.authenticate(authorization[7:]) if authorization.startswith('Bearer ') else m8.local_actor()
                if actor.session_id and not path.startswith(scoped_prefixes):
                    raise AccessDenied('Sesi anggota hanya berlaku pada API M8 yang memeriksa workspace')
            request.state.m8_actor = actor
            if path.startswith(scoped_prefixes) and request.method == 'POST':
                blocks = [];size = 0
                async for block in request.stream():
                    size += len(block)
                    if size > 1024**2:
                        return JSONResponse({'error': 'request_too_large', 'message': 'Permintaan M8 maksimal 1 MiB'}, status_code=413)
                    blocks.append(block)
                request._body = b''.join(blocks)
            response = await call_next(request)
            if path.startswith(('/api/studio/m8/','/api/studio/m9/')):
                response.headers['Cache-Control'] = 'no-store'
                response.headers['Referrer-Policy'] = 'no-referrer'
            return response
        except (ValueError, KeyError) as exc:
            return error_response(exc)
