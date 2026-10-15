from fastapi import APIRouter,Body
from fastapi.responses import FileResponse,HTMLResponse
from .delivery7_contract import selection
from .delivery7_review import Reviews


def router(service,guarded):
    api=APIRouter();reviews=Reviews(service)
    @api.post('/projects/{pid}/delivery7/preflight')
    @guarded
    def preflight(pid:str,data:dict=Body(default={})):
        return selection(service,service.store.get(pid),data,fresh=True)
    @api.post('/projects/{pid}/delivery7/reviews')
    @guarded
    def create_review(pid:str,data:dict=Body(...)):return reviews.create(pid,data)
    @api.get('/projects/{pid}/delivery7/reviews')
    @guarded
    def listing(pid:str):return {'reviews':reviews.listing(pid)}
    @api.post('/projects/{pid}/delivery7/reviews/{ident}/revoke')
    @guarded
    def revoke(pid:str,ident:str,data:dict=Body(...)):return reviews.revoke(pid,ident,data.get('expected_revision'))
    @api.get('/delivery7/review/{token}')
    @guarded
    def review(token:str):return reviews.view(token)
    @api.get('/delivery7/review/{token}/watch')
    @guarded
    def watch(token:str):
        import html
        value=reviews.view(token);parts=['<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Review klip</title><body><h1>Review klip</h1>']
        for r in value['entries']:
            parts.append('<h2>'+html.escape(r['title'])+' · '+html.escape(r['variant_id'])+'</h2><video controls preload="metadata" style="max-width:100%;max-height:70vh" src="'+html.escape(r['url'],quote=True)+'"></video>')
        if value['download_url']:parts.append('<p><a href="'+html.escape(value['download_url'],quote=True)+'">Unduh paket yang direview</a></p>')
        parts.append('<p>Revisi '+str(value['input_revision'])+' · Akses berakhir sesuai masa berlaku. Preview bukan DRM.</p></body></html>')
        return HTMLResponse(''.join(parts),headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; media-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"})
    @api.get('/delivery7/review/{token}/files/{member}')
    @guarded
    def file(token:str,member:str):
        path=reviews.resolve(token,member)
        return FileResponse(path,filename=path.name if member=='package' else None,headers={'Cache-Control':'private, no-store','Referrer-Policy':'no-referrer'})
    return api
