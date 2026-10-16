"""Frozen publish requests, explicit approval, portable handoff and safe revisions."""
import copy
import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from .artifact_store import verify, ArtifactSet
from .dependency_cache import content_id
from .m8_contract import canonical, digest, integer, metadata, only, schedule, text
from .m8_store import ident
from .project_store import Conflict

TERMINAL = {'published', 'handoff_ready', 'failed', 'canceled', 'remote_mismatch'}


class Publishing:
    def __init__(self, m8):
        self.m8 = m8

    def artifact(self, actor, data, *, expected_revision=None):
        pid = text(data['project_id'], 'Proyek', 100)
        self.m8.workspaces.require(actor, 'read', pid)
        doc = self.m8.service.store.get(pid)
        if expected_revision is not None and doc['revision'] != expected_revision:
            raise Conflict(doc['revision'])
        package = next((r for r in doc.get('exports', []) if r.get('version') == '4.0.18-m7' and r.get('package_content_id') == data['package_content_id']), None)
        if not package or not verify(package, fresh=True):
            raise ValueError('ArtifactSet M7 hilang atau berubah; buat paket M7 kembali')
        manifest = json.loads(Path(package['delivery_manifest_path']).read_text(encoding='utf-8'))
        selected = next((r for r in manifest['coverage'] if r['clip_id'] == data['clip_id'] and r['variant_id'] == data['variant_id']), None)
        if not selected:
            raise ValueError('Klip/rasio tidak ada dalam paket M7')
        clip = doc.get('clips', {}).get(data['clip_id'])
        if not clip or not clip.get('included', True) or clip.get('rejected') or clip.get('selection_decision') == 'rejected':
            raise ValueError('Klip tidak lagi dipilih atau ditolak')
        ready = self.m8.service.export_readiness(doc, data['clip_id'], data['variant_id'], fresh=True)
        if ready['status'] != 'ready':
            raise ValueError(ready['message'])
        result = self.m8.service.variant(doc, data['clip_id'], data['variant_id'])['result']
        if selected['reviewed_output_content_id'] != result['output_content_id']:
            raise ValueError('Paket merujuk final lama; buat paket M7 dari final aktif')
        root = Path(package['folder']).resolve()
        name = PurePosixPath(selected['file'])
        if name.is_absolute() or '..' in name.parts:
            raise ValueError('Path final paket tidak valid')
        path = root.joinpath(*name.parts)
        if path.is_symlink() or not path.resolve().is_relative_to(root) or content_id(path, fresh=True) != selected['output_content_id']:
            raise ValueError('Final M7 berubah')
        return doc, package, manifest, selected, path

    def get(self, actor, key, *, private=False):
        self.m8.workspaces.require(actor)
        with self.m8.service.store.connect() as db:
            row = db.execute('SELECT * FROM m8_publish WHERE id=? AND workspace=?', (key, actor.workspace)).fetchone()
        if not row:
            raise KeyError('Publikasi tidak ditemukan')
        self.m8.workspaces.require(actor, 'read', row['project_id'])
        value = dict(row)
        for field in ('request', 'approval', 'cursor', 'remote'):
            value[field] = json.loads(value[field]) if value[field] else None
        if private:
            return value
        request = value['request']
        shown = {k: request[k] for k in ('project_id', 'project_revision', 'clip_id', 'variant_id', 'package_content_id', 'metadata', 'schedule', 'mode', 'platform', 'remote_schedule', 'output_content_id', 'account_version')}
        remote = value['remote'] or {}
        return {k: value[k] for k in ('id', 'version', 'status', 'account_id', 'created', 'updated', 'due')} | {
            'request': shown, 'approval': value['approval'], 'remote': remote,
            'progress': {k: value['cursor'][k] for k in ('offset', 'total', 'attempts', 'last_error', 'phase') if k in (value['cursor'] or {})}}

    def listing(self, actor, project_id=None):
        self.m8.workspaces.require(actor, 'read', project_id)
        with self.m8.service.store.connect() as db:
            keys = [r[0] for r in db.execute('SELECT id FROM m8_publish WHERE workspace=?' + (' AND project_id=?' if project_id else '') + ' ORDER BY created DESC LIMIT 200',
                    (actor.workspace, project_id) if project_id else (actor.workspace,))]
        output = []
        for key in keys:
            try:
                output.append(self.get(actor, key))
            except ValueError:
                continue  # A moved project immediately loses its old workspace's visibility.
        return output

    def draft(self, actor, data):
        self.m8.workspaces.require(actor, 'publish', data.get('project_id'))
        only(data, ('project_id', 'expected_revision', 'package_content_id', 'clip_id', 'variant_id', 'account_id', 'metadata',
                    'local_time', 'timezone', 'fold', 'remote_schedule', 'mode', 'duplicate_reason'),
             ('project_id', 'expected_revision', 'package_content_id', 'clip_id', 'variant_id', 'account_id', 'metadata'))
        revision = integer(data['expected_revision'], 'Revisi proyek')
        doc, package, manifest, selected, path = self.artifact(actor, data, expected_revision=revision)
        account = self.m8.accounts.get(actor, data['account_id'])
        if not account['enabled']:
            raise ValueError('Akun dinonaktifkan')
        mode = data.get('mode', 'handoff')
        if mode not in ('handoff', 'youtube') or mode == 'youtube' and not account['capabilities']['upload']:
            raise ValueError('Upload langsung belum tersedia untuk akun ini; pilih handoff')
        meta = metadata(account['platform'], data['metadata'])
        chosen = schedule(data.get('local_time'), data.get('timezone', self.m8.workspaces.settings(actor)['timezone']), data.get('fold'))
        remote_schedule = data.get('remote_schedule', False)
        if type(remote_schedule) is not bool:
            raise ValueError('Pilihan jadwal remote harus boolean')
        if remote_schedule and (mode != 'youtube' or not chosen['utc'] or chosen['utc'] <= self.m8.db.clock() or meta['privacy'] != 'public'):
            raise ValueError('Jadwal remote memerlukan YouTube, waktu mendatang, dan tujuan public; unggahan awal tetap private')
        duplicate_reason = text(data.get('duplicate_reason', ''), 'Alasan pengulangan video', 500, 0)
        if mode == 'youtube' and not duplicate_reason:
            receipts = self.m8.service.work/'m8-publish-receipts'
            if receipts.is_symlink():
                raise ValueError('Folder receipt tidak aman')
            for file in receipts.glob('publish-*.json'):
                if file.is_symlink():
                    raise ValueError('Receipt tidak aman')
                record = json.loads(file.read_text(encoding='utf-8'))
                if record.get('attempted') and record.get('output_content_id') == selected['output_content_id'] and record.get('platform') == account['platform'] and record.get('account_remote_id') == account['data'].get('remote_id'):
                    raise ValueError('Receipt unggahan video/channel ini sudah ada, termasuk setelah rollback. Rekonsiliasi dahulu atau berikan alasan pengulangan yang disengaja.')
        artifact_key = digest([selected['output_content_id'], account['id']])
        key = ident('publish')
        request = {'schema_version': 1, 'project_id': doc['project_id'], 'project_revision': revision,
            'package_content_id': package['package_content_id'], 'clip_id': selected['clip_id'], 'variant_id': selected['variant_id'],
            'output_content_id': selected['output_content_id'], 'path': str(path), 'bytes': path.stat().st_size,
            'artifact_manifest_id': package['artifact_manifest_id'], 'delivery_manifest_path': package['delivery_manifest_path'],
            'account_id': account['id'], 'account_version': account['version'], 'platform': account['platform'],
            'metadata': meta, 'schedule': chosen, 'remote_schedule': remote_schedule, 'mode': mode, 'duplicate_reason': duplicate_reason}
        request['chunk_size'] = 8*1024**2
        with path.open('rb') as source:
            request['chunk_hashes'] = [hashlib.sha256(block).hexdigest() for block in iter(lambda: source.read(request['chunk_size']), b'')]
        if content_id(path, fresh=True) != request['output_content_id']:
            raise ValueError('Final berubah saat snapshot unggahan dibuat')
        with self.m8.db.transaction() as db:
            self.m8.workspaces.require(actor, 'publish', doc['project_id'], db)
            row = db.execute('SELECT revision FROM projects WHERE id=?', (doc['project_id'],)).fetchone()
            if row['revision'] != revision:
                raise Conflict(row['revision'])
            prior = db.execute("SELECT id,status FROM m8_publish WHERE workspace=? AND artifact_key=? AND (status!='canceled' OR json_extract(cursor,'$.attempted')=1 OR json_extract(remote,'$.id') IS NOT NULL) LIMIT 1", (actor.workspace, artifact_key)).fetchone()
            if prior and not duplicate_reason:
                raise ValueError('Video ini sudah memiliki permintaan untuk akun yang sama: '+prior['id']+'. Buka permintaan lama, atau beri alasan pengulangan yang disengaja.')
            now = self.m8.db.clock()
            db.execute('INSERT INTO m8_publish VALUES(?,?,?,0,?,?,?,?,NULL,?,NULL,?,?,NULL,NULL,?,?)',
                (key, actor.workspace, doc['project_id'], 'draft', account['id'], artifact_key, canonical(request), canonical({}), chosen['utc'], now, now, now))
            self.m8.db.event(db, actor.workspace, 'publish.drafted', doc['project_id'], revision, {'id': key, 'platform': account['platform']})
        return self.get(actor, key)

    def preflight(self, actor, key):
        row = self.get(actor, key, private=True)
        request = row['request']
        blockers = []
        try:
            self.artifact(actor, request, expected_revision=request['project_revision'])
            account = self.m8.accounts.get(actor, row['account_id'])
            if not account['enabled'] or account['version'] != request['account_version']:
                blockers.append('Profil akun berubah; buat permintaan dari profil aktif')
            if request['mode'] == 'youtube' and not account['capabilities']['upload']:
                blockers.append('Izin unggah YouTube belum tersedia')
            if request['mode'] == 'youtube' and (not account['data'].get('probed_at') or account['data']['probed_at'] < self.m8.db.clock()-900):
                blockers.append('Periksa koneksi channel dahulu; hasil probe berlaku 15 menit')
        except (ValueError, KeyError, OSError) as exc:
            blockers.append(str(exc))
        if shutil.disk_usage(self.m8.service.work).free < self.m8.workspaces.settings(actor)['minimum_free_bytes']:
            blockers.append('Ruang disk di bawah batas workspace')
        return {'id': key, 'version': row['version'], 'ready': not blockers, 'blockers': blockers,
            'approval_hash': digest(request), 'frozen': self.get(actor, key)['request'],
            'worker': self.m8.worker_status(), 'warnings': [
                'Jadwal lokal memerlukan worker aktif. Worker yang tidur/offline tidak menjalankan tugas.',
                'Privacy, processing, dan jadwal aktual baru dipastikan dari respons platform.'
            ] if request['mode'] == 'youtube' else ['Paket handoff menunggu unggahan manual; pembuatan ZIP tidak berarti video sudah diposting.']}

    def approve(self, actor, data):
        only(data, ('id', 'expected_version', 'approval_hash'), ('id', 'expected_version', 'approval_hash'))
        row = self.get(actor, data['id'], private=True)
        self.m8.workspaces.require(actor, 'approve', row['project_id'])
        if row['version'] != data['expected_version']:
            raise Conflict(row['version'])
        if row['status'] != 'draft':
            raise ValueError('Hanya draf yang dapat disetujui')
        report = self.preflight(actor, row['id'])
        if not report['ready']:
            raise ValueError('; '.join(report['blockers']))
        if data['approval_hash'] != report['approval_hash']:
            raise ValueError('Isi persetujuan berubah; periksa kembali')
        request = row['request']
        proof = {'hash': report['approval_hash'], 'user_id': actor.user_id, 'workspace': actor.workspace,
                 'approved_at': self.m8.db.clock(), 'project_revision': request['project_revision']}
        with self.m8.db.transaction() as db:
            self.m8.workspaces.require(actor, 'approve', row['project_id'], db)
            current = db.execute('SELECT revision FROM projects WHERE id=?', (row['project_id'],)).fetchone()
            if current['revision'] != request['project_revision']:
                raise Conflict(current['revision'])
            self.m8.workspaces.reserve(db, actor, 'publish', row['id'])
            if db.execute("UPDATE m8_publish SET status='queued',approval=?,version=version+1,updated=? WHERE id=? AND version=? AND status='draft'", (canonical(proof), self.m8.db.clock(), row['id'], row['version'])).rowcount != 1:
                raise Conflict(row['version']+1)
            self.m8.db.event(db, actor.workspace, 'publish.approved', row['project_id'], request['project_revision'], {'id': row['id'], 'hash': proof['hash']})
        return self.get(actor, row['id'])

    def revise(self, actor, data):
        only(data, ('id', 'expected_version', 'metadata', 'local_time', 'timezone', 'fold'), ('id', 'expected_version'))
        row = self.get(actor, data['id'], private=True)
        self.m8.workspaces.require(actor, 'publish', row['project_id'])
        if row['status'] not in ('draft', 'queued', 'paused', 'stale') or row['cursor'].get('attempted'):
            raise ValueError('Permintaan sudah menyentuh remote; gunakan perubahan remote atau panel platform')
        if row['version'] != data['expected_version']:
            raise Conflict(row['version'])
        request = copy.deepcopy(row['request'])
        request['project_revision'] = self.m8.service.store.get(row['project_id'])['revision']
        self.artifact(actor, request, expected_revision=request['project_revision'])
        if 'metadata' in data:
            request['metadata'] = metadata(request['platform'], data['metadata'])
        if 'local_time' in data:
            request['schedule'] = schedule(data['local_time'], data.get('timezone', request['schedule']['timezone']), data.get('fold'))
        if request['remote_schedule'] and (request['metadata']['privacy'] != 'public' or not request['schedule']['utc'] or request['schedule']['utc'] <= self.m8.db.clock()):
            raise ValueError('Jadwal remote public harus berada di masa depan')
        with self.m8.db.transaction() as db:
            changed = db.execute("UPDATE m8_publish SET request=?,approval=NULL,status='draft',due=?,version=version+1,updated=? WHERE id=? AND version=? AND lease_owner IS NULL", (canonical(request), request['schedule']['utc'], self.m8.db.clock(), row['id'], row['version']))
            if changed.rowcount != 1:
                raise Conflict(row['version']+1)
            db.execute("UPDATE m8_ledger SET state='released' WHERE workspace=? AND reference=?", (actor.workspace, row['id']))
            self.m8.db.event(db, actor.workspace, 'publish.revised', row['project_id'], request['project_revision'], {'id': row['id']})
        return self.get(actor, row['id'])

    def cancel(self, actor, data):
        only(data, ('id', 'expected_version', 'remote_to_private'), ('id', 'expected_version'))
        row = self.get(actor, data['id'], private=True)
        self.m8.workspaces.require(actor, 'publish', row['project_id'])
        if row['version'] != data['expected_version']:
            raise Conflict(row['version'])
        remote = data.get('remote_to_private', False)
        if type(remote) is not bool:
            raise ValueError('Pilihan pembatalan remote harus boolean')
        if row['status'] == 'handoff_ready' and remote:
            raise ValueError('Unggahan manual harus dibatalkan pada platform; tidak ada remote ID terverifikasi')
        cursor = row['cursor']
        if (row['remote'] or {}).get('operator_reported_id'):
            return {'id': row['id'], 'status': row['status'], 'local_cancel': False,
                    'remote_cancel': 'manual_platform_action_required', 'message': 'Posting ini dilaporkan diunggah manual; batalkan di platform lalu catat hasilnya.'}
        touched = cursor.get('attempted') or (row['remote'] or {}).get('id')
        if touched and not remote:
            return {'id': row['id'], 'status': row['status'], 'local_cancel': False,
                    'remote_cancel': 'requires_explicit_remote_to_private', 'message': 'Remote mungkin sudah menerima video. Pilih pembatalan remote atau periksa platform.'}
        if remote:
            account = self.m8.accounts.get(actor, row['account_id'])
            if not account['capabilities']['remote_cancel_to_private']:
                raise ValueError('Izin membatalkan remote belum tersedia; periksa YouTube Studio. Status lokal dipertahankan.')
        status = 'cancel_requested' if touched or row['lease_owner'] else 'canceled'
        with self.m8.db.transaction() as db:
            if db.execute('UPDATE m8_publish SET status=?,version=version+1,updated=?,next_run=? WHERE id=? AND version=?',
                          (status, self.m8.db.clock(), self.m8.db.clock(), row['id'], row['version'])).rowcount != 1:
                raise Conflict(row['version']+1)
            if not touched:
                db.execute("UPDATE m8_ledger SET state='released' WHERE workspace=? AND reference=?", (actor.workspace, row['id']))
            self.m8.db.event(db, actor.workspace, 'publish.cancel_requested', row['project_id'], data={'id': row['id'], 'remote': remote})
        return self.get(actor, row['id'])

    def retry(self, actor, data):
        only(data, ('id', 'expected_version'), ('id', 'expected_version'))
        row = self.get(actor, data['id'], private=True)
        self.m8.workspaces.require(actor, 'publish', row['project_id'])
        if row['version'] != data['expected_version']:
            raise Conflict(row['version'])
        if row['status'] not in ('paused', 'needs_reconcile', 'failed'):
            raise ValueError('Permintaan tidak memerlukan retry')
        cursor = row['cursor']
        if cursor.get('attempted') and not cursor.get('session_ref') and not (row['remote'] or {}).get('id'):
            raise ValueError('Sesi tidak diketahui. Rekonsiliasi manual wajib; unggahan baru tidak dibuat otomatis.')
        if not cursor.get('attempted'):
            report = self.preflight(actor, row['id'])
            if not report['ready']:
                raise ValueError('; '.join(report['blockers']))
        status = 'processing' if (row['remote'] or {}).get('id') else 'uploading' if cursor.get('session_ref') else 'queued'
        with self.m8.db.transaction() as db:
            if db.execute('UPDATE m8_publish SET status=?,version=version+1,next_run=?,updated=? WHERE id=? AND version=? AND lease_owner IS NULL',
                          (status, self.m8.db.clock(), self.m8.db.clock(), row['id'], row['version'])).rowcount != 1:
                raise Conflict(row['version']+1)
            self.m8.db.event(db, actor.workspace, 'publish.retry_requested', row['project_id'], data={'id': row['id'], 'reconcile_first': True})
        return self.get(actor, row['id'])

    def remote_edit(self, actor, data):
        only(data, ('id', 'expected_version', 'metadata'), ('id', 'expected_version', 'metadata'))
        row = self.get(actor, data['id'], private=True)
        self.m8.workspaces.require(actor, 'approve', row['project_id'])
        self.m8.workspaces.require(actor, 'publish', row['project_id'])
        if row['version'] != data['expected_version']:
            raise Conflict(row['version'])
        if row['status'] not in ('published', 'scheduled_remote', 'remote_mismatch') or not (row['remote'] or {}).get('id'):
            raise ValueError('Perubahan remote memerlukan posting/schedule yang memiliki ID terverifikasi')
        account = self.m8.accounts.get(actor, row['account_id'])
        if not account['capabilities']['remote_edit']:
            raise ValueError('Izin mengubah metadata remote belum tersedia')
        updated = metadata(row['request']['platform'], data['metadata'])
        if updated['privacy'] != row['request']['metadata']['privacy'] or updated['made_for_kids'] != row['request']['metadata']['made_for_kids']:
            raise ValueError('Perubahan ini hanya judul/deskripsi/tag; ubah privacy atau konten anak melalui platform')
        cursor = dict(row['cursor']);cursor['change_metadata'] = updated
        cursor['change_approved_by'] = actor.user_id
        with self.m8.db.transaction() as db:
            if db.execute("UPDATE m8_publish SET status='remote_change',cursor=?,version=version+1,next_run=?,updated=? WHERE id=? AND version=? AND lease_owner IS NULL",
                (canonical(cursor), self.m8.db.clock(), self.m8.db.clock(), row['id'], row['version'])).rowcount != 1:
                raise Conflict(row['version']+1)
            self.m8.db.event(db, actor.workspace, 'publish.remote_edit_approved', row['project_id'], data={'id': row['id'], 'metadata_hash': digest(updated)})
        return self.get(actor, row['id'])

    def manual_receipt(self, actor, data):
        only(data, ('id', 'expected_version', 'remote_id', 'remote_url', 'privacy', 'note'), ('id', 'expected_version', 'remote_id', 'remote_url', 'privacy'))
        row = self.get(actor, data['id'], private=True)
        self.m8.workspaces.require(actor, 'publish', row['project_id'])
        if row['version'] != data['expected_version']:
            raise Conflict(row['version'])
        if row['request']['mode'] != 'handoff' or row['status'] != 'handoff_ready':
            raise ValueError('Receipt manual hanya untuk paket handoff yang sudah dibuat')
        from urllib.parse import urlsplit
        address = text(data['remote_url'], 'URL remote', 2000)
        parsed = urlsplit(address)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('URL remote harus HTTPS tanpa credential')
        if data['privacy'] not in ('private', 'unlisted', 'public'):
            raise ValueError('Privacy aktual diperlukan')
        remote = {**(row['remote'] or {}), 'operator_reported_id': text(data['remote_id'], 'ID remote', 200),
            'operator_reported_url': address, 'operator_reported_privacy': data['privacy'], 'reported_by': actor.user_id,
            'reported_at': self.m8.db.clock(), 'note': text(data.get('note', ''), 'Catatan', 2000, 0), 'api_verified': False}
        with self.m8.db.transaction() as db:
            if db.execute('UPDATE m8_publish SET remote=?,version=version+1,updated=? WHERE id=? AND version=?', (canonical(remote), self.m8.db.clock(), row['id'], row['version'])).rowcount != 1:
                raise Conflict(row['version']+1)
            self.m8.db.event(db, actor.workspace, 'publish.manual_reported', row['project_id'], data={'id': row['id'], 'api_verified': False})
        return self.get(actor, row['id'])

    def handoff(self, actor, row):
        request = row['request']
        doc, package, manifest, selected, video = self.artifact(actor, request, expected_revision=request['project_revision'])
        txn = ArtifactSet(self.m8.service.work / 'm8-handoffs', {'publish_id': row['id'], 'approval_hash': row['approval']['hash']})
        try:
            shutil.copy2(video, txn.staging/'video.mp4')
            if content_id(txn.staging/'video.mp4', fresh=True) != request['output_content_id']:
                raise ValueError('Salinan final handoff tidak sesuai snapshot')
            members = [{'path': 'video.mp4', 'content_id': content_id(video, fresh=True), 'role': 'final_video'}]
            root = Path(package['folder']).resolve()
            clip_folder = PurePosixPath(selected['file']).parent
            for item in manifest['files']:
                name = PurePosixPath(item['path'])
                if not name.is_relative_to(clip_folder):
                    continue
                relative = name.relative_to(clip_folder)
                if not relative.parts or relative.parts[0] not in ('Sidecars', 'Publish') or name.suffix.lower() not in ('.srt', '.vtt', '.ass', '.jpg', '.txt', '.json'):
                    continue
                source = root.joinpath(*name.parts)
                if source.is_symlink() or not source.resolve().is_relative_to(root) or content_id(source, fresh=True) != item['content_id']:
                    raise ValueError('Aset handoff berubah')
                destination = Path('assets')/Path(*name.parts)
                target = txn.staging/destination;target.parent.mkdir(parents=True, exist_ok=True);shutil.copy2(source, target)
                if content_id(target, fresh=True) != item['content_id']:
                    raise ValueError('Salinan sidecar handoff tidak sesuai snapshot')
                members.append({'path': destination.as_posix(), 'content_id': item['content_id'], 'role': item['role']})
            report = {'schema_version': 1, 'publish_id': row['id'], 'status': 'manual_upload_required',
                'platform': request['platform'], 'account': self.m8.accounts.get(actor, row['account_id'])['name'],
                'project_id': request['project_id'], 'project_revision': request['project_revision'],
                'approval_hash': row['approval']['hash'], 'metadata': request['metadata'], 'schedule': request['schedule'],
                'members': members, 'remote_id': None, 'privacy_actual': None,
                'note': 'Paket ini belum diposting. Unggah video/aset melalui aplikasi platform, lalu catat ID dan privacy aktual.'}
            (txn.staging/'handoff.json').write_text(canonical(report)+'\n', encoding='utf-8')
            (txn.staging/'BACA_DULU.txt').write_text('Paket unggah manual. Periksa akun, judul, caption, privacy, cover dan jadwal pada handoff.json.\n'
                'TikTok/Meta/LinkedIn/X tidak diberi label autopublish. Aset caption/cover dipasang sesuai kemampuan platform.\n'
                'Setelah mengunggah, catat URL/ID remote di Clipper. Status manual tidak berubah menjadi bukti API.\n', encoding='utf-8')
            archive = txn.staging/'Clipper_M8_Handoff.zip'
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
                for path in sorted(txn.staging.rglob('*')):
                    if path.is_file() and path != archive:
                        z.write(path, path.relative_to(txn.staging).as_posix())
            with zipfile.ZipFile(archive) as z:
                if z.testzip():
                    raise ValueError('CRC handoff gagal')
            self.artifact(actor, request, expected_revision=request['project_revision'])
            sealed = txn.seal()
            path = txn.final/archive.name
            return {'handoff_url': self.m8.service.register_file(request['project_id'], path),
                    'handoff_content_id': content_id(path, fresh=True), 'remote_id': None, 'manual_upload_required': True,
                    'artifact_manifest_id': sealed['artifact_manifest_id']}
        except BaseException as exc:
            txn.abort(exc)
            raise
