"""Immutable local assets, real Unicode cmap checks and portable brand packs."""
import hashlib,json,shutil,struct,time,uuid,zipfile
from pathlib import Path,PurePosixPath
from functools import lru_cache
from PIL import Image,ImageFont
from .project_store import Conflict,dumps
from .contracts import fingerprint
from .finishing5_contract import VERSION,style,layers,text

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
@lru_cache(maxsize=64)
def sfnt(path,digest):
    p=Path(path)
    if p.stat().st_size>32*1024*1024 or sha(p)!=digest:raise ValueError('Font berubah/terlalu besar')
    data=p.read_bytes();u16=lambda i:struct.unpack_from('>H',data,i)[0];u32=lambda i:struct.unpack_from('>I',data,i)[0]
    try:
        if data[:4] not in (b'\0\1\0\0',b'OTTO',b'true') or not 1<=u16(4)<=256:raise ValueError('Pilih font tunggal TTF/OTF')
        tables={}
        for i in range(u16(4)):
            at=12+i*16;off,n=u32(at+8),u32(at+12)
            if off+n>len(data):raise ValueError('Tabel font terpotong')
            tables[data[at:at+4].decode('ascii')]=(off,n)
        names={};at,n=tables['name'];strings=at+u16(at+4)
        if u16(at+2)>4096:raise ValueError('Nama font tidak valid')
        for i in range(u16(at+2)):
            platform,enc,lang,key,size,off=struct.unpack_from('>6H',data,at+6+i*12)
            if strings+off+size>at+n:raise ValueError('Nama font terpotong')
            if key in (1,2,16,17):
                value=data[strings+off:strings+off+size].decode('utf-16-be' if platform in (0,3) else 'mac_roman',errors='replace').strip();pri=(platform==3,lang==0x409)
                if value and (key not in names or pri>names[key][0]):names[key]=(pri,value)
        family=names.get(16,names.get(1,(None,'')))[1];face=names.get(17,names.get(2,(None,'Regular')))[1]
        if not family or any(c in family for c in '\\{},\r\n'):raise ValueError('Family font tidak aman')
        weight=400;italic='italic' in face.lower()
        if 'OS/2' in tables:
            at,n=tables['OS/2'];weight=u16(at+4)
            if n>=64:italic=bool(u16(at+62)&1)
        base,length=tables['cmap'];glyphs=set();subs=set()
        for i in range(u16(base+2)):
            plat,enc,off=struct.unpack_from('>HHI',data,base+4+i*8)
            if plat==0 or plat==3 and enc in (1,10):subs.add(base+off)
        for at in subs:
            form=u16(at)
            if form==12:
                count=u32(at+12)
                if count>200000 or at+16+count*12>base+length:raise ValueError('Cmap tidak valid')
                for i in range(count):
                    a,b,g=struct.unpack_from('>III',data,at+16+i*12)
                    if b<a or b>0x10ffff:raise ValueError('Rentang cmap tidak valid')
                    glyphs.update(range(a+(g==0),b+1))
            elif form==4:
                end=at+u16(at+2);count=u16(at+6)//2;ends=at+14;starts=ends+count*2+2;deltas=starts+count*2;offsets=deltas+count*2
                if end>base+length:raise ValueError('Cmap terpotong')
                for i in range(count):
                    a,b=u16(starts+2*i),u16(ends+2*i);delta=u16(deltas+2*i);off=u16(offsets+2*i)
                    if b<a:raise ValueError('Cmap terbalik')
                    for code in range(a,min(b,65534)+1):
                        if off:
                            pos=offsets+2*i+off+2*(code-a)
                            if pos+2>end:raise ValueError('Cmap glyph terpotong')
                            g=u16(pos);g=(g+delta)&65535 if g else 0
                        else:g=(code+delta)&65535
                        if g:glyphs.add(code)
        if not glyphs:raise ValueError('Unicode cmap font belum didukung')
        ImageFont.truetype(str(p),40).getbbox('Clipper')
        return dict(family=family,style=face,weight=weight,bold=weight>=700,italic=italic,sha256=digest,glyphs=frozenset(glyphs))
    except (struct.error,KeyError,OSError,UnicodeError) as exc:raise ValueError('Struktur font tidak terbaca') from exc
