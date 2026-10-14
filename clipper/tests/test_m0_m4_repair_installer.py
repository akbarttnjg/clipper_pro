"""Recoverable 4.0.15.1 overlay on frozen releases; runtime stub labelled explicitly."""
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
from tools import build_m0_m4_repair_release as builder,complete_installer as installer
from .frozen_release import _restore,restore_m1,restore_m2,restore_m3_producer,restore_m4_audit,restore_m4_fixed_producer
from .test_m1_installer import restore_baseline


class RepairInstallerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.package=Path(cls.tmp.name)/'repair-package'
        producer=restore_m4_fixed_producer(Path(cls.tmp.name)/'producer')
        with patch.object(builder,'ROOT',producer),contextlib.redirect_stdout(io.StringIO()):cls.report=builder.build(cls.package,'0'*40)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.target=Path(self.t.name)/'machine';self.target.mkdir()
        root=Path(__file__).resolve().parents[2]
        meta=json.loads((root/'docs/releases/m0_m2_repair_fixture_provenance.json').read_text())
        _restore(self.target,root/'docs/releases/m0_m2_repair_m2_fixture.zip',meta)
        self.probe=patch.object(installer,'probe_runtime',return_value={'python':'explicit unit double','work_dir':str(self.target/'work')});self.probe.start()
        for rel in ['work/user.bin','clips/user.mp4','uploads/user.wav','models/user.bin','.env','docs/releases/m0_fixture.zip']:
            p=self.target/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'personal exact bytes\r\n')
        self.db=self.target/'work/studio4.sqlite3'
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE projects(id TEXT PRIMARY KEY,document TEXT)');db.execute('INSERT INTO projects VALUES(?,?)',('prior',json.dumps({'clips':{}})))
    def tearDown(self):self.probe.stop();self.t.cleanup()
    def user_hashes(self):
        return {str(p.relative_to(self.target)):hashlib.sha256(p.read_bytes()).hexdigest() for d in ['work','clips','uploads','models'] for p in (self.target/d).rglob('*') if p.is_file()}
    def code_tree(self):
        return {str(p.relative_to(self.target)):p.read_bytes() for p in self.target.rglob('*') if p.is_file() and 'steezy_backups' not in p.parts}
    def test_check_install_reinstall_rollback_and_user_bytes(self):
        before=self.code_tree();users=self.user_hashes();legacy=(self.target/'docs/releases/m0_fixture.zip').read_bytes()
        installer.install(self.target,self.package,dry_run=True);self.assertEqual(self.code_tree(),before)
        backup=installer.install(self.target,self.package);self.assertEqual(self.user_hashes(),users)
        self.assertIn('4.0.15.1',(self.target/'static/index.html').read_text());self.assertIsNone(installer.install(self.target,self.package))
        self.assertEqual((self.target/'docs/releases/m0_fixture.zip').read_bytes(),legacy)
        installer.rollback(self.target,backup);self.assertEqual(self.code_tree(),before)
    def test_installs_over_frozen_m0(self):
        import shutil
        shutil.rmtree(self.target);restore_baseline(self.target)
        installer.install(self.target,self.package);self.assertTrue((self.target/'clipper/source_imports.py').is_file())
    def test_installs_over_frozen_m1(self):
        import shutil
        shutil.rmtree(self.target);self.target.mkdir();restore_m1(self.target)
        installer.install(self.target,self.package);self.assertTrue((self.target/'static/features/editor_clock.js').is_file())
    def test_unknown_code_edit_is_rejected_before_first_write(self):
        p=self.target/'clipper/pipeline.py';p.write_text(p.read_text()+'\n# local unknown edit\n');before=self.code_tree()
        with self.assertRaises(ValueError):installer.install(self.target,self.package)
        self.assertEqual(self.code_tree(),before)
    def test_partial_copy_failure_rolls_back_all_code_and_keeps_database(self):
        before=self.code_tree();copy=installer.atomic_copy;seen=[]
        def fail(source,dest):
            if 'payload' in Path(source).parts:
                seen.append(str(dest))
                if len(seen)==3:raise OSError('controlled copy fault')
            return copy(source,dest)
        with patch.object(installer,'atomic_copy',side_effect=fail):
            with self.assertRaises(OSError):installer.install(self.target,self.package)
        self.assertEqual(self.code_tree(),before)
    def test_advanced_state_rollback_keeps_latest_checkpoint(self):
        backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:db.execute('INSERT INTO projects VALUES(?,?)',('new',json.dumps({'m3_feedback':[{'status':'accepted'}],'clips':{}})))
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
        installer.rollback(self.target,backup,restore_project_state=True)
        checkpoint=backup/'data/studio4-latest-before-rollback.sqlite3'
        with sqlite3.connect(checkpoint) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM projects').fetchone()[0],2);self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM projects').fetchone()[0],1)
    def test_zip_payload_crc_sha_and_protected_fixture(self):
        with zipfile.ZipFile(self.package.with_suffix('.zip')) as z:
            self.assertIsNone(z.testzip());manifest=json.loads(z.read(self.package.name+'/manifest.json'))
            self.assertEqual(manifest['version'],'4.0.15.1')
            self.assertNotIn('docs/releases/m0_fixture.zip',{r['path'] for r in manifest['files']+manifest['guards']})
            for row in manifest['files']:self.assertEqual(hashlib.sha256(z.read(self.package.name+'/payload/'+row['path'])).hexdigest(),row['sha256'])

    def test_installs_and_rolls_back_exact_public_m4_preserving_new_m4_data(self):
        import shutil
        shutil.rmtree(self.target);restore_m4_audit(self.target)
        self.db=self.target/'work/studio4.sqlite3';self.db.parent.mkdir()
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE projects(id TEXT PRIMARY KEY,document TEXT)')
        before=self.code_tree();backup=installer.install(self.target,self.package)
        document={'m3_feedback':[{'status':'accepted'}],'clips':{'c':{'variants':{'square':{'camera4_controls':{'motion':'static'},'camera4_feedback':[{'accepted':True}],'camera4_ratio':{'width':1080,'height':1080}}}}}}
        with sqlite3.connect(self.db) as db:db.execute('INSERT INTO projects VALUES(?,?)',('after',json.dumps(document)))
        installer.rollback(self.target,backup)
        with sqlite3.connect(self.db) as db:self.assertEqual(json.loads(db.execute('SELECT document FROM projects').fetchone()[0]),document)
        for name,data in before.items():
            if name!='work/studio4.sqlite3':self.assertEqual((self.target/name).read_bytes(),data)
    def test_installs_over_frozen_m3_and_protects_m4_queue_on_rollback(self):
        import shutil
        shutil.rmtree(self.target);restore_m2(self.target);restore_m3_producer(self.target)
        self.db=self.target/'work/studio4.sqlite3';self.db.parent.mkdir()
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE jobs(id TEXT,kind TEXT,status TEXT)')
        backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:db.execute("INSERT INTO jobs VALUES('job','camera_m4','queued')")
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
        installer.rollback(self.target,backup,restore_project_state=True)
        with sqlite3.connect(backup/'data/studio4-latest-before-rollback.sqlite3') as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
    def test_m2_state_survives_code_rollback_to_m2(self):
        backup=installer.install(self.target,self.package)
        document={'source':{'info':{'kind':'audio'}},'source_timing_overrides':{'0':{'start':.1,'end':.5}},'clips':{}}
        with sqlite3.connect(self.db) as db:db.execute('INSERT INTO projects VALUES(?,?)',('new',json.dumps(document)))
        installer.rollback(self.target,backup)
        with sqlite3.connect(self.db) as db:self.assertEqual(json.loads(db.execute("SELECT document FROM projects WHERE id='new'").fetchone()[0]),document)
