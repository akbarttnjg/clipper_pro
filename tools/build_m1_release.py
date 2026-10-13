"""Build the M1 offline overlay against the verified GitHub M0 baseline.

No credentials, environments, video sources, model weights, or user data are
included. The existing recoverable installer validates every payload and guard.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))
from tools import complete_installer as installer


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(output, source_commit, verification=None):
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('SHA commit sumber harus lengkap.')
    output = Path(output).resolve()
    archive = output.with_suffix('.zip')
    if output.exists() or archive.exists():
        raise ValueError('Pilih nama paket baru; paket lama tidak ditimpa.')
    baseline = json.loads((ROOT / 'docs/releases/m1_base_hashes.json').read_text())
    output.mkdir(parents=True)
    files = []
    for name in baseline['payload_paths']:
        source = installer.safe_path(ROOT, name)
        data = source.read_bytes()
        dest = installer.safe_path(output / 'payload', name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        text_hash = digest(data.replace(b'\r\n', b'\n'))
        files.append({'path': name, 'sha256': digest(data), 'text_sha256': text_hash,
            'allowed_text_sha256': sorted(set(baseline['allowed_hashes'].get(name, []) + [text_hash]))})
    guards = [{'path': name, 'allowed_text_sha256': baseline['allowed_hashes'][name]}
              for name in baseline['guard_paths']]
    manifest = {'schema_version': 1, 'version': '4.0.12', 'milestone': 'M1',
        'release_id': 'm1-complete-20261013', 'source_commit': source_commit, 'source_origin': 'local',
        'baseline_github_commit': baseline['base_commit'],
        'accepted_baseline_github_commits': [baseline['base_commit'],*baseline.get('additional_base_commits',[])],
        'requires_installation': 'Verified Clipper Studio 4.0.11 M0 or first M1; current payload accepted for idempotent reinstall',
        'install_command': 'PASANG_M1_4_0_12.cmd',
        'offline_update': True, 'files': files, 'guards': guards,
        'data_directories_untouched': ['work', 'clips', 'uploads', '.venv', 'ClipperModels', 'models'],
        'specification_basis': {'document':'Arsitektur_Clipper_Pro_Terpadu_120_Halaman (2).pdf','pages':120,
            'sha256':'76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36','packages':['M1.1','M1.2','M1.3','M1.4','M1.5','M1.6']},
        'implementation_status':'six M1 packages implemented; target acceptance pending',
        'pending_acceptance': ['Actual Windows browser/two-tab/150-percent zoom and five-user usability',
            'Native OpenCV and pyCapCut tests on the target environment','Original-video preview/final on i5-12500H + RTX3050 4GB',
            'CapCut 4.7.0 regression; Resolve text remains deferred']}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    shutil.copyfile(ROOT / 'tools/complete_installer.py', output / 'complete_installer.py')
    shutil.copyfile(ROOT / 'docs/UPGRADE_4_0_12_M1.md', output / 'PANDUAN_M1.md')
    shutil.copyfile(ROOT / 'docs/M1_REQUIREMENTS.json', output / 'M1_REQUIREMENTS.json')
    for name, flag in [('CEK_SEBELUM_UPGRADE.cmd', '--check'),
                       ('PASANG_M1_4_0_12.cmd', ''), ('PULIHKAN_M1_4_0_12.cmd', '--rollback')]:
        command = ('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\n'
            'where py >nul 2>nul\r\nif errorlevel 1 (\r\n'
            '  python "%~dp0complete_installer.py" '+flag+' %*\r\n'
            ') else (\r\n  py -3 "%~dp0complete_installer.py" '+flag+' %*\r\n)\r\n'
            'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
        (output / name).write_bytes(command.encode('utf-8'))
    (output / 'BACA_DULU.txt').write_text(
        'CLIPPER PRO 4.0.12 M1 - ENAM PAKET EDITOR\n\n'
        'Dasar: 4.0.11 M0 atau M1 awal yang cocok dengan hash.\n'
        '1. Ekstrak ZIP ke folder baru di luar folder mesin.\n'
        '2. Hentikan antrean, lalu tutup server dengan Ctrl+C.\n'
        '3. Klik CEK_SEBELUM_UPGRADE.cmd; isi lokasi folder mesin lama.\n'
        '4. Jika lulus, klik PASANG_M1_4_0_12.cmd; pilih folder yang sama.\n'
        '5. Jalankan JALANKAN_PRO.cmd dari mesin, lalu Ctrl+F5 di browser.\n'
        '6. Pastikan tulisan versi menjadi 4.0.12 M1. Baca PANDUAN_M1.md.\n\n'
        'Paket memeriksa kode dasar, mencadangkan kode dan SQLite, dan pulih\n'
        'bila pemasangan gagal. Jangan menyalin payload secara manual.\n'
        'Tidak mengunduh model atau memasang dependensi. Video, .env, model,\n'
        'font pribadi dan koreksi proyek tidak ditimpa.\n'
        'Rollback: PULIHKAN_M1_4_0_12.cmd. Proyek dengan efek M1 lanjutan\n'
        'memerlukan pilihan pemulihan state; pekerjaan terbaru dicadangkan utuh.\n'
        'Bukti uji dan batasnya ada pada verification/ dan PANDUAN_M1.md.\n', encoding='utf-8')
    test_command=('@echo off\r\nsetlocal\r\nset /p "CLIPPER_TEST_TARGET=Folder mesin untuk diuji: "\r\n'
        'if not exist "%CLIPPER_TEST_TARGET%\\.venv\\Scripts\\python.exe" (echo Python .venv mesin belum ditemukan.& pause& exit /b 1)\r\n'
        'cd /d "%CLIPPER_TEST_TARGET%"\r\n'
        '".venv\\Scripts\\python.exe" -c "import pytest" >nul 2>nul\r\n'
        'if errorlevel 1 (echo Pytest belum terpasang. Untuk environment uji, gunakan .venv\\Scripts\\python.exe -m pip install pytest& pause& exit /b 1)\r\n'
        'if not exist "m1-test-results" mkdir "m1-test-results"\r\n'
        '".venv\\Scripts\\python.exe" -m pytest clipper/tests -q --junitxml="m1-test-results\\junit-%RANDOM%.xml"\r\n'
        'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
    (output/'JALANKAN_UJI_M1.cmd').write_bytes(test_command.encode('utf-8'))
    if verification:
        shutil.copytree(verification, output / 'verification')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for file in sorted(output.rglob('*')):
            if file.is_file():
                zipped.write(file, output.name+'/'+file.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip():
            raise ValueError('CRC paket gagal.')
        for row in files:
            if digest(zipped.read(output.name+'/payload/'+row['path'])) != row['sha256']:
                raise ValueError('Checksum payload gagal: '+row['path'])
    result = {'archive': str(archive), 'bytes': archive.stat().st_size,
        'sha256': digest(archive.read_bytes()), 'payload_files': len(files), 'guards': len(guards),
        'source_commit': source_commit, 'baseline_github_commit': baseline['base_commit'],
        'milestone': 'M1', 'zip_crc': 'passed'}
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--verification')
    args = parser.parse_args()
    build(args.output, args.source_commit, args.verification)
