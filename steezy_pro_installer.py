"""Transactional overlay installer and guarded rollback. Python stdlib only."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(root, relative):
    rel = Path(relative)
    path = (root / rel).resolve()
    if rel.is_absolute() or '..' in rel.parts or not path.is_relative_to(root.resolve()):
        raise ValueError('Path tidak aman: ' + relative)
    return path


def atomic_copy(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + '.steezy-tmp')
    try:
        shutil.copy2(source, tmp)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def install(target, package, dry_run=False, install_deps=True):
    target, package = target.resolve(), package.resolve()
    if not (target / 'app.py').is_file() or not (target / 'clipper').is_dir():
        raise ValueError('Folder harus berisi app.py dan folder clipper dari instalasi Steezy.')
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    payload = package / 'payload'
    entries = manifest['files']
    for row in entries:
        src = contained(payload, row['path'])
        contained(target, row['path'])
        if not src.is_file() or digest(src) != row['sha256']:
            raise ValueError('Paket rusak/tidak lengkap: ' + row['path'])
    changes = [e for e in entries if not contained(target, e['path']).is_file()
               or digest(contained(target, e['path'])) != e['sha256']]
    print(f'Target: {target}\nFile yang diperbarui: {len(changes)}')
    if dry_run:
        return None
    if not changes:
        print('Versi paket ini sudah terpasang.')
        return None
    py = target / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if install_deps:
        if not py.is_file():
            raise ValueError('Python .venv tidak ditemukan. Jalankan setup Steezy terlebih dahulu.')
        subprocess.run([str(py), '-m', 'pip', 'install', '--disable-pip-version-check',
                        '-r', str(payload / 'requirements-pro.txt')], check=True)
    backup = target / 'steezy_backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    records = []
    for row in changes:
        dst = contained(target, row['path'])
        existed = dst.exists()
        if existed and not dst.is_file():
            raise ValueError('Target bukan file: ' + row['path'])
        old = digest(dst) if existed else None
        if existed:
            atomic_copy(dst, contained(backup / 'original', row['path']))
        records.append({**row, 'existed': existed, 'original_sha256': old})
    record = {'version': manifest['version'], 'target': str(target), 'status': 'prepared', 'files': records}
    journal = backup / 'backup.json'
    journal.write_text(json.dumps(record, indent=2), encoding='utf-8')
    touched = []
    try:
        for row in records:
            atomic_copy(contained(payload, row['path']), contained(target, row['path']))
            touched.append(row)
        record['status'] = 'installed'
        journal.write_text(json.dumps(record, indent=2), encoding='utf-8')
    except Exception:
        for row in reversed(touched):
            dst = contained(target, row['path'])
            if row['existed']:
                atomic_copy(contained(backup / 'original', row['path']), dst)
            elif dst.exists():
                dst.unlink()
        record['status'] = 'reverted_after_error'
        journal.write_text(json.dumps(record, indent=2), encoding='utf-8')
        raise
    print('Pemasangan selesai. Cadangan: ' + str(backup))
    print('Jalankan JALANKAN_PRO.cmd di folder Steezy.')
    return backup


def rollback(target, backup=None):
    target = target.resolve()
    if backup is None:
        journals = sorted((target / 'steezy_backups').glob('*/backup.json'), reverse=True)
        journal = next((p for p in journals if json.loads(p.read_text())['status'] == 'installed'), None)
        if journal is None:
            raise ValueError('Cadangan aktif tidak ditemukan.')
        backup = journal.parent
    record = json.loads((backup / 'backup.json').read_text(encoding='utf-8'))
    if Path(record['target']).resolve() != target or record['status'] != 'installed':
        raise ValueError('Cadangan tidak sesuai target atau sudah dipulihkan.')
    conflicts = []
    for row in record['files']:
        path = contained(target, row['path'])
        if not path.is_file() or digest(path) != row['sha256']:
            conflicts.append(row['path'])
        if row['existed'] and digest(contained(backup / 'original', row['path'])) != row['original_sha256']:
            raise ValueError('Integritas cadangan gagal: ' + row['path'])
    if conflicts:
        raise ValueError('File berubah setelah pemasangan. Simpan/periksa dahulu sebelum pemulihan: ' + ', '.join(conflicts))
    for row in reversed(record['files']):
        dst = contained(target, row['path'])
        if row['existed']:
            atomic_copy(contained(backup / 'original', row['path']), dst)
        else:
            dst.unlink()
    record['status'] = 'restored'
    (backup / 'backup.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print('File versi sebelumnya berhasil dipulihkan.')


def main():
    parser = argparse.ArgumentParser(description='Pasang Steezy Pro Local dengan cadangan otomatis.')
    parser.add_argument('--target')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--skip-deps', action='store_true', help='Untuk pengujian/offline jika Pillow sudah terpasang.')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        raise ValueError('Gunakan Python 3.10 atau lebih baru.')
    target = args.target
    if not target:
        default = Path(r'C:\AI\clipper')
        target = str(default) if default.is_dir() else input('Folder instalasi Steezy (contoh C:\\AI\\clipper): ').strip().strip('"')
    if not target:
        raise ValueError('Folder target belum diisi.')
    if args.rollback:
        rollback(Path(target))
    else:
        install(Path(target), Path(__file__).resolve().parent, args.dry_run, not args.skip_deps)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('GAGAL: ' + str(exc), file=sys.stderr)
        sys.exit(1)
