"""Actual M4 code/data recovery. Native runtime probe is explicitly doubled."""
import contextlib,hashlib,io,json,shutil,sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from tools import build_m4_release,complete_installer as installer
from .frozen_release import restore_m2,restore_m3_producer,restore_m4_producer

def baseline(path,m3=True):
    restore_m2(path)
    if m3:restore_m3_producer(path)
    return path

class M4InstallerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared=tempfile.TemporaryDirectory();cls.package=Path(cls.shared.name)/'M4-test-package'
        producer=restore_m4_producer(Path(cls.shared.name)/'producer')
        with patch.object(build_m4_release,'ROOT',producer),contextlib.redirect_stdout(io.StringIO()):cls.built=build_m4_release.build(cls.package,'0'*40)
    @classmethod
    def tearDownClass(cls):cls.shared.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.target=baseline(Path(self.temp.name)/'machine');self.work=self.target/'work';self.work.mkdir();self.db=self.work/'studio4.sqlite3'
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE preserved(note TEXT)');db.execute("INSERT INTO preserved VALUES('before')")
        self.private={'.env':b'local setting retained','.env.pro':b'local pro setting retained','uploads/original.mp4':b'user original source','clips/final.mp4':b'previous result','ClipperModels/local.bin':b'user weights','clipper/fonts/Personal.ttf':b'personal font','docs/releases/m0_fixture.zip':b'unknown historical local evidence'}
        for name,data in self.private.items():p=self.target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.probe=patch.object(installer,'probe_runtime',return_value={'python':'explicit-runtime-double','work_dir':str(self.work)});self.probe.start();self.stop=patch.object(installer,'require_stopped',return_value=None);self.stop.start();self.out=contextlib.redirect_stdout(io.StringIO());self.out.__enter__()
    def tearDown(self):self.out.__exit__(None,None,None);self.probe.stop();self.stop.stop();self.temp.cleanup()
    def tree(self):return {str(p.relative_to(self.target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.target.rglob('*') if p.is_file() and 'steezy_backups' not in p.parts and 'work' not in p.parts}
    def test_M3_and_M2_baselines_preflight_and_dry_run(self):
        before=self.tree();m,changes,_=installer.preflight(self.target,self.package,runtime=False,stopped=False);self.assertEqual(m['milestone'],'M4');self.assertTrue(changes);installer.install(self.target,self.package,dry_run=True);self.assertEqual(self.tree(),before);self.assertFalse((self.target/'steezy_backups').exists())
        m2=baseline(Path(self.temp.name)/'m2',False);self.assertTrue(installer.preflight(m2,self.package,runtime=False,stopped=False)[1])
    def test_install_idempotence_and_rollback_preserve_private_files_and_SQLite(self):
        before=self.tree();backup=installer.install(self.target,self.package);self.assertTrue((self.target/'clipper/camera4_contract.py').is_file());self.assertIsNone(installer.install(self.target,self.package));self.assertEqual(installer.preflight(self.target,self.package,runtime=False,stopped=False)[1],[])
        for name,data in self.private.items():self.assertEqual((self.target/name).read_bytes(),data)
        installer.rollback(self.target,backup);self.assertEqual(self.tree(),before)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT * FROM preserved').fetchall(),[('before',)])
    def test_unknown_guard_and_new_module_collision_block_before_backup(self):
        for name in ('clipper/transcribe.py','clipper/camera4_contract.py'):
            path=self.target/name;existed=path.exists();old=path.read_bytes() if existed else None;path.write_bytes(b'unknown local source');before=self.tree()
            with self.assertRaisesRegex(ValueError,'Kode lokal berbeda'):installer.install(self.target,self.package)
            self.assertEqual(self.tree(),before)
            if existed:path.write_bytes(old)
            else:path.unlink()
        self.assertFalse((self.target/'steezy_backups').exists())
    def test_payload_or_frozen_archive_tampering_fails_before_backup(self):
        for name in ('clipper/camera4_plan.py','docs/releases/m4_m3_producer.zip'):
            package=Path(self.temp.name)/('bad-'+Path(name).stem);shutil.copytree(self.package,package);p=package/'payload'/name;p.write_bytes(p.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'Paket rusak'):installer.install(self.target,package)
        self.assertFalse((self.target/'steezy_backups').exists())
    def test_mid_copy_failure_recovers_complete_source(self):
        before=self.tree();original=installer.atomic_copy;count=0
        def fail(source,dest):
            nonlocal count
            if 'payload' in Path(source).parts:
                count+=1
                if count==5:raise OSError('controlled failure')
            return original(source,dest)
        with patch.object(installer,'atomic_copy',side_effect=fail):
            with self.assertRaises(OSError):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before)
    def test_post_install_probe_failure_recovers_complete_source(self):
        before=self.tree()
        def probe(target,after=False):
            if after:raise ValueError('controlled probe failure')
            return {'work_dir':str(self.work)}
        with patch.object(installer,'probe_runtime',side_effect=probe):
            with self.assertRaisesRegex(ValueError,'controlled probe'):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before)
    def test_M4_state_requires_latest_checkpoint_before_restore(self):
        before=self.tree();backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE projects(id TEXT,document TEXT)');db.execute('INSERT INTO projects VALUES(?,?)',('p',json.dumps({'clips':{'c':{'variants':{'portrait':{'camera4_feedback':[{'accepted':True}]}}}}})));db.execute("INSERT INTO preserved VALUES('after')")
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
        installer.rollback(self.target,backup,restore_project_state=True);self.assertEqual(self.tree(),before)
        with sqlite3.connect(backup/'data/studio4-latest-before-rollback.sqlite3') as db:self.assertEqual(db.execute('SELECT count(*) FROM preserved').fetchone()[0],2)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT count(*) FROM preserved').fetchone()[0],1)
    def test_M4_pending_queue_is_protected_without_report(self):
        backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE jobs(id TEXT,kind TEXT,status TEXT)');db.execute("INSERT INTO jobs VALUES('job','camera_m4','queued')")
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
    def test_existing_M3_data_is_not_lost_when_rolling_back_to_M3(self):
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE projects(id TEXT,document TEXT)');db.execute('INSERT INTO projects VALUES(?,?)',('p',json.dumps({'m3_feedback':[{'status':'accepted'}]})))
        backup=installer.install(self.target,self.package);record=json.loads((backup/'complete-backup.json').read_text());self.assertTrue(record['baseline_version'].startswith('4.0.14'))
        installer.rollback(self.target,backup)
        with sqlite3.connect(self.db) as db:self.assertIn('m3_feedback',json.loads(db.execute('SELECT document FROM projects').fetchone()[0]))
    def test_CRLF_checkout_accepted_and_local_fixture_excluded(self):
        p=self.target/'clipper/config.py';p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'));m,changes,_=installer.preflight(self.target,self.package,runtime=False,stopped=False);self.assertTrue(changes);self.assertNotIn('docs/releases/m0_fixture.zip',{r['path'] for r in m['files']+m['guards']})
    def test_archive_crc_source_hashes_and_VF01_to_VF17(self):
        with zipfile.ZipFile(self.package.with_suffix('.zip')) as z:
            self.assertIsNone(z.testzip());m=json.loads(z.read(self.package.name+'/manifest.json'))
            for row in m['files']:self.assertEqual(hashlib.sha256(z.read(self.package.name+'/payload/'+row['path'])).hexdigest(),row['sha256'])
            trace=json.loads(z.read(self.package.name+'/M4_REQUIREMENTS.json'))
        self.assertEqual({r['id'] for r in trace['requirements']},{'VF'+str(i).zfill(2) for i in range(1,18)});self.assertEqual(trace['gate_g4'],'pending_real_corpus')