def font_info(folder,key):
    from .font_catalog import FONTS
    if key in FONTS:r={**FONTS[key],'font_id':key,'source':'bundled'}
    else:
        manifest=json.loads((Path(folder)/'m5-fonts.json').read_text())
        if key not in manifest:raise ValueError('Font tidak tersedia: '+key)
        r={**manifest[key],'font_id':key,'source':'local_import'}
    p=Path(folder)/r['file'];m=sfnt(str(p.resolve()),sha(p))
    return {**r,**{k:v for k,v in m.items() if k!='glyphs'}}
def choose_font(folder,key,fallback,value):
    required={ord(c) for c in value if not c.isspace()};covered=set()
    for k in dict.fromkeys([key,*fallback]):
        r=font_info(folder,k);g=sfnt(str((Path(folder)/r['file']).resolve()),r['sha256'])['glyphs'];covered|=g
        if required<=g:return r
    raise ValueError('Glyph/font belum tersedia: '+', '.join(f'U+{c:04X}' for c in sorted(required-covered)[:12])+'. Import font yang sesuai sebelum render.')

class Assets:
    def __init__(self,service):
        self.service=service;self.store=service.store;self.root=service.work/'m5-assets';self.root.mkdir(exist_ok=True)
        with self.store.connect() as db:db.executescript('CREATE TABLE IF NOT EXISTS assets5(id TEXT PRIMARY KEY,data TEXT);CREATE TABLE IF NOT EXISTS kits5(id TEXT PRIMARY KEY,revision INTEGER,data TEXT);CREATE TABLE IF NOT EXISTS kit_history5(id TEXT,revision INTEGER,data TEXT,PRIMARY KEY(id,revision));')
        with self.store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS asset_history5(id TEXT,revision INTEGER,data TEXT,PRIMARY KEY(id,revision))')
    def list(self,q='',collection=None):
        with self.store.connect() as db:rows=[json.loads(r['data']) for r in db.execute('SELECT data FROM assets5 ORDER BY id')]
        return [r for r in rows if (not collection or collection in r['collections']) and all(t in dumps({k:v for k,v in r.items() if k!='path'}).casefold() for t in q.casefold().split())]
    def get(self,key):
        with self.store.connect() as db:r=db.execute('SELECT data FROM assets5 WHERE id=?',(key,)).fetchone()
        if not r:raise ValueError('Aset M5 tidak ditemukan')
        row=json.loads(r['data'])
        if not Path(row['path']).is_file() or sha(row['path'])!=row['sha256']:raise ValueError('Aset berubah/hilang: '+row['name'])
        return row
    def register(self,path,meta):
        p=Path(str(path).strip().strip('"\'')).expanduser().resolve()
        if not p.is_file() or p.stat().st_size>512*1024*1024:raise ValueError('Aset harus file lokal maksimal 512 MB')
        kind={'.ttf':'font','.otf':'font','.png':'image','.jpg':'image','.jpeg':'image','.webp':'image','.mp4':'video','.mov':'video','.mkv':'video','.webm':'video','.wav':'audio','.mp3':'audio','.m4a':'audio'}.get(p.suffix.lower())
        keys='name origin license permission attribution tags collections speaker_id object text'.split()
        if not kind or not isinstance(meta,dict) or set(meta)-set(keys):raise ValueError('Format/metadata aset tidak valid')
        permission=meta.get('permission','unknown')
        if permission not in ('unknown','user_owned','licensed'):raise ValueError('Izin aset tidak valid')
        digest=sha(p);key=('font-' if kind=='font' else 'asset-')+digest[:32];dest=self.root/(digest+p.suffix.lower())
        extra={}
        if kind=='font':extra={k:v for k,v in sfnt(str(p),digest).items() if k!='glyphs'}
        elif kind=='image':
            with Image.open(p) as im:
                if im.width*im.height>40_000_000:raise ValueError('Gambar terlalu besar')
                extra={'width':im.width,'height':im.height};im.verify()
        else:
            from .ffmpeg_util import probe
            info=probe(p);extra={k:info.get(k) for k in ('width','height','duration')}
            if not extra.get('duration'):raise ValueError('Durasi aset tidak tersedia')
        for existing in self.list():
            if existing['id']==key:return self.get(key)
        row=dict(id=key,kind=kind,path=str(dest),sha256=digest,name=text(meta.get('name',p.stem),120,'Nama'),permission=permission,license=text(meta.get('license',''),1000,'Lisensi'),origin=text(meta.get('origin','local import'),2000,'Asal'),attribution=text(meta.get('attribution',''),2000,'Kredit'),speaker_id=text(meta.get('speaker_id',''),96,'Speaker'),object=text(meta.get('object',''),200,'Objek'),text=text(meta.get('text',''),1000,'Teks'),created=time.time(),metadata=extra)
        for k in ('tags','collections'):
            v=meta.get(k,[])
            if not isinstance(v,list) or len(v)>30:raise ValueError(k+' tidak valid')
            row[k]=[text(t,100,k) for t in v]
        pending=dest.with_suffix(dest.suffix+'.pending-'+uuid.uuid4().hex)
        try:
            shutil.copyfile(p,pending)
            if sha(pending)!=digest:raise ValueError('Aset berubah saat import')
            pending.replace(dest)
            with self.store.connect() as db:db.execute('INSERT INTO assets5 VALUES(?,?)',(key,dumps(row)))
        finally:pending.unlink(missing_ok=True)
        return row
    def fonts_folder(self,keys,base):
        from .font_catalog import FONTS
        custom=[self.get(k) for k in dict.fromkeys(keys) if k not in FONTS]
        if any(r['kind']!='font' or r['permission']=='unknown' for r in custom):raise ValueError('Font memerlukan metadata izin')
        if not custom:return str(base)
        folder=self.root/'font-sets'/fingerprint([(r['id'],r['sha256']) for r in custom]);folder.mkdir(parents=True,exist_ok=True);manifest={};faces={}
        for k,v in FONTS.items():
            src=Path(base)/v['file'];dest=folder/v['file']
            if not dest.exists() or sha(dest)!=sha(src):shutil.copyfile(src,dest)
            m=font_info(base,k);faces[(m['family'],m['style'])]=m['sha256']
        for r in custom:
            m=r['metadata'];face=(m['family'],m['style'])
            if face in faces and faces[face]!=r['sha256']:raise ValueError('Family/style font ambigu: gunakan family unik agar renderer konsisten')
            faces[face]=r['sha256'];dest=folder/Path(r['path']).name
            if not dest.exists() or sha(dest)!=r['sha256']:shutil.copyfile(r['path'],dest)
            manifest[r['id']]={**m,'file':dest.name,'label':r['name']}
        for source in Path(base).iterdir():
            if source.is_file() and ('license' in source.name.lower() or source.name.upper().startswith('OFL')):shutil.copyfile(source,folder/source.name)
        (folder/'m5-font-license.json').write_text(dumps({r['id']:{k:r[k] for k in ('sha256','origin','license','permission','attribution')} for r in custom}),encoding='utf-8')
        (folder/'m5-fonts.json').write_text(dumps(manifest),encoding='utf-8');return str(folder)
    def update_metadata(self,key,revision,values):
        row=self.get(key)
        if not isinstance(values,dict) or set(values)-set('name permission license origin attribution tags collections speaker_id object text'.split()):raise ValueError('Metadata tidak valid')
        new={**row};before_revision=row.get('metadata_revision',0)
        if type(revision) is not int or revision!=before_revision:raise Conflict(before_revision,'Metadata aset berubah')
        for k,v in values.items():
            if k=='permission':
                if v not in ('unknown','licensed','user_owned'):raise ValueError('Izin tidak valid')
                new[k]=v
            elif k in ('tags','collections'):
                if not isinstance(v,list) or len(v)>30:raise ValueError('Daftar metadata tidak valid')
                new[k]=[text(t,100,k) for t in v]
            else:new[k]=text(v,2000,k)
        new['metadata_revision']=before_revision+1
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');current=json.loads(db.execute('SELECT data FROM assets5 WHERE id=?',(key,)).fetchone()['data'])
            if current!=row:raise Conflict(current.get('metadata_revision',0),'Metadata berubah')
            db.execute('INSERT OR IGNORE INTO asset_history5 VALUES(?,?,?)',(key,before_revision,dumps(row)));db.execute('INSERT INTO asset_history5 VALUES(?,?,?)',(key,new['metadata_revision'],dumps(new)));db.execute('UPDATE assets5 SET data=? WHERE id=?',(dumps(new),key));db.commit()
        return new
    def kits(self):
        with self.store.connect() as db:return [json.loads(r['data']) for r in db.execute('SELECT data FROM kits5 ORDER BY id')]
    def kit(self,key):
        row=next((r for r in self.kits() if r['id']==key),None)
        if not row:raise ValueError('Kit M5 tidak ditemukan')
        return row
    def kit_revision(self,key,revision):
        if revision is None:return self.kit(key)
        with self.store.connect() as db:row=db.execute('SELECT data FROM kit_history5 WHERE id=? AND revision=?',(key,revision)).fetchone()
        if not row:raise ValueError('Revision kit induk tidak tersedia')
        return json.loads(row['data'])
    def save_kit(self,data):
        if not isinstance(data,dict) or set(data)-set('id expected_revision name parent_id style layers glossary asset_ids license'.split()):raise ValueError('Schema kit tidak valid')
        name=text(data.get('name',''),80,'Nama')
        if not name:raise ValueError('Nama kit diperlukan')
        parent_record=self.kit(data['parent_id']) if data.get('parent_id') else None
        values=style(data.get('style',{}));inherited={**(parent_record.get('effective_style',parent_record['style']) if parent_record else {}),**values}
        dec=layers(data.get('layers',parent_record.get('layers',[]) if parent_record else []));keys=data.get('asset_ids',[])
        if not isinstance(keys,list) or len(keys)>100:raise ValueError('Daftar aset tidak valid')
        ids=set(keys)|{r['asset_id'] for r in dec if r.get('asset_id')}|{v for k,v in inherited.items() if k in ('font_main','font_accent') and v.startswith('font-')}|{v for v in inherited.get('fallback_fonts',[]) if v.startswith('font-')}
        rows=[self.get(k) for k in sorted(ids)]
        if any(r['permission']=='unknown' for r in rows):raise ValueError('Izin seluruh aset kit harus diisi')
        glossary=data.get('glossary',parent_record.get('glossary',[]) if parent_record else [])
        if not isinstance(glossary,list) or len(glossary)>100:raise ValueError('Kamus tidak valid')
        from .stage3 import fact_review
        for r in glossary:
            if not isinstance(r,dict) or set(r)!={'heard','preferred'}:raise ValueError('Kamus harus heard/preferred')
            a=text(r['heard'],100,'Ejaan sumber');b=text(r['preferred'],100,'Ejaan pilihan')
            if not a or not b or fact_review(a,b)['requires_confirmation']:raise ValueError('Kamus brand tidak boleh mengubah fakta kritis')
        key=data.get('id') or 'kit5-'+uuid.uuid4().hex[:24];parent=data.get('parent_id');seen={key};ancestor=parent
        while ancestor:
            if ancestor in seen:raise ValueError('Siklus sub-brand tidak valid')
            seen.add(ancestor);ancestor=self.kit(ancestor).get('parent_id')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT revision FROM kits5 WHERE id=?',(key,)).fetchone()
            if old and data.get('expected_revision')!=old['revision']:raise Conflict(old['revision'],'Kit berubah')
            if not old and data.get('id'):raise ValueError('Kit tidak ditemukan')
            rev=old['revision']+1 if old else 0;kit=dict(id=key,revision=rev,name=name,parent_id=parent,style=values,layers=dec,glossary=glossary,asset_ids=sorted(ids),license=text(data.get('license',''),1000,'Lisensi'),asset_digests={r['id']:r['sha256'] for r in rows},version=VERSION,schema_version=1)
            kit['asset_metadata']={r['id']:{k:v for k,v in r.items() if k not in ('path','created')} for r in rows}
            kit['effective_style']=inherited;kit['parent_revision']=parent_record['revision'] if parent_record else None
            kit['parent_snapshot']={k:parent_record.get(k) for k in ('id','revision','name','style','effective_style')} if parent_record else None
            db.execute('INSERT OR REPLACE INTO kits5 VALUES(?,?,?)',(key,rev,dumps(kit)));db.execute('INSERT INTO kit_history5 VALUES(?,?,?)',(key,rev,dumps(kit)));db.commit()
        return kit
    def export(self,key,target):
        kit=self.kit(key);parents=[];p=kit.get('parent_id');revision=kit.get('parent_revision')
        while p:row=self.kit_revision(p,revision);parents.insert(0,row);p=row.get('parent_id');revision=row.get('parent_revision')
        ids={i for k in [*parents,kit] for i in k['asset_ids']};m={'schema_version':1,'version':VERSION,'kit':kit,'parents':parents,'assets':[]}
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
            for key in sorted(ids):
                r=self.get(key)
                if r['permission']=='unknown':raise ValueError('Izin aset belum diisi')
                name='assets/'+r['sha256']+Path(r['path']).suffix;z.write(r['path'],name);m['assets'].append({**{k:v for k,v in r.items() if k not in ('path','created')},'file':name})
            z.writestr('manifest.json',dumps(m))
        return Path(target)
    def import_pack(self,path):
        with zipfile.ZipFile(path) as z:
            names=z.namelist()
            if len(names)>202 or len(names)!=len({n.casefold() for n in names}) or sum(r.file_size for r in z.infolist())>512*1024*1024:raise ValueError('Paket terlalu besar/duplikat')
            for r in z.infolist():
                n=PurePosixPath(r.filename)
                if n.is_absolute() or '..' in n.parts or '\\' in r.filename or ':' in r.filename or r.is_dir() or (r.external_attr>>16&0o170000)==0o120000:raise ValueError('Path paket tidak aman')
            m=json.loads(z.read('manifest.json'))
            if m.get('schema_version')!=1 or not isinstance(m.get('assets'),list):raise ValueError('Versi kit tidak valid')
            records=[]
            for r in m['assets']:
                data=z.read(r['file'])
                if not r['file'].startswith('assets/') or hashlib.sha256(data).hexdigest()!=r['sha256']:raise ValueError('Digest aset portable tidak cocok')
                records.append((r,data))
            if set(names)!={'manifest.json',*[r['file'] for r,_ in records]}:raise ValueError('File tambahan di paket')
            kits=[*m.get('parents',[]),m['kit']]
            if len(kits)>30:raise ValueError('Rantai sub-brand terlalu panjang')
            for k in kits:style(k['style']);layers(k['layers'])
            for r,data in records:
                pending=self.root/(uuid.uuid4().hex+Path(r['file']).suffix)
                try:
                    pending.write_bytes(data);self.register(pending,{k:r.get(k,[] if k in ('tags','collections') else '') for k in 'name origin license permission attribution tags collections speaker_id object text'.split()})
                finally:pending.unlink(missing_ok=True)
            mapping={};last=None
            for k in kits:
                value={f:v for f,v in k.items() if f in ('name','style','layers','glossary','asset_ids','license')};value['parent_id']=mapping.get(k.get('parent_id'));last=self.save_kit(value);mapping[k['id']]=last['id']
            return last
