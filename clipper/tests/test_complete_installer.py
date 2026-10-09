"""Checked overlay, real SQLite backup, interrupted install and code rollback."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/f'{name}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


installer=module('complete_installer');builder=module('build_complete_release')
sha=lambda data:hashlib.sha256(data).hexdigest()


class CompleteInstaller(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        self.target=root/'machine';self.package=root/'package';self.work=root/'project-data'
        (self.target/'clipper').mkdir(parents=True);(self.package/'payload/clipper').mkdir(parents=True)
        self.work.mkdir();self.db=self.work/'studio4.sqlite3'
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE edits(text TEXT)');db.execute("INSERT INTO edits VALUES('before')")
        (self.target/'app.py').write_bytes(b'# app\n');(self.target/'clipper/fixture.py').write_bytes(b'VALUE=1\n')
        (self.package/'payload/clipper/fixture.py').write_bytes(b'VALUE=2\n')
        self.manifest={'schema_version':1,'version':'4.0.8','source_commit':'0'*40,
            'files':[{'path':'clipper/fixture.py','sha256':sha(b'VALUE=2\n'),'allowed_text_sha256':[sha(b'VALUE=1\n'),sha(b'VALUE=2\n')]}],
            'guards':[{'path':'app.py','allowed_text_sha256':[sha(b'# app\n')]}]}
        self.save_manifest()
        for stub in [patch.object(installer,'require_stopped'),patch.object(installer,'probe_runtime',return_value={'python':'fixture','work_dir':str(self.work)})]:
            stub.start();self.addCleanup(stub.stop)
    def save_manifest(self):(self.package/'manifest.json').write_text(json.dumps(self.manifest))
    def test_install_backup_idempotence_and_rollback_keeps_later_edits(self):
        backup=installer.install(self.target,self.package);record=json.loads((backup/'complete-backup.json').read_text())
        with sqlite3.connect(record['database_backup']['copy']) as db:self.assertEqual(db.execute('SELECT * FROM edits').fetchall(),[('before',)])
        self.assertIsNone(installer.install(self.target,self.package))
        with sqlite3.connect(self.db) as db:db.execute("INSERT INTO edits VALUES('after')")
        installer.rollback(self.target,backup);self.assertEqual((self.target/'clipper/fixture.py').read_bytes(),b'VALUE=1\n')
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT count(*) FROM edits').fetchone()[0],2)
    def test_corrupt_payload_and_unknown_local_code_rejected(self):
        (self.package/'payload/clipper/fixture.py').write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'rusak'):installer.install(self.target,self.package)
        (self.package/'payload/clipper/fixture.py').write_bytes(b'VALUE=2\n');(self.target/'clipper/fixture.py').write_bytes(b'LOCAL=3\n')
        with self.assertRaisesRegex(ValueError,'Kode lokal berbeda'):installer.install(self.target,self.package)
        self.assertEqual((self.target/'clipper/fixture.py').read_bytes(),b'LOCAL=3\n')
    def test_failure_after_copy_rolls_back(self):
        def probe(target,after=False):
            if after:raise ValueError('post-import fixture')
            return {'work_dir':str(self.work)}
        with patch.object(installer,'probe_runtime',side_effect=probe):
            with self.assertRaisesRegex(ValueError,'post-import'):installer.install(self.target,self.package)
        self.assertEqual((self.target/'clipper/fixture.py').read_bytes(),b'VALUE=1\n')
    def test_traversal_and_model_directory_forbidden(self):
        for path in ('../escape.py','ClipperModels/model.bin','work/data.sqlite3','.venv/python'):
            with self.assertRaises(ValueError):installer.safe_path(self.target,path)
    def test_gitignore_allowed_and_core_data_not_removed(self):
        self.assertEqual(installer.safe_path(self.target,'.gitignore'),self.target/'.gitignore')
        marker=self.target/'ClipperModels/weights';marker.parent.mkdir();marker.write_bytes(b'local model')
        installer.install(self.target,self.package);self.assertEqual(marker.read_bytes(),b'local model')
    def test_real_release_includes_every_changed_file_and_passes_self_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=builder.build(Path(tmp)/'complete','0'*40)
            manifest,changes,_=installer.preflight(ROOT,Path(tmp)/'complete',runtime=False,stopped=False)
            self.assertEqual(manifest['version'],'4.0.8');self.assertEqual(changes,[])
            self.assertEqual(report['zip_crc'],'passed')
            names={r['path'] for r in manifest['files']};self.assertIn('static/features/batch7.js',names)
            self.assertIn('clipper/framing.py',names);self.assertIn('clipper/batch7.py',names)


if __name__=='__main__':unittest.main()
