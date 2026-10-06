"""Atomic metadata and owned runtime generations (no project file mutations)."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import uuid


def write(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally: temporary.unlink(missing_ok=True)


def read(path, default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:return default


def safe_path(root, name):
    relative=PurePosixPath(name)
    if not name or relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
        raise ValueError('Path runtime tidak aman')
    root=Path(root).resolve();path=root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root):raise ValueError('Path keluar dari folder runtime')
    return path


def digest(path, algorithm='sha256'):
    path=Path(path);hash_=hashlib.new('sha1' if algorithm=='git-sha1' else algorithm)
    if algorithm=='git-sha1':hash_.update(('blob '+str(path.stat().st_size)+'\0').encode())
    with path.open('rb') as stream:
        while block:=stream.read(1024*1024):hash_.update(block)
    return hash_.hexdigest()


def runtime_root(repo=None, work=None):
    if os.environ.get('CLIPPER_RUNTIME_DIR'):return Path(os.environ['CLIPPER_RUNTIME_DIR']).expanduser().resolve()
    if work:return Path(work).resolve()/'runtime'
    repo=Path(repo or Path(__file__).resolve().parents[2])
    return (repo/os.environ.get('WORK_DIR','work')/'runtime').resolve()
