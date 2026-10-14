"""Build the cumulative 4.0.16.1 audit repair overlay on pinned M0/M1/M2/M3/M4/M5 baselines.

No credentials, environments, video sources, model weights, or user data are
included. The recoverable installer preserves Fix1 and validates every payload and guard.
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
LEGACY_FIXTURE = 'docs/releases/m0_fixture.zip'
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
    baseline = json.loads((ROOT / 'docs/releases/m0_m5_repair_base_hashes.json').read_text())
    if LEGACY_FIXTURE.casefold() in {n.casefold() for n in baseline['payload_paths'] + baseline['guard_paths']}:
        raise ValueError('Fixture lokal lama harus dipertahankan; tidak boleh menjadi payload/guard M2.')
    output.mkdir(parents=True)
    files = []
    for name in baseline['payload_paths']:
        source = installer.safe_path(ROOT, name)
        data = source.read_bytes()
        dest = installer.safe_path(output / 'payload', name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        text_hash = digest(data.replace(b'\r\n', b'\n'))
        binary = source.suffix == '.zip'
        allowed = baseline.get('allowed_raw_hashes', {}).get(name, []) if binary else baseline['allowed_hashes'].get(name, [])
        files.append({'path': name, 'sha256': digest(data), 'text_sha256': text_hash,
            'baseline_checksum': 'sha256' if binary else 'sha256-lf',
            'allowed_text_sha256': sorted(set(allowed + [digest(data) if binary else text_hash]))})
    guards = [{'path': name, 'baseline_checksum': 'sha256-lf', 'allowed_text_sha256': baseline['allowed_hashes'][name]}
              for name in baseline['guard_paths']]
    manifest = {'schema_version': 1, 'version': '4.0.16.1', 'milestone': 'M0-M5-repairs',
        'release_id': 'm0-m5-audit-repairs-20261015', 'installer_revision': 1,
        'preserved_local_files': [LEGACY_FIXTURE],
        'source_commit': source_commit, 'source_origin': 'local',
        'baseline_github_commit': baseline['base_commit'], 'repair_baseline_commit': baseline['repair_baseline_commit'],
        'accepted_baseline_github_commits': [baseline['base_commit'],*baseline.get('additional_base_commits',[])],
        'requires_installation': 'Verified M5 9dd8e73, original M4 e6ed700, repaired M4 4.0.15.1 or prior verified M0-M3; one cumulative installation',
        'install_command': 'PASANG_PERBAIKAN_4_0_16_1.cmd',
        'offline_update': True, 'files': files, 'guards': guards,
        'data_directories_untouched': ['work', 'clips', 'uploads', '.venv', 'ClipperModels', 'models'],
        'specification_basis': {'document':'Arsitektur_Clipper_Pro_Terpadu_120_Halaman (2).pdf','pages':120,
            'sha256':'76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36','milestones':['M0','M1','M2','M3','M4','M5'],'requirement_ids':['CL01-CL19','VF01-VF17']},
        'implementation_status':'26 confirmed M0-M5 findings repaired in regression scope; real corpus and target acceptance remain pending',
        'pending_acceptance': ['G5 real video human meaning and aesthetics','Remotion M5 parity not claimed','G3 real blind clipping corpus', 'G4 real composition corpus', 'Actual local ASR/VAD/alignment/diarization generation on original Indonesian and code-switch corpus', 'Live platform/cloud account access and channel ownership OAuth', 'Actual Windows browser/two-tab/150-percent zoom',
            'Native OpenCV and pyCapCut tests on the target environment','Original-video preview/final on i5-12500H + RTX3050 4GB',
            'CapCut 4.7.0 regression; Resolve text remains deferred']}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    installer.load_manifest(output)
    shutil.copyfile(ROOT / 'tools/complete_installer.py', output / 'complete_installer.py')
    shutil.copyfile(ROOT / 'docs/UPGRADE_4_0_16_1_M0_M5.md', output / 'PANDUAN_PERBAIKAN.md')
    shutil.copyfile(ROOT / 'docs/M0_M5_REPAIRS_4_0_16_1.json', output / 'M0_M5_REPAIRS_4_0_16_1.json')
    shutil.copyfile(ROOT / 'docs/releases/m0_m5_repair_m5_provenance.json', output / 'BASELINE_M5_GITHUB.json')
    shutil.copyfile(ROOT/'docs/M5_REQUIREMENTS.json',output/'M5_REQUIREMENTS.json')
    for name, flag in [('CEK_SEBELUM_UPGRADE.cmd', '--check'),
                       ('PASANG_PERBAIKAN_4_0_16_1.cmd', ''), ('PULIHKAN_PERBAIKAN_4_0_16_1.cmd', '--rollback')]:
        command = ('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\n'
            'where py >nul 2>nul\r\nif errorlevel 1 (\r\n'
            '  python "%~dp0complete_installer.py" '+flag+' %*\r\n'
            ') else (\r\n  py -3 "%~dp0complete_installer.py" '+flag+' %*\r\n)\r\n'
            'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
        (output / name).write_bytes(command.encode('utf-8'))
    (output / 'BACA_DULU.txt').write_text(
        'CLIPPER PRO 4.0.16.1 - PERBAIKAN M0-M5\n\n'
        'Dasar utama: M5 4.0.16 GitHub 9dd8e73; M4 asli/perbaikan dan M0-M3 terverifikasi didukung.\n'
        'Tidak perlu memasang paket perbaikan M0-M4 lama terlebih dahulu.\n'
        '1. Ekstrak ZIP ke folder baru di luar folder mesin.\n'
        '2. Hentikan antrean, lalu tutup server dengan Ctrl+C.\n'
        '3. Jalankan CEK_SEBELUM_UPGRADE.cmd; isi folder mesin lama.\n'
        '4. Jika lulus, jalankan PASANG_PERBAIKAN_4_0_16_1.cmd.\n'
        '5. Jalankan JALANKAN_PRO.cmd dari mesin, lalu Ctrl+F5.\n'
        '6. Buka PANDUAN_PERBAIKAN.md untuk alur impor, timing dan bilingual.\n\n'
        'Kode/SQLite dicadangkan. Video, model, environment dan font pribadi\n'
        'tidak ditimpa. Jangan menyalin payload secara manual.\n'
        'Paket tidak memasang dependensi atau mengunduh model.\n'
        'Perbaikan error docs/releases/m0_fixture.zip: arsip lama tetap\n'
        'disimpan persis dan tidak menjadi syarat dasar pemasangan.\n'
        'Jangan menghapus atau mengganti arsip lama untuk melewati error.\n'
        'Lihat verification untuk hasil regresi perbaikan ini.\n'
        'G2/G3/G4/G5 memerlukan corpus asli, model lokal dan uji Windows/GPU.\n'
        'Kepemilikan channel OAuth masih parsial; akses cloud live belum diuji.\n'
        'Rollback: PULIHKAN_PERBAIKAN_4_0_16_1.cmd. Data M2 memerlukan pemulihan\n'
        'state jika kode lama belum mendukung data milestone baru. Rollback ke M5 mempertahankan data M5; ke M4 memerlukan state sebelum M5 jika data M5 sudah digunakan. Baca panduan.\n', encoding='utf-8')
    test_command=('@echo off\r\nsetlocal\r\nset /p "CLIPPER_TEST_TARGET=Folder mesin untuk diuji: "\r\n'
        'if not exist "%CLIPPER_TEST_TARGET%\\.venv\\Scripts\\python.exe" (echo Python .venv mesin belum ditemukan.& pause& exit /b 1)\r\n'
        'cd /d "%CLIPPER_TEST_TARGET%"\r\n'
        '".venv\\Scripts\\python.exe" -c "import pytest" >nul 2>nul\r\n'
        'if errorlevel 1 (echo Pytest belum terpasang. Untuk environment uji, gunakan .venv\\Scripts\\python.exe -m pip install pytest& pause& exit /b 1)\r\n'
        'if not exist "repair-test-results" mkdir "repair-test-results"\r\n'
        '".venv\\Scripts\\python.exe" -m pytest clipper/tests -q --junitxml="repair-test-results\\junit-%RANDOM%.xml"\r\n'
        'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
    (output/'JALANKAN_UJI_PERBAIKAN.cmd').write_bytes(test_command.encode('utf-8'))
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
        'source_commit': source_commit, 'baseline_github_commit': baseline['base_commit'], 'repair_baseline_commit': baseline['repair_baseline_commit'],
        'milestone': 'M0-M5-repairs', 'installer_revision': 1, 'zip_crc': 'passed'}
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--verification')
    args = parser.parse_args()
    build(args.output, args.source_commit, args.verification)
