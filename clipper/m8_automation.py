"""Local folder/project workflows stop at render/review and explicit publish approval."""
import copy
import json
from pathlib import Path
from .m8_contract import AccessDenied, canonical, digest, integer, only, text
from .m8_store import ident
from .m8_workspace import Actor
from .dependency_cache import content_id
from .project_store import Conflict


class Automation:
    def __init__(self, m8):
        self.m8 = m8

    def save(self, actor, data):
        self.m8.workspaces.require(actor, 'manage')
        only(data, ('name', 'folder', 'enabled', 'selection_options', 'delivery_options', 'id', 'expected_version'), ('name',))
        enabled = data.get('enabled', False)
        if type(enabled) is not bool:
            raise ValueError('Status workflow harus boolean')
        folder = data.get('folder')
        if folder:
            if not actor.local or actor.workspace != 'solo':
                raise AccessDenied('Watch folder host tersedia bagi operator solo lokal; workspace server memakai proyek yang sudah diberi akses')
            path = Path(folder).expanduser()
            if not path.is_absolute() or path.is_symlink() or not path.is_dir() or any(p.is_symlink() for p in path.parents):
                raise ValueError('Pilih folder lokal absolut yang sudah ada, tanpa symlink')
            folder = str(path.resolve())
        from .selection_contract import constraints
        options = data.get('selection_options', {})
        # Validate with a long placeholder source; real duration is checked by M3 later.
        constraints(options, 7200, self.m8.service.base)
        from .delivery7_contract import options as delivery_options
        delivery = delivery_options(data.get('delivery_options', {'editors': [], 'clean': False, 'stems': False, 'publish': True}))
        value = {'name': text(data['name'], 'Nama workflow', 160), 'folder': folder, 'enabled': enabled,
            'selection_options': options, 'delivery_options': delivery, 'user_id': actor.user_id,
            'publish_policy': 'explicit_approval_per_frozen_publish_request', 'seen': {}, 'known_files': {}}
        if data.get('id'):
            prior = next((r for r in self.m8.db.records(actor.workspace, 'workflow') if r['id'] == data['id']), None)
            if not prior:
                raise KeyError('Workflow tidak ditemukan')
            if prior['data']['folder'] == folder:
                value['seen'] = prior['data']['seen'];value['known_files'] = prior['data']['known_files']
        return self.m8.db.record(actor.workspace, 'workflow', value, data.get('id'), data.get('expected_version'))

    def submit(self, actor, data, command_id):
        only(data, ('workflow_id', 'project_id', 'expected_revision'), ('workflow_id', 'project_id', 'expected_revision'))
        self.m8.workspaces.require(actor, 'edit', data['project_id'])
        workflow = next((r for r in self.m8.db.records(actor.workspace, 'workflow') if r['id'] == data['workflow_id']), None)
        if not workflow:
            raise KeyError('Workflow tidak ditemukan')
        doc = self.m8.service.store.get(data['project_id'])
        if doc['revision'] != data['expected_revision']:
            raise Conflict(doc['revision'])
        return self.m8.db.record(actor.workspace, 'automation_run', {'workflow_id': workflow['id'], 'workflow_version': workflow['version'],
            'workflow': copy.deepcopy(workflow['data']), 'project_id': doc['project_id'], 'expected_revision': doc['revision'],
            'stage': 'selection' if doc.get('transcript_id') else 'analyze', 'state': 'ready', 'job_ids': [],
            'user_id': actor.user_id, 'command_id': command_id, 'publish_approval_required': True})

    def resume(self, actor, data):
        only(data, ('id', 'expected_version', 'expected_revision'), ('id', 'expected_version', 'expected_revision'))
        row = next((r for r in self.m8.db.records(actor.workspace, 'automation_run') if r['id'] == data['id']), None)
        if not row:
            raise KeyError('Workflow run tidak ditemukan')
        value = copy.deepcopy(row['data']);pid = value.get('project_id')
        self.m8.workspaces.require(actor, 'edit', pid)
        if value['state'] not in ('awaiting_review', 'paused', 'failed'):
            raise ValueError('Workflow tidak menunggu resume')
        doc = self.m8.service.store.get(pid)
        if doc['revision'] != data['expected_revision']:
            raise Conflict(doc['revision'])
        value.update(expected_revision=doc['revision'], state='ready', job_ids=[])
        return self.m8.db.record(actor.workspace, 'automation_run', value, row['id'], data['expected_version'])

    def _save_run(self, workspace, row, value):
        return self.m8.db.record(workspace, 'automation_run', value, row['id'], row['version'])

    def _folder(self, actor, row):
        workflow = copy.deepcopy(row['data']);folder = Path(workflow['folder'])
        if not folder.is_dir() or folder.is_symlink():
            return
        from .source_imports import MEDIA_SUFFIXES
        now = self.m8.db.clock();changed = False
        # A bounded direct-child scan avoids crawling private trees or symlink targets.
        for path in sorted(folder.iterdir())[:200]:
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:
                continue
            stat = path.stat();signature = [stat.st_size, stat.st_mtime_ns]
            prior = workflow['seen'].get(path.name)
            if not prior or prior['signature'] != signature:
                workflow['seen'][path.name] = {'signature': signature, 'since': now};changed = True;continue
            if now-prior['since'] < 10:
                continue
            identity = content_id(path, fresh=True)
            if identity in workflow['known_files']:
                continue
            operation = 'm8-watch-'+digest([row['id'], identity])
            imported = self.m8.service.imports.submit({'items': [{'kind': 'local', 'path': str(path)}], 'operation_id': operation,
                'force_new': True, 'auto_analyze': False})
            run = {'workflow_id': row['id'], 'workflow_version': row['version'], 'workflow': copy.deepcopy(workflow),
                'stage': 'import', 'state': 'waiting', 'import_id': imported['items'][0]['id'], 'job_ids': [],
                'user_id': actor.user_id, 'publish_approval_required': True, 'source_content_id': identity}
            run_id='automation-run-'+digest([actor.workspace,row['id'],identity])
            with self.m8.db.transaction() as db:
                db.execute('INSERT OR IGNORE INTO m8_records VALUES(?,?,?,?,?,?,?)',(run_id,actor.workspace,'automation_run',0,canonical(run),now,now))
            saved={'id':run_id}
            workflow['known_files'][identity] = saved['id'];changed = True
            break
        if changed:
            self.m8.db.record(actor.workspace, 'workflow', workflow, row['id'], row['version'])

    def _run(self, actor, row):
        value = copy.deepcopy(row['data']);pid = value.get('project_id')
        if value['stage'] == 'import':
            imported = self.m8.service.imports.get(value['import_id'])
            if imported['status'] == 'completed':
                pid = imported['result']['project_id']
                with self.m8.db.transaction() as db:
                    existing = db.execute('SELECT workspace FROM m8_projects WHERE project_id=?', (pid,)).fetchone()
                    if existing and existing['workspace'] != actor.workspace:
                        raise AccessDenied('Proyek hasil impor sudah berada pada workspace lain')
                    db.execute('INSERT OR IGNORE INTO m8_projects(project_id,workspace) VALUES(?,?)', (pid, actor.workspace))
                doc = self.m8.service.store.get(pid)
                value.update(project_id=pid, expected_revision=doc['revision'], stage='analyze', state='ready')
                self._save_run(actor.workspace, row, value)
            elif imported['status'] in ('failed', 'canceled', 'interrupted'):
                value.update(state='failed', reason='source_import_requires_review');self._save_run(actor.workspace, row, value)
            return
        self.m8.workspaces.require(actor, 'edit', pid)
        doc = self.m8.service.store.get(pid)
        if value['state'] == 'waiting':
            jobs = [self.m8.service.queue.get(key) for key in value['job_ids']]
            if any(j['status'] in ('failed', 'canceled', 'interrupted', 'stale') for j in jobs):
                value.update(state='awaiting_review', reason='core_job_requires_review');self._save_run(actor.workspace, row, value);return
            if not jobs or not all(j['status'] == 'completed' for j in jobs):
                return
            # Job publication legitimately advances the revision. Any later human edit
            # is detected by comparing the current revision with the latest job commit.
            with self.m8.service.store.connect() as db:
                revisions = [db.execute('SELECT MAX(revision) FROM history_metadata WHERE project_id=? AND operation_id=?', (pid, job['id']+'-publish')).fetchone()[0] for job in jobs]
            known = [r for r in revisions if r is not None]
            latest = max(known) if known else doc['revision']
            if latest != doc['revision']:
                value.update(state='awaiting_review', reason='revision_changed_after_job');self._save_run(actor.workspace, row, value);return
            order = ['analyze', 'selection', 'render', 'delivery']
            position = order.index(value['stage'])
            if value['stage'] == 'delivery':
                value.update(state='awaiting_publish_approval', expected_revision=doc['revision'],
                             package_content_id=next((j['result']['package_content_id'] for j in jobs), None))
            else:
                value.update(stage=order[position+1], state='ready', expected_revision=doc['revision'], job_ids=[])
            self._save_run(actor.workspace, row, value);return
        if value['state'] != 'ready':
            return
        if doc['revision'] != value['expected_revision']:
            value.update(state='awaiting_review', reason='project_revision_changed');self._save_run(actor.workspace, row, value);return
        stage = value['stage'];workflow = value['workflow']
        reference = row['id']+':'+stage+':'+str(doc['revision'])
        units = max(1, sum(len(c['variants']) for c in doc['clips'].values() if c.get('included', True))) if stage == 'render' else 1
        with self.m8.db.transaction() as db:
            self.m8.workspaces.reserve(db, actor, 'job', reference, units)
        try:
            if stage == 'render':
                jobs = self.m8.service.enqueue_batch(pid, doc['revision'])
                jobs = jobs.get('jobs', []) if isinstance(jobs, dict) else jobs
            else:
                kind = {'analyze': 'analyze', 'selection': 'selection_m3', 'delivery': 'delivery_m7'}[stage]
                options = workflow['selection_options'] if stage == 'selection' else workflow['delivery_options'] if stage == 'delivery' else None
                jobs = [self.m8.service.enqueue(pid, kind, expected_revision=doc['revision'], options=options)]
            value.update(state='waiting', job_ids=[j['id'] for j in jobs])
            if not jobs and stage=='render':
                value.update(stage='delivery',state='ready',expected_revision=doc['revision'])
        except (ValueError, KeyError):
            value.update(state='awaiting_review', reason='core_guard_requires_review')
        self._save_run(actor.workspace, row, value)

    def tick(self):
        now = self.m8.db.clock();owner = self.m8.worker.owner
        with self.m8.db.transaction() as db:
            lock = db.execute("SELECT owner,expires FROM m8_worker WHERE name='automation'").fetchone()
            if lock and lock['expires'] and lock['expires'] > now:
                return {'status': 'busy'}
            db.execute("INSERT INTO m8_worker VALUES('automation',?,?,?) ON CONFLICT(name) DO UPDATE SET owner=excluded.owner,expires=excluded.expires,heartbeat=excluded.heartbeat", (owner, now+90, now))
            workspaces = [r[0] for r in db.execute('SELECT id FROM m8_workspaces')]
        try:
            for workspace in workspaces:
                for workflow in self.m8.db.records(workspace, 'workflow', 30):
                    value = workflow['data']
                    if value.get('enabled') and value.get('folder') and workspace == 'solo':
                        actor = Actor(workspace, value['user_id'], local=True)
                        self.m8.workspaces.require(actor, 'manage')
                        self._folder(actor, workflow)
                for run in self.m8.db.records(workspace, 'automation_run', 100):
                    if run['data']['state'] in ('ready', 'waiting'):
                        actor = Actor(workspace, run['data']['user_id'])
                        try:
                            self._run(actor, run)
                        except (ValueError, KeyError, OSError):
                            value = copy.deepcopy(run['data']);value.update(state='awaiting_review', reason='workflow_access_or_budget_changed')
                            self._save_run(workspace, run, value)
                        return {'status': 'advanced', 'run_id': run['id']}
            return {'status': 'idle'}
        finally:
            with self.m8.db.transaction() as db:
                db.execute("UPDATE m8_worker SET expires=NULL WHERE name='automation' AND owner=?", (owner,))
