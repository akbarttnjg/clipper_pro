"""Bounded, cancellable CPU media operations shared by M9 preview and final."""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from .m9_contract import number


def run(arguments, *, check=lambda: None, timeout=1800, binary='ffmpeg'):
    args = [binary, '-nostdin', '-v', 'error', '-y', '-threads', '2', '-filter_threads', '2', '-filter_complex_threads', '2']
    for argument in arguments:
        if argument == '-i':args += ['-protocol_whitelist', 'file,pipe']
        args.append(str(argument))
    args[-1:-1]=['-threads','2']
    check();started = time.monotonic()
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            while process.poll() is None:
                check()
                if time.monotonic()-started > timeout:raise ValueError('Batas waktu media M9 terlampaui')
                time.sleep(.08)
            if process.returncode:
                errors.seek(max(0, errors.tell()-3000));message = errors.read().decode('utf-8', 'replace')
                raise ValueError('Pemrosesan media M9 gagal: '+message[-3000:])
        finally:
            if process.poll() is None:
                process.kill();process.wait(timeout=10)
    check()
    return {'wall_seconds': round(time.monotonic()-started, 3), 'cpu_threads': 2}


def verify_media(path, *, check=lambda: None):
    from .media_context import inspect
    path = Path(path)
    if not path.is_file() or not path.stat().st_size:raise ValueError('Hasil media kosong')
    run(['-xerror', '-i', str(path), '-map', '0:v?', '-map', '0:a?', '-f', 'null', '-'], check=check, timeout=3600)
    info = inspect(path)
    if info['duration'] > 12*3600:raise ValueError('Hasil melebihi 12 jam')
    return info


def available_filters():
    try:
        result = subprocess.run(['ffmpeg', '-hide_banner', '-filters'], capture_output=True, text=True, timeout=15, check=True)
        return {line.split()[1] for line in result.stdout.splitlines() if len(line.split()) >= 3 and len(line.split()[0]) == 3 and line.split()[0][0] in '.TSC'}
    except (OSError, subprocess.SubprocessError):return set()
