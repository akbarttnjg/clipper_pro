"""Atomic, restart-safe local state and source-aware cache keys."""
import hashlib
import json
import os
from pathlib import Path


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def source_key(path, cfg):
    p = Path(path)
    if not p.exists():
        return None
    stat = p.stat()
    # Header/tail + size/mtime avoid hashing a multi-GB source before every review.
    h = hashlib.sha256()
    with p.open('rb') as stream:
        h.update(stream.read(1024 * 1024))
        if stat.st_size > 1024 * 1024:
            stream.seek(max(0, stat.st_size - 1024 * 1024))
            h.update(stream.read())
    h.update(json.dumps([stat.st_size, stat.st_mtime_ns, cfg.whisper_model,
                         cfg.language, cfg.whisper_compute, 'asr-v2']).encode())
    return h.hexdigest()
