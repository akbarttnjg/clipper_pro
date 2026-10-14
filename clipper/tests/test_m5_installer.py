"""Actual code/SQLite recovery, with explicitly doubled native runtime probes."""
import contextlib,hashlib,io,json,shutil,sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from tools import build_m5_release,complete_installer as installer
from .frozen_release import restore_m2,restore_m3_producer,restore_m4_producer
def baseline(path,version='m4'):
    restore_m2(path)
    if version in ('m3','m4'):restore_m3_producer(path)
    if version=='m4':restore_m4_producer(path)
    return path
class M5InstallerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared=tempfile.TemporaryDirectory();cls.package=Path(cls.shared.name)/'M5-test-package'
        with contextlib.redirect_stdout(io.StringIO()):cls.built=build_m5_release.build(cls.package,'0'*40)
    @classmethod
    def tearDownClass(cls):cls.shared.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.target=baseline(Path(self.temp.name)/'machine');self.work=self.target/'work';self.work.mkdir();self.db=self.work/'studio4.sqlite3'
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE preserved(note TEXT)');db.execute("INSERT INTO preserved VALUES('before')")
        self.private={'.env':b'local retained','.env.pro':b'pro retained','uploads/original.mp4':b'user source','clips/final.mp4':b'previous final','ClipperModels/local.bin':b'user weights','clipper/fonts/Personal.ttf':b'user font','docs/releases/m0_fixture.zip':b'unknown local evidence'}
        for name,data in self.private.items():p=self.target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.probe=patch.object(installer,'probe_runtime',return_value={'python':'explicit native-runtime protocol double','work_dir':str(self.work)});self.probe.start();self.stop=patch.object(installer,'require_stopped',return_value=None);self.stop.start();self.output=contextlib.redirect_stdout(io.StringIO());self.output.__enter__()
    def tearDown(self):self.output.__exit__(None,None,None);self.probe.stop();self.stop.stop();self.temp.cleanup()
    def tree(self):return {str(p.relative_to(self.target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.target.rglob('*') if p.is_file() and 'steezy_backups' not in p.parts and 'work' not in p.parts}
    def test_M2_M3_M4_baselines_preflight_without_mutating(self):
        before=self.tree()
        for version in ('m2','m3','m4'):
            target=baseline(Path(self.temp.name)/version,version);m,changes,_=installer.preflight(target,self.package,runtime=False,stopped=False);self.assertEqual(m['milestone'],'M5');self.assertTrue(changes)
        installer.install(self.target,self.package,dry_run=True);self.assertEqual(self.tree(),before);self.assertFalse((self.target/'steezy_backups').exists())
    def test_install_reinstall_rollback_preserves_code_private_media_fonts_and_database(self):
        before=self.tree();backup=installer.install(self.target,self.package);self.assertTrue((self.target/'clipper/finishing5_plan.py').is_file());self.assertIsNone(installer.install(self.target,self.package))
        for name,data in self.private.items():self.assertEqual((self.target/name).read_bytes(),data)
        record=json.loads((backup/'complete-backup.json').read_text());self.assertTrue(record['baseline_version'].startswith('4.0.15'));installer.rollback(self.target,backup);self.assertEqual(self.tree(),before)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT * FROM preserved').fetchall(),[('before',)])
    def test_unknown_source_or_new_module_collision_blocks_before_backup(self):
        for name in ('clipper/transcribe.py','clipper/finishing5_plan.py'):
            p=self.target/name;old=p.read_bytes() if p.exists() else None;p.write_bytes(b'unknown local source');before=self.tree()
            with self.assertRaisesRegex(ValueError,'Kode lokal berbeda'):installer.install(self.target,self.package)
            self.assertEqual(self.tree(),before)
            if old is None:p.unlink()
            else:p.write_bytes(old)
        self.assertFalse((self.target/'steezy_backups').exists())
    def test_payload_tamper_fails_before_first_copy(self):
        p=Path(self.temp.name)/'bad';shutil.copytree(self.package,p);target=p/'payload/clipper/finishing5_render.py';target.write_bytes(target.read_bytes()+b'bad')
        with self.assertRaisesRegex(ValueError,'Paket rusak'):installer.install(self.target,p)
        self.assertFalse((self.target/'steezy_backups').exists())
    def test_mid_copy_and_post_probe_failures_recover_complete_tree(self):
        before=self.tree();original=installer.atomic_copy;count=0
        def fail(source,dest):
            nonlocal count
            if 'payload' in Path(source).parts:
                count+=1
                if count==7:raise OSError('controlled copy failure')
            return original(source,dest)
        with patch.object(installer,'atomic_copy',side_effect=fail):
            with self.assertRaises(OSError):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before)
        def probe(target,after=False):
            if after:raise ValueError('controlled post-install failure')
            return {'work_dir':str(self.work)}
        with patch.object(installer,'probe_runtime',side_effect=probe):
            with self.assertRaisesRegex(ValueError,'controlled post-install'):installer.install(self.target,self.package)
        self.assertEqual(self.tree(),before)
    def test_M4_data_remains_readable_on_code_only_rollback_to_M4(self):
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE projects(id TEXT,document TEXT)');db.execute('INSERT INTO projects VALUES(?,?)',('p',json.dumps({'m3_feedback':[{'status':'accepted'}],'clips':{'c':{'variants':{'portrait':{'camera4_feedback':[{'accepted':True}]}}}}})))
        backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:db.execute("INSERT INTO preserved VALUES('after-M4-compatible')")
        installer.rollback(self.target,backup)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT count(*) FROM preserved').fetchone()[0],2)
    def test_M5_state_requires_latest_checkpoint_before_restoring_old_database(self):
        backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE projects(id TEXT,document TEXT)');db.execute('INSERT INTO projects VALUES(?,?)',('p',json.dumps({'clips':{'c':{'variants':{'portrait':{'finishing5':{'enabled':True,'style':{'glow_px':2}}}}}}})));db.execute("INSERT INTO preserved VALUES('after')")
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
        installer.rollback(self.target,backup,restore_project_state=True)
        with sqlite3.connect(backup/'data/studio4-latest-before-rollback.sqlite3') as db:self.assertEqual(db.execute('SELECT count(*) FROM preserved').fetchone()[0],2)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT count(*) FROM preserved').fetchone()[0],1)
    def test_pending_M5_jobs_and_asset_registry_are_protected(self):
        backup=installer.install(self.target,self.package)
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE jobs(id TEXT,kind TEXT,status TEXT)');db.execute("INSERT INTO jobs VALUES('j','gallery_m5','queued')")
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
        with sqlite3.connect(self.db) as db:db.execute('DELETE FROM jobs');db.execute('CREATE TABLE assets5(id TEXT,data TEXT)');db.execute("INSERT INTO assets5 VALUES('a','{}')")
        with self.assertRaisesRegex(ValueError,'restore-project-state'):installer.rollback(self.target,backup)
    def test_CRC_all_payload_digests_requirement_trace_and_private_exclusion(self):
        with zipfile.ZipFile(self.package.with_suffix('.zip')) as z:
            self.assertIsNone(z.testzip());m=json.loads(z.read(self.package.name+'/manifest.json'));self.assertEqual(m['version'],'4.0.16')
            for row in m['files']:self.assertEqual(hashlib.sha256(z.read(self.package.name+'/payload/'+row['path'])).hexdigest(),row['sha256'])
            trace=json.loads(z.read(self.package.name+'/M5_REQUIREMENTS.json'));self.assertEqual(trace['gate_g5'],'pending_real_corpus');self.assertEqual(len(trace['requirements']),33)
            self.assertEqual({r['id'] for r in trace['requirements'] if r['id'].startswith('TX')},{'TX'+str(i).zfill(2) for i in range(1,19)})
            self.assertFalse(any('.env' in r['path'] or r['path'].endswith('.mp4') for r in m['files']));self.assertNotIn('docs/releases/m0_fixture.zip',{r['path'] for r in m['files']+m['guards']})

