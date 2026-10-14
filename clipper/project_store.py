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


class JobLeaseLost(ValueError):pass


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
                CREATE TABLE IF NOT EXISTS history_actions(project_id TEXT,revision INTEGER,action TEXT,target_revision INTEGER,PRIMARY KEY(project_id,revision));
                CREATE TABLE IF NOT EXISTS history_metadata(project_id TEXT,revision INTEGER,actor TEXT,operation_id TEXT,command_schema INTEGER,PRIMARY KEY(project_id,revision));
                CREATE TABLE IF NOT EXISTS editor_drafts(id TEXT PRIMARY KEY,project_id TEXT,base_revision INTEGER,request TEXT,document TEXT,diff TEXT,reviews TEXT,created REAL);
                CREATE TABLE IF NOT EXISTS editor_sync_evidence(id TEXT PRIMARY KEY,project_id TEXT,data TEXT,created REAL);
                CREATE TABLE IF NOT EXISTS word_views(view_key TEXT PRIMARY KEY,project_id TEXT,take_id TEXT,scope TEXT,created REAL);
                CREATE TABLE IF NOT EXISTS word_view_rows(view_key TEXT,ordinal INTEGER,start REAL,end REAL,display_search TEXT,heard_search TEXT,data TEXT,PRIMARY KEY(view_key,ordinal));
                CREATE INDEX IF NOT EXISTS word_view_time ON word_view_rows(view_key,start,end);
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

    def create_import(self,document,import_id,lease,result):
        """Commit source project, derived take and import completion together.

        Cancellation and recovery observe either the entire result or none of
        it. A stable project identity also protects recovery after commit.
        """
        project_id=fingerprint(['source-import-project',import_id])[:12]
        value=copy.deepcopy(document);value.update(project_id=project_id,schema_version=4)
        if value['source']['source_id']!=result['content_id']:raise ValueError('Sumber berubah sebelum pembuatan proyek')
        if result.get('transcript_id'):raise ValueError('Assembly transcript tidak boleh merujuk proyek lain')
        value['source'].update(import_receipt=result['receipt'],import_id=import_id)
        if result.get('lineage'):value['source']['lineage']=copy.deepcopy(result['lineage'])
        transcript=result.get('transcript');take_id='assembly-'+fingerprint(import_id)[:32] if transcript else None
        if transcript:value.update(transcript_id=take_id,transcript_revision=1)
        published={k:v for k,v in result.items() if k!='transcript'};published['project_id']=project_id
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                item=db.execute('SELECT status,lease,result FROM m2_imports WHERE id=?',(import_id,)).fetchone()
                if item and item['status']=='completed':
                    prior=json.loads(item['result']);db.commit();return self.get(prior['project_id'])
                if not item or item['status']!='running' or item['lease']!=lease:raise JobLeaseLost('Impor dibatalkan atau worker berubah; proyek tidak dipublikasikan')
                now=time.time()
                db.execute('INSERT INTO projects VALUES(?,?,?,?,?)',(project_id,0,dumps(value),now,now))
                if transcript:
                    metadata,records=self._transcript_records(transcript,take_id)
                    db.execute('INSERT INTO transcripts VALUES(?,?,?,?)',(take_id,project_id,dumps(metadata),now))
                    db.executemany('INSERT INTO words VALUES(?,?,?,?,?,?,?,?)',records)
                if db.execute("UPDATE m2_imports SET status='completed',result=?,error=NULL,updated=? WHERE id=? AND status='running' AND lease=?",
                        (dumps(published),time.time(),import_id,lease)).rowcount!=1:raise JobLeaseLost('Impor tidak lagi aktif')
                db.commit()
            except BaseException:db.rollback();raise
        return self.get(project_id)

    def get(self,project_id):
        with self.connect() as db:row=db.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone()
        if row is None:raise KeyError('Proyek tidak ditemukan')
        return {**json.loads(row['document']),'revision':row['revision'],'updated':row['updated']}

    def list(self):
        with self.connect() as db:rows=db.execute('SELECT id,revision,document,updated FROM projects ORDER BY updated DESC').fetchall()
        return [{'project_id':r['id'],'revision':r['revision'],'updated':r['updated'],
                 'name':json.loads(r['document']).get('name','Proyek'),'clips':len(json.loads(r['document']).get('clips',{}))} for r in rows]

    def mutate(self,project_id,expected_revision,operation_id,request,change,label='Sunting proyek',*,job_guard=None,job_result=None,history_action=None,preview_only=False):
        if type(expected_revision) is not int or expected_revision<0:raise ValueError('Revisi proyek harus disertakan')
        if not isinstance(operation_id,str) or not 8<=len(operation_id)<=160:raise ValueError('ID operasi diperlukan')
        request_hash=fingerprint(request)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                prior=db.execute('SELECT request_hash,response FROM operations WHERE project_id=? AND operation_id=?',(project_id,operation_id)).fetchone()
                if prior and not preview_only:
                    if prior['request_hash']!=request_hash:raise ValueError('ID operasi dipakai untuk perubahan berbeda')
                    db.commit();return json.loads(prior['response'])
                row=db.execute('SELECT revision,document FROM projects WHERE id=?',(project_id,)).fetchone()
                if row is None:raise KeyError('Proyek tidak ditemukan')
                if expected_revision!=row['revision']:raise Conflict(row['revision'])
                if job_guard:
                    owned=db.execute('SELECT status,owner,lease_token,lease_expires FROM jobs WHERE id=?',(job_guard['id'],)).fetchone()
                    if (not owned or owned['status']!='running' or owned['owner']!=job_guard['owner']
                            or owned['lease_token']!=job_guard['lease_token']
                            or not owned['lease_expires'] or owned['lease_expires']<=time.time()):
                        raise JobLeaseLost('Proses dibatalkan atau lease berubah; hasil tidak dipublikasikan.')
                before=json.loads(row['document']);after=copy.deepcopy(before)
                extra=change(after) or {};patch=differences(before,after)
                if preview_only:
                    db.rollback()
                    return {**extra,'status':'preview','project_id':project_id,'revision':row['revision'],
                        'base_revision':row['revision'],'document':{**after,'revision':row['revision']},'changes':patch}
                revision=row['revision']+1
                db.execute('UPDATE projects SET revision=?,document=?,updated=? WHERE id=?',(revision,dumps(after),time.time(),project_id))
                db.execute('INSERT INTO history VALUES(?,?,?,?,?)',(project_id,revision,label,dumps(patch),time.time()))
                action=history_action or {'action':'job' if job_guard else 'edit'}
                db.execute('INSERT INTO history_actions VALUES(?,?,?,?)',(project_id,revision,action['action'],action.get('target_revision')))
                actor=request.get('actor','worker' if job_guard else 'pengguna_lokal') if isinstance(request,dict) else 'pengguna_lokal'
                if not isinstance(actor,str) or not 1<=len(actor)<=100:raise ValueError('Identitas operator tidak valid')
                db.execute('INSERT INTO history_metadata VALUES(?,?,?,?,?)',(project_id,revision,actor,operation_id,1))
                response={**extra,'status':'ready','project_id':project_id,'revision':revision,'operation_id':operation_id}
                db.execute('INSERT INTO operations VALUES(?,?,?,?)',(project_id,operation_id,request_hash,dumps(response)))
                if job_guard:
                    db.execute("UPDATE jobs SET status='completed',progress=100,result=?,message=?,updated=?,lease_expires=NULL WHERE id=?",
                        (dumps(job_result),'Selesai dan tersimpan pada revisi '+str(revision),time.time(),job_guard['id']))
                    if job_result and job_result.get('kind') in ('render','preview'):
                        db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?)',('artifact-'+uuid.uuid4().hex,project_id,
                            job_guard.get('clip_id'),job_guard.get('variant_id'),job_result['kind'],job_result['fingerprint'],dumps(job_result),time.time()))
                db.commit();return response
            except BaseException:db.rollback();raise

    def history(self,project_id,limit=50):
        with self.connect() as db:rows=db.execute('SELECT h.revision,h.label,h.changes,h.created,a.action,a.target_revision,m.actor,m.operation_id FROM history h LEFT JOIN history_actions a ON a.project_id=h.project_id AND a.revision=h.revision LEFT JOIN history_metadata m ON m.project_id=h.project_id AND m.revision=h.revision WHERE h.project_id=? ORDER BY h.revision DESC LIMIT ?',(project_id,min(100,max(1,limit)))).fetchall()
        result=[]
        for row in rows:
            value={**dict(row),'changes':json.loads(row['changes'])}
            value['can_undo']=bool(value['changes']) and value['action'] not in ('job','undo') and not value['label'].startswith('Selesai:')
            value['can_redo']=bool(value['changes']) and value['action']=='undo'
            result.append(value)
        return result

    def revision_document(self,project_id,revision):
        if type(revision) is not int or revision<0:raise ValueError('Revisi tidak valid')
        with self.connect() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT revision,document FROM projects WHERE id=?',(project_id,)).fetchone()
            if row is None:raise KeyError('Proyek tidak ditemukan')
            if revision>row['revision']:raise ValueError('Revisi belum tersedia')
            doc=json.loads(row['document'])
            records=db.execute('SELECT revision,changes FROM history WHERE project_id=? AND revision>? ORDER BY revision DESC',(project_id,revision)).fetchall()
            if len(records)!=row['revision']-revision:raise ValueError('Riwayat tidak lengkap; gunakan backup atau revisi yang tersedia')
            for record in records:
                for change in reversed(json.loads(record['changes'])):
                    put(doc,change['path'],change['before_exists'],change['before'])
            db.commit()
        return {**doc,'revision':revision}

    def create_editor_draft(self,project_id,base_revision,request,preview):
        ident='draft-'+fingerprint([project_id,base_revision,request,preview['document']])[:32]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT revision FROM projects WHERE id=?',(project_id,)).fetchone()
            if row is None:raise KeyError('Proyek tidak ditemukan')
            if row['revision']!=base_revision:raise Conflict(row['revision'])
            db.execute('INSERT OR IGNORE INTO editor_drafts VALUES(?,?,?,?,?,?,?,?)',(ident,project_id,base_revision,
                dumps(request),dumps(preview['document']),dumps(preview['changes']),dumps(preview.get('reviews',[])),time.time()))
            db.commit()
        return self.editor_draft(project_id,ident)

    def editor_draft(self,project_id,draft_id):
        with self.connect() as db:row=db.execute('SELECT * FROM editor_drafts WHERE id=? AND project_id=?',(draft_id,project_id)).fetchone()
        if row is None:raise KeyError('Snapshot draf tidak ditemukan')
        result=dict(row)
        for key in ('request','document','diff','reviews'):result[key]=json.loads(result[key])
        return result

    def editor_drafts(self,project_id,limit=50):
        with self.connect() as db:
            rows=db.execute('SELECT id,base_revision,created FROM editor_drafts WHERE project_id=? ORDER BY created DESC LIMIT ?',
                (project_id,min(100,max(1,limit)))).fetchall()
        return [dict(row) for row in rows]

    def publish_editor_draft(self,project_id,guard,result):
        """Publish only a draft artifact and job receipt; never replace active final pointers."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                job=db.execute('SELECT status,owner,lease_token,lease_expires FROM jobs WHERE id=?',(guard['id'],)).fetchone()
                if not job or job['status']!='running' or job['owner']!=guard['owner'] or job['lease_token']!=guard['lease_token'] or not job['lease_expires'] or job['lease_expires']<=time.time():
                    raise JobLeaseLost('Draf tidak diterbitkan karena pembatalan atau lease berubah')
                db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?)',('artifact-'+uuid.uuid4().hex,project_id,
                    guard.get('clip_id'),guard.get('variant_id'),'preview_draft',result['fingerprint'],dumps(result),time.time()))
                db.execute("UPDATE jobs SET status='completed',progress=100,result=?,message=?,updated=?,lease_expires=NULL WHERE id=?",
                    (dumps(result),'Preview snapshot draf selesai; final tersimpan tetap tersedia.',time.time(),guard['id']))
                db.commit()
            except BaseException:db.rollback();raise
        return result

    def undo(self,project_id,expected_revision,operation_id,revision):
        return self._reverse(project_id,expected_revision,operation_id,revision,'undo')

    def redo(self,project_id,expected_revision,operation_id,revision):
        return self._reverse(project_id,expected_revision,operation_id,revision,'redo')

    def _reverse(self,project_id,expected_revision,operation_id,revision,action):
        if type(revision) is not int or revision<1:raise ValueError('Revisi riwayat tidak valid')
        with self.connect() as db:row=db.execute('SELECT changes,label FROM history WHERE project_id=? AND revision=?',(project_id,revision)).fetchone()
        if not row:raise ValueError('Revisi tidak ditemukan')
        with self.connect() as db:mark=db.execute('SELECT action FROM history_actions WHERE project_id=? AND revision=?',(project_id,revision)).fetchone()
        kind=mark['action'] if mark else None
        if action=='redo' and kind!='undo':raise ValueError('Redo hanya tersedia untuk operasi undo tersimpan')
        if action=='undo' and (kind in ('job','undo') or row['label'].startswith('Selesai:')):raise ValueError('Pilih perubahan edit; hasil proses tidak di-undo melalui editor')
        patch=json.loads(row['changes'])
        if not patch:raise ValueError('Revisi ini tidak mempunyai perubahan untuk dipulihkan')
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
        return self.mutate(project_id,expected_revision,operation_id,{action+'_revision':revision},change,
            ('Undo: ' if action=='undo' else 'Redo: ')+row['label'],history_action={'action':action,'target_revision':revision})

    def effective_words_page(self,project_id,take_id,scope,view_key,factory,*,offset=0,limit=150,start=None,end=None,q='',search_mode='display'):
        """Search an immutable derived view; source/heard rows are never rewritten.

        Projection creation and pagination share one SQLite transaction. Old
        views remain usable by concurrent readers and are bounded per scope.
        """
        if type(offset) is not int or offset<0 or search_mode not in ('display','heard','both'):raise ValueError('Halaman atau mode pencarian tidak valid')
        limit=max(1,min(200,int(limit)));query=str(q).strip()[:120].casefold()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if not db.execute('SELECT 1 FROM word_views WHERE view_key=?',(view_key,)).fetchone():
                    records=[]
                    for ordinal,word in enumerate(factory()):
                        value={**word,'ordinal':ordinal}
                        records.append((view_key,ordinal,float(word['start']),float(word['end']),word['word'].casefold(),word.get('heard','').casefold(),dumps(value)))
                    db.execute('INSERT INTO word_views VALUES(?,?,?,?,?)',(view_key,project_id,take_id,scope,time.time()))
                    db.executemany('INSERT INTO word_view_rows VALUES(?,?,?,?,?,?,?)',records)
                    old=db.execute('SELECT view_key FROM word_views WHERE project_id=? AND scope=? ORDER BY created DESC LIMIT -1 OFFSET 4',(project_id,scope)).fetchall()
                    for item in old:
                        db.execute('DELETE FROM word_view_rows WHERE view_key=?',(item[0],));db.execute('DELETE FROM word_views WHERE view_key=?',(item[0],))
                where='view_key=?';args=[view_key]
                if start is not None:where+=' AND end>?';args.append(float(start))
                if end is not None:where+=' AND start<?';args.append(float(end))
                if ' ' in query:
                    from .editor_search import phrase_groups
                    rows=[json.loads(row[0]) for row in db.execute('SELECT data FROM word_view_rows WHERE '+where+' ORDER BY ordinal',args)]
                    matches={}
                    for field in (('word','heard') if search_mode=='both' else ('heard',) if search_mode=='heard' else ('word',)):
                        for group in phrase_groups(rows,query,field):
                            item=rows[group['first']]
                            matches[(group['first'],group['last'])]={**item,'match_phrase':group['before'],
                                'match_origin_word_ids':group['origin_word_ids'],'match_start':item['start'],'match_end':rows[group['last']]['end']}
                    ordered=[matches[key] for key in sorted(matches)];words=ordered[offset:offset+limit];total=len(ordered)
                    db.commit()
                    return {'words':words,'total':total,'offset':offset,'next_offset':offset+len(words) if offset+len(words)<total else None,
                        'view_key':view_key,'search_mode':search_mode}
                if query:
                    clauses=[]
                    for column in (('display_search','heard_search') if search_mode=='both' else ('heard_search',) if search_mode=='heard' else ('display_search',)):
                        clauses.append('instr('+column+',?)>0');args.append(query)
                    where+=' AND ('+' OR '.join(clauses)+')'
                total=db.execute('SELECT count(*) FROM word_view_rows WHERE '+where,args).fetchone()[0]
                found=db.execute('SELECT data FROM word_view_rows WHERE '+where+' ORDER BY ordinal LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
                db.commit()
            except BaseException:db.rollback();raise
        words=[json.loads(row[0]) for row in found]
        return {'words':words,'total':total,'offset':offset,'next_offset':offset+len(words) if offset+len(words)<total else None,'view_key':view_key,'search_mode':search_mode}

    @staticmethod
    def _transcript_records(transcript,take_id):
        metadata={k:v for k,v in transcript.items() if k not in ('words','raw_words')}
        records=[]
        for kind,words in [('display',transcript.get('words',[])),('heard',transcript.get('raw_words',transcript.get('words',[])))]:
            for i,w in enumerate(words):
                w={**w,'word_id':w.get('word_id',i)}
                if not 0<=float(w['start'])<float(w['end']):raise ValueError('Waktu kata tidak valid')
                records.append((take_id,kind,i,dumps(w['word_id']),w['start'],w['end'],w['word'],dumps(w)))
        return metadata,records

    def save_transcript(self,project_id,transcript,take_id=None):
        """Insert once; later word edits live in sparse project corrections."""
        take_id=take_id or 'asr-'+uuid.uuid4().hex
        metadata,records=self._transcript_records(transcript,take_id)
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
