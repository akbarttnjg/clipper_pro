"""Explicit workspace membership and expiring, revocable bearer sessions."""
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from .m8_contract import AccessDenied, ROLES, canonical, integer, number, only, text, zone
from .m8_store import ident
from .project_store import Conflict


@dataclass(frozen=True)
class Actor:
    workspace: str = 'solo'
    user_id: str = 'local'
    session_id: str | None = None
    local: bool = False


class Workspaces:
    def __init__(self, m8):
        self.m8 = m8
        self.db = m8.db
        self.service = m8.service

    def require(self, actor, permission='read', project_id=None, db=None):
        if db is None:
            with self.service.store.connect() as connection:
                return self.require(actor, permission, project_id, connection)
        row = db.execute('SELECT role FROM m8_members WHERE workspace=? AND user_id=?',
                         (actor.workspace, actor.user_id)).fetchone()
        if not row or permission not in ROLES.get(row['role'], set()):
            raise AccessDenied('Role tidak memiliki izin ' + permission)
        if actor.session_id:
            live = db.execute('SELECT * FROM m8_sessions WHERE id=?', (actor.session_id,)).fetchone()
            if not live or live['revoked'] or live['expires'] <= self.db.clock() or live['workspace'] != actor.workspace or live['user_id'] != actor.user_id:
                raise AccessDenied('Sesi berakhir atau dicabut')
        if project_id:
            if actor.local and actor.workspace == 'solo':
                db.execute("INSERT OR IGNORE INTO m8_projects(project_id,workspace) SELECT id,'solo' FROM projects WHERE id=?", (project_id,))
            scope = db.execute('SELECT workspace FROM m8_projects WHERE project_id=?', (project_id,)).fetchone()
            if not scope or scope['workspace'] != actor.workspace:
                raise AccessDenied('Proyek berada di luar workspace')
        return row['role']

    def authenticate(self, token):
        if not isinstance(token, str) or not 40 <= len(token) <= 120:
            raise AccessDenied('Sesi diperlukan')
        hashed = hashlib.sha256(token.encode()).hexdigest()
        with self.service.store.connect() as db:
            row = db.execute('SELECT * FROM m8_sessions WHERE token_hash=? AND revoked=0 AND expires>?', (hashed, self.db.clock())).fetchone()
        if not row:
            raise AccessDenied('Sesi berakhir atau dicabut')
        actor = Actor(row['workspace'], row['user_id'], row['id'])
        self.require(actor)
        return actor

    def issue_session(self, actor, data):
        self.require(actor, 'manage')
        only(data, ('user_id', 'role', 'hours'), ('user_id', 'role'))
        user = text(data['user_id'], 'Identitas anggota', 100)
        role = data['role']
        hours = integer(data.get('hours', 24), 'Masa sesi (jam)', 1, 168)
        if role not in ROLES:
            raise ValueError('Role tidak dikenal')
        key, token = ident('session'), secrets.token_urlsafe(32)
        expires = self.db.clock() + hours * 3600
        with self.db.transaction() as db:
            existing = db.execute('SELECT role FROM m8_members WHERE workspace=? AND user_id=?', (actor.workspace, user)).fetchone()
            if existing and existing['role'] != role:
                raise ValueError('Anggota sudah ada dengan role lain; ubah role secara eksplisit dahulu')
            db.execute('INSERT OR IGNORE INTO m8_members VALUES(?,?,?)', (actor.workspace, user, role))
            db.execute('INSERT INTO m8_sessions VALUES(?,?,?,?,?,0)', (key, hashlib.sha256(token.encode()).hexdigest(), actor.workspace, user, expires))
            self.db.event(db, actor.workspace, 'session.created', data={'id': key, 'user_id': user, 'role': role})
        return {'id': key, 'token': token, 'workspace': actor.workspace, 'user_id': user, 'role': role, 'expires': expires}

    def revoke_session(self, actor, session_id):
        self.require(actor, 'manage')
        with self.db.transaction() as db:
            if db.execute('UPDATE m8_sessions SET revoked=1 WHERE id=? AND workspace=?', (session_id, actor.workspace)).rowcount != 1:
                raise KeyError('Sesi tidak ditemukan')
            self.db.event(db, actor.workspace, 'session.revoked', data={'id': session_id})
        return {'id': session_id, 'revoked': True}

    def member(self, actor, data):
        self.require(actor, 'manage')
        only(data, ('user_id', 'role'), ('user_id', 'role'))
        user, role = text(data['user_id'], 'Anggota', 100), data['role']
        if role not in ROLES:
            raise ValueError('Role tidak dikenal')
        with self.db.transaction() as db:
            prior = db.execute('SELECT role FROM m8_members WHERE workspace=? AND user_id=?', (actor.workspace, user)).fetchone()
            owners = db.execute("SELECT COUNT(*) FROM m8_members WHERE workspace=? AND role='owner'", (actor.workspace,)).fetchone()[0]
            if prior and prior['role'] == 'owner' and role != 'owner' and owners <= 1:
                raise ValueError('Workspace memerlukan setidaknya satu owner')
            db.execute('INSERT INTO m8_members VALUES(?,?,?) ON CONFLICT(workspace,user_id) DO UPDATE SET role=excluded.role', (actor.workspace, user, role))
            self.db.event(db, actor.workspace, 'member.changed', data={'user_id': user, 'role': role})
        return {'user_id': user, 'role': role}

    def create(self, actor, data):
        self.require(actor, 'manage')
        only(data, ('name',), ('name',))
        key = ident('workspace')
        settings = self.settings(actor)
        with self.db.transaction() as db:
            db.execute('INSERT INTO m8_workspaces VALUES(?,?,0,?)', (key, text(data['name'], 'Nama workspace', 100), canonical(settings)))
            db.execute('INSERT INTO m8_members VALUES(?,?,?)', (key, actor.user_id, 'owner'))
            self.db.event(db, key, 'workspace.created', data={'id': key})
        return {'id': key, 'name': data['name'], 'version': 0}

    def settings(self, actor):
        self.require(actor)
        with self.service.store.connect() as db:
            row = db.execute('SELECT settings FROM m8_workspaces WHERE id=?', (actor.workspace,)).fetchone()
        return json.loads(row['settings'])

    def configure(self, actor, data):
        self.require(actor, 'manage')
        only(data, ('expected_version', 'timezone', 'daily_publish', 'daily_jobs', 'daily_provider_usd', 'minimum_free_bytes'), ('expected_version',))
        changes = dict(data)
        expected = integer(changes.pop('expected_version'), 'Versi workspace')
        if 'timezone' in changes:
            zone(changes['timezone'])
        for field in ('daily_publish', 'daily_jobs'):
            if field in changes:
                integer(changes[field], field, 0, 10000)
        if 'daily_provider_usd' in changes:
            number(changes['daily_provider_usd'], 'Budget provider', 0, 10000)
        if 'minimum_free_bytes' in changes:
            integer(changes['minimum_free_bytes'], 'Ruang kosong minimum', 0, 10**13)
        with self.db.transaction() as db:
            row = db.execute('SELECT * FROM m8_workspaces WHERE id=?', (actor.workspace,)).fetchone()
            if row['version'] != expected:
                raise Conflict(row['version'])
            updated = {**json.loads(row['settings']), **changes}
            db.execute('UPDATE m8_workspaces SET version=version+1,settings=? WHERE id=?', (canonical(updated), actor.workspace))
            self.db.event(db, actor.workspace, 'workspace.configured', data=changes)
        return {'version': expected + 1, 'settings': updated}

    def projects(self, actor):
        self.require(actor)
        with self.db.transaction() as db:
            if actor.local and actor.workspace == 'solo':
                db.execute("INSERT OR IGNORE INTO m8_projects(project_id,workspace) SELECT id,'solo' FROM projects")
            scope = {r['project_id']: dict(r) for r in db.execute('SELECT * FROM m8_projects WHERE workspace=?', (actor.workspace,))}
        return [{**r, **{k: scope[r['project_id']][k] for k in ('collection', 'archived', 'version')}}
                for r in self.service.store.list() if r['project_id'] in scope]

    def organize(self, actor, data):
        only(data, ('project_id', 'expected_version', 'collection', 'archived', 'destination_workspace'), ('project_id', 'expected_version'))
        pid = data['project_id']
        self.require(actor, 'edit', pid)
        collection = text(data.get('collection', ''), 'Koleksi', 100, 0)
        archived = data.get('archived', False)
        if type(archived) is not bool:
            raise ValueError('Arsip harus boolean')
        destination = data.get('destination_workspace', actor.workspace)
        if destination != actor.workspace:
            self.require(actor, 'manage', pid)
            self.require(Actor(destination, actor.user_id, local=actor.local), 'manage')
        with self.db.transaction() as db:
            self.require(actor, 'edit', pid, db)
            row = db.execute('SELECT * FROM m8_projects WHERE project_id=?', (pid,)).fetchone()
            if data['expected_version'] != row['version']:
                raise Conflict(row['version'])
            active = db.execute("SELECT 1 FROM m8_publish WHERE project_id=? LIMIT 1", (pid,)).fetchone()
            if destination != actor.workspace and active:
                raise ValueError('Proyek mempunyai riwayat publikasi. Transfer lintas workspace memerlukan migrasi akun dan riwayat yang belum tersedia; gunakan backup sebagai salinan.')
            if destination != actor.workspace:
                # Moving only the binding would strand project-bound M9 records.
                has_m9=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m9_items'").fetchone()
                scopes={r['workspace'] for r in db.execute("SELECT DISTINCT workspace FROM m9_items WHERE json_extract(data,'$.project_id')=?",(pid,))} if has_m9 else set()
                # A legacy orphan may be recovered by returning its project to
                # the one workspace that already owns all attached M9 records.
                if scopes and scopes!={destination}:
                    raise ValueError('Proyek mempunyai data M9; transfer lintas workspace belum mendukung migrasi dependensi. Gunakan backup sebagai salinan.')
                if db.execute("SELECT 1 FROM jobs WHERE kind LIKE '%_m9' AND status IN ('queued','running','cancel_requested') AND json_extract(request,'$.m9.project_id')=? LIMIT 1",(pid,)).fetchone():
                    raise ValueError('Selesaikan atau batalkan tugas M9 sebelum transfer workspace')
            db.execute('UPDATE m8_projects SET workspace=?,collection=?,archived=?,version=version+1 WHERE project_id=?', (destination, collection, int(archived), pid))
            self.db.event(db, actor.workspace, 'project.organized', pid, data={'collection': collection, 'archived': archived, 'destination': destination})
        return {'project_id': pid, 'workspace': destination, 'version': row['version']+1}

    def reserve(self, db, actor, kind, reference, units=1):
        self.require(actor, 'publish' if kind == 'publish' else 'edit', db=db)
        row = db.execute('SELECT settings FROM m8_workspaces WHERE id=?', (actor.workspace,)).fetchone()
        cfg = json.loads(row['settings'])
        day = datetime.fromtimestamp(self.db.clock(), zone(cfg['timezone'])).date().isoformat()
        field = {'publish': 'daily_publish', 'job': 'daily_jobs', 'provider_usd': 'daily_provider_usd'}[kind]
        prior = db.execute('SELECT id,state FROM m8_ledger WHERE workspace=? AND kind=? AND reference=?', (actor.workspace, kind, reference)).fetchone()
        if prior and prior['state'] != 'released':
            return prior['id']
        used = db.execute("SELECT COALESCE(SUM(units),0) FROM m8_ledger WHERE workspace=? AND day=? AND kind=? AND state!='released'", (actor.workspace, day, kind)).fetchone()[0]
        if used + units > cfg[field]:
            raise ValueError('Kuota/budget harian habis: ' + kind)
        key = prior['id'] if prior else ident('usage')
        db.execute('INSERT INTO m8_ledger VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET day=excluded.day,units=excluded.units,state=excluded.state,created=excluded.created', (key, actor.workspace, day, kind, units, 'reserved', reference, self.db.clock()))
        return key

    def summary(self, actor):
        role = self.require(actor)
        with self.service.store.connect() as db:
            workspace = dict(db.execute('SELECT * FROM m8_workspaces WHERE id=?', (actor.workspace,)).fetchone())
            members = [dict(r) for r in db.execute('SELECT user_id,role FROM m8_members WHERE workspace=?', (actor.workspace,))]
            sessions = [dict(r) for r in db.execute('SELECT id,user_id,expires,revoked FROM m8_sessions WHERE workspace=?', (actor.workspace,))] if role == 'owner' else []
            ledger = [dict(r) for r in db.execute('SELECT day,kind,state,SUM(units) AS units FROM m8_ledger WHERE workspace=? GROUP BY day,kind,state ORDER BY day DESC LIMIT 100', (actor.workspace,))]
        workspace['settings'] = json.loads(workspace['settings'])
        return {'workspace': workspace, 'role': role, 'members': members, 'sessions': sessions,
                'projects': self.projects(actor), 'ledger': ledger, 'sso': {'status': 'not_configured', 'local_login_required': False}}
