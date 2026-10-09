"""Full-code overlay/rollback against the verified pre-upgrade git snapshot."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import zipfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


class FullOverlay(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)
        self.target=self.folder/'machine';self.package=self.folder/'upgrade'
        self.installer=module('complete_installer');self.builder=module('build_typography9_release')
        # Portable fixture: no local-only commit ID or full git history needed.
        shutil.copytree(ROOT,self.target,ignore=shutil.ignore_patterns('.git','.venv','work','clips','__pycache__','.pytest_cache'))
        baseline=json.loads((ROOT/'docs/releases/typography9_base_hashes.json').read_text())
        with zipfile.ZipFile(ROOT/'docs/releases/typography9_fixture.zip') as archive:
            provenance=json.loads(archive.read('__provenance__.json'))
            for name in baseline['payload_paths']:
                dest=self.installer.safe_path(self.target,name)
                if name not in provenance['normalized_sha256']:dest.unlink(missing_ok=True)
            for name,expected in provenance['normalized_sha256'].items():
                data=archive.read(name)
                self.assertEqual(hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest(),expected)
                dest=self.installer.safe_path(self.target,name);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        self.builder.build(self.package,'0'*40)
        self.work=self.target/'work';self.work.mkdir();self.db=self.work/'studio4.sqlite3'
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE edits(note TEXT)');db.execute("INSERT INTO edits VALUES('before')")
        self.env=self.target/'.env';self.env.write_text('WORK_DIR=work\nLOCAL_MARKER=keep-this\n')
        self.model=self.target/'ClipperModels/weights/user-model.bin';self.model.parent.mkdir(parents=True);self.model.write_bytes(b'user-model')
        self.font=self.target/'clipper/fonts/UserCustom.ttf';self.font.write_bytes(b'user-font')
        self.before=(self.target/'clipper/typography.py').read_bytes()
    def test_full_install_self_check_idempotence_and_rollback_preserve_data(self):
        with patch.object(self.installer,'require_stopped'),patch.object(self.installer,'probe_runtime',return_value={'work_dir':str(self.work)}):
            backup=self.installer.install(self.target,self.package)
            self.assertIsNone(self.installer.install(self.target,self.package))
            _,changes,_=self.installer.preflight(self.target,self.package,runtime=False,stopped=False)
            self.assertEqual(changes,[]);self.assertTrue((self.target/'clipper/caption_director.py').is_file())
            record=json.loads((backup/'complete-backup.json').read_text());self.assertEqual(record['version'],'4.0.9')
            with sqlite3.connect(record['database_backup']['copy']) as db:self.assertEqual(db.execute('SELECT * FROM edits').fetchall(),[('before',)])
            with sqlite3.connect(self.db) as db:db.execute("INSERT INTO edits VALUES('after')")
            self.installer.rollback(self.target,backup)
        self.assertEqual((self.target/'clipper/typography.py').read_bytes(),self.before)
        self.assertFalse((self.target/'clipper/caption_director.py').exists())
        self.assertIn('LOCAL_MARKER=keep-this',self.env.read_text());self.assertEqual(self.model.read_bytes(),b'user-model');self.assertEqual(self.font.read_bytes(),b'user-font')
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT count(*) FROM edits').fetchone()[0],2)
    def test_unknown_local_runtime_code_is_rejected_before_copy(self):
        p=self.target/'clipper/runtime/install.py';p.write_text(p.read_text()+'\n# local customization\n')
        with self.assertRaisesRegex(ValueError,'Kode lokal berbeda'):
            self.installer.preflight(self.target,self.package,runtime=False,stopped=False)
        self.assertEqual((self.target/'clipper/typography.py').read_bytes(),self.before)
        self.assertFalse((self.target/'clipper/caption_director.py').exists())
    def test_partial_install_failure_removes_new_modules_and_restores_old_code(self):
        def probe(target,after=False):
            if after:raise ValueError('controlled post-import failure')
            return {'work_dir':str(self.work)}
        with patch.object(self.installer,'require_stopped'),patch.object(self.installer,'probe_runtime',side_effect=probe):
            with self.assertRaisesRegex(ValueError,'post-import'):self.installer.install(self.target,self.package)
        self.assertEqual((self.target/'clipper/typography.py').read_bytes(),self.before)
        self.assertFalse((self.target/'clipper/segmentation.py').exists())
    def test_real_core_imports_after_overlay_when_dependencies_are_available(self):
        required=('fastapi','cv2','multipart','dotenv','requests')
        if any(importlib.util.find_spec(name) is None for name in required):self.skipTest('Actual core dependency environment unavailable')
        (self.target/'.venv').symlink_to(Path(sys.prefix),target_is_directory=True)
        with patch.object(self.installer,'require_stopped'):
            self.installer.install(self.target,self.package)
        report=self.installer.probe_runtime(self.target,after=True)
        self.assertEqual(report['core_modules'],'available')


if __name__=='__main__':unittest.main()
