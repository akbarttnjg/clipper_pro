"""Add missing CPU ONNX dependencies to the selected isolated Silero runtime.

This explicit maintenance command adds packages while constraining every
existing version. It does not create a replacement Torch environment, change
the active pointer, or promote the previous audio sample to a passing result.
Run with the Clipper server stopped. Python stdlib only in the launcher.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import sqlite3
import subprocess
import sys
import uuid


CHECK = '''import json, math
import numpy, onnxruntime, torch
from silero_vad import load_silero_vad
model = load_silero_vad(onnx=True)
value = float(model(torch.zeros(512, dtype=torch.float32), 16000).item())
assert math.isfinite(value) and 0 <= value <= 1
providers = model.session.get_providers()
assert providers == ['CPUExecutionProvider'], providers
print(json.dumps({'passed': True, 'level': 'dependency-repair', 'device': 'cpu',
    'providers': providers, 'silence_probability': value,
    'detail': 'Dependensi dan inference ONNX CPU pada 512 sampel hening berhasil; uji audio pengguna belum dijalankan.'}))
'''


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def contained(root, relative):
    relative = PurePosixPath(relative)
    if relative.is_absolute() or '..' in relative.parts or ':' in str(relative) or '\\' in str(relative):
        raise ValueError('Path generasi tidak aman')
    root = Path(root).resolve()
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Path generasi keluar dari runtime')
    return path


def runtime_root(target, override=None):
    if override:
        return Path(override).expanduser().resolve()
    settings = {key: os.environ[key] for key in ('CLIPPER_RUNTIME_DIR', 'WORK_DIR') if key in os.environ}
    # Match app.py: .env respects process values, .env.pro overrides them.
    # Only two path settings are read; no credentials are copied or printed.
    for name in ('.env', '.env.pro'):
        path = target / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\s*(?:export\s+)?(CLIPPER_RUNTIME_DIR|WORK_DIR)\s*=\s*(.*?)\s*$', line)
            if not match:
                continue
            key, value = match.groups()
            if value[:1] in ('"', "'"):
                quote = value[0]
                end = value.find(quote, 1)
                if end < 0:
                    raise ValueError('Path runtime dalam ' + name + ' belum lengkap; gunakan --runtime')
                value = value[1:end]
            else:
                value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
            if '${' in value or '\\n' in value:
                raise ValueError('Path runtime memakai ekspansi; tentukan --runtime secara langsung')
            if name == '.env.pro' or key not in settings:
                settings[key] = value
    path = Path(settings['CLIPPER_RUNTIME_DIR']) if settings.get('CLIPPER_RUNTIME_DIR') else Path(settings.get('WORK_DIR', 'work')) / 'runtime'
    path = path.expanduser()
    return (path if path.is_absolute() else target / path).resolve()


def selected_environment(target, runtime=None):
    target = Path(target).expanduser().resolve()
    if not (target / 'app.py').is_file() or not (target / 'clipper/runtime/catalog.py').is_file():
        raise ValueError('Pilih folder mesin yang sudah memakai upgrade tahap 2')
    root = runtime_root(target, runtime)
    pointer = read(root / 'components/silero-vad/active.json')
    generation = pointer.get('generation', '')
    if not generation.startswith('silero-vad/'):
        raise ValueError('Pointer aktif bukan generasi Silero VAD')
    directory = contained(root / 'generations', generation)
    receipt = read(directory / 'receipt.json')
    if receipt.get('component') != 'silero-vad' or not receipt.get('installed') or receipt.get('generation') != generation:
        raise ValueError('Receipt aktif Silero tidak sesuai')
    py = directory / 'env' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not py.is_file() or not (directory / 'installed-lock.txt').is_file():
        raise ValueError('Lingkungan Silero belum lengkap')
    return target, root, directory, py, receipt


def require_idle(root):
    try:
        connection = socket.create_connection(('127.0.0.1', 8765), timeout=.3)
    except OSError:
        pass
    else:
        connection.close()
        raise ValueError('Hentikan server Clipper dengan Ctrl+C sebelum perbaikan')
    db = root / 'runtime.sqlite3'
    if not db.is_file():
        raise ValueError('Database antrean runtime tidak ditemukan')
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as connection:
        busy = connection.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running','cancel_requested')").fetchone()[0]
    if busy:
        raise ValueError('Antrean masih aktif atau menunggu; hentikan dahulu melalui panel komponen')


def versions(freeze):
    return {re.sub(r'[-_.]+', '-', name).lower(): version
            for line in freeze.splitlines() if '==' in line
            for name, version in [line.split('==', 1)]}


def invoke(command, environment, timeout=600):
    # Lists preserve spaces in Windows paths; no shell interpolation is used.
    result = subprocess.run([str(arg) for arg in command], env=environment,
                            capture_output=True, text=True, errors='replace', timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-4000:] or 'Perintah berhenti dengan kode ' + str(result.returncode))
    return result.stdout


def repair(target, runtime=None, dry_run=False, runner=invoke):
    target, root, directory, py, receipt = selected_environment(target, runtime)
    print('Target: ' + str(target) + '\nSilero aktif: ' + str(directory))
    if dry_run:
        print('Pemeriksaan selesai. Belum ada perubahan atau unduhan.')
        return None
    require_idle(root)
    environment = {**os.environ, 'PYTHONNOUSERSITE': '1', 'PYTHONUNBUFFERED': '1',
                   'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'OMP_NUM_THREADS': '4'}
    environment.pop('PYTHONPATH', None)
    before = runner([py, '-m', 'pip', 'freeze', '--all'], environment, timeout=60)
    locked = versions(before)
    if not {'torch', 'torchaudio', 'silero-vad'}.issubset(locked):
        raise ValueError('Paket utama Silero tidak lengkap; perbaikan ringan ditolak')
    old_lock = (directory / 'installed-lock.txt').read_bytes()
    for artifact in receipt.get('artifacts', []):
        if artifact['path'] == 'installed-lock.txt' and artifact['hash'] != hashlib.sha256(old_lock).hexdigest():
            raise ValueError('Lock lingkungan telah berubah; periksa dahulu sebelum perbaikan')
    journal_dir = root / 'repairs/silero-vad' / (datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    journal_dir.mkdir(parents=True)
    constraint = journal_dir / 'before-lock.txt'
    constraint.write_text(before, encoding='utf-8')
    write(journal_dir / 'before-receipt.json', receipt)
    write(journal_dir / 'status.json', {'status': 'started', 'generation': receipt['generation']})
    print('Melengkapi NumPy dan ONNX Runtime CPU. Torch tetap dikunci pada versi yang sudah ada.\nLaporan: ' + str(journal_dir), flush=True)
    try:
        command = [py, '-m', 'pip', '--isolated', 'install', '--disable-pip-version-check',
                   '--index-url', 'https://pypi.org/simple', '--only-binary=:all:',
                   '--cache-dir', root / 'cache/pip', '--constraint', constraint,
                   '--report', journal_dir / 'pip-report.json', 'numpy', 'onnxruntime']
        try:
            output = runner(command, environment)
            (journal_dir / 'pip-output.txt').write_text(output, encoding='utf-8')
        except Exception as exc:
            (journal_dir / 'pip-output.txt').write_text(str(exc), encoding='utf-8')
            raise
        after = runner([py, '-m', 'pip', 'freeze', '--all'], environment, timeout=60)
        current = versions(after)
        if any(current.get(name) != version for name, version in locked.items()):
            raise ValueError('Versi paket lama berubah; metadata tidak diaktifkan. Lihat laporan perbaikan.')
        if not {'numpy', 'onnxruntime'}.issubset(current):
            raise ValueError('NumPy / ONNX Runtime belum lengkap')
        checked = runner([py, '-c', CHECK], environment, timeout=120)
        (journal_dir / 'check-output.txt').write_text(checked, encoding='utf-8')
        diagnostic = json.loads(checked.strip().splitlines()[-1])
        if not diagnostic.get('passed') or diagnostic.get('device') != 'cpu' or diagnostic.get('level') != 'dependency-repair':
            raise ValueError('Hasil pemeriksaan dependensi belum valid')
        # Preserve sample/test and active pointer. Update the lock hash so a
        # later generation rollback still verifies its actual package lock.
        new_versions = dict(line.split('==', 1) for line in after.splitlines() if '==' in line)
        new_versions['python'] = receipt.get('versions', {}).get('python', '')
        new_lock = after.encode('utf-8')
        updated = {**receipt, 'versions': new_versions, 'diagnostic': diagnostic,
                   'dependency_repairs': receipt.get('dependency_repairs', []) + [journal_dir.relative_to(root).as_posix()]}
        updated['artifacts'] = [{**a, 'hash': hashlib.sha256(new_lock).hexdigest()} if a['path'] == 'installed-lock.txt' else a
                                for a in receipt.get('artifacts', [])]
        write(journal_dir / 'after-receipt.json', updated)
        (journal_dir / 'after-lock.txt').write_bytes(new_lock)
        original_receipt = (directory / 'receipt.json').read_bytes()
        try:
            temporary = directory / 'installed-lock.txt.repair-tmp'
            temporary.write_bytes(new_lock)
            os.replace(temporary, directory / 'installed-lock.txt')
            write(directory / 'receipt.json', updated)
        except BaseException:
            (directory / 'installed-lock.txt').write_bytes(old_lock)
            (directory / 'receipt.json').write_bytes(original_receipt)
            raise
        result = {'status': 'completed', 'generation': receipt['generation'],
                  'added_packages': {name: version for name, version in current.items() if name not in locked},
                  'existing_versions_preserved': True, 'diagnostic': diagnostic, 'sample_status_preserved': True}
        write(journal_dir / 'status.json', result)
        print('Perbaikan dependensi selesai. Jalankan mesin, pilih CPU, lalu Uji sampel Silero VAD pada sumber video Anda.')
        return result
    except BaseException as exc:
        write(journal_dir / 'status.json', {'status': 'failed', 'error': str(exc), 'generation': receipt['generation']})
        raise


def main():
    parser = argparse.ArgumentParser(description='Lengkapi dependensi Silero VAD tanpa memasang ulang Torch.')
    parser.add_argument('--target')
    parser.add_argument('--runtime', help='Folder work/runtime jika konfigurasi memakai path khusus')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--package', help='Paket overlay katalog, bila dijalankan dari ZIP perbaikan')
    args = parser.parse_args()
    target = args.target
    if not target:
        default = Path(r'C:\AI\clipper')
        target = str(default) if default.is_dir() else input('Folder mesin Clipper (contoh C:\\AI\\clipper): ').strip().strip('"')
    if not target:
        raise ValueError('Folder mesin belum diisi')
    # Validate environment before any source overlay is copied.
    _, root, _, _, _ = selected_environment(target, args.runtime)
    if not args.dry_run:
        require_idle(root)
    if args.package:
        from steezy_pro_installer import install
        install(Path(target), Path(args.package), dry_run=args.dry_run, install_deps=False)
    repair(target, args.runtime, dry_run=args.dry_run)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Perbaikan dihentikan. Jalankan kembali untuk melengkapi dependensi.', file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print('GAGAL: ' + str(exc), file=sys.stderr)
        sys.exit(1)
