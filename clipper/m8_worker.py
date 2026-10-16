"""One bounded publication step per tick; cross-process leases fence all writes.

Run with python -m clipper.m8_cli worker. No scheduler can run while its host sleeps.
"""
import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from .m8_contract import Busy, canonical, digest
from .m8_workspace import Actor
from .m8_youtube import NetworkFailure, RemoteFailure

ACTIVE = ('queued', 'uploading', 'processing', 'scheduled_remote', 'cancel_requested', 'remote_change')


class Worker:
    def __init__(self, m8):
        self.m8 = m8
        self.owner = uuid.uuid4().hex
        self.stop_event = threading.Event()
        self.thread = None

    def claim(self):
        now = self.m8.db.clock()
        with self.m8.db.transaction() as db:
            old = db.execute("SELECT * FROM m8_worker WHERE name='publisher'").fetchone()
            if old and old['expires'] and old['expires'] > now:
                return None
            db.execute("INSERT INTO m8_worker VALUES('publisher',?,?,?) ON CONFLICT(name) DO UPDATE SET owner=excluded.owner,expires=excluded.expires,heartbeat=excluded.heartbeat", (self.owner, now+90, now))
            marks = ','.join('?' for _ in ACTIVE)
            row = db.execute('SELECT * FROM m8_publish WHERE status IN ('+marks+') AND (lease_expires IS NULL OR lease_expires<=?) AND (next_run IS NULL OR next_run<=?) '
                "AND (status!='queued' OR due IS NULL OR due<=? OR json_extract(request,'$.remote_schedule')=1) ORDER BY created LIMIT 1", (*ACTIVE, now, now, now)).fetchone()
            if not row:
                db.execute("UPDATE m8_worker SET expires=NULL WHERE name='publisher' AND owner=?", (self.owner,))
                return None
            db.execute('UPDATE m8_publish SET lease_owner=?,lease_expires=? WHERE id=?', (self.owner, now+90, row['id']))
        value = dict(row)
        for field in ('request', 'approval', 'cursor', 'remote'):
            value[field] = json.loads(value[field]) if value[field] else None
        return value

    def checkpoint(self, row, *, status=None, cursor=None, remote=None, delay=0, event=None):
        now = self.m8.db.clock()
        with self.m8.db.transaction() as db:
            live = db.execute('SELECT status,version,lease_owner,lease_expires FROM m8_publish WHERE id=?', (row['id'],)).fetchone()
            if not live or live['lease_owner'] != self.owner or not live['lease_expires'] or live['lease_expires'] <= now:
                raise Busy('Lease publikasi berubah; worker lama tidak dapat menulis hasil')
            if live['status'] == 'cancel_requested' and status not in (None, 'cancel_requested', 'canceled', 'needs_reconcile'):
                if cursor and cursor.get('phase') in ('initializing','chunk_in_flight'):
                    raise Busy('Pembatalan diterima sebelum pengiriman berikutnya')
                status = 'cancel_requested'
            values = {'updated': now, 'next_run': now+delay, 'lease_expires': now+90}
            if status:
                values['status'] = status
            if cursor is not None:
                values['cursor'] = canonical(cursor)
            if remote is not None:
                values['remote'] = canonical(remote)
            if cursor and cursor.get('attempted'):
                self.durable_receipt(db, row, status or live['status'], cursor, remote)
            db.execute('UPDATE m8_publish SET '+','.join(k+'=?' for k in values)+' WHERE id=?', (*values.values(), row['id']))
            db.execute("UPDATE m8_worker SET expires=?,heartbeat=? WHERE name='publisher' AND owner=?", (now+90, now, self.owner))
            if event:
                self.m8.db.event(db, row['workspace'], event, row['project_id'], row['request']['project_revision'],
                    {'id': row['id'], 'status': status or live['status'], 'remote_id': (remote or {}).get('id')})
            if status in ('published', 'handoff_ready', 'scheduled_remote'):
                db.execute("UPDATE m8_ledger SET state='consumed' WHERE workspace=? AND reference=?", (row['workspace'], row['id']))

    def durable_receipt(self, db, row, status, cursor, remote):
        """Survives an explicit SQLite rollback, without storing upload URI or token."""
        account = db.execute('SELECT platform,data FROM m8_accounts WHERE id=?', (row['account_id'],)).fetchone()
        folder = self.m8.service.work/'m8-publish-receipts';folder.mkdir(exist_ok=True)
        if folder.is_symlink():
            raise ValueError('Folder receipt tidak boleh symlink')
        target = folder/(row['id']+'.json')
        prior = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else {}
        value = {'schema_version': 1, 'id': row['id'], 'workspace': row['workspace'], 'attempted': True,
            'output_content_id': row['request']['output_content_id'], 'platform': account['platform'] if account else row['request']['platform'],
            'account_remote_id': json.loads(account['data']).get('remote_id') if account else prior.get('account_remote_id'),
            'status': status, 'remote_id': (remote or {}).get('id') or prior.get('remote_id'),
            'approval_hash': row['approval']['hash'], 'updated': self.m8.db.clock()}
        temporary = target.with_name(target.name+'.'+self.owner+'.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as out:
                out.write(canonical(value)+'\n');out.flush();os.fsync(out.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def release(self, key):
        with self.m8.db.transaction() as db:
            db.execute('UPDATE m8_publish SET lease_owner=NULL,lease_expires=NULL WHERE id=? AND lease_owner=?', (key, self.owner))
            db.execute("UPDATE m8_worker SET expires=NULL,heartbeat=? WHERE name='publisher' AND owner=?", (self.m8.db.clock(), self.owner))

    def actor(self, row):
        approval = row['approval'] or {}
        if not approval.get('user_id') or approval.get('hash') != digest(row['request']):
            raise ValueError('Persetujuan tidak cocok dengan permintaan yang dibekukan')
        actor = Actor(row['workspace'], approval['user_id'])
        self.m8.workspaces.require(actor, 'publish', row['project_id'])
        self.m8.workspaces.require(actor, 'approve', row['project_id'])
        return actor

    def validate(self, actor, row):
        self.m8.publishing.artifact(actor, row['request'], expected_revision=row['request']['project_revision'])
        account = self.m8.accounts.get(actor, row['account_id'], private=True)
        if not account['enabled'] or account['version'] != row['request']['account_version']:
            raise ValueError('Akun berubah setelah persetujuan')
        with self.m8.service.store.connect() as db:
            live = db.execute('SELECT status,lease_owner,lease_expires FROM m8_publish WHERE id=?', (row['id'],)).fetchone()
        if live['status'] == 'cancel_requested':
            raise Busy('Pembatalan menunggu rekonsiliasi')
        if live['lease_owner'] != self.owner or live['lease_expires'] <= self.m8.db.clock():
            raise Busy('Lease publikasi berakhir')
        return account

    def tick(self):
        row = self.claim()
        if not row:
            return {'status': 'idle'}
        try:
            actor = self.actor(row)
            request, cursor = row['request'], dict(row['cursor'] or {})
            account = self.m8.accounts.get(actor, row['account_id'], private=True)
            if row['status'] == 'cancel_requested':
                self.cancel_step(actor, row, account, cursor)
            elif (row['remote'] or {}).get('id'):
                self.poll_step(actor, row, account, cursor)
            else:
                account = self.validate(actor, row)
                if request['mode'] == 'handoff':
                    remote = self.m8.publishing.handoff(actor, row)
                    self.validate(actor, row)
                    self.checkpoint(row, status='handoff_ready', remote=remote, cursor={'phase': 'handoff_ready'}, event='publish.handoff_ready')
                else:
                    self.upload_step(actor, row, account, cursor)
            return self.m8.publishing.get(actor, row['id'])
        except Busy:
            return {'id': row['id'], 'status': 'lease_or_cancel_changed'}
        except (NetworkFailure, RemoteFailure) as exc:
            # A resumed worker always queries this saved session before sending again.
            with self.m8.service.store.connect() as db:
                live = db.execute('SELECT cursor FROM m8_publish WHERE id=?', (row['id'],)).fetchone()
            cursor = json.loads(live['cursor']) or {}
            cursor['attempts'] = cursor.get('attempts', 0)+1
            cursor['last_error'] = 'network_reconcile_required' if isinstance(exc, NetworkFailure) else 'http_'+str(exc.status)+'_'+exc.reason
            ambiguous = cursor.get('attempted') and not cursor.get('session_ref') and not (row['remote'] or {}).get('id')
            expired = isinstance(exc, RemoteFailure) and exc.status in (404, 410) and cursor.get('session_ref')
            status = 'needs_reconcile' if ambiguous or expired else 'paused' if cursor['attempts'] >= 6 or isinstance(exc, RemoteFailure) and exc.status in (400, 401, 403) else None
            self.checkpoint(row, status=status, cursor=cursor, delay=min(900, 2**min(cursor['attempts'], 9)), event='publish.reconcile_required')
            return {'id': row['id'], 'status': status or 'retry_reconcile_scheduled'}
        except (ValueError, KeyError, OSError, TypeError) as exc:
            # Never retain arbitrary exception text, URLs, tokens or request payloads.
            with self.m8.service.store.connect() as db:
                live = db.execute('SELECT cursor,remote FROM m8_publish WHERE id=?', (row['id'],)).fetchone()
            cursor = json.loads(live['cursor']) or {}
            cursor['last_error'] = 'validation_or_access_changed'
            touched = cursor.get('attempted') or bool(json.loads(live['remote'] or '{}').get('id'))
            self.checkpoint(row, status='needs_reconcile' if touched else 'stale', cursor=cursor, event='publish.blocked')
            return {'id': row['id'], 'status': 'needs_reconcile' if touched else 'stale'}
        finally:
            self.release(row['id'])

    def upload_step(self, actor, row, account, cursor):
        request = row['request'];path = Path(request['path'])
        if not account['capabilities']['upload']:
            raise ValueError('Izin upload belum tersedia')
        self.m8.youtube.probe(account)
        total = path.stat().st_size
        cursor['total'] = total
        if not cursor.get('session_ref'):
            if cursor.get('attempted'):
                self.checkpoint(row, status='needs_reconcile', cursor=cursor, event='publish.reconcile_required')
                return
            cursor.update(attempted=True, phase='initializing', offset=0)
            self.checkpoint(row, status='uploading', cursor=cursor)
            self.validate(actor, row)
            uri = self.m8.youtube.begin(account, request, path)
            cursor.update(session_ref=self.m8.vault.put({'session_uri': uri}), phase='session_saved')
            self.checkpoint(row, cursor=cursor, event='publish.session_saved')
            return
        uri = self.m8.vault.get(cursor['session_ref'])['session_uri']
        progress = self.m8.youtube.upload_status(account, uri, total)
        if not progress['complete']:
            self.validate(actor, row)
            cursor.update(offset=progress['offset'], phase='chunk_in_flight')
            self.checkpoint(row, status='uploading', cursor=cursor)
            # If this PUT times out, next tick queries the same session, not a new upload.
            progress = self.m8.youtube.chunk(account, uri, path, progress['offset'], request['chunk_size'], request['chunk_hashes'])
        cursor.update(offset=progress['offset'], phase='remote_accepted' if progress['complete'] else 'chunk_saved', attempts=0)
        if progress['complete']:
            remote = {'id': progress['remote_id'], 'privacy': None, 'processing_status': 'unknown',
                      'url': 'https://www.youtube.com/watch?v='+progress['remote_id']}
            self.checkpoint(row, status='processing', cursor=cursor, remote=remote, event='publish.remote_accepted')
        else:
            self.checkpoint(row, cursor=cursor)

    def poll_step(self, actor, row, account, cursor):
        remote_id = row['remote']['id']
        if row['status'] == 'remote_change':
            change = cursor.get('change_metadata')
            if not change:
                raise ValueError('Perubahan metadata tidak tersedia')
            remote = self.m8.youtube.change(account, remote_id, metadata=change)
            equal = all(remote['snippet'].get(k, '' if k != 'tags' else []) == change[target] for k, target in (('title', 'title'), ('description', 'description'), ('tags', 'tags')))
            remote['metadata_update_confirmed'] = equal
            cursor['last_metadata_change'] = {'metadata': change, 'approved_by': cursor.get('change_approved_by'), 'confirmed': equal}
            cursor.pop('change_metadata', None)
            status = self.classify(row, remote) if equal else 'remote_mismatch'
            self.checkpoint(row, status=status, cursor=cursor, remote=remote, delay=300 if status=='scheduled_remote' else 0, event='publish.remote_updated')
            return
        remote = self.m8.youtube.poll(account, remote_id)
        request = row['request']
        current = self.m8.service.store.get(row['project_id'])
        remote['approved_revision_current'] = current['revision'] == request['project_revision']
        status = self.classify(row, remote)
        delay = 30 if status == 'processing' else 300 if status == 'scheduled_remote' else 0
        self.checkpoint(row, status=status, cursor=cursor, remote=remote, delay=delay, event='publish.'+status)

    def classify(self, row, remote):
        request = row['request']
        if remote['upload_status'] in ('failed', 'rejected', 'deleted') or remote['processing_status'] in ('failed', 'terminated'):
            status = 'failed'
        elif request['remote_schedule'] and remote['privacy'] == 'private' and remote.get('publish_at'):
            actual = datetime.fromisoformat(remote['publish_at'].replace('Z', '+00:00')).timestamp()
            status = 'scheduled_remote' if abs(actual-request['schedule']['utc']) < 1 else 'remote_mismatch'
        elif remote['processing_status'] not in ('succeeded', None) or remote['upload_status'] not in ('processed', 'uploaded'):
            status = 'processing'
        elif remote['privacy'] != request['metadata']['privacy']:
            status = 'remote_mismatch'
        elif remote['processing_status'] is None and remote['upload_status'] != 'processed':
            status = 'processing'
        else:
            status = 'published'
        return status

    def cancel_step(self, actor, row, account, cursor):
        remote = dict(row['remote'] or {})
        if not remote.get('id') and cursor.get('session_ref'):
            uri = self.m8.vault.get(cursor['session_ref'])['session_uri']
            state = self.m8.youtube.upload_status(account, uri, cursor['total'])
            if state['complete']:
                remote['id'] = state['remote_id']
            else:
                # No more bytes will be sent. An incomplete upload is never called a remote post.
                remote.update(remote_cancel='partial_session_abandoned', post_confirmed=False)
                self.checkpoint(row, status='canceled', cursor=cursor, remote=remote, event='publish.canceled')
                return
        if remote.get('id'):
            remote = self.m8.youtube.change(account, remote['id'], cancel=True)
            okay = remote.get('privacy') == 'private' and not remote.get('publish_at')
            remote['remote_cancel'] = 'confirmed_private_unscheduled' if okay else 'not_confirmed'
            self.checkpoint(row, status='canceled' if okay else 'needs_reconcile', cursor=cursor, remote=remote, event='publish.cancel_reconciled')
        elif cursor.get('attempted'):
            self.checkpoint(row, status='needs_reconcile', cursor=cursor, remote={'remote_cancel': 'unknown_session'}, event='publish.reconcile_required')
        else:
            self.checkpoint(row, status='canceled', cursor=cursor, remote={'remote_cancel': 'no_remote_submission'}, event='publish.canceled')

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        def loop():
            while not self.stop_event.is_set():
                try:
                    self.tick()
                    self.m8.webhooks.tick()
                    self.m8.automation.tick()
                except Exception:
                    pass  # Public errors are recorded by individual state machines, never raw logs.
                self.stop_event.wait(2)
        self.thread = threading.Thread(target=loop, daemon=True, name='m8-publisher')
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)
        with self.m8.db.transaction() as db:
            db.execute("UPDATE m8_worker SET heartbeat=0 WHERE name IN ('publisher','automation') AND owner=? AND expires IS NULL", (self.owner,))
