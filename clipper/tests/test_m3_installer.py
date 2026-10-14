"""Actual M3 overlay/rollback on verified frozen M2. Runtime probe is doubled.

These tests check files, SQLite and recovery; native Windows import/GPU is
explicitly outside this Linux host's evidence.
"""
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
from tools import build_m3_release,complete_installer as installer
from .frozen_release import restore_m2


class M3InstallerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.package=Path(cls.temp.name)/'M3-test-package'
        with contextlib.redirect_stdout(io.StringIO()):cls.report=build_m3_release.build(cls.package,'0'*40)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.target=restore_m2(Path(self.temp.name)/'machine')
        self.work=self.target/'work';self.work.mkdir();self.db=self.work/'studio4.sqlite3'
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE preserved(note TEXT)');db.execute("INSERT INTO preserved VALUES('before')")
        self.user_files={'.env':b'private configuration retained\n','.env.pro':b'private pro configuration retained\n',
            'uploads/source.mp4':b'original source','clips/accepted.mp4':b'previous final','models/local.bin':b'local weights',
            'clipper/fonts/MyCustom.ttf':b'personal font','docs/releases/m0_fixture.zip':b'arbitrary local historical evidence\r\n'}
        for name,data in self.user_files.items():
            p=self.target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.probe=patch.object(installer,'probe_runtime',return_value={'python':'explicit-runtime-double','work_dir':str(self.work)});self.probe.start()
        self.stop=patch.object(installer,'require_stopped',return_value=None);self.stop.start()
        self.output=contextlib.redirect_stdout(io.StringIO());self.output.__enter__()
    def tearDown(self):self.output.__exit__(None,None,None);self.probe.stop();self.stop.stop();self.temp.cleanup()
    def tree(self):
        return {str(p.relative_to(self.target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.target.rglob('*')
            if p.is_file() and 'steezy_backups' not in p.parts and 'work' not in p.parts}
    def test_preflight_declares_verified_m2_github_and_does_not_mutate(self):
        before=self.tree();manifest,changes,_=installer.preflight(self.target,self.package,runtime=False,stopped=False)
        self.assertEqual(manifest['baseline_github_commit'],'b8d12eb972b742a75379c39dc8fa7d35752b9e5e');self.assertEqual(manifest['milestone'],'M3');self.assertTrue(changes)
        self.assertEqual(self.tree(),before);self.assertFalse((self.target/'steezy_backups').exists())
    def test_install_reinstall_and_rollback_preserve_source_fonts_models_config_and_database(self):
        before=self.tree();backup=installer.install(self.target,self.package)
        self.assertTrue((self.target/'clipper/selection_engine.py').is_file());self.assertIsNone(installer.install(self.target,self.package))
        self.assertEqual(installer.preflight(self.target,self.package,runtime=False,stopped=False)[1],[])
        for name,data in self.user_files.items():self.assertEqual((self.target/name).read_bytes(),data)
        installer.rollback(self.target,backup);self.assertEqual(self.tree(),before)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT * FROM preserved').fetchall(),[('before',)])
    def test_unknown_guard_code_blocks_before_backup(self):
        path=self.target/'clipper/transcribe.py';path.write_bytes(path.read_bytes()+b'\n# unrecognized private source edit\n');before=self.tree()
        with self.assertRaisesRegex(ValueError,'transcribe.py'):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before);self.assertFalse((self.target/'steezy_backups').exists())
    def test_collision_with_new_module_is_not_overwritten(self):
        path=self.target/'clipper/selection_index.py';path.write_text('private local module')
        with self.assertRaisesRegex(ValueError,'selection_index.py'):installer.install(self.target,self.package)
        self.assertEqual(path.read_text(),'private local module')
    def test_crlf_text_is_accepted_but_binary_archive_is_strict(self):
        path=self.target/'clipper/config.py';path.write_bytes(path.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
        self.assertTrue(installer.preflight(self.target,self.package,runtime=False,stopped=False)[1])
        p=self.target/'docs/releases/m2_m1_fixture.zip';p.write_bytes(p.read_bytes()+b'tampered')
        with self.assertRaisesRegex(ValueError,'m2_m1_fixture.zip'):installer.preflight(self.target,self.package,runtime=False,stopped=False)
    def test_tampered_payload_and_raw_fixture_fail_before_backup(self):
        for name in ('clipper/selection_contract.py','docs/releases/m3_m2_fixture.zip'):
            package=Path(self.temp.name)/('bad-'+Path(name).stem);shutil.copytree(self.package,package)
            path=package/'payload'/name;path.write_bytes(path.read_bytes()+b'\nchanged')
            with self.assertRaisesRegex(ValueError,'Paket rusak'):installer.install(self.target,package)
        self.assertFalse((self.target/'steezy_backups').exists())
    def test_mid_copy_failure_recovers_original_files_and_local_fixture(self):
        before=self.tree();original=installer.atomic_copy;count=0
        def fail(source,dest):
            nonlocal count
            if 'payload' in Path(source).parts:
                count+=1
                if count==5:raise OSError('controlled copy failure')
            return original(source,dest)
        with patch.object(installer,'atomic_copy',side_effect=fail):
            with self.assertRaises(OSError):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before)
    def test_after_install_probe_failure_recovers_original_files(self):
        before=self.tree()
        def fail(target,after=False):
            if after:raise ValueError('controlled import failure')
            return {'work_dir':str(self.work)}
        with patch.object(installer,'probe_runtime',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'controlled import'):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before)
    def test_advanced_m3_decisions_require_latest_checkpoint_before_state_restore(self):
        backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE projects(id TEXT,document TEXT)')
            db.execute('INSERT INTO projects VALUES(?,?)',('project',json.dumps({'m3_feedback':[{'status':'accepted','reason':'reviewed'}]})))
            db.execute("INSERT INTO preserved VALUES('after')")
        before=self.tree()
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
        self.assertEqual(self.tree(),before);installer.rollback(self.target,backup,restore_project_state=True)
        checkpoint=backup/'data/studio4-latest-before-rollback.sqlite3'
        with sqlite3.connect(checkpoint) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM preserved').fetchone()[0],2)
            self.assertIn('m3_feedback',json.loads(db.execute('SELECT document FROM projects').fetchone()[0]))
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT count(*) FROM preserved').fetchone()[0],1)
    def test_pending_m3_queue_requires_state_restore_even_without_selection_report(self):
        backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE jobs(id TEXT,kind TEXT,status TEXT)');db.execute("INSERT INTO jobs VALUES('job','selection_m3','queued')")
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
    def test_zip_crc_checksums_schema_and_nineteen_requirements(self):
        with zipfile.ZipFile(self.package.with_suffix('.zip')) as z:
            self.assertIsNone(z.testzip());manifest=json.loads(z.read(self.package.name+'/manifest.json'))
            for row in manifest['files']:
                self.assertEqual(hashlib.sha256(z.read(self.package.name+'/payload/'+row['path'])).hexdigest(),row['sha256'])
            trace=json.loads(z.read(self.package.name+'/M3_REQUIREMENTS.json'))
        self.assertEqual({r['id'] for r in trace['requirements']},{'CL'+str(i).zfill(2) for i in range(1,20)})
        self.assertNotIn('docs/releases/m0_fixture.zip',{r['path'] for r in manifest['files']+manifest['guards']})
        self.assertIn('blind_real_corpus_acceptance_pending',trace['gate_g3'])
