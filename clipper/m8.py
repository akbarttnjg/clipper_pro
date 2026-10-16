"""M8 application facade shared by HTTP, CLI, Python, MCP and automation."""
import copy
import json
import os
import shutil
import threading
import time
from pathlib import Path, PureWindowsPath
from .m8_contract import AccessDenied, Busy, SCHEMA, VERSION, canonical, digest, integer, only, text
from .m8_store import M8Store, ident
from .m8_workspace import Actor, Workspaces
from .m8_vault import Vault
from .m8_youtube import Transport, YouTube
from .m8_accounts import Accounts
from .m8_publish import Publishing
from .m8_analytics import Analytics
from .m8_worker import Worker
from .project_store import Conflict
from .dependency_cache import content_id

READ = {'status', 'project.list', 'project.get', 'job.list', 'publish.list', 'publish.get', 'publish.preflight',
        'account.list', 'workspace.get', 'analytics.get', 'events', 'record.list', 'capabilities', 'plugin.list'}
PERMISSIONS = {
    'project.create': 'edit', 'project.propose': 'edit', 'project.apply': 'edit', 'job.submit': 'edit', 'job.cancel': 'edit', 'job.resume': 'edit',
    'account.save': 'manage', 'account.probe': 'manage', 'account.disconnect': 'manage',
    'publish.draft': 'publish', 'publish.approve': 'approve', 'publish.revise': 'publish', 'publish.cancel': 'publish', 'publish.retry': 'publish',
    'publish.remote_edit': 'approve', 'publish.manual_receipt': 'publish', 'workspace.create': 'manage', 'workspace.configure': 'manage',
    'workspace.member': 'manage', 'workspace.organize': 'edit', 'session.revoke': 'manage', 'analytics.observe': 'review', 'analytics.refresh': 'review',
    'analytics.export': 'read', 'comment.save': 'review', 'effort.record': 'edit', 'cost.record': 'edit', 'experiment.create': 'review', 'experiment.assign': 'publish',
    'topic.import': 'review', 'workflow.save': 'manage', 'workflow.run': 'edit', 'workflow.resume': 'edit', 'webhook.save': 'manage', 'webhook.list': 'manage',
    'backup.create': 'manage', 'backup.restore': 'manage', 'diagnostics.create': 'read', 'plugin.register': 'manage', 'feedback.policy': 'manage', 'feedback.rollback': 'manage',
    'review.revoke':'review','review.list':'read',
}
from .m9 import READ as M9_READ, PERMISSIONS as M9_PERMISSIONS
READ |= M9_READ
PERMISSIONS.update(M9_PERMISSIONS)


