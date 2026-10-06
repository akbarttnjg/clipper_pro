"""Resumable, content-verified model/source download, using only the stdlib."""
import hashlib
import re
import shutil
import urllib.request
from pathlib import Path
from .state import write, read, digest


class Canceled(RuntimeError): pass


def fetch(url, target, expected, *, algorithm='sha256', size=None, headers=None,
          progress=lambda done,total:None, canceled=lambda:False, opener=urllib.request.urlopen):
    if algorithm not in ('sha256','git-sha1') or not re.fullmatch('[a-fA-F0-9]{'+str(64 if algorithm=='sha256' else 40)+'}',expected):
        raise ValueError('Hash sumber wajib diketahui sebelum mengunduh')
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    partial=target.with_name(target.name+'.part');meta=partial.with_name(partial.name+'.json')
    if target.exists() and digest(target,algorithm)==expected.lower():
        progress(target.stat().st_size,size or target.stat().st_size);return target
    identity={'url_hash':hashlib.sha256(url.encode()).hexdigest(),'hash':expected.lower(),'algorithm':algorithm}
    saved=read(meta,{})
    if any(saved.get(k)!=v for k,v in identity.items()):partial.unlink(missing_ok=True);saved={}
    offset=partial.stat().st_size if partial.exists() else 0
    if size is not None and offset>size:partial.unlink(missing_ok=True);offset=0
    if offset and size==offset and digest(partial,algorithm)==expected.lower():
        partial.replace(target);meta.unlink(missing_ok=True);progress(offset,size);return target
    if size is not None and shutil.disk_usage(target.parent).free < max(0,size-offset)+8*1024**2:
        raise OSError('Ruang disk tidak cukup untuk melanjutkan unduhan')
    if canceled():raise Canceled('Unduhan dibatalkan; potongan data disimpan untuk dilanjutkan')
    request_headers={'User-Agent':'Clipper-Studio/4.0.2',**(headers or {})}
    if offset:
        request_headers['Range']='bytes='+str(offset)+'-'
        if saved.get('etag'):request_headers['If-Range']=saved['etag']
    request=urllib.request.Request(url,headers=request_headers)
    with opener(request,timeout=45) as response:
        code=getattr(response,'status',None) or response.getcode()
        content_range=response.headers.get('Content-Range','')
        if offset and code==206:
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+|\*)',content_range)
            if not match or int(match[1])!=offset:raise ValueError('Server memberi rentang unduhan yang tidak sesuai')
            if saved.get('etag') and response.headers.get('ETag') and saved['etag']!=response.headers['ETag']:
                partial.unlink(missing_ok=True);meta.unlink(missing_ok=True)
                raise ValueError('ETag berubah saat melanjutkan unduhan; coba ulang dari awal')
        elif offset:
            offset=0
        length=response.headers.get('Content-Length')
        total=size if size is not None else offset+int(length) if length else None
        if total is not None and shutil.disk_usage(target.parent).free < max(0,total-offset)+8*1024**2:
            raise OSError('Ruang disk tidak cukup untuk unduhan')
        write(meta,{**identity,'etag':response.headers.get('ETag'),'size':total})
        with partial.open('ab' if offset else 'wb') as stream:
            done=offset;progress(done,total)
            while True:
                if canceled():raise Canceled('Unduhan dibatalkan; dapat dilanjutkan')
                block=response.read(1024*1024)
                if not block:break
                stream.write(block);done+=len(block);progress(done,total)
            stream.flush()
        if total is not None and done!=total:raise OSError('Unduhan terputus; data parsial disimpan')
    if digest(partial,algorithm)!=expected.lower():
        partial.unlink(missing_ok=True);meta.unlink(missing_ok=True)
        raise ValueError('Hash unduhan tidak cocok; berkas tidak diaktifkan')
    partial.replace(target);meta.unlink(missing_ok=True);return target
