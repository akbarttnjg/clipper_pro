"""Real code-copy, manifest checks, SQLite backup and rollback on temporary fixtures."""
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
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/f'{name}.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


installer=module('repair1_installer')
builder=module('build_repair1_release')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Installer(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.target=self.base/'machine';self.package=self.base/'package'
        (self.target/'clipper').mkdir(parents=True)
        app=b'# fixture app\n';old=b'VALUE=1\n';new=b'VALUE=2\n';guide=b'# new guide\n'
        (self.target/'app.py').write_bytes(app);(self.target/'clipper/fixture.py').write_bytes(old)
        (self.package/'payload/clipper').mkdir(parents=True);(self.package/'payload/docs').mkdir()
        (self.package/'payload/clipper/fixture.py').write_bytes(new)
        (self.package/'payload/docs/repair.md').write_bytes(guide)
        files=[{'path':'clipper/fixture.py','sha256':sha(new),'allowed_text_sha256':[sha(old),sha(new)]},
               {'path':'docs/repair.md','sha256':sha(guide),'allowed_text_sha256':[sha(guide)]}]
        self.manifest={'schema_version':1,'version':'4.0.7','source_commit':'0'*40,'files':files,
                       'guards':[{'path':'app.py','allowed_text_sha256':[sha(app)]}]}
        (self.package/'manifest.json').write_text(json.dumps(self.manifest))
        self.work=self.base/'custom work';self.work.mkdir();self.database=self.work/'studio4.sqlite3'
        with sqlite3.connect(self.database) as db:
            db.execute('CREATE TABLE notes(text TEXT)');db.execute("INSERT INTO notes VALUES('prior edit')")
        self.runtime=patch.object(installer,'probe_runtime',return_value={'python':'fixture','work_dir':str(self.work)})
        self.runtime.start();self.addCleanup(self.runtime.stop)
        stopped=patch.object(installer,'require_stopped');stopped.start();self.addCleanup(stopped.stop)

    def test_install_idempotence_and_rollback_preserve_new_project_data(self):
        backup=installer.install(self.target,self.package)
        self.assertEqual((self.target/'clipper/fixture.py').read_bytes(),b'VALUE=2\n')
        record=json.loads((backup/'repair1-backup.json').read_text())
        with sqlite3.connect(record['database_backup']['copy']) as db:
            self.assertEqual(db.execute('SELECT text FROM notes').fetchall(),[('prior edit',)])
        self.assertIsNone(installer.install(self.target,self.package))
        with sqlite3.connect(self.database) as db:db.execute("INSERT INTO notes VALUES('new edit')")
        installer.rollback(self.target,backup)
        self.assertEqual((self.target/'clipper/fixture.py').read_bytes(),b'VALUE=1\n')
        self.assertFalse((self.target/'docs/repair.md').exists())
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM notes').fetchone()[0],2)

    def test_corrupt_payload_or_local_change_is_rejected_before_copy(self):
        (self.package/'payload/clipper/fixture.py').write_bytes(b'VALUE=99\n')
        with self.assertRaisesRegex(ValueError,'rusak'):installer.install(self.target,self.package)
        self.assertEqual((self.target/'clipper/fixture.py').read_bytes(),b'VALUE=1\n')
        (self.package/'payload/clipper/fixture.py').write_bytes(b'VALUE=2\n')
        (self.target/'clipper/fixture.py').write_bytes(b'VALUE=9\n')
        with self.assertRaisesRegex(ValueError,'Kode lokal berbeda'):installer.install(self.target,self.package)
        self.assertEqual((self.target/'clipper/fixture.py').read_bytes(),b'VALUE=9\n')

    def test_failed_after_probe_restores_all_code(self):
        def probe(target,after=False):
            if after:raise ValueError('Fixture post-import failure')
            return {'python':'fixture','work_dir':str(self.work)}
        with patch.object(installer,'probe_runtime',side_effect=probe):
            with self.assertRaisesRegex(ValueError,'post-import'):installer.install(self.target,self.package)
        self.assertEqual((self.target/'clipper/fixture.py').read_bytes(),b'VALUE=1\n')
        self.assertFalse((self.target/'docs/repair.md').exists())
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM notes').fetchone()[0],1)

    def test_path_traversal_is_rejected(self):
        self.manifest['files'][0]['path']='../outside.py'
        (self.package/'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError):installer.install(self.target,self.package)
        self.assertEqual((self.target/'clipper/fixture.py').read_bytes(),b'VALUE=1\n')

    def test_real_release_builder_produces_verified_installable_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=builder.build(Path(tmp)/'release','0'*40)
            self.assertEqual(report['zip_crc'],'passed')
            manifest,changes,_=installer.preflight(ROOT,Path(tmp)/'release',runtime=False,stopped=False)
            self.assertEqual(manifest['version'],'4.0.7');self.assertEqual(changes,[])


if __name__=='__main__':unittest.main()
