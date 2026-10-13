"""Exercise code installation/rollback on the frozen M0 production baseline.

Filesystem, SQLite and checksum checks are real. Runtime dependency probing is
stubbed: this environment has no full FastAPI/.venv installation to import.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import build_m1_release, complete_installer as installer

ROOT = Path(__file__).resolve().parents[2]


def restore_baseline(target):
    target.mkdir()
    with zipfile.ZipFile(ROOT / 'docs/releases/m1_fixture.zip') as zipped:
        info = json.loads(zipped.read('__provenance__.json'))
        if info['github_commit'] != 'b8c4ce275021a7b09db2710939a4c063b754f35b':
            raise ValueError('M0 fixture provenance mismatch')
        for name, expected in info['raw_sha256'].items():
            data = zipped.read(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('Frozen M0 checksum mismatch: '+name)
            dest = installer.safe_path(target, name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    return target


class InstallerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package_temp = tempfile.TemporaryDirectory()
        cls.package = Path(cls.package_temp.name) / 'M1-test-package'
        with contextlib.redirect_stdout(io.StringIO()):
            cls.report = build_m1_release.build(cls.package, '0'*40)

    @classmethod
    def tearDownClass(cls):
        cls.package_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.target = restore_baseline(Path(self.temp.name) / 'machine')
        self.work = self.target / 'work'
        self.work.mkdir()
        self.database = self.work / 'studio4.sqlite3'
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE preserved(note TEXT)')
            db.execute("INSERT INTO preserved VALUES('before')")
        for name, value in [('.env', b'USER_SETTING=preserve\n'),
                            ('clipper/fonts/MyCustom.ttf', b'custom-font'),
                            ('ClipperModels/custom.bin', b'user-model'),
                            ('clips/user-result.mp4', b'user-result'),
                            ('uploads/user-source.mp4', b'user-source')]:
            dest = self.target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(value)
        self.runtime = patch.object(installer, 'probe_runtime', return_value={
            'python': 'stubbed', 'work_dir': str(self.work)})
        self.stopped = patch.object(installer, 'require_stopped', return_value=None)
        self.runtime.start()
        self.stopped.start()
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)
        self.stopped.stop()
        self.runtime.stop()
        self.temp.cleanup()

    def code(self):
        with zipfile.ZipFile(ROOT / 'docs/releases/m1_fixture.zip') as zipped:
            names = json.loads(zipped.read('__provenance__.json'))['raw_sha256']
        return {name: (self.target / name).read_bytes() for name in names}

    def test_install_backup_idempotence_and_rollback_preserve_later_database_edits(self):
        before = self.code()
        manifest, changes, _ = installer.preflight(self.target, self.package)
        self.assertEqual(manifest['milestone'], 'M1')
        self.assertTrue(changes)
        backup = installer.install(self.target, self.package)
        self.assertIsNone(installer.install(self.target, self.package))
        record = json.loads((backup / 'complete-backup.json').read_text())
        with sqlite3.connect(record['database_backup']['copy']) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT * FROM preserved').fetchall(), [('before',)])
        with sqlite3.connect(self.database) as db:
            db.execute("INSERT INTO preserved VALUES('after')")
        installer.rollback(self.target, backup)
        self.assertEqual(self.code(), before)
        self.assertFalse((self.target / 'static/features/editor_state.js').exists())
        self.assertEqual((self.target / '.env').read_bytes(), b'USER_SETTING=preserve\n')
        self.assertEqual((self.target / 'clipper/fonts/MyCustom.ttf').read_bytes(), b'custom-font')
        self.assertEqual((self.target / 'ClipperModels/custom.bin').read_bytes(), b'user-model')
        self.assertEqual((self.target / 'clips/user-result.mp4').read_bytes(), b'user-result')
        self.assertEqual((self.target / 'uploads/user-source.mp4').read_bytes(), b'user-source')
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM preserved').fetchone()[0], 2)

    def test_unknown_baseline_code_is_rejected_before_backup(self):
        code = self.target / 'clipper/render.py'
        code.write_bytes(code.read_bytes()+b'\n# local edit\n')
        with self.assertRaisesRegex(ValueError, 'Kode lokal berbeda'):
            installer.install(self.target, self.package)
        self.assertFalse((self.target / 'steezy_backups').exists())

    def test_existing_unknown_new_module_is_not_overwritten(self):
        code = self.target / 'static/features/editor_state.js'
        code.write_text('// existing local module\n')
        with self.assertRaisesRegex(ValueError, 'Kode lokal berbeda'):
            installer.preflight(self.target, self.package)
        self.assertEqual(code.read_text(), '// existing local module\n')

    def test_tampered_payload_rejected_before_install(self):
        import shutil
        package = Path(self.temp.name) / 'tampered'
        shutil.copytree(self.package, package)
        (package / 'payload/clipper/project_store.py').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'rusak'):
            installer.install(self.target, package)
        self.assertFalse((self.target / 'steezy_backups').exists())

    def test_mid_copy_failure_recovers_original_code(self):
        before = self.code()
        copy_file = installer.atomic_copy
        count = 0
        def controlled(source, dest):
            nonlocal count
            if 'payload' in Path(source).parts:
                count += 1
                if count == 5:
                    raise OSError('controlled ENOSPC')
            return copy_file(source, dest)
        with patch.object(installer, 'atomic_copy', controlled), self.assertRaisesRegex(OSError, 'ENOSPC'):
            installer.install(self.target, self.package)
        self.assertEqual(self.code(), before)
        self.assertFalse((self.target / 'static/features/editor_state.js').exists())
        journal = next((self.target / 'steezy_backups').glob('complete-*/complete-backup.json'))
        self.assertEqual(json.loads(journal.read_text())['status'], 'restored')

    def test_post_install_probe_failure_recovers_original_code(self):
        before = self.code()
        def probe(target, after=False):
            if after:
                raise ValueError('controlled import failure')
            return {'python': 'stubbed', 'work_dir': str(self.work)}
        with patch.object(installer, 'probe_runtime', probe), self.assertRaisesRegex(ValueError, 'import failure'):
            installer.install(self.target, self.package)
        self.assertEqual(self.code(), before)
        self.assertFalse((self.target / 'static/features/editor_state.js').exists())

    def test_windows_newlines_are_accepted_and_preserved_in_backup(self):
        code = self.target / 'clipper/studio_service.py'
        windows = code.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        code.write_bytes(windows)
        installer.preflight(self.target, self.package)
        backup = installer.install(self.target, self.package)
        installer.rollback(self.target, backup)
        self.assertEqual(code.read_bytes(), windows)

    def test_archive_crc_hashes_and_no_user_data_payload(self):
        self.assertEqual(self.report['zip_crc'], 'passed')
        with zipfile.ZipFile(self.report['archive']) as zipped:
            self.assertIsNone(zipped.testzip())
            prefix = self.package.name+'/'
            manifest = json.loads(zipped.read(prefix+'manifest.json'))
            for row in manifest['files']:
                self.assertEqual(hashlib.sha256(zipped.read(prefix+'payload/'+row['path'])).hexdigest(), row['sha256'])
                self.assertNotIn(row['path'].split('/')[0], ['.env', '.env.pro', 'work', 'clips', 'uploads', '.venv', 'ClipperModels', 'models'])
            with zipfile.ZipFile(ROOT / 'docs/releases/m1_fixture.zip') as frozen:
                self.assertFalse(any(name.endswith(('.mp4', '.env', '.env.pro')) for name in frozen.namelist()))

    def test_advanced_project_rollback_requires_explicit_checkpoint_choice(self):
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE projects(id TEXT PRIMARY KEY,document TEXT)')
            db.execute('INSERT INTO projects VALUES(?,?)',('p',json.dumps({'clips':{}})))
        before=self.code();backup=installer.install(self.target,self.package)
        advanced={'clips':{'c':{'variants':{'portrait':{'editor':{'segments':[{'id':'edit'}]}}}}}}
        with sqlite3.connect(self.database) as db:db.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(advanced),'p'))
        installed=self.code()
        with self.assertRaisesRegex(ValueError,'tidak dikenali kode lama'):installer.rollback(self.target,backup)
        self.assertEqual(self.code(),installed)
        with sqlite3.connect(self.database) as db:self.assertEqual(json.loads(db.execute('SELECT document FROM projects').fetchone()[0]),advanced)
        installer.rollback(self.target,backup,restore_project_state=True)
        self.assertEqual(self.code(),before)
        record=json.loads((backup/'complete-backup.json').read_text())
        checkpoint=Path(record['latest_project_checkpoint']['path'])
        self.assertEqual(hashlib.sha256(checkpoint.read_bytes()).hexdigest(),record['latest_project_checkpoint']['sha256'])
        with sqlite3.connect(checkpoint) as db:self.assertEqual(json.loads(db.execute('SELECT document FROM projects').fetchone()[0]),advanced)
        with sqlite3.connect(self.database) as db:self.assertEqual(json.loads(db.execute('SELECT document FROM projects').fetchone()[0]),{'clips':{}})

    def test_first_m1_baseline_can_upgrade_and_return_without_losing_files(self):
        # Materialize the exact first-M1 files recorded in the accepted hash set.
        with zipfile.ZipFile(ROOT/'docs/releases/m1_initial_fixture.zip') as archive:
            provenance=json.loads(archive.read('__provenance__.json'))
            self.assertEqual(provenance['local_commit'],'dea470c7a486ab65514dff96c92b332b7ffc1062')
            for name,expected in provenance['raw_sha256'].items():
                data=archive.read(name)
                self.assertEqual(hashlib.sha256(data).hexdigest(),expected)
                path=installer.safe_path(self.target,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        manifest,changed,_=installer.preflight(self.target,self.package)
        self.assertEqual(manifest['version'],'4.0.12');self.assertTrue(changed)
        before=self.code();backup=installer.install(self.target,self.package)
        installer.rollback(self.target,backup)
        self.assertEqual(self.code(),before)


if __name__ == '__main__':
    unittest.main()
