"""Checksummed project backups. Restore is a new, scoped project, never a publish replay."""
import copy
import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from .dependency_cache import content_id
from .m8_contract import canonical, integer, only
from .m8_store import ident
from .project_store import Conflict

TABLES = ('transcripts', 'history', 'history_actions', 'history_metadata', 'operations', 'editor_drafts', 'editor_sync_evidence')
MEDIA = {'.mp4', '.mov', '.mkv', '.webm', '.wav', '.mp3', '.m4a', '.flac', '.ogg', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.ttf', '.otf', '.srt', '.vtt', '.ass', '.json', '.txt', '.zip', '.xml', '.lua', '.fcpxml', '.otio'}


def rewrite(value, paths, ids):
    if isinstance(value, dict):
        return {ids.get(k, k): rewrite(v, paths, ids) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite(v, paths, ids) for v in value]
    if isinstance(value, str):
        if value in ids:
            return ids[value]
        for before, after in sorted(paths.items(), key=lambda r: len(r[0]), reverse=True):
            if value == before or value.startswith(before+str(Path('/'))):
                return after+value[len(before):]
        return value
    return value


class Backups:
    def __init__(self, m8):
        self.m8 = m8

    def create(self, actor, data):
        only(data, ('project_id', 'expected_revision', 'include_source', 'max_bytes'), ('project_id', 'expected_revision'))
        pid = data['project_id'];self.m8.workspaces.require(actor, 'manage', pid)
        doc = self.m8.service.store.get(pid)
        if doc['revision'] != data['expected_revision']:
            raise Conflict(doc['revision'])
        include_source = data.get('include_source', True)
        if type(include_source) is not bool:
            raise ValueError('Pilihan sumber harus boolean')
        cap = integer(data.get('max_bytes', 30*1024**3), 'Batas backup', 1024, 100*1024**3)
        source = Path(doc['source']['path']).resolve()
        files = set();trees = set()
        references=set()
        def visit(value):
            if isinstance(value, dict):
                root = value.get('artifact_root')
                if root and Path(root).is_dir():
                    resolved = Path(root).resolve()
                    if not resolved.is_relative_to(self.m8.service.work) and not resolved.is_relative_to(Path(self.m8.service.base.out_dir)):
                        raise ValueError('Artifact root berada di luar folder proyek/hasil; periksa proyek sebelum backup')
                    trees.add(resolved)
                for v in value.values():
                    visit(v)
            elif isinstance(value, list):
                for v in value:
                    visit(v)
            elif isinstance(value, str):
                references.add(value)
                try:
                    path = Path(value)
                    if path.is_absolute() and path.is_file() and path.suffix.lower() in MEDIA:
                        resolved = path.resolve()
                        if resolved == source and not include_source:
                            return
                        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
                            raise ValueError('Symlink pada bahan backup tidak diizinkan')
                        files.add(resolved)
                except (OSError, ValueError) as exc:
                    if isinstance(exc, ValueError) and 'Symlink' in str(exc):
                        raise
        visit(doc)
        m9_items=[];m9_evidence={}
        with self.m8.service.store.connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m9_items'").fetchone():
                if db.execute("SELECT 1 FROM jobs WHERE kind LIKE '%_m9' AND status IN ('queued','running','cancel_requested') AND json_extract(request,'$.m9.project_id')=? LIMIT 1",(pid,)).fetchone():
                    raise ValueError('Selesaikan atau batalkan tugas M9 proyek sebelum backup')
                for row in db.execute("SELECT * FROM m9_items WHERE json_extract(data,'$.project_id')=? ORDER BY id",(pid,)):
                    row=dict(row);value=json.loads(row['data'])
                    if row['workspace']!=actor.workspace:raise ValueError('Relasi M9 proyek berada di workspace berbeda; pulihkan hubungan sebelum backup')
                    if value.get('status') in ('capturing','finalizing'):raise ValueError('Jeda/finalisasi rekaman sebelum backup')
                    m9_items.append(row);visit(value)
                    if row['kind']=='recording':
                        tracks=[dict(t) for t in db.execute('SELECT * FROM m9_tracks WHERE session_id=?',(row['id'],))]
                        chunks=[dict(c) for t in tracks for c in db.execute('SELECT * FROM m9_chunks WHERE track_id=?',(t['id'],))]
                        m9_evidence[row['id']]={'tracks':tracks,'chunks':chunks,'invites_included':False}
                        tree=self.m8.service.work/'m9'/'recordings'/row['id']
                        if tree.is_dir():trees.add(tree.resolve())
        registries={'assets5':[],'kits5':[],'kit_history5':[],'asset_history5':[]}
        with self.m8.service.store.connect() as db:
            for row in db.execute('SELECT * FROM kits5'):
                if row['id'] in references:
                    registries['kits5'].append(dict(row));visit(json.loads(row['data']))
            for row in db.execute('SELECT * FROM assets5'):
                if row['id'] in references:
                    registries['assets5'].append(dict(row));visit(json.loads(row['data']))
            for table,parent in [('kit_history5','kits5'),('asset_history5','assets5')]:
                selected={r['id'] for r in registries[parent]}
                registries[table]=[dict(r) for r in db.execute('SELECT * FROM '+table) if r['id'] in selected]
        for tree in trees:
            for path in tree.rglob('*'):
                if path.is_symlink():
                    raise ValueError('Symlink pada ArtifactSet backup')
                if path.is_file():
                    files.add(path)
        if include_source and not source.is_file():
            raise ValueError('Sumber tidak tersedia; pilih backup tanpa sumber secara eksplisit')
        if include_source:
            files.add(source)
        if len(files)+2>30000:
            raise ValueError('Backup melebihi batas 30.000 anggota; kurangi jumlah bahan/rekaman sebelum membuat paket')
        total = sum(p.stat().st_size for p in files)
        if total > cap or shutil.disk_usage(self.m8.service.work).free < total+64*1024**2:
            raise ValueError('Batas ukuran atau ruang disk backup tidak cukup')
        folder = self.m8.service.work/'m8-backups'/ident('backup');folder.mkdir(parents=True)
        target = folder/'Clipper_M8_Backup.zip';pending = folder/'backup.partial'
        tables = {}
        with self.m8.service.store.connect() as db:
            db.execute('BEGIN')
            current = db.execute('SELECT revision FROM projects WHERE id=?', (pid,)).fetchone()
            if current['revision'] != doc['revision']:
                raise Conflict(current['revision'])
            for name in TABLES:
                tables[name] = [dict(r) for r in db.execute('SELECT * FROM '+name+' WHERE project_id=?', (pid,))]
            tables['words'] = [dict(r) for r in db.execute('SELECT w.* FROM words w JOIN transcripts t ON t.id=w.take_id WHERE t.project_id=?', (pid,))]
            db.commit()
        roots = sorted(trees, key=lambda p: len(str(p)))
        roots = [p for p in roots if not any(p != other and p.is_relative_to(other) for other in roots)]
        mappings = {str(root): 'assets/tree-'+str(i) for i, root in enumerate(roots)}
        for path in sorted(files):
            if not any(path.is_relative_to(root) for root in roots):
                mappings[str(path)] = 'assets/files/'+hashlib.sha256(str(path).encode()).hexdigest()[:20]+path.suffix.lower()
        project_records = {}
        for kind in ('comment', 'effort', 'cost', 'feedback_policy'):
            project_records[kind] = [r for r in self.m8.db.records(actor.workspace, kind, 10000) if r['data'].get('project_id') == pid]
        snapshot = {'document': doc, 'tables': tables, 'records': project_records, 'registries':registries,
            'm9_items':m9_items,'m9_evidence':m9_evidence,
            'source_workspace': actor.workspace, 'revision': doc['revision'], 'restore_policy': 'clone_into_authorized_workspace; no credentials, sessions, account access, or publication replay'}
        inventory = {}
        try:
            with zipfile.ZipFile(pending, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
                for path in sorted(files):
                    before = content_id(path, fresh=True)
                    ancestor = next((root for root in roots if path.is_relative_to(root)), None)
                    packed = mappings[str(ancestor)]+'/'+path.relative_to(ancestor).as_posix() if ancestor else mappings[str(path)]
                    archive.write(path, packed)
                    if content_id(path, fresh=True) != before:
                        raise ValueError('Bahan berubah saat backup; paket tidak dipublikasikan')
                    inventory[packed] = before
                body = canonical(snapshot).encode()
                if total+len(body)>cap:raise ValueError('Batas ukuran backup termasuk metadata tidak cukup')
                archive.writestr('snapshot.json', body)
                inventory['snapshot.json'] = 'sha256:'+hashlib.sha256(body).hexdigest()
                manifest = {'schema_version': 2, 'kind': 'clipper_m8_project_backup', 'project_id': pid, 'project_revision': doc['revision'],
                    'files': inventory, 'path_map': mappings, 'include_source': include_source, 'unpacked_bytes': total+len(body)}
                archive.writestr('manifest.json', canonical(manifest))
            with zipfile.ZipFile(pending) as archive:
                if archive.testzip():
                    raise ValueError('CRC backup gagal')
            if self.m8.service.store.get(pid)['revision'] != doc['revision']:
                raise Conflict(self.m8.service.store.get(pid)['revision'])
            with self.m8.db.transaction() as db:
                current=db.execute('SELECT revision FROM projects WHERE id=?',(pid,)).fetchone()
                if current['revision']!=doc['revision']:raise Conflict(current['revision'])
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m9_items'").fetchone():
                    current_items=[dict(row) for row in db.execute("SELECT * FROM m9_items WHERE json_extract(data,'$.project_id')=? ORDER BY id",(pid,))]
                    if current_items!=m9_items:raise ValueError('Data M9 berubah saat backup')
                    if db.execute("SELECT 1 FROM jobs WHERE kind LIKE '%_m9' AND status IN ('queued','running','cancel_requested') AND json_extract(request,'$.m9.project_id')=? LIMIT 1",(pid,)).fetchone():
                        raise ValueError('Tugas M9 dimulai saat backup')
                    for key,evidence in m9_evidence.items():
                        tracks=[dict(t) for t in db.execute('SELECT * FROM m9_tracks WHERE session_id=?',(key,))]
                        chunks=[dict(c) for t in tracks for c in db.execute('SELECT * FROM m9_chunks WHERE track_id=?',(t['id'],))]
                        if tracks!=evidence['tracks'] or chunks!=evidence['chunks']:raise ValueError('Track/chunk M9 berubah saat backup')
                pending.replace(target)
            return {'url': self.m8.register_file(actor, target, pid), 'content_id': content_id(target, fresh=True),
                'project_revision': doc['revision'], 'source_included': include_source, 'credentials_included': False, 'publish_replay': False}
        finally:
            pending.unlink(missing_ok=True)

    def restore(self, actor, data):
        self.m8.workspaces.require(actor, 'manage')
        if not actor.local:
            raise ValueError('Restore media/path dilakukan operator lokal; sesi server tidak dapat mengimpor akses filesystem dari backup')
        only(data, ('file_id', 'path', 'max_bytes'), ())
        if ('file_id' in data) == ('path' in data):
            raise ValueError('Pilih satu file_id atau path backup lokal')
        if 'path' in data and not actor.local:
            raise ValueError('Path backup host hanya untuk operator lokal')
        source = self.m8.file(actor, data['file_id']) if 'file_id' in data else Path(data['path']).resolve()
        cap = integer(data.get('max_bytes', 30*1024**3), 'Batas restore', 1024, 100*1024**3)
        destination = self.m8.service.work/'m8-restores'/ident('restore');destination.mkdir(parents=True)
        committed = False
        try:
            with zipfile.ZipFile(source) as archive:
                members = archive.infolist()
                if len(members) > 30000 or len({r.filename.casefold() for r in members}) != len(members) or sum(r.file_size for r in members) > cap:
                    raise ValueError('Backup terlalu besar atau memiliki anggota ganda')
                if shutil.disk_usage(destination).free < sum(r.file_size for r in members)+64*1024**2:
                    raise ValueError('Ruang restore tidak cukup')
                for item in members:
                    name = PurePosixPath(item.filename)
                    if name.is_absolute() or '..' in name.parts or '\\' in item.filename or ':' in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Path backup tidak aman')
                manifest = json.loads(archive.read('manifest.json'))
                if manifest.get('kind') != 'clipper_m8_project_backup' or manifest.get('schema_version') not in (1,2):
                    raise ValueError('Schema backup belum didukung')
                if set(manifest['files']) != {r.filename for r in members}-{'manifest.json'}:
                    raise ValueError('Inventaris backup tidak lengkap')
                for name, expected in manifest['files'].items():
                    target = destination/name
                    if not target.resolve().is_relative_to(destination):
                        raise ValueError('Path inventaris tidak aman')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as inp, target.open('wb') as out:
                        shutil.copyfileobj(inp, out, 4*1024**2)
                    if content_id(target, fresh=True) != expected:
                        raise ValueError('Checksum backup berbeda')
            snapshot = json.loads((destination/'snapshot.json').read_text(encoding='utf-8'))
            if snapshot.get('m9_items'):
                self.m8.service.lab  # Additive schema setup before the atomic restore transaction.
            original = snapshot['document'];old_id = original['project_id'];pid = ident('project')
            ids = {old_id: pid}
            for row in snapshot['tables']['transcripts']:
                if row.get('project_id') != old_id:
                    raise ValueError('Transkrip backup berada di luar proyek')
                ids[row['id']] = ident('take')
            m9_items=snapshot.get('m9_items',[])
            if not isinstance(m9_items,list):raise ValueError('Daftar M9 backup tidak valid')
            for row in m9_items:
                if not isinstance(row,dict) or row.get('workspace')!=snapshot.get('source_workspace') or json.loads(row['data']).get('project_id')!=old_id:
                    raise ValueError('Baris M9 backup di luar proyek/workspace')
                if row['id'] in ids:raise ValueError('ID M9 backup ganda')
                ids[row['id']]=ident('m9restored')
            for row in snapshot.get('registries',{}).get('kits5',[]):
                ids[row['id']]=ident('kit')
            paths = {}
            for old, packed in manifest['path_map'].items():
                path = destination/packed
                if not path.resolve().is_relative_to(destination):
                    raise ValueError('Mapping bahan backup tidak aman')
                paths[old] = str(path)
            document = rewrite(original, paths, ids)
            revision = integer(document.pop('revision'), 'Revisi backup');document.pop('updated', None)
            document.update(project_id=pid, name=document.get('name', 'Proyek')+' (dipulihkan)', restored_from=old_id)
            # Current result files remain available as evidence; dependency checks mark
            # paths/config that changed as stale. Remote publication is never resumed.
            with self.m8.db.transaction() as db:
                self.m8.workspaces.require(actor, 'manage', db=db)
                now = self.m8.db.clock()
                db.execute('INSERT INTO projects VALUES(?,?,?,?,?)', (pid, revision, canonical(document), now, now))
                for table in (*TABLES, 'words'):
                    for row in snapshot['tables'].get(table, []):
                        if table == 'words' and row.get('take_id') not in ids or table != 'words' and row.get('project_id') != old_id:
                            raise ValueError('Baris backup berada di luar proyek')
                        allowed = {r['name'] for r in db.execute('PRAGMA table_info('+table+')')}
                        if set(row)!=allowed:
                            raise ValueError('Kolom backup belum didukung')
                        record = rewrite(row, paths, ids)
                        for field in ('document', 'request', 'response', 'changes', 'metadata', 'data', 'diff', 'reviews'):
                            if field in record and isinstance(record[field], str):
                                try:
                                    record[field] = canonical(rewrite(json.loads(record[field]), paths, ids))
                                except ValueError:
                                    raise ValueError('JSON riwayat backup tidak valid') from None
                        if table in ('editor_drafts', 'editor_sync_evidence'):
                            record['id'] = ident('restored')
                        fields = list(record)
                        db.execute('INSERT INTO '+table+'('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')', tuple(record.values()))
                for table,rows in snapshot.get('registries',{}).items():
                    if table not in ('assets5','kits5','kit_history5','asset_history5'):
                        raise ValueError('Registry backup tidak dikenal')
                    for row in rows:
                        fields=list(row)
                        allowed={r['name'] for r in db.execute('PRAGMA table_info('+table+')')}
                        if set(fields)!=allowed:
                            raise ValueError('Schema registry backup tidak cocok')
                        record=rewrite(row,paths,ids);data_row=rewrite(json.loads(record['data']),paths,ids)
                        if table=='assets5':
                            path=Path(data_row['path'])
                            if not path.resolve().is_relative_to(destination) or not path.is_file() or content_id(path,fresh=True)!='sha256:'+data_row['sha256']:
                                raise ValueError('Aset registry backup berubah atau berada di luar paket')
                            existing=db.execute('SELECT data FROM assets5 WHERE id=?',(record['id'],)).fetchone()
                            if existing:
                                old=json.loads(existing['data'])
                                if old.get('sha256')!=data_row['sha256']:
                                    raise ValueError('ID aset backup berbenturan')
                                if Path(old.get('path','')).is_file() and content_id(old['path'],fresh=True)=='sha256:'+data_row['sha256']:
                                    continue
                                db.execute('DELETE FROM assets5 WHERE id=?',(record['id'],))
                        record['data']=canonical(data_row)
                        db.execute('INSERT OR IGNORE INTO '+table+'('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',tuple(record[f] for f in fields))
                db.execute('INSERT INTO m8_projects(project_id,workspace) VALUES(?,?)', (pid, actor.workspace))
                for kind, records in snapshot.get('records', {}).items():
                    if kind not in ('comment', 'effort', 'cost', 'feedback_policy'):
                        raise ValueError('Catatan backup tidak didukung')
                    for row in records:
                        db.execute('INSERT INTO m8_records VALUES(?,?,?,?,?,?,?)', (ident(kind), actor.workspace, kind, 0, canonical(rewrite(row['data'], paths, ids)), now, now))
                if m9_items:
                    # Schema exists on 4.0.22; never executescript inside this transaction.
                    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='m9_items'").fetchone():
                        raise ValueError('Buka studio M9 sekali sebelum memulihkan backup M9')
                for item in m9_items:
                    value=rewrite(json.loads(item['data']),paths,ids)
                    creative=item['kind']=='creative'
                    value.update(status='requires_review' if creative else 'restored_evidence',restored_from_item=item['id'],
                                 restored_evidence_only=not creative,review_required=True,original_kind=item['kind'])
                    if not creative:
                        value['restore_evidence']=rewrite(snapshot.get('m9_evidence',{}).get(item['id'],{}),paths,ids)
                        value['restore_policy']='evidence_only; no job, capture, invitation, provider or publication replay'
                    db.execute('INSERT INTO m9_items VALUES(?,?,?,0,?,?,?)',(ids[item['id']],actor.workspace,'creative' if creative else 'restored_evidence',canonical(value),now,now))
                self.m8.db.event(db, actor.workspace, 'backup.restored', pid, revision, {'original_project_id': old_id, 'mode': 'clone', 'publish_replay': False})
            committed = True
            return {'project_id': pid, 'revision': revision, 'restored_from': old_id, 'workspace': actor.workspace,
                'm9_items_restored':len(m9_items),'m9_executable_state_restored':False,'publish_replay': False, 'account_sessions_restored': False, 'note': 'Periksa relink dan render readiness pada proyek baru; proyek lama tetap tersedia.'}
        finally:
            if not committed:
                shutil.rmtree(destination, ignore_errors=True)

    def diagnostics(self, actor, data):
        only(data, ('project_id',));self.m8.workspaces.require(actor, 'read', data.get('project_id'))
        status = self.m8.status(actor)
        report = {'schema_version': 1, 'version': status['version'], 'mode': status['mode'], 'worker': status['worker'],
            'vault_backend': status['vault']['backend'], 'project_count': len(self.m8.workspaces.projects(actor)),
            'live_acceptance': 'not_tested', 'note': 'Tidak berisi token, path sumber, isi video, transcript, email, atau log mentah. Tinjau sebelum membagikan.'}
        folder = self.m8.service.work/'m8-diagnostics'/ident('diagnostics');folder.mkdir(parents=True)
        target = folder/'diagnostics.json';target.write_text(canonical(report)+'\n', encoding='utf-8')
        return {'url': self.m8.register_file(actor, target, data.get('project_id')), 'preview': report, 'sent_to_anyone': False}
