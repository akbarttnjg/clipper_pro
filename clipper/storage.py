"""Atomic, restart-safe local state and source-aware cache keys."""
import hashlib
import json
import os
import uuid
from pathlib import Path


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('w',encoding='utf-8') as stream:
            stream.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
            stream.flush();os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:temp.unlink(missing_ok=True)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def source_key(path, cfg):
    p = Path(path)
    if not p.exists():
        return None
    from .dependency_cache import content_id
    from .analysis_adapter import asr_fingerprint
    actual=content_id(p,fresh=True)
    return asr_fingerprint(getattr(cfg,'source_content_id','') or actual,
        getattr(cfg,'audio_stream_id','') or 'audio:0',cfg,alias_revision=None)+':'+actual
