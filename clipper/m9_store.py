"""Additive M9 records and durable chunk receipts; all scoped to M8 workspace."""
import copy
import json
import time
from .m8_contract import AccessDenied, canonical, text
from .m8_store import ident
from .project_store import Conflict

SQL = '''
CREATE TABLE IF NOT EXISTS m9_items(id TEXT PRIMARY KEY,workspace TEXT,kind TEXT,version INTEGER,data TEXT,created REAL,updated REAL);
CREATE INDEX IF NOT EXISTS m9_items_workspace ON m9_items(workspace,kind);
CREATE TABLE IF NOT EXISTS m9_tracks(id TEXT PRIMARY KEY,session_id TEXT,participant TEXT,kind TEXT,mime TEXT,version INTEGER,data TEXT);
CREATE TABLE IF NOT EXISTS m9_chunks(track_id TEXT,seq INTEGER,sha256 TEXT,bytes INTEGER,data TEXT,PRIMARY KEY(track_id,seq));
CREATE TABLE IF NOT EXISTS m9_invites(id TEXT PRIMARY KEY,session_id TEXT,participant TEXT,token_hash TEXT UNIQUE,expires REAL,revoked INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS m9_resource_holds(job_id TEXT PRIMARY KEY,workspace TEXT,provider_id TEXT,state TEXT,prompt_id TEXT,created REAL);
'''


class Store:
    def __init__(self, lab):
        self.lab = lab;self.service = lab.service;self.m8 = lab.m8
        with self.service.store.connect() as db:db.executescript(SQL)

    def create(self, actor, kind, data, key=None):
        self.m8.workspaces.require(actor, 'edit')
        key = key or ident('m9'+kind)
        with self.m8.db.transaction() as db:
            if data.get('project_id'):
                self.m8.workspaces.require(actor,'edit',data['project_id'],db)
                if kind=='creative' and data.get('source'):
                    from .source_guard import verify
                    source=db.execute('SELECT revision,document FROM projects WHERE id=?',(data['project_id'],)).fetchone()
                    verify(self.service,data['source'],json.loads(source['document']),source['revision'])
            now = self.m8.db.clock()
            db.execute('INSERT INTO m9_items VALUES(?,?,?,0,?,?,?)', (key, actor.workspace, kind, canonical(data), now, now))
            self.m8.db.event(db, actor.workspace, 'm9.'+kind+'.created', data={'id': key})
        return self.get(actor, key)

    def get(self, actor, key, permission='read', db=None):
        key=text(key,'ID item M9',100)
        self.m8.workspaces.require(actor, permission, db=db)
        if db is None:
            with self.service.store.connect() as connection:return self.get(actor, key, permission, connection)
        row = db.execute('SELECT * FROM m9_items WHERE id=? AND workspace=?', (key, actor.workspace)).fetchone()
        if not row:raise KeyError('Item M9 tidak ditemukan dalam workspace')
        result = dict(row);result['data'] = json.loads(result['data'])
        if permission!='read' and result['data'].get('restored_evidence_only'):
            raise ValueError('Item dipulihkan sebagai bukti; buat tugas baru untuk mengaktifkan hasil')
        pid = result['data'].get('project_id')
        if pid:self.m8.workspaces.require(actor, permission, pid, db)
        return result

    def listing(self, actor, kind=None):
        self.m8.workspaces.require(actor)
        with self.service.store.connect() as db:
            rows = db.execute("SELECT i.id FROM m9_items i WHERE i.workspace=? AND (json_extract(i.data,'$.project_id') IS NULL OR EXISTS(SELECT 1 FROM m8_projects p WHERE p.project_id=json_extract(i.data,'$.project_id') AND p.workspace=i.workspace)) "+('AND i.kind=? ' if kind else '')+'ORDER BY i.created DESC LIMIT 300',
                              (actor.workspace, kind) if kind else (actor.workspace,)).fetchall()
        return [self.get(actor, row['id']) for row in rows]

    def change(self, actor, key, expected, change, permission='edit'):
        with self.m8.db.transaction() as db:
            row = self.get(actor, key, permission, db)
            if type(expected) is not int or row['version'] != expected:raise Conflict(row['version'])
            data = copy.deepcopy(row['data']);change(data, db)
            db.execute('UPDATE m9_items SET version=version+1,data=?,updated=? WHERE id=?', (canonical(data), self.m8.db.clock(), key))
            self.m8.db.event(db, actor.workspace, 'm9.'+row['kind']+'.changed', data={'id': key, 'version': expected+1})
        return self.get(actor, key)
