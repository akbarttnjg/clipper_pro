"""Versioned M9 inputs. No arbitrary FFmpeg graphs, shell commands or paid provider URLs."""
import hashlib
import json
import math
import re
from pathlib import Path
from .m8_contract import AccessDenied, canonical, integer, only, text

VERSION = '4.0.22-m8-m9'
MAX_CHUNK = 25 * 1024**2
MAX_RECORDING = 30 * 1024**3
MAX_CHUNKS = 10000
KINDS = {'screen', 'camera', 'microphone', 'slides', 'system_audio'}
MIME = {'video/webm', 'audio/webm', 'video/mp4', 'audio/mp4', 'audio/ogg', 'audio/wav'}


def number(value, label, minimum=0, maximum=86400):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(label + ' di luar batas')
    return float(value)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checksum(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('SHA256 harus 64 karakter heksadesimal')
    return value


def safe_media(path, root):
    path = Path(path)
    if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()) or not path.is_file():
        raise ValueError('Berkas M9 hilang atau keluar dari folder kerja')
    return path.resolve()


def spans(value, duration):
    if not isinstance(value, list) or len(value) > 300:
        raise ValueError('Maksimal 300 interval')
    result = []; previous = 0.
    for row in value:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError('Interval harus [awal, akhir]')
        a = number(row[0], 'Awal', previous, duration)
        b = number(row[1], 'Akhir', a, duration)
        if b <= a:
            raise ValueError('Interval kosong')
        result.append([a, b]); previous = b
    return result


def atomic_bytes(path, data):
    import os
    import uuid
    path = Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.part')
    try:
        with temporary.open('xb') as handle:
            handle.write(data);handle.flush();os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != 'nt':
            fd = os.open(path.parent, os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def artifact(path):
    from .dependency_cache import content_id
    path = Path(path)
    return {'name': path.name, 'bytes': path.stat().st_size, 'content_id': content_id(path, fresh=True)}
