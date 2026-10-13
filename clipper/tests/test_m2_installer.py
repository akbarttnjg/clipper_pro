"""Real M2 overlay/rollback tests on frozen M0/M1; runtime probe is explicitly stubbed."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from tools import build_m2_release,complete_installer as installer
from .frozen_release import restore_m1
from .test_m1_installer import restore_baseline


class M2InstallerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.package=Path(cls.temp.name)/'M2-test-package'
        with contextlib.redirect_stdout(io.StringIO()):cls.report=build_m2_release.build(cls.package,'0'*40)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.target=restore_m1(Path(self.temp.name)/'machine');self.work=self.target/'work';self.work.mkdir();self.db=self.work/'studio4.sqlite3'
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE preserved(note TEXT)');db.execute("INSERT INTO preserved VALUES('before')")
        self.user_files={'.env':b'PRIVATE_SETTING=preserve\n','uploads/source.wav':b'user source','clips/final.mp4':b'user result','clipper/fonts/MyCustom.ttf':b'font bytes','ClipperModels/local.bin':b'model bytes'}
        for name,data in self.user_files.items():path=self.target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        self.probe=patch.object(installer,'probe_runtime',return_value={'python':'explicit_runtime_double','work_dir':str(self.work)});self.probe.start();self.stop=patch.object(installer,'require_stopped',return_value=None);self.stop.start();self.output=contextlib.redirect_stdout(io.StringIO());self.output.__enter__()
    def tearDown(self):self.output.__exit__(None,None,None);self.probe.stop();self.stop.stop();self.temp.cleanup()
    def tree(self):return {str(p.relative_to(self.target)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('clipper','static','docs','tools') for p in (self.target/folder).rglob('*') if p.is_file()}
    def test_preflight_complete_m1_and_frozen_m0(self):
        manifest,changes,_=installer.preflight(self.target,self.package,runtime=False,stopped=False);self.assertEqual(manifest['milestone'],'M2');self.assertTrue(changes)
        m0=restore_baseline(Path(self.temp.name)/'m0');self.assertTrue(installer.preflight(m0,self.package,runtime=False,stopped=False)[1])
    def test_dry_run_does_not_change_any_code_or_data(self):
        before=self.tree();installer.install(self.target,self.package,dry_run=True);self.assertEqual(self.tree(),before);self.assertFalse((self.target/'steezy_backups').exists())
    def test_install_idempotence_and_rollback_preserve_user_data(self):
        before=self.tree();backup=installer.install(self.target,self.package);self.assertTrue((self.target/'clipper/transcript_tracks.py').is_file());self.assertEqual(installer.preflight(self.target,self.package,runtime=False,stopped=False)[1],[])
        installer.rollback(self.target,backup);self.assertEqual(self.tree(),before)
        for name,data in self.user_files.items():self.assertEqual((self.target/name).read_bytes(),data)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT * FROM preserved').fetchall(),[('before',)])
    def test_tampered_payload_rejected_before_backup(self):
        package=Path(self.temp.name)/'tampered';shutil.copytree(self.package,package);(package/'payload/clipper/transcript_tracks.py').write_text('tampered')
        with self.assertRaises(ValueError):installer.install(self.target,package)
        self.assertFalse((self.target/'steezy_backups').exists())
    def test_unknown_local_source_code_is_not_overwritten(self):
        p=self.target/'clipper/transcribe.py';p.write_bytes(p.read_bytes()+b'\n# local edit\n')
        with self.assertRaisesRegex(ValueError,'Kode lokal berbeda'):installer.install(self.target,self.package)
        self.assertFalse((self.target/'steezy_backups').exists())
    def test_unknown_existing_new_module_is_not_overwritten(self):
        p=self.target/'clipper/transcript_tracks.py';p.write_text('local code')
        with self.assertRaises(ValueError):installer.install(self.target,self.package)
        self.assertEqual(p.read_text(),'local code')
    def test_mid_copy_failure_recovers_original_code(self):
        before=self.tree();original=installer.atomic_copy;count=0
        def failing(src,dest):
            nonlocal count
            if 'payload' in Path(src).parts:
                count+=1
                if count==4:raise OSError('controlled copy failure')
            return original(src,dest)
        with patch.object(installer,'atomic_copy',side_effect=failing):
            with self.assertRaises(OSError):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before)
    def test_after_install_runtime_failure_recovers_original_code(self):
        before=self.tree()
        def fail(target,after=False):
            if after:raise ValueError('controlled import failure')
            return {'python':'double','work_dir':str(self.work)}
        with patch.object(installer,'probe_runtime',side_effect=fail):
            with self.assertRaises(ValueError):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before)
    def test_m2_project_rollback_requires_checkpointed_state_restore(self):
        backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE projects(id TEXT,document TEXT)');db.execute('INSERT INTO projects VALUES(?,?)',('project',json.dumps({'translation_tracks':{'translation':{'approved':True}}})));db.execute("INSERT INTO preserved VALUES('after')")
        before=self.tree()
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
        self.assertEqual(self.tree(),before);installer.rollback(self.target,backup,restore_project_state=True)
        checkpoint=backup/'data/studio4-latest-before-rollback.sqlite3';self.assertTrue(checkpoint.is_file())
        with sqlite3.connect(checkpoint) as db:self.assertEqual(db.execute('SELECT count(*) FROM preserved').fetchone()[0],2)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT count(*) FROM preserved').fetchone()[0],1)
    def test_active_m2_import_queue_blocks_code_only_rollback(self):
        backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE m2_imports(status TEXT)');db.execute("INSERT INTO m2_imports VALUES('queued')")
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
    def test_archive_crc_and_payload_members_verify(self):
        import zipfile
        with zipfile.ZipFile(self.package.with_suffix('.zip')) as z:
            self.assertIsNone(z.testzip());manifest=json.loads(z.read(self.package.name+'/manifest.json'))
            for row in manifest['files']:self.assertEqual(hashlib.sha256(z.read(self.package.name+'/payload/'+row['path'])).hexdigest(),row['sha256'])
    def legacy_fixture(self, data=b'locally generated historical QA archive\r\n'):
        path=self.target/'docs/releases/m0_fixture.zip';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        return path
    def test_unknown_local_fixture_survives_check_install_reinstall_and_rollback(self):
        path=self.legacy_fixture();original=path.read_bytes();before=self.tree()
        installer.install(self.target,self.package,dry_run=True)
        self.assertEqual(self.tree(),before);self.assertFalse((self.target/'steezy_backups').exists())
        backup=installer.install(self.target,self.package)
        self.assertEqual(path.read_bytes(),original);self.assertIsNone(installer.install(self.target,self.package))
        record=json.loads((backup/'complete-backup.json').read_text())
        self.assertNotIn('docs/releases/m0_fixture.zip',{row['path'] for row in record['files']})
        installer.rollback(self.target,backup);self.assertEqual(self.tree(),before);self.assertEqual(path.read_bytes(),original)
    def test_equivalent_repacked_fixture_no_longer_blocks_installation(self):
        original=self.package/'payload/docs/releases/m2_m0_fixture.zip';path=self.legacy_fixture()
        with zipfile.ZipFile(original) as source,zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as dest:
            for name in source.namelist():
                info=zipfile.ZipInfo(name,date_time=(2026,10,12,0,0,0));info.create_system=0;info.external_attr=0;info.compress_type=zipfile.ZIP_DEFLATED;dest.writestr(info,source.read(name))
        with zipfile.ZipFile(original) as source,zipfile.ZipFile(path) as repacked:
            self.assertEqual(source.namelist(),repacked.namelist())
            self.assertTrue(all(source.read(name)==repacked.read(name) for name in source.namelist()))
        self.assertNotEqual(path.read_bytes(),original.read_bytes());before=path.read_bytes()
        installer.install(self.target,self.package);self.assertEqual(path.read_bytes(),before)
    def test_legacy_fixture_is_not_created_on_clean_github_checkout(self):
        path=self.target/'docs/releases/m0_fixture.zip';self.assertFalse(path.exists())
        installer.install(self.target,self.package)
        self.assertFalse(path.exists());self.assertTrue((self.target/'docs/releases/m2_m0_fixture.zip').is_file())
    def test_legacy_fixture_folder_is_also_left_untouched(self):
        path=self.target/'docs/releases/m0_fixture.zip';path.mkdir(parents=True)
        (path/'local.txt').write_bytes(b'local evidence')
        installer.install(self.target,self.package)
        self.assertEqual((path/'local.txt').read_bytes(),b'local evidence')
    def test_local_fixture_preserved_when_copy_fails(self):
        path=self.legacy_fixture();before=self.tree();original=installer.atomic_copy;count=0
        def fail(source,dest):
            nonlocal count
            if 'payload' in Path(source).parts:
                count+=1
                if count==4:raise OSError('controlled fixture preservation failure')
            return original(source,dest)
        with patch.object(installer,'atomic_copy',side_effect=fail):
            with self.assertRaises(OSError):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before);self.assertEqual(path.read_bytes(),b'locally generated historical QA archive\r\n')
    def test_local_fixture_preserved_when_after_install_probe_fails(self):
        self.legacy_fixture();before=self.tree()
        def fail(target,after=False):
            if after:raise ValueError('controlled post-install failure')
            return {'work_dir':str(self.work)}
        with patch.object(installer,'probe_runtime',side_effect=fail):
            with self.assertRaises(ValueError):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before)
    def test_ignoring_legacy_fixture_does_not_bypass_source_guard(self):
        path=self.legacy_fixture();code=self.target/'app.py';code.write_bytes(code.read_bytes()+b'\n# unrecognized local code\n');before=self.tree()
        with self.assertRaisesRegex(ValueError,'app.py'):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before);self.assertFalse((self.target/'steezy_backups').exists());self.assertTrue(path.is_file())
    def test_crlf_source_checkout_is_still_supported(self):
        code=self.target/'clipper/transcribe.py';code.write_bytes(code.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
        self.assertTrue(installer.preflight(self.target,self.package,runtime=False,stopped=False)[1])
    def test_versioned_fixture_tampering_is_rejected_before_backup(self):
        package=Path(self.temp.name)/'tampered-fixture';shutil.copytree(self.package,package);path=package/'payload/docs/releases/m2_m0_fixture.zip';path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'Paket rusak'):installer.install(self.target,package)
        self.assertFalse((self.target/'steezy_backups').exists())
    def test_manifest_declares_preservation_and_raw_binary_checksums(self):
        manifest=installer.load_manifest(self.package);self.assertEqual(manifest['installer_revision'],1)
        self.assertEqual(manifest['preserved_local_files'],['docs/releases/m0_fixture.zip'])
        self.assertNotIn('docs/releases/m0_fixture.zip',{r['path'] for r in manifest['files']+manifest['guards']})
        for row in manifest['files']:
            self.assertEqual(row['baseline_checksum'],'sha256' if row['path'].endswith('.zip') else 'sha256-lf')
