"""Validate the complete release archive without installing model dependencies."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_tool('build_stage4_release')
installer = load_tool('stage4_installer')


class Stage4ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='clipper-stage4-release-')
        cls.output = Path(cls.temp.name) / 'Clipper_Studio_4_0_4_Tahap_4'
        with contextlib.redirect_stdout(io.StringIO()):
            cls.report = builder.build(cls.output, 'a' * 40)
        cls.manifest = installer.load_manifest(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_archive_contains_the_actual_stage4_guide(self):
        with zipfile.ZipFile(self.report['archive']) as archive:
            guide = archive.read(self.output.name + '/PANDUAN_TAHAP_4.md')
        self.assertEqual(guide, (ROOT / 'docs/TAHAP_4_KAMERA_AREA_AMAN.md').read_bytes())

    def test_every_manifest_payload_is_inside_the_verified_archive(self):
        with zipfile.ZipFile(self.report['archive']) as archive:
            self.assertIsNone(archive.testzip())
            for row in self.manifest['files']:
                with self.subTest(path=row['path']):
                    data = archive.read(self.output.name + '/payload/' + row['path'])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
                    self.assertEqual(data, (ROOT / row['path']).read_bytes())

    def test_windows_launchers_use_stage4_and_preserve_exit_status(self):
        expected = {'CEK_SEBELUM_UPGRADE.cmd': '--check',
                    'UPGRADE_TAHAP_4.cmd': '',
                    'PULIHKAN_UPGRADE_TAHAP_4.cmd': '--rollback'}
        for name, flag in expected.items():
            with self.subTest(name=name):
                data = (self.output / name).read_bytes()
                self.assertIn(b'\r\n', data)
                text = data.decode('utf-8')
                self.assertIn('stage4_installer.py', text)
                self.assertIn(flag, text)
                self.assertIn('set "RESULT=%ERRORLEVEL%"', text)
                self.assertIn('exit /b %RESULT%', text)
                self.assertNotIn('TAHAP_3.cmd', text)

    def test_standalone_installer_matches_the_payload(self):
        self.assertEqual((self.output / 'stage4_installer.py').read_bytes(),
                         (self.output / 'payload/tools/stage4_installer.py').read_bytes())

    def test_package_does_not_include_project_data_or_model_environments(self):
        with zipfile.ZipFile(self.report['archive']) as archive:
            for name in archive.namelist():
                parts = Path(name).parts[1:]
                self.assertFalse(set(parts) & {'work', 'clips', 'uploads', '.venv', 'models'})
                self.assertNotIn('.env', parts)
                self.assertNotIn('.env.pro', parts)
        self.assertTrue(self.manifest['offline_update'])

    def test_existing_release_is_not_overwritten(self):
        before = Path(self.report['archive']).read_bytes()
        with self.assertRaisesRegex(ValueError, 'tidak ditimpa'):
            builder.build(self.output, 'a' * 40)
        self.assertEqual(before, Path(self.report['archive']).read_bytes())

    def test_invalid_source_commit_is_rejected_before_creating_output(self):
        for value in ('main', '4180032', '../code', ''):
            target = Path(self.temp.name) / ('invalid-' + str(len(value)))
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'SHA commit'):
                builder.build(target, value)
            self.assertFalse(target.exists())

    def test_local_source_is_labelled_without_claiming_github_publication(self):
        target = Path(self.temp.name) / 'Local_Snapshot'
        with contextlib.redirect_stdout(io.StringIO()):
            builder.build(target, 'b' * 40, source_origin='local')
        manifest = installer.load_manifest(target)
        self.assertEqual(manifest['source_origin'], 'local')
        self.assertEqual(manifest['source_commit'], 'b' * 40)


if __name__ == '__main__':
    unittest.main(verbosity=2)
