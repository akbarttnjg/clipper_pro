"""SQLite project revisions, immutable transcript pages and small edit patches.

The database is the Studio 4 source of truth. JSON project documents contain
settings, candidates and sparse corrections, never a full transcript copy.
"""
import copy
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .contracts import fingerprint


class Conflict(ValueError):
    def __init__(self, revision, message='Proyek berubah di tab lain. Draf tetap tersedia.', paths=()):
        super().__init__(message)
        self.revision=revision;self.paths=list(paths)


def dumps(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def differences(before,after,path=()):
    """Missing and JSON null are distinct; lists are atomic values."""
    if isinstance(before,dict) and isinstance(after,dict):
        rows=[]
        for key in sorted(before.keys()|after.keys()):
            if key not in before or key not in after:
                rows.append(dict(path=[*path,key],before=before.get(key),after=after.get(key),
                    before_exists=key in before,after_exists=key in after))
            else:rows+=differences(before[key],after[key],(*path,key))
        return rows
    return [] if before==after else [dict(path=list(path),before=before,after=after,before_exists=True,after_exists=True)]


def at(document,path):
    value=document
    for key in path:
        if not isinstance(value,dict) or key not in value:return False,None
        value=value[key]
    return True,value


def put(document,path,exists,value):
    if not path:raise ValueError('Penggantian seluruh proyek tidak diizinkan')
    target=document
    for key in path[:-1]:target=target.setdefault(key,{})
    if exists:target[path[-1]]=copy.deepcopy(value)
    else:target.pop(path[-1],None)


class ProjectStore:
    def __init__(self,path):
        self.path=Path(path).resolve();self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,document TEXT NOT NULL,created REAL,updated REAL);
                CREATE TABLE IF NOT EXISTS transcripts(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,metadata TEXT NOT NULL,created REAL);
                CREATE TABLE IF NOT EXISTS words(take_id TEXT NOT NULL,kind TEXT NOT NULL,ordinal INTEGER NOT NULL,word_id TEXT,start REAL,end REAL,text TEXT,data TEXT NOT NULL,PRIMARY KEY(take_id,kind,ordinal));
                CREATE INDEX IF NOT EXISTS words_time ON words(take_id,kind,start,end);
                CREATE INDEX IF NOT EXISTS words_identity ON words(take_id,kind,word_id);
                CREATE TABLE IF NOT EXISTS operations(project_id TEXT,operation_id TEXT,request_hash TEXT,response TEXT,PRIMARY KEY(project_id,operation_id));
                CREATE TABLE IF NOT EXISTS history(project_id TEXT,revision INTEGER,label TEXT,changes TEXT,created REAL,PRIMARY KEY(project_id,revision));
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project_id TEXT,kind TEXT,target TEXT,status TEXT,request TEXT,result TEXT,progress INTEGER DEFAULT 0,message TEXT,error TEXT,created REAL,updated REAL,pid INTEGER,owner TEXT);
                CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status,created);
                CREATE TABLE IF NOT EXISTS artifacts(id TEXT PRIMARY KEY,project_id TEXT,clip_id TEXT,variant_id TEXT,kind TEXT,fingerprint TEXT,data TEXT,created REAL);
            ''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=30,isolation_level=None)
        db.row_factory=sqlite3.Row;db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA foreign_keys=ON')
        try:yield db
        finally:db.close()

    def create(self,document,project_id=None):
        project_id=project_id or uuid.uuid4().hex[:12]
        value=copy.deepcopy(document);value.update(project_id=project_id,schema_version=4)
        now=time.time()
        with self.connect() as db:
            db.execute('INSERT INTO projects VALUES(?,?,?,?,?)',(project_id,0,dumps(value),now,now))
        return self.get(project_id)

    def get(self,project_id):
        with self.connect() as db:row=db.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone()
        if row is None:raise KeyError('Proyek tidak ditemukan')
        return {**json.loads(row['document']),'revision':row['revision'],'updated':row['updated']}

    def list(self):
        with self.connect() as db:rows=db.execute('SELECT id,revision,document,updated FROM projects ORDER BY updated DESC').fetchall()
        return [{'project_id':r['id'],'revision':r['revision'],'updated':r['updated'],
                 'name':json.loads(r['document']).get('name','Proyek'),'clips':len(json.loads(r['document']).get('clips',{}))} for r in rows]

    def mutate(self,project_id,expected_revision,operation_id,request,change,label='Sunting proyek'):
        if type(expected_revision) is not int or expected_revision<0:raise ValueError('Revisi proyek harus disertakan')
        if not isinstance(operation_id,str) or not 8<=len(operation_id)<=160:raise ValueError('ID operasi diperlukan')
        request_hash=fingerprint(request)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                prior=db.execute('SELECT request_hash,response FROM operations WHERE project_id=? AND operation_id=?',(project_id,operation_id)).fetchone()
                if prior:
                    if prior['request_hash']!=request_hash:raise ValueError('ID operasi dipakai untuk perubahan berbeda')
                    db.commit();return json.loads(prior['response'])
                row=db.execute('SELECT revision,document FROM projects WHERE id=?',(project_id,)).fetchone()
                if row is None:raise KeyError('Proyek tidak ditemukan')
                if expected_revision!=row['revision']:raise Conflict(row['revision'])
                before=json.loads(row['document']);after=copy.deepcopy(before)
                extra=change(after) or {};patch=differences(before,after)
                revision=row['revision']+1
                db.execute('UPDATE projects SET revision=?,document=?,updated=? WHERE id=?',(revision,dumps(after),time.time(),project_id))
                db.execute('INSERT INTO history VALUES(?,?,?,?,?)',(project_id,revision,label,dumps(patch),time.time()))
                response={**extra,'status':'ready','project_id':project_id,'revision':revision,'operation_id':operation_id}
                db.execute('INSERT INTO operations VALUES(?,?,?,?)',(project_id,operation_id,request_hash,dumps(response)))
                db.commit();return response
            except BaseException:db.rollback();raise

    def history(self,project_id,limit=50):
        with self.connect() as db:rows=db.execute('SELECT revision,label,changes,created FROM history WHERE project_id=? ORDER BY revision DESC LIMIT ?',(project_id,min(100,max(1,limit)))).fetchall()
        return [{**dict(r),'changes':json.loads(r['changes'])} for r in rows]

    def undo(self,project_id,expected_revision,operation_id,revision):
        with self.connect() as db:row=db.execute('SELECT changes,label FROM history WHERE project_id=? AND revision=?',(project_id,revision)).fetchone()
        if not row:raise ValueError('Revisi tidak ditemukan')
        patch=json.loads(row['changes'])
        def change(doc):
            metadata={'timeline_revision','transcript_revision','override_keys'}
            conflicts=[r['path'] for r in patch if r['path'][-1] not in metadata and at(doc,r['path'])!=(r['after_exists'],r['after'])]
            if conflicts:raise Conflict(expected_revision,'Bagian ini sudah disunting lagi; undo tidak menimpa perubahan baru.',conflicts)
            for r in reversed(patch):
                key=r['path'][-1]
                if key in ('timeline_revision','transcript_revision'):
                    put(doc,r['path'],True,(at(doc,r['path'])[1] or 0)+1)
                elif key=='override_keys':
                    existing=set(at(doc,r['path'])[1] or []);before=set(r['before'] or []);after=set(r['after'] or [])
                    put(doc,r['path'],True,sorted((existing-(after-before))|(before-after)))
                else:put(doc,r['path'],r['before_exists'],r['before'])
        return self.mutate(project_id,expected_revision,operation_id,{'undo_revision':revision},change,'Undo: '+row['label'])

    def save_transcript(self,project_id,transcript,take_id=None):
        """Insert once; later word edits live in sparse project corrections."""
        take_id=take_id or 'asr-'+uuid.uuid4().hex
        metadata={k:v for k,v in transcript.items() if k not in ('words','raw_words')}
        records=[]
        for kind,words in [('display',transcript.get('words',[])),('heard',transcript.get('raw_words',transcript.get('words',[])))]:
            for i,w in enumerate(words):
                w={**w,'word_id':w.get('word_id',i)}
                if not 0<=float(w['start'])<float(w['end']):raise ValueError('Waktu kata tidak valid')
                records.append((take_id,kind,i,dumps(w['word_id']),w['start'],w['end'],w['word'],dumps(w)))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('INSERT INTO transcripts VALUES(?,?,?,?)',(take_id,project_id,dumps(metadata),time.time()))
                db.executemany('INSERT INTO words VALUES(?,?,?,?,?,?,?,?)',records);db.commit()
            except BaseException:db.rollback();raise
        return take_id

    def transcript(self,take_id):
        with self.connect() as db:
            row=db.execute('SELECT metadata FROM transcripts WHERE id=?',(take_id,)).fetchone()
            if not row:raise KeyError('Transkrip belum tersedia')
            data=json.loads(row['metadata'])
            for kind,field in [('display','words'),('heard','raw_words')]:
                data[field]=[json.loads(r[0]) for r in db.execute('SELECT data FROM words WHERE take_id=? AND kind=? ORDER BY ordinal',(take_id,kind))]
        return data

    def words_page(self,take_id,*,offset=0,limit=150,start=None,end=None,q='',kind='display'):
        if kind not in ('display','heard') or type(offset) is not int or offset<0:raise ValueError('Halaman kata tidak valid')
        limit=max(1,min(200,int(limit)));where='take_id=? AND kind=?';args=[take_id,kind]
        if start is not None:where+=' AND end>?';args.append(float(start))
        if end is not None:where+=' AND start<?';args.append(float(end))
        if q:where+=' AND instr(lower(text),lower(?))>0';args.append(q[:120])
        with self.connect() as db:
            total=db.execute('SELECT count(*) FROM words WHERE '+where,args).fetchone()[0]
            rows=db.execute('SELECT ordinal,data FROM words WHERE '+where+' ORDER BY ordinal LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
        return {'words':[{**json.loads(r['data']),'ordinal':r['ordinal']} for r in rows],
                'total':total,'offset':offset,'next_offset':offset+len(rows) if offset+len(rows)<total else None}

    def word(self,take_id,word_id):
        with self.connect() as db:row=db.execute('SELECT data FROM words WHERE take_id=? AND kind=? AND word_id=?',(take_id,'display',dumps(word_id))).fetchone()
        if row is None:raise ValueError('Kata tidak ditemukan pada transkrip aktif')
        return json.loads(row['data'])

    def heard_by_ids(self,take_id,word_ids):
        ids=list(dict.fromkeys(dumps(i) for i in word_ids));rows=[]
        with self.connect() as db:
            for start in range(0,len(ids),500):
                batch=ids[start:start+500]
                rows.extend(db.execute('SELECT ordinal,data FROM words WHERE take_id=? AND kind=? AND word_id IN ('+
                    ','.join('?' for _ in batch)+') ORDER BY ordinal',[take_id,'heard',*batch]).fetchall())
        return [json.loads(row['data']) for row in sorted(rows,key=lambda r:r['ordinal'])]

    def artifact(self,project_id,clip_id,variant_id,kind,key,data):
        ident='artifact-'+uuid.uuid4().hex
        with self.connect() as db:db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?)',(ident,project_id,clip_id,variant_id,kind,key,dumps(data),time.time()))
        return ident

    def artifacts(self,project_id,clip_id=None,variant_id=None,limit=30):
        where='project_id=?';args=[project_id]
        for key,value in [('clip_id',clip_id),('variant_id',variant_id)]:
            if value is not None:where+=' AND '+key+'=?';args.append(value)
        with self.connect() as db:rows=db.execute('SELECT * FROM artifacts WHERE '+where+' ORDER BY created DESC LIMIT ?',[*args,min(limit,100)]).fetchall()
        return [{**dict(r),'data':json.loads(r['data'])} for r in rows]

    def backup_database(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as source:
            target=sqlite3.connect(path)
            try:source.backup(target)
            finally:target.close()
        return path
