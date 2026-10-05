"""Build a guarded, complete application overlay from committed source only."""
import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

BASES = [
    'b4772099c5591e8a83152a767ecb1004972b266b',
    'f67b03280774089f8f95ae8d94018377c4897b93',
    '6d8c6dce97e77fd6b9be2e6ccc91132b05912d41',
]
ROOT_FILES = {
    'app.py', 'README.md', 'LICENSE', 'ARCHITECTURE.md', 'PANDUAN_STUDIO_4.md',
    'requirements.txt', 'requirements-pro.txt', 'doctor_pro.py',
    'JALANKAN_PRO.cmd', 'CEK_PRO.cmd', 'PULIHKAN_PRO.cmd', 'SETUP_STUDIO4.cmd',
    'steezy_pro_installer.py', 'pytest.ini', 'conftest.py',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def build(output, verification=None):
    root = Path(__file__).resolve().parents[1]
    if git(root, 'status', '--porcelain').strip():
        raise ValueError('Commit perubahan aplikasi sebelum membangun paket rilis.')
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Pilih folder paket baru; folder yang sudah ada tidak ditimpa.')
    output.mkdir(parents=True)
    payload = output / 'payload'
    entries = []
    tracked = git(root, 'ls-files', '-z').decode().split('\0')
    for name in sorted(n for n in tracked if n):
        parts = Path(name).parts
        allowed = name in ROOT_FILES or parts[0] in {'clipper', 'static', 'docs', 'tools'}
        if not allowed or '__pycache__' in parts or name.endswith(('.pyc', '.sqlite3')):
            continue
        path = root / name
        if path.is_symlink():
            raise ValueError('Symlink tidak diizinkan dalam payload: ' + name)
        data = path.read_bytes()
        dest = payload / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        allowed_bases = []
        for base in BASES:
            old = subprocess.run(['git', 'show', base + ':' + name], cwd=root, capture_output=True)
            if old.returncode == 0:
                allowed_bases.append(sha(old.stdout.replace(b'\r\n', b'\n')))
        entries.append({'path': name, 'sha256': sha(data),
                        'text_sha256': sha(data.replace(b'\r\n', b'\n')),
                        'base_text_sha256': allowed_bases[0] if allowed_bases else None,
                        'allowed_base_text_sha256': sorted(set(allowed_bases))})
    manifest = {'version': '4.0.0-integration-AB', 'release_status': 'integration_preview',
                'requires_versions': ['3.3', '4.0'], 'offline_update': False,
                'source_commit': git(root, 'rev-parse', 'HEAD').decode().strip(),
                'accepted_bases': BASES, 'files': entries,
                'pending_gates': ['B34 native CapCut/DaVinci import', 'B36 real-source human-reference benchmark',
                                  'Windows/NVENC hardware acceptance', 'HDR media fixture']}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    for name in ('steezy_pro_installer.py', 'PANDUAN_STUDIO_4.md'):
        (output / name).write_bytes((root / name).read_bytes())
    for name, flags in [('CEK_UPGRADE.cmd', '--dry-run'), ('PASANG_UPGRADE.cmd', ''),
                        ('PULIHKAN_UPGRADE.cmd', '--rollback')]:
        text = ('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\n'
                'where py >nul 2>nul\r\nif errorlevel 1 (\r\n'
                '  echo Python launcher tidak ditemukan. Gunakan python steezy_pro_installer.py dari terminal.\r\n'
                '  pause\r\n  exit /b 1\r\n)\r\n'
                'py -3 "%~dp0steezy_pro_installer.py" ' + flags + ' %*\r\n'
                'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
        (output / name).write_bytes(text.encode('utf-8'))
    (output / 'BACA_DULU.txt').write_text(
        'Clipper Studio 4 - paket uji gabungan A 01-22 + B 23-43\n\n'
        'Ekstrak seluruh ZIP. Tutup Clipper. Jalankan CEK_UPGRADE.cmd, kemudian PASANG_UPGRADE.cmd.\n'
        'Pilih folder aplikasi yang berisi app.py dan clipper. Backup kode dibuat otomatis.\n'
        'Baca PANDUAN_STUDIO_4.md untuk pemasangan baru, pemulihan, folder dan pemakaian.\n'
        'Kode dari versi yang tidak dikenal tidak ditimpa oleh installer.\n\n'
        'Gate yang belum selesai: impor native CapCut/DaVinci, benchmark video asli/acuan manusia,\n'
        'Windows/NVENC dan fixture HDR. Video bukti pengujian adalah media sintetis.\n', encoding='utf-8')
    (output / 'developer').mkdir()
    git(root, 'bundle', 'create', str(output / 'developer/upgrade-AB.bundle'), BASES[0] + '..HEAD')
    (output / 'developer/INTEGRASI.txt').write_text(
        'Alternatif untuk pengguna Git. Repository harus mempunyai baseline ' + BASES[0] + '.\n'
        'Jangan menerapkan overlay dan bundle dua kali. Simpan pekerjaan lokal sebelum merge.\n'
        'git bundle verify /path/upgrade-AB.bundle\n'
        'git fetch /path/upgrade-AB.bundle HEAD:upgrade/combined-43\n'
        'Tinjau branch upgrade/combined-43 lalu merge sesuai alur repository Anda.\n', encoding='utf-8')
    if verification:
        shutil.copytree(verification, output / 'verification', copy_function=shutil.copyfile)
    archive = output.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                z.write(path, output.name + '/' + path.relative_to(output).as_posix())
    report = {'file': str(archive), 'bytes': archive.stat().st_size, 'sha256': sha(archive.read_bytes()),
              'source_commit': manifest['source_commit'], 'payload_files': len(entries)}
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, help='New directory; ZIP is placed beside it')
    parser.add_argument('--verification', help='Directory containing reviewed QA evidence')
    args = parser.parse_args()
    build(args.output, args.verification)
