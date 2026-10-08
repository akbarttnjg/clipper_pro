"""Actual overlay/rollback file operations; runtime import probe is stubbed."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
installer=module('stage6_installer');builder=module('build_stage6_release')
BASE=ROOT.parent/'clipper_stage5'
def snapshot(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and 'steezy_backups' not in p.parts}


@unittest.skipUnless(BASE.is_dir(),'Full source 4.0.5 fixture not present beside checkout; run from release QA workspace')
class InstallerFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package_temp=tempfile.TemporaryDirectory();cls.package=Path(cls.package_temp.name)/'Stage 6 package'
        with contextlib.redirect_stdout(io.StringIO()):builder.build(cls.package,'b'*40,source_origin='local')
        cls.manifest=installer.load_manifest(cls.package)
    @classmethod
    def tearDownClass(cls):cls.package_temp.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.target=Path(self.temp.name)/'Mesin lama'
        shutil.copytree(BASE,self.target,ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache','work','clips','uploads','models','stage3_browser.cjs'))
        self.sentinels={'work/projects.sqlite3':b'project-test-data','clips/hasil.mp4':b'render-test-data','uploads/raw.mp4':b'upload-data',
                        'models/weights.bin':b'model-data','.venv/data.txt':b'environment-data','.env':b'personal-config','.env.pro':b'private-config'}
        for name,data in self.sentinels.items():p=self.target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.before=snapshot(self.target)
        self.runtime=patch.object(installer,'probe_runtime',return_value={'python':'runtime-probe-stub'});self.runtime.start()
        self.stop=patch.object(installer,'require_stopped');self.stop.start()
        self.silent=contextlib.redirect_stdout(io.StringIO());self.silent.__enter__()
    def tearDown(self):self.silent.__exit__(None,None,None);self.stop.stop();self.runtime.stop();self.temp.cleanup()
    def install(self):return installer.install(self.target,self.package)
    def test_dry_run_performs_no_writes(self):
        self.assertIsNone(installer.install(self.target,self.package,dry_run=True));self.assertEqual(snapshot(self.target),self.before)
        self.assertFalse((self.target/'steezy_backups').exists())
    def test_full_payload_installs_and_rolls_back_exactly(self):
        backup=self.install()
        for row in self.manifest['files']:self.assertEqual(installer.checksum(self.target/row['path']),row['sha256'])
        for name,data in self.sentinels.items():self.assertEqual((self.target/name).read_bytes(),data)
        installer.rollback(self.target,backup);self.assertEqual(snapshot(self.target),self.before)
    def test_repeat_install_is_idempotent(self):
        self.install();before=snapshot(self.target);self.assertIsNone(self.install());self.assertEqual(snapshot(self.target),before)
    def test_local_change_rejected_before_any_write(self):
        (self.target/'app.py').write_text('# custom application\n');before=snapshot(self.target)
        with self.assertRaises(ValueError):self.install()
        self.assertEqual(snapshot(self.target),before);self.assertFalse((self.target/'steezy_backups').exists())
    def test_corrupt_payload_rejected_before_any_write(self):
        package=Path(self.temp.name)/'Corrupt';shutil.copytree(self.package,package);path=package/'payload'/self.manifest['files'][0]['path'];path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):installer.install(self.target,package)
        self.assertEqual(snapshot(self.target),self.before)
    def test_mid_copy_failure_restores_all_code(self):
        original=installer.atomic_copy;count=0
        def fail(source,dest):
            nonlocal count
            if Path(source).is_relative_to(self.package/'payload'):
                count+=1
                if count==4:raise OSError('injected copy failure')
            return original(source,dest)
        with patch.object(installer,'atomic_copy',side_effect=fail),self.assertRaises(OSError):self.install()
        self.assertEqual(snapshot(self.target),self.before)
    def test_post_import_failure_restores_all_code(self):
        def probe(target,after=False):
            if after:raise ValueError('injected import failure')
            return {'python':'stub'}
        with patch.object(installer,'probe_runtime',side_effect=probe),self.assertRaises(ValueError):self.install()
        self.assertEqual(snapshot(self.target),self.before)
    def test_rollback_blocks_later_edits_without_partial_restore(self):
        backup=self.install();changed=self.target/'clipper/config.py';changed.write_text(changed.read_text()+'\n# newer local edit\n');before=snapshot(self.target)
        with self.assertRaises(ValueError):installer.rollback(self.target,backup)
        self.assertEqual(snapshot(self.target),before)
    def test_corrupt_backup_blocks_rollback(self):
        backup=self.install();(backup/'original/clipper/config.py').write_text('bad backup');before=snapshot(self.target)
        with self.assertRaises(ValueError):installer.rollback(self.target,backup)
        self.assertEqual(snapshot(self.target),before)
    def test_busy_server_detection(self):
        self.stop.stop()
        with socket.socket() as server:
            server.bind(('127.0.0.1',0));server.listen(1)
            with self.assertRaises(ValueError):installer.require_stopped(server.getsockname()[1])
        self.stop.start();self.assertEqual(snapshot(self.target),self.before)
    def test_data_and_traversal_paths_are_refused(self):
        for name in ('work/project.sqlite3','../escape.py','clipper/../../escape.py','C:\\clipper\\config.py','models/weights.bin','/tmp/bad'):
            with self.subTest(name=name),self.assertRaises(ValueError):installer.safe_path(self.target,name)


if __name__=='__main__':unittest.main()
