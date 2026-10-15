"""Permission/expiry bound local review URLs for exact immutable M7 deliveries."""
import hashlib,json,secrets,time,uuid
from pathlib import Path
from .artifact_store import verify
from .dependency_cache import content_id
from .project_store import Conflict,dumps
from .storage import read_json


def token_hash(token):return hashlib.sha256(str(token).encode()).hexdigest()


class Reviews:
    def __init__(self,service,clock=time.time):
        self.service=service;self.store=service.store;self.clock=clock
        with self.store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS reviews7(id TEXT PRIMARY KEY,project_id TEXT,token_hash TEXT UNIQUE,data TEXT,revoked INTEGER DEFAULT 0)')

    def create(self,pid,data):
        if set(data)-{'expected_revision','package_content_id','permission','expires_minutes'}:raise ValueError('Opsi review tidak dikenal')
        doc=self.store.get(pid)
        if type(data.get('expected_revision')) is not int or data.get('expected_revision')!=doc['revision']:raise Conflict(doc['revision'])
        permission=data.get('permission','review');minutes=data.get('expires_minutes',1440)
        if permission not in ('review','download') or type(minutes) is not int or not 15<=minutes<=10080:raise ValueError('Izin review/download dan masa berlaku 15–10080 menit diperlukan')
        package=next((p for p in doc.get('exports',[]) if p.get('version')=='4.0.18-m7' and p.get('package_content_id')==data.get('package_content_id')),None)
        if not package or not verify(package):raise ValueError('ArtifactSet M7 hilang/berubah; buat paket kembali')
        manifest=read_json(package['delivery_manifest_path']);entries=[];root=Path(package['folder'])
        for row in manifest['coverage']:
            path=root/row['file'];entries.append({'id':row['key'],'title':row['title'],'variant_id':row['variant_id'],
                'path':str(path),'content_id':row['output_content_id'],'role':'preview','duration':row['duration']})
        ident='review-'+uuid.uuid4().hex;token=secrets.token_urlsafe(32);now=self.clock()
        value={'id':ident,'project_id':pid,'permission':permission,'created':now,'expires':now+minutes*60,
            'input_revision':package['input_revision'],'package_content_id':package['package_content_id'],
            'manifest_path':package['artifact_manifest_path'],'manifest_content_id':package['artifact_manifest_id'],
            'artifact_root':package['artifact_root'],'zip':package['zip'],'entries':entries}
        with self.store.connect() as db:db.execute('INSERT INTO reviews7 VALUES(?,?,?,?,0)',(ident,pid,token_hash(token),dumps(value)))
        return {k:value[k] for k in ('id','permission','expires','input_revision','package_content_id')}|{'url':'/api/studio/delivery7/review/'+token,'local_only':True,'copy_protection':False}

    def listing(self,pid):
        self.store.get(pid)
        with self.store.connect() as db:rows=db.execute('SELECT data,revoked FROM reviews7 WHERE project_id=? ORDER BY id',(pid,)).fetchall()
        return [{**{k:json.loads(r['data'])[k] for k in ('id','permission','created','expires','input_revision','package_content_id')},
            'revoked':bool(r['revoked']),'expired':json.loads(r['data'])['expires']<=self.clock()} for r in rows]

    def revoke(self,pid,ident,expected_revision):
        doc=self.store.get(pid)
        if expected_revision!=doc['revision']:raise Conflict(doc['revision'])
        with self.store.connect() as db:
            result=db.execute('UPDATE reviews7 SET revoked=1 WHERE id=? AND project_id=?',(ident,pid))
            if result.rowcount!=1:raise ValueError('Review tidak ditemukan')
        return {'id':ident,'revoked':True}

    def lookup(self,token):
        if not isinstance(token,str) or not 40<=len(token)<=80:raise ValueError('Tautan review tidak valid')
        with self.store.connect() as db:row=db.execute('SELECT data,revoked FROM reviews7 WHERE token_hash=?',(token_hash(token),)).fetchone()
        if not row or row['revoked']:raise ValueError('Tautan review tidak aktif')
        value=json.loads(row['data'])
        if value['expires']<=self.clock():raise ValueError('Tautan review kedaluwarsa')
        path=Path(value['manifest_path']);root=Path(value['artifact_root']).resolve()
        if path.is_symlink() or not path.resolve().is_relative_to(root) or content_id(path,fresh=True)!=value['manifest_content_id']:raise ValueError('Set yang direview berubah')
        return value

    def resolve(self,token,member):
        value=self.lookup(token)
        if member=='package':
            if value['permission']!='download':raise ValueError('Tautan ini hanya untuk review, unduhan ZIP tidak diizinkan')
            path=Path(value['zip']);expected=value['package_content_id']
        else:
            row=next((r for r in value['entries'] if r['id']==member),None)
            if not row:raise ValueError('Anggota review tidak ditemukan')
            path=Path(row['path']);expected=row['content_id']
        root=Path(value['artifact_root']).resolve()
        if path.is_symlink() or not path.resolve().is_relative_to(root) or content_id(path,fresh=True)!=expected:raise ValueError('Anggota review hilang/berubah')
        return path

    def view(self,token):
        value=self.lookup(token);prefix='/api/studio/delivery7/review/'+token
        return {k:value[k] for k in ('permission','expires','input_revision','package_content_id')}|{
            'entries':[{k:r[k] for k in ('id','title','variant_id','role','duration','content_id')}|{'url':prefix+'/files/'+r['id']} for r in value['entries']],
            'download_url':prefix+'/files/package' if value['permission']=='download' else None,
            'copy_protection':False,'note':'Akses lokal terbatas endpoint; preview video tetap dapat disimpan oleh penerima.'}
