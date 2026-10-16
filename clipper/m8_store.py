"""Additive M8 schema; Studio revisions and M8 reservations share one SQLite DB."""
import json
import time
import uuid
from contextlib import contextmanager
from .m8_contract import canonical, clean

SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS m8_schema(version INTEGER PRIMARY KEY,created REAL);
CREATE TABLE IF NOT EXISTS m8_workspaces(id TEXT PRIMARY KEY,name TEXT,version INTEGER,settings TEXT);
CREATE TABLE IF NOT EXISTS m8_members(workspace TEXT,user_id TEXT,role TEXT,PRIMARY KEY(workspace,user_id));
CREATE TABLE IF NOT EXISTS m8_projects(project_id TEXT PRIMARY KEY,workspace TEXT,collection TEXT DEFAULT '',archived INTEGER DEFAULT 0,version INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS m8_sessions(id TEXT PRIMARY KEY,token_hash TEXT UNIQUE,workspace TEXT,user_id TEXT,expires REAL,revoked INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS m8_commands(workspace TEXT,command_id TEXT,request_hash TEXT,status TEXT,response TEXT,created REAL,updated REAL,PRIMARY KEY(workspace,command_id));
CREATE TABLE IF NOT EXISTS m8_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,workspace TEXT,type TEXT,project_id TEXT,revision INTEGER,data TEXT,created REAL);
CREATE INDEX IF NOT EXISTS m8_event_workspace ON m8_events(workspace,seq);
CREATE TABLE IF NOT EXISTS m8_accounts(id TEXT PRIMARY KEY,workspace TEXT,platform TEXT,name TEXT,version INTEGER,data TEXT,secret_ref TEXT,enabled INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS m8_publish(id TEXT PRIMARY KEY,workspace TEXT,project_id TEXT,version INTEGER,status TEXT,account_id TEXT,artifact_key TEXT,request TEXT,approval TEXT,cursor TEXT,remote TEXT,due REAL,next_run REAL,lease_owner TEXT,lease_expires REAL,created REAL,updated REAL);
CREATE INDEX IF NOT EXISTS m8_publish_due ON m8_publish(status,next_run,due);
CREATE TABLE IF NOT EXISTS m8_ledger(id TEXT PRIMARY KEY,workspace TEXT,day TEXT,kind TEXT,units REAL,state TEXT,reference TEXT,created REAL,UNIQUE(workspace,kind,reference));
CREATE TABLE IF NOT EXISTS m8_metrics(id TEXT PRIMARY KEY,workspace TEXT,publish_id TEXT,metric TEXT,value REAL,reason TEXT,start_date TEXT,end_date TEXT,source TEXT,retrieved REAL,data TEXT);
CREATE TABLE IF NOT EXISTS m8_records(id TEXT PRIMARY KEY,workspace TEXT,kind TEXT,version INTEGER,data TEXT,created REAL,updated REAL);
CREATE INDEX IF NOT EXISTS m8_records_kind ON m8_records(workspace,kind);
CREATE TABLE IF NOT EXISTS m8_subscriptions(id TEXT PRIMARY KEY,workspace TEXT,data TEXT,secret_ref TEXT,enabled INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS m8_webhook_deliveries(subscription TEXT,event_seq INTEGER,status TEXT,attempts INTEGER DEFAULT 0,next_run REAL,PRIMARY KEY(subscription,event_seq));
CREATE TABLE IF NOT EXISTS m8_worker(name TEXT PRIMARY KEY,owner TEXT,expires REAL,heartbeat REAL);
'''


def ident(prefix):
    return prefix + '-' + uuid.uuid4().hex


class M8Store:
    def __init__(self, studio_store, clock=time.time):
        self.studio = studio_store
        self.clock = clock
        with self.studio.connect() as db:
            db.executescript(SCHEMA_SQL)
            db.execute('INSERT OR IGNORE INTO m8_schema VALUES(1,?)', (clock(),))
            db.execute('INSERT OR IGNORE INTO m8_workspaces VALUES(?,?,0,?)',
                       ('solo', 'Lokal pribadi', canonical({'timezone': 'Asia/Jakarta', 'daily_publish': 10,
                        'daily_jobs': 50, 'daily_provider_usd': 0, 'minimum_free_bytes': 1024**3})))
            db.execute("INSERT OR IGNORE INTO m8_members VALUES('solo','local','owner')")

    @contextmanager
    def transaction(self):
        with self.studio.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def event(self, db, workspace, kind, project_id=None, revision=None, data=None):
        row = db.execute('INSERT INTO m8_events(workspace,type,project_id,revision,data,created) VALUES(?,?,?,?,?,?)',
                         (workspace, kind, project_id, revision, canonical(clean(data or {})), self.clock()))
        return row.lastrowid

    def events(self, workspace, after=0, limit=100):
        with self.studio.connect() as db:
            rows = db.execute('SELECT * FROM m8_events WHERE workspace=? AND seq>? ORDER BY seq LIMIT ?',
                              (workspace, after, min(200, max(1, limit)))).fetchall()
        return [{**dict(r), 'data': json.loads(r['data'])} for r in rows]

    def record(self, workspace, kind, data, record_id=None, version=None):
        key = record_id or ident(kind)
        with self.transaction() as db:
            old = db.execute('SELECT * FROM m8_records WHERE id=? AND workspace=? AND kind=?', (key, workspace, kind)).fetchone()
            if record_id and not old:
                raise KeyError('Catatan tidak ditemukan')
            if old and version != old['version']:
                from .project_store import Conflict
                raise Conflict(old['version'], 'Catatan berubah; muat ulang sebelum menyimpan')
            next_version = old['version'] + 1 if old else 0
            now = self.clock()
            db.execute('INSERT INTO m8_records VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,data=excluded.data,updated=excluded.updated',
                       (key, workspace, kind, next_version, canonical(data), old['created'] if old else now, now))
            self.event(db, workspace, kind + '.saved', data={'id': key, 'version': next_version})
        return {'id': key, 'version': next_version, 'data': data}

    def records(self, workspace, kind, limit=200):
        with self.studio.connect() as db:
            rows = db.execute('SELECT id,version,data,created,updated FROM m8_records WHERE workspace=? AND kind=? ORDER BY created DESC LIMIT ?', (workspace, kind, limit)).fetchall()
        return [{**dict(r), 'data': json.loads(r['data'])} for r in rows]