class M8:
    def __init__(self, service, *, clock=time.time, transport=None, server_mode=None):
        self.service = service
        self.db = M8Store(service.store, clock)
        self.server_mode = os.environ.get('CLIPPER_M8_SERVER_MODE') == '1' if server_mode is None else server_mode
        self.vault = Vault(service.work)
        self.transport = transport or Transport()
        self.workspaces = Workspaces(self)
        self.accounts = Accounts(self)
        self.youtube = YouTube(self)
        self.publishing = Publishing(self)
        self.analytics = Analytics(self)
        self.worker = Worker(self)
        from .m8_webhooks import Webhooks
        from .m8_automation import Automation
        from .m8_backup import Backups
        from .m8_plugins import Plugins
        self.webhooks = Webhooks(self)
        self.automation = Automation(self)
        self.backups = Backups(self)
        self.plugins = Plugins(self)

    def local_actor(self, workspace='solo'):
        return Actor(workspace, 'local', local=True)

    def worker_status(self):
        with self.service.store.connect() as db:
            row = db.execute("SELECT heartbeat,expires FROM m8_worker WHERE name='publisher'").fetchone()
        now = self.db.clock()
        return {'online': bool(row and now-row['heartbeat'] < 15), 'last_seen': row['heartbeat'] if row else None,
                'host_must_remain_awake': True, 'remote_host_configured': False}

    def status(self, actor):
        self.workspaces.require(actor)
        return {'version': VERSION, 'schema_version': SCHEMA, 'mode': 'server_api' if self.server_mode else 'solo_local',
            'workspace': actor.workspace, 'role': self.workspaces.require(actor), 'worker': self.worker_status(),
            'vault': self.vault.ready(), 'network_accounts_connected': sum(r['connection'] == 'oauth' for r in self.accounts.listing(actor)),
            'requires_paid_api': False, 'live_platform_acceptance': 'not_tested', 'sso': 'not_configured'}

    def capabilities(self, actor):
        self.workspaces.require(actor)
        path = Path(__file__).resolve().parents[1]/'docs/M8_REQUIREMENTS.json'
        if path.is_file():
            return json.loads(path.read_text(encoding='utf-8'))
        return {'schema_version': SCHEMA, 'version': VERSION, 'status': 'implementation_in_progress'}

    def register_file(self, actor, path, project_id=None):
        self.workspaces.require(actor, 'read', project_id)
        path = Path(path).resolve()
        if not path.is_file() or not path.is_relative_to(self.service.work):
            raise ValueError('Berkas M8 harus berada dalam folder kerja')
        value = self.db.record(actor.workspace, 'm8file', {'path': str(path), 'content_id': content_id(path, fresh=True), 'project_id': project_id})
        return '/api/studio/m8/v1/files/'+value['id']

    def file(self, actor, key):
        self.workspaces.require(actor)
        if key.startswith('file-'):
            # M7 and handoff members use the existing registry and inherit project access.
            with self.service.store.connect() as db:
                row = db.execute('SELECT project_id,path FROM files WHERE id=?', (key,)).fetchone()
            if not row:
                raise KeyError('Berkas tidak ditemukan')
            self.workspaces.require(actor, 'read', row['project_id'])
            return self.service.file(key)
        row = next((r for r in self.db.records(actor.workspace, 'm8file', 1000) if r['id'] == key), None)
        if not row:
            raise KeyError('Berkas tidak ditemukan')
        self.workspaces.require(actor, 'read', row['data'].get('project_id'))
        path = Path(row['data']['path'])
        if path.is_symlink() or not path.resolve().is_relative_to(self.service.work) or content_id(path, fresh=True) != row['data']['content_id']:
            raise ValueError('Berkas berubah')
        return path

    def command(self, actor, request):
        only(request, ('schema_version', 'command_id', 'action', 'args'), ('schema_version', 'action', 'args'))
        if type(request['schema_version']) is not int or request['schema_version'] != SCHEMA:
            raise ValueError('Versi schema M8 belum didukung')
        action = text(request['action'], 'Aksi', 100)
        args = request['args']
        if not isinstance(args, dict):
            raise ValueError('Args harus berupa object')
        self.workspaces.require(actor)
        if action in READ:
            return self.dispatch(actor, action, args, None)
        if action not in PERMISSIONS:
            raise ValueError('Aksi M8 tidak dikenal: '+action)
        # Membership is rechecked even for a cached receipt after a role change.
        self.workspaces.require(actor, PERMISSIONS[action], args.get('project_id'))
        command_id = text(request.get('command_id'), 'ID perintah idempotent', 160, 8)
        hashed = digest([actor.user_id, action, args, SCHEMA])
        with self.db.transaction() as db:
            old = db.execute('SELECT * FROM m8_commands WHERE workspace=? AND command_id=?', (actor.workspace, command_id)).fetchone()
            if old:
                if old['request_hash'] != hashed:
                    raise ValueError('ID perintah dipakai untuk isi/aktor yang berbeda')
                if old['status'] == 'completed':
                    return json.loads(old['response'])
                raise Busy('Perintah sedang berjalan atau hasilnya belum direkonsiliasi. Periksa event/antrean sebelum mengulang; tidak dibuat tindakan ganda.')
            now = self.db.clock()
            db.execute('INSERT INTO m8_commands VALUES(?,?,?,?,?,?,?)', (actor.workspace, command_id, hashed, 'running', None, now, now))
        try:
            result = self.dispatch(actor, action, args, command_id)
        except (ValueError, KeyError, OSError, TypeError) as exc:
            # No request body or exception payload is retained. Failures after a side
            # effect remain fenced; use a new explicit command only after inspection.
            with self.db.transaction() as db:
                db.execute("UPDATE m8_commands SET status='needs_reconcile',updated=? WHERE workspace=? AND command_id=?", (self.db.clock(), actor.workspace, command_id))
                self.db.event(db, actor.workspace, 'command.blocked', args.get('project_id'), data={'command_id': command_id, 'action': action})
            raise
        with self.db.transaction() as db:
            db.execute("UPDATE m8_commands SET status='completed',response=?,updated=? WHERE workspace=? AND command_id=?", (canonical(result), self.db.clock(), actor.workspace, command_id))
            self.db.event(db, actor.workspace, 'command.completed', args.get('project_id'), data={'command_id': command_id, 'action': action})
        return result

    def dispatch(self, actor, action, args, command_id):
        if action.startswith('m9.'):
            return self.service.lab.dispatch(actor, action, args, command_id)
        pid = args.get('project_id')
        if action == 'status':
            only(args, ());return self.status(actor)
        if action == 'capabilities':
            only(args, ());return self.capabilities(actor)
        if action == 'project.list':
            only(args, ());return {'projects': self.workspaces.projects(actor)}
        if action == 'project.get':
            only(args, ('project_id',), ('project_id',));self.workspaces.require(actor, 'read', pid)
            return self.service.public(pid)
        if action == 'project.create':
            only(args, ('path', 'settings', 'name'), ('path',));self.workspaces.require(actor, 'edit')
            if not actor.local:
                raise AccessDenied('Impor path host hanya tersedia dari operator lokal; server tidak menerima path filesystem bebas')
            doc = self.service.create(args['path'], args.get('settings'), args.get('name'))
            with self.db.transaction() as db:
                db.execute('INSERT INTO m8_projects(project_id,workspace) VALUES(?,?)', (doc['project_id'], actor.workspace))
            return {'project_id': doc['project_id'], 'revision': doc['revision']}
        if action == 'project.propose':
            only(args, ('project_id', 'expected_revision', 'clip_id', 'variant_id', 'operations'), ('project_id', 'expected_revision', 'operations'))
            self.workspaces.require(actor, 'edit', pid)
            self.scoped_inputs(actor, pid, args['operations'])
            from .editor_service import make_draft
            return make_draft(self.service, {**args, 'actor': actor.user_id, 'operation_id': command_id})
        if action == 'project.apply':
            only(args, ('project_id', 'expected_revision', 'draft_id', 'rebase'), ('project_id', 'expected_revision', 'draft_id'))
            self.workspaces.require(actor, 'edit', pid)
            draft=self.service.store.editor_draft(pid,args['draft_id'])
            self.scoped_inputs(actor,pid,draft['request'].get('operations',[]))
            from .editor_service import commit_draft
            return commit_draft(self.service, pid, args['draft_id'], args['expected_revision'], command_id, rebase=args.get('rebase', False))
        if action == 'job.list':
            only(args, ('project_id',), ('project_id',));self.workspaces.require(actor, 'read', pid)
            return {'jobs': self.service.queue.list(pid)}
        if action == 'job.submit':
            only(args, ('project_id', 'expected_revision', 'kind', 'clip_id', 'variant_id', 'options'), ('project_id', 'expected_revision', 'kind'))
            self.workspaces.require(actor, 'edit', pid)
            self.scoped_inputs(actor, pid, args.get('options', {}))
            with self.db.transaction() as db:
                self.workspaces.reserve(db, actor, 'job', command_id)
            return self.service.enqueue(pid, args['kind'], args.get('clip_id'), args.get('variant_id', 'portrait'), integer(args['expected_revision'], 'Revisi'), args.get('options'))
        if action in ('job.cancel', 'job.resume'):
            only(args, ('id', 'expected_revision'), ('id', 'expected_revision'))
            job = self.service.queue.get(args['id']);self.workspaces.require(actor, 'edit', job['project_id'])
            current = self.service.store.get(job['project_id'])
            if args['expected_revision'] != current['revision']:
                raise Conflict(current['revision'])
            if action == 'job.cancel':
                return self.service.queue.cancel(job['id'])
            if job['status'] not in ('interrupted', 'failed', 'canceled', 'stale'):
                raise ValueError('Job tidak memerlukan resume')
            with self.db.transaction() as db:
                self.workspaces.reserve(db, actor, 'job', command_id)
            return self.service.enqueue(job['project_id'], job['kind'], job['target'].get('clip_id'), job['target'].get('variant_id', 'portrait'), current['revision'], job['request'].get('options'))
        if action == 'account.list':
            only(args, ());return {'accounts': self.accounts.listing(actor)}
        if action == 'account.save':
            return self.accounts.save(actor, args)
        if action == 'account.probe':
            only(args, ('id',), ('id',));return self.accounts.probe(actor, args['id'])
        if action == 'account.disconnect':
            only(args, ('id', 'expected_version'), ('id', 'expected_version'));return self.accounts.disconnect(actor, args['id'], args['expected_version'])
        if action == 'publish.list':
            only(args, ('project_id',));return {'requests': self.publishing.listing(actor, pid)}
        if action in ('publish.get', 'publish.preflight'):
            only(args, ('id',), ('id',));return self.publishing.preflight(actor, args['id']) if action.endswith('preflight') else self.publishing.get(actor, args['id'])
        if action in ('publish.draft', 'publish.approve', 'publish.revise', 'publish.cancel', 'publish.retry', 'publish.remote_edit', 'publish.manual_receipt'):
            return getattr(self.publishing, action.split('.')[1])(actor, args)
        if action == 'workspace.get':
            only(args, ());return self.workspaces.summary(actor)
        if action == 'workspace.create':
            return self.workspaces.create(actor, args)
        if action == 'workspace.configure':
            return self.workspaces.configure(actor, args)
        if action == 'workspace.member':
            return self.workspaces.member(actor, args)
        if action == 'workspace.organize':
            return self.workspaces.organize(actor, args)
        if action == 'session.revoke':
            only(args, ('id',), ('id',));return self.workspaces.revoke_session(actor, args['id'])
        if action == 'events':
            only(args, ('after',));return {'events': self.db.events(actor.workspace, integer(args.get('after', 0), 'Event cursor'))}
        if action == 'analytics.get':
            only(args, ('project_id',));return self.analytics.dashboard(actor, pid)
        if action == 'analytics.observe':
            return self.analytics.observe(actor, args)
        if action == 'analytics.refresh':
            return self.analytics.refresh(actor, args)
        if action == 'analytics.export':
            only(args, ('project_id',));return self.analytics.export(actor, pid)
        if action in ('comment.save', 'effort.record', 'cost.record', 'experiment.create', 'experiment.assign', 'topic.import'):
            method = {'comment.save': 'comment', 'effort.record': 'effort', 'cost.record': 'cost', 'experiment.create': 'experiment', 'experiment.assign': 'assign', 'topic.import': 'topic'}[action]
            return getattr(self.analytics, method)(actor, args)
        if action == 'record.list':
            only(args, ('kind', 'project_id'), ('kind',));self.workspaces.require(actor, 'read', pid)
            if args['kind'] not in ('comment', 'effort', 'cost', 'experiment', 'topic', 'feedback_policy', 'workflow', 'automation_run'):
                raise ValueError('Jenis catatan tidak terbuka untuk dibaca')
            rows = self.db.records(actor.workspace, args['kind'])
            allowed = {r['project_id'] for r in self.workspaces.projects(actor)}
            selected = [r for r in rows if (not r['data'].get('project_id') or r['data']['project_id'] in allowed) and (not pid or r['data'].get('project_id') == pid)]
            if not actor.local and args['kind'] in ('workflow','automation_run'):
                def filtered(row):
                    row=copy.deepcopy(row)
                    for key in ('folder','seen','known_files'):row['data'].pop(key,None)
                    if 'workflow' in row['data']:
                        row['data']['workflow']={k:v for k,v in row['data']['workflow'].items() if k not in ('folder','seen','known_files')}
                    return row
                selected=[filtered(r) for r in selected]
            return {'records': selected}
        if action == 'workflow.save':
            return self.automation.save(actor, args)
        if action == 'workflow.run':
            return self.automation.submit(actor, args, command_id)
        if action == 'workflow.resume':
            return self.automation.resume(actor, args)
        if action in ('webhook.save', 'webhook.list'):
            return self.webhooks.save(actor, args) if action.endswith('save') else self.webhooks.listing(actor)
        if action == 'backup.create':
            return self.backups.create(actor, args)
        if action == 'backup.restore':
            return self.backups.restore(actor, args)
        if action == 'diagnostics.create':
            return self.backups.diagnostics(actor, args)
        if action in ('review.list','review.revoke'):
            from .delivery7_review import Reviews
            self.workspaces.require(actor,'read' if action=='review.list' else 'review',pid)
            reviews=Reviews(self.service)
            if action=='review.list':
                only(args,('project_id',),('project_id',));return {'reviews':reviews.listing(pid)}
            if action=='review.revoke':
                only(args,('project_id','id','expected_revision'),('project_id','id','expected_revision'))
                return reviews.revoke(pid,args['id'],args['expected_revision'])
        if action == 'plugin.register':
            return self.plugins.register(actor, args)
        if action == 'plugin.list':
            return self.plugins.listing(actor)
        if action == 'feedback.policy':
            self.workspaces.require(actor, 'manage', pid)
            only(args, ('project_id', 'feedback_id', 'expected_revision'), ('project_id', 'feedback_id', 'expected_revision'))
            if actor.workspace != 'solo':
                raise ValueError('Preferensi inti saat ini lokal bersama; promosi pada workspace server belum didukung')
            # Reuses the existing paired human-evaluation gate, no automatic retraining.
            before = self.service.workspace.preference()
            result = self.service.workspace.promote(pid, {k: v for k, v in args.items() if k != 'project_id'})
            return self.db.record(actor.workspace, 'feedback_policy', {'project_id': pid, 'preference': result, 'previous': before, 'mode': 'human_reviewed_template', 'automatic_ranking_training': False})
        if action == 'feedback.rollback':
            self.workspaces.require(actor, 'manage')
            only(args, ('policy_id', 'expected_revision'), ('policy_id', 'expected_revision'))
            if actor.workspace != 'solo':
                raise ValueError('Rollback preferensi inti hanya pada workspace solo lokal')
            policy = next((r for r in self.db.records(actor.workspace, 'feedback_policy') if r['id'] == args['policy_id']), None)
            if not policy or 'previous' not in policy['data']:
                raise ValueError('Versi preferensi sebelumnya tidak tersedia')
            with self.db.transaction() as db:
                row = db.execute("SELECT data FROM workspace_preferences WHERE id='default'").fetchone()
                current = json.loads(row['data']) if row else {'revision': 0}
                if current['revision'] != args['expected_revision']:
                    raise Conflict(current['revision'])
                restored = {**policy['data']['previous'], 'revision': current['revision']+1, 'source': 'explicit_policy_rollback', 'updated': self.db.clock()}
                db.execute("INSERT OR REPLACE INTO workspace_preferences VALUES('default',?)", (canonical(restored),))
                self.db.event(db, actor.workspace, 'feedback.policy_rolled_back', data={'policy_id': policy['id'], 'revision': restored['revision']})
            return restored
        raise ValueError('Aksi M8 tidak dikenal: '+action)

    def scoped_inputs(self, actor, project_id, value):
        if actor.local:
            return
        doc=self.service.store.get(project_id)
        known=set()
        def collect(item):
            if isinstance(item,dict):
                for v in item.values():collect(v)
            elif isinstance(item,list):
                for v in item:collect(v)
            elif isinstance(item,str):known.add(item)
        collect(doc)
        from .font_catalog import FONTS
        def validate(item,key=''):
            if isinstance(item,dict):
                for k,v in item.items():validate(v,k)
            elif isinstance(item,list):
                for v in item:validate(v,key)
            elif isinstance(item,str) and item:
                risky=any(word in key.lower() for word in ('path','directory','endpoint','api_key','token','secret')) or key.lower().endswith(('_dir','_url'))
                risky=risky or Path(item).is_absolute() or PureWindowsPath(item).is_absolute() or '..' in PureWindowsPath(item).parts
                if risky and item not in known:
                    raise AccessDenied('Sesi anggota tidak dapat memilih path host, endpoint, atau credential baru; operator lokal harus menyiapkan bahan proyek')
                if ((item.startswith(('asset-','font-','kit-')) or key in ('kit_id','parent_id','font_id','font_main','font_accent')) and item not in known and item not in FONTS):
                    raise AccessDenied('Aset belum termasuk dalam bahan proyek yang diizinkan')
        validate(value)
        def expanded(item):
            if isinstance(item,dict):
                if item.get('op')=='m5_kit':
                    from .finishing5_service import assets
                    validate(assets(self.service).kit(item['kit_id']))
                for child in item.values():expanded(child)
            elif isinstance(item,list):
                for child in item:expanded(child)
        expanded(value)

    def start(self):
        self.worker.start()

    def close(self):
        self.worker.close()
        self.accounts.close()
