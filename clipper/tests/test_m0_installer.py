"""Actual full baseline upgrade, import check, SQLite backup and code-only rollback."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch
import pytest
from .frozen_release import restore

ROOT=Path(__file__).resolve().parents[2]

from clipper.tests._media_requirements import OPENCV_AVAILABLE, OPENCV_REASON


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


@pytest.fixture
def release(tmp_path,monkeypatch):
    target=restore(tmp_path/'machine');package=tmp_path/'upgrade'
    installer=module('complete_installer');builder=module('build_m0_release')
    producer=restore(tmp_path/'m0-producer',producer=True)
    with contextlib.redirect_stdout(io.StringIO()),patch.dict(builder.complete_build.__globals__,{'ROOT':producer}):report=builder.build(package,'0'*40)
    work=target/'work';work.mkdir();database=work/'studio4.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE preserved(note TEXT)');db.execute("INSERT INTO preserved VALUES('before')")
    (target/'.venv').symlink_to(Path(sys.prefix),target_is_directory=True)
    (target/'.env').write_text('WORK_DIR=work\nCUSTOM_VALUE=preserve\n')
    custom=target/'clipper/fonts/CustomUser.ttf';custom.write_bytes(b'custom user font marker')
    model=target/'ClipperModels/user.bin';model.parent.mkdir();model.write_bytes(b'user model marker')
    monkeypatch.setenv('WORK_DIR',str(work));monkeypatch.setenv('OUT_DIR',str(target/'clips'))
    monkeypatch.setattr(installer,'require_stopped',lambda:None)
    return installer,target,package,database,report


@pytest.mark.skipif(not OPENCV_AVAILABLE,reason=OPENCV_REASON)
def test_m0_actual_upgrade_imports_backup_idempotence_and_rollback(release):
    installer,target,package,database,report=release
    before=(target/'clipper/project_store.py').read_bytes()
    with contextlib.redirect_stdout(io.StringIO()):
        backup=installer.install(target,package)
        assert installer.probe_runtime(target,after=True)['core_modules']=='available'
        assert installer.install(target,package) is None
    record=json.loads((backup/'complete-backup.json').read_text())
    assert record['version']=='4.0.11' and report['zip_crc']=='passed'
    with sqlite3.connect(record['database_backup']['copy']) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT * FROM preserved').fetchall()==[('before',)]
    with sqlite3.connect(database) as db:db.execute("INSERT INTO preserved VALUES('after')")
    with contextlib.redirect_stdout(io.StringIO()):installer.rollback(target,backup)
    assert (target/'clipper/project_store.py').read_bytes()==before
    assert not (target/'clipper/artifact_store.py').exists()
    assert 'CUSTOM_VALUE=preserve' in (target/'.env').read_text()
    assert (target/'clipper/fonts/CustomUser.ttf').read_bytes()==b'custom user font marker'
    assert (target/'ClipperModels/user.bin').read_bytes()==b'user model marker'
    with sqlite3.connect(database) as db:assert db.execute('SELECT count(*) FROM preserved').fetchone()[0]==2


@pytest.mark.skipif(not OPENCV_AVAILABLE,reason=OPENCV_REASON)
def test_m0_disk_failure_mid_copy_rolls_back_every_file(release,monkeypatch):
    installer,target,package,database,_=release
    before={p.relative_to(target):p.read_bytes() for p in target.rglob('*') if p.is_file() and '.venv' not in p.parts}
    real_copy=installer.atomic_copy;count=0
    def controlled(source,destination):
        nonlocal count
        if 'payload' in Path(source).parts:
            count+=1
            if count==9:raise OSError('controlled ENOSPC at payload copy 9')
        return real_copy(source,destination)
    monkeypatch.setattr(installer,'atomic_copy',controlled)
    with contextlib.redirect_stdout(io.StringIO()),pytest.raises(OSError,match='ENOSPC'):installer.install(target,package)
    assert all((target/name).read_bytes()==value for name,value in before.items())
    assert not (target/'clipper/artifact_store.py').exists()


def test_m0_unknown_local_code_and_corrupt_package_rejected_before_backup(release):
    installer,target,package,database,_=release
    local=target/'clipper/render.py';local.write_text(local.read_text()+'\n# unknown local customization\n')
    with pytest.raises(ValueError,match='Kode lokal berbeda'):installer.preflight(target,package)
    assert not (target/'steezy_backups').exists()
    payload=package/'payload/clipper/job_queue.py';payload.write_text('corrupt')
    with pytest.raises(ValueError,match='rusak'):installer.preflight(target,package)
    assert not (target/'steezy_backups').exists()
