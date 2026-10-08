"""Offline code overlay with baseline checks, recoverable journal and rollback.

Python standard library only. Project data and model environments are outside
the allowed payload paths. Run from an extracted release, not from payload/.
"""
import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath


ROOT_FILES = {'README.md', 'app.py', 'doctor_pro.py', 'requirements.txt',
              'requirements-pro.txt', 'JALANKAN_PRO.cmd', 'CEK_PRO.cmd'}


def checksum(path, text=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if text else data).hexdigest()


def safe_path(root, name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or '\0' in name:
        raise ValueError('Path paket tidak valid: ' + str(name))
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or str(rel) != name:
        raise ValueError('Path paket tidak aman: ' + name)
    if rel.parts[0] not in {'clipper', 'static', 'docs', 'tools'} and name not in ROOT_FILES:
        raise ValueError('Payload hanya boleh berisi kode aplikasi: ' + name)
    root = root.resolve()
    path = root.joinpath(*rel.parts)
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symlink tidak diizinkan: ' + name)
    if not path.resolve().is_relative_to(root):
        raise ValueError('Path keluar dari folder: ' + name)
    return path


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    try:
        with temp.open('w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_copy(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_name(dest.name + '.stage5-tmp')
    try:
        with source.open('rb') as src, temp.open('wb') as out:
            shutil.copyfileobj(src, out); out.flush(); os.fsync(out.fileno())
        shutil.copystat(source, temp)
        os.replace(temp, dest)
    finally:
        temp.unlink(missing_ok=True)


def require_stopped(port=8765):
    try:
        connection = socket.create_connection(('127.0.0.1', port), timeout=.3)
    except OSError:
        return
    connection.close()
    raise ValueError(f'Tutup server Clipper pada port {port} dengan Ctrl+C sebelum melanjutkan.')


def python_for(target):
    path = target / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not path.is_file():
        raise ValueError('Python .venv mesin lama tidak ditemukan. Pilih folder instalasi yang dipakai menjalankan Clipper.')
    return path


def probe_runtime(target, after=False):
    python = python_for(target)
    code = ('import importlib.util,json,sys; '
            "names=['fastapi','requests','PIL','cv2','multipart','dotenv']; "
            'missing=[name for name in names if importlib.util.find_spec(name) is None]; '
            "assert sys.version_info >= (3,10), 'Python 3.10 atau lebih baru diperlukan'; "
            "assert not missing, 'Modul belum tersedia: '+', '.join(missing); "
            'sys.path.insert(0,sys.argv[1]); ')
    if after:
        code += 'import clipper.visual4,clipper.visual_worker,clipper.stage3,clipper.speech_jobs,clipper.api_studio,clipper.studio_exchange,clipper.style5,clipper.caption_renderer,clipper.explanation5,clipper.asset_rank; '
    code += "print(json.dumps({'python':sys.version.split()[0],'core_modules':'available'}))"
    process = subprocess.run([str(python), '-I', '-c', code, str(target)], cwd=target,
                             capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45)
    if process.returncode:
        raise ValueError('Pemeriksaan Python gagal: ' + process.stderr[-1500:])
    if not after:
        for command in ('ffmpeg', 'ffprobe'):
            check = subprocess.run([command, '-version'], capture_output=True, timeout=15)
            if check.returncode:
                raise ValueError(command + ' belum bisa dijalankan.')
    return json.loads(process.stdout.strip())


def load_manifest(package):
    data = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or data.get('version') != '4.0.5':
        raise ValueError('Manifest bukan paket Tahap 5 yang didukung.')
    for key in ('files', 'guards'):
        rows = data.get(key)
        if not isinstance(rows, list) or not rows:
            raise ValueError('Daftar ' + key + ' tidak lengkap.')
        seen = set()
        for row in rows:
            safe_path(package, row['path'])
            name = row['path'].casefold()
            if name in seen:
                raise ValueError('Path ganda dalam manifest: ' + row['path'])
            seen.add(name)
            if key == 'files' and not re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', '')):
                raise ValueError('Checksum payload tidak valid.')
            allowed = row.get('allowed_text_sha256', [])
            if not isinstance(allowed, list) or any(not re.fullmatch(r'[0-9a-f]{64}', h) for h in allowed):
                raise ValueError('Checksum dasar tidak valid.')
    return data


def preflight(target, package, runtime=True, stopped=True):
    target, package = target.resolve(), package.resolve()
    if target == package or target.is_relative_to(package / 'payload'):
        raise ValueError('Pilih folder mesin lama, bukan folder paket upgrade atau payload.')
    if not (target / 'app.py').is_file() or not (target / 'clipper').is_dir():
        raise ValueError('Folder mesin harus berisi app.py dan folder clipper.')
    manifest = load_manifest(package)
    for row in manifest['files']:
        source = safe_path(package / 'payload', row['path'])
        if not source.is_file() or checksum(source) != row['sha256']:
            raise ValueError('Paket rusak atau tidak lengkap: ' + row['path'])
        if source.suffix == '.py':
            ast.parse(source.read_text(encoding='utf-8-sig'), filename=row['path'])
    conflicts = []
    for row in manifest['guards']:
        dest = safe_path(target, row['path'])
        if not dest.is_file() or checksum(dest, True) not in row['allowed_text_sha256']:
            conflicts.append(row['path'])
    for row in manifest['files']:
        dest = safe_path(target, row['path'])
        if dest.exists() and (not dest.is_file() or checksum(dest, True) not in row['allowed_text_sha256']):
            conflicts.append(row['path'])
    if conflicts:
        raise ValueError('Kode lokal berbeda atau dasar paket belum lengkap. Tidak ada file ditimpa:\n' +
                         '\n'.join(sorted(set(conflicts))))
    if stopped:
        require_stopped()
    report = probe_runtime(target) if runtime else {}
    changes = [row for row in manifest['files'] if not safe_path(target, row['path']).is_file()
               or checksum(safe_path(target, row['path'])) != row['sha256']]
    return manifest, changes, report


def rollback(target, backup=None, stopped=True):
    target = target.resolve()
    if stopped:
        require_stopped()
    states = {'installed', 'prepared', 'restoring', 'rollback_required'}
    if backup is None:
        journals = sorted((target / 'steezy_backups').glob('stage5-*/stage5-backup.json'), reverse=True)
        journal = next((p for p in journals if json.loads(p.read_text(encoding='utf-8')).get('status') in states), None)
        if journal is None:
            raise ValueError('Cadangan Tahap 5 yang aktif tidak ditemukan.')
    else:
        journal = Path(backup).resolve() / 'stage5-backup.json'
    record = json.loads(journal.read_text(encoding='utf-8'))
    if Path(record['target']).resolve() != target or record['status'] not in states:
        raise ValueError('Cadangan tidak sesuai target atau sudah dipulihkan.')
    # Validate every original and current file before changing the first one.
    for row in record['files']:
        dest = safe_path(target, row['path'])
        if dest.exists() and not dest.is_file():
            raise ValueError('Path kode berubah menjadi folder; periksa dahulu: ' + row['path'])
        if row['existed']:
            old = safe_path(journal.parent / 'original', row['path'])
            if not old.is_file() or checksum(old) != row['original_sha256']:
                raise ValueError('Integritas cadangan gagal: ' + row['path'])
        current = checksum(dest) if dest.is_file() else None
        if current not in {row['sha256'], row['original_sha256']}:
            raise ValueError('File berubah setelah upgrade; simpan atau bandingkan dahulu: ' + row['path'])
    record['status'] = 'restoring'; atomic_json(journal, record)
    for row in reversed(record['files']):
        dest = safe_path(target, row['path'])
        if row['existed']:
            if checksum(dest) != row['original_sha256']:
                atomic_copy(safe_path(journal.parent / 'original', row['path']), dest)
        else:
            dest.unlink(missing_ok=True)
    record['status'] = 'restored'; atomic_json(journal, record)
    print('Kode sebelum Tahap 5 berhasil dipulihkan. Data proyek tetap tersedia.')
    return journal.parent


def install(target, package, dry_run=False):
    target, package = target.resolve(), package.resolve()
    manifest, changes, runtime = preflight(target, package)
    print(f'Target: {target}\nVersi paket: 4.0.5\nFile yang diperbarui: {len(changes)}')
    print('Pemeriksaan Python: ' + runtime.get('python', ''))
    if dry_run:
        print('Pemeriksaan lulus. Jalankan UPGRADE_TAHAP_5.cmd untuk memasang.'); return None
    if not changes:
        print('Paket ini sudah terpasang.'); return None
    backup = target / 'steezy_backups' / ('stage5-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True)
    records = []
    for row in changes:
        dest = safe_path(target, row['path']); existed = dest.is_file()
        if existed:
            atomic_copy(dest, safe_path(backup / 'original', row['path']))
        records.append({**row, 'existed': existed, 'original_sha256': checksum(dest) if existed else None})
    record = {'schema_version': 1, 'version': '4.0.5', 'source_commit': manifest['source_commit'],
              'target': str(target), 'status': 'prepared', 'files': records}
    journal = backup / 'stage5-backup.json'; atomic_json(journal, record)
    try:
        # Detect edits made after the initial check and before the first copy.
        preflight(target, package)
        for row in records:
            dest = safe_path(target, row['path'])
            current = checksum(dest) if dest.is_file() else None
            if current != row['original_sha256']:
                raise ValueError('File berubah saat pemasangan: ' + row['path'])
            atomic_copy(safe_path(package / 'payload', row['path']), dest)
        probe_runtime(target, after=True)
        record['status'] = 'installed'; atomic_json(journal, record)
    except Exception:
        try:
            rollback(target, backup, stopped=False)
        except Exception as recovery:
            record['status'] = 'rollback_required'; atomic_json(journal, record)
            raise ValueError('Pemasangan gagal dan pemulihan perlu dilanjutkan. Cadangan: ' + str(backup) +
                             '. ' + str(recovery)) from recovery
        raise
    print('Pemasangan selesai. Cadangan kode: ' + str(backup))
    print('Jalankan JALANKAN_PRO.cmd pada mesin lama, lalu Ctrl+F5 di browser.')
    return backup


def main():
    parser = argparse.ArgumentParser(description='Pemasang offline Clipper Studio Tahap 5')
    parser.add_argument('--target'); parser.add_argument('--package')
    parser.add_argument('--check', action='store_true'); parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--backup', help='Folder cadangan tertentu untuk dipulihkan')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        raise ValueError('Gunakan Python 3.10 atau lebih baru.')
    default = Path(r'C:\AI\clipper')
    raw = args.target or (str(default) if default.is_dir() else input('Folder mesin lama (contoh C:\\AI\\clipper): '))
    target = Path(raw.strip().strip('"')).resolve()
    if args.rollback:
        rollback(target, args.backup)
    else:
        package = Path(args.package).resolve() if args.package else Path(__file__).resolve().parent
        install(target, package, dry_run=args.check)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('GAGAL: ' + str(exc), file=sys.stderr); sys.exit(1)
