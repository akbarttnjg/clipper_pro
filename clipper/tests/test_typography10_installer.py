"""4.0.10 overlay against byte-verified GitHub 4.0.9, without git history."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class VerifiedOverlay(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.target = self.folder / 'machine'
        self.package = self.folder / 'upgrade'
        self.installer = module('complete_installer')
        self.builder = module('build_typography10_release')
        # The fixture contains every protected baseline file. No user's machine,
        # installed weights, private config or external commit is required.
        self.target.mkdir()
        with zipfile.ZipFile(ROOT / 'docs/releases/typography10_fixture.zip') as archive:
            provenance = json.loads(archive.read('__provenance__.json'))
            self.assertEqual(provenance['base_commit'], '2e5d97621be0d2576f62c13c4c04696c6cadef06')
            for name, expected in provenance['normalized_sha256'].items():
                data = archive.read(name)
                self.assertEqual(hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest(), expected)
                dest = self.installer.safe_path(self.target, name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        with contextlib.redirect_stdout(io.StringIO()):
            self.builder.build(self.package, '0' * 40)
        self.work = self.target / 'work'
        self.work.mkdir()
        self.db = self.work / 'studio4.sqlite3'
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE edits(note TEXT)')
            db.execute("INSERT INTO edits VALUES('before')")
        self.env = self.target / '.env'
        self.env.write_text('WORK_DIR=work\nLOCAL_MARKER=keep-this\n')
        self.model = self.target / 'ClipperModels/weights/user-model.bin'
        self.model.parent.mkdir(parents=True)
        self.model.write_bytes(b'user-model')
        self.font = self.target / 'clipper/fonts/UserCustom.ttf'
        self.font.parent.mkdir(parents=True, exist_ok=True)
        self.font.write_bytes(b'user-font')
        self.before = (self.target / 'clipper/typography.py').read_bytes()

    def assert_untouched(self):
        self.assertEqual((self.target / 'clipper/typography.py').read_bytes(), self.before)
        self.assertFalse((self.target / 'clipper/caption_fit.py').exists())
        self.assertEqual(self.env.read_text(), 'WORK_DIR=work\nLOCAL_MARKER=keep-this\n')
        self.assertEqual(self.model.read_bytes(), b'user-model')
        self.assertEqual(self.font.read_bytes(), b'user-font')

    def test_install_idempotence_database_backup_and_rollback(self):
        with patch.object(self.installer, 'require_stopped'), patch.object(self.installer, 'probe_runtime', return_value={'work_dir': str(self.work)}), contextlib.redirect_stdout(io.StringIO()):
            backup = self.installer.install(self.target, self.package)
            self.assertIsNone(self.installer.install(self.target, self.package))
            _, changes, _ = self.installer.preflight(self.target, self.package, runtime=False, stopped=False)
            self.assertEqual(changes, [])
            self.assertTrue((self.target / 'clipper/caption_fit.py').is_file())
            record = json.loads((backup / 'complete-backup.json').read_text())
            self.assertEqual(record['version'], '4.0.10')
            with sqlite3.connect(record['database_backup']['copy']) as db:
                self.assertEqual(db.execute('SELECT * FROM edits').fetchall(), [('before',)])
            with sqlite3.connect(self.db) as db:
                db.execute("INSERT INTO edits VALUES('after')")
            self.installer.rollback(self.target, backup)
        self.assert_untouched()
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM edits').fetchone()[0], 2)

    def test_unknown_local_runtime_code_rejected_before_copy(self):
        dest = self.target / 'clipper/runtime/install.py'
        dest.write_text(dest.read_text() + '\n# local customization\n')
        with self.assertRaisesRegex(ValueError, 'Kode lokal berbeda'):
            self.installer.preflight(self.target, self.package, runtime=False, stopped=False)
        self.assert_untouched()

    def test_corrupt_payload_rejected_before_copy(self):
        dest = self.package / 'payload/clipper/caption_fit.py'
        dest.write_text(dest.read_text() + '\n# corrupt download\n')
        with self.assertRaisesRegex(ValueError, 'Paket rusak'):
            self.installer.preflight(self.target, self.package, runtime=False, stopped=False)
        self.assert_untouched()

    def test_post_import_failure_restores_old_code_and_removes_new_modules(self):
        def probe(target, after=False):
            if after:
                raise ValueError('controlled post-import failure')
            return {'work_dir': str(self.work)}
        with patch.object(self.installer, 'require_stopped'), patch.object(self.installer, 'probe_runtime', side_effect=probe), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'post-import'):
                self.installer.install(self.target, self.package)
        self.assert_untouched()

    def test_real_core_imports_when_dependencies_are_available(self):
        required = ('fastapi', 'cv2', 'multipart', 'dotenv', 'requests')
        if any(importlib.util.find_spec(name) is None for name in required):
            self.skipTest('Core app dependencies unavailable in build environment')
        (self.target / '.venv').symlink_to(Path(sys.prefix), target_is_directory=True)
        # Unchanged optional runtime assets are part of the application, not the
        # compact fixture; restore those from the checked source for this probe.
        for source in ROOT.rglob('*'):
            rel = source.relative_to(ROOT)
            if rel.parts[0] not in {'clipper', 'static'} or '__pycache__' in rel.parts:
                continue
            dest = self.target / rel
            if source.is_file() and not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)
        with patch.object(self.installer, 'require_stopped'), contextlib.redirect_stdout(io.StringIO()):
            self.installer.install(self.target, self.package)
        self.assertEqual(self.installer.probe_runtime(self.target, after=True)['core_modules'], 'available')


if __name__ == '__main__':
    unittest.main()
