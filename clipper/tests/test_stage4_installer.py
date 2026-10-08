"""Exercise install failures and rollback using disposable code and data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('stage4_installer',Path(__file__).resolve().parents[2]/'tools/stage4_installer.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


def sha(data):return hashlib.sha256(data).hexdigest()


@pytest.fixture
def overlay(tmp_path,monkeypatch):
    target=tmp_path/'Mesin lama';package=tmp_path/'Paket Tahap 4'
    (target/'clipper').mkdir(parents=True);(target/'app.py').write_text('x=1\n')
    (target/'clipper/value.py').write_bytes(b'x=1\r\n')
    (target/'work').mkdir();(target/'work/project.sqlite3').write_bytes(b'project-data')
    (target/'clips').mkdir();(target/'clips/hasil.mp4').write_bytes(b'video-data')
    (target/'.env').write_bytes(b'personal-settings')
    rows=[]
    for name,data,old in [('clipper/value.py',b'x=2\n',b'x=1\n'),('tools/new.py',b'y=3\n',None)]:
        p=package/'payload'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        rows.append({'path':name,'sha256':sha(data),'allowed_text_sha256':[sha(data)]+([sha(old)] if old else [])})
    manifest={'schema_version':1,'version':'4.0.4','source_commit':'a'*40,'files':rows,
              'guards':[{'path':'app.py','allowed_text_sha256':[sha(b'x=1\n')]}]}
    (package/'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(installer,'probe_runtime',lambda *a,**k:{'python':'3.12'})
    monkeypatch.setattr(installer,'require_stopped',lambda *a:None)
    return target,package,manifest


def test_check_has_no_writes_and_install_rollback_preserve_data(overlay):
    target,package,_=overlay
    before={str(p.relative_to(target)):p.read_bytes() for p in target.rglob('*') if p.is_file()}
    assert installer.install(target,package,True) is None
    assert not (target/'steezy_backups').exists()
    backup=installer.install(target,package)
    assert (target/'clipper/value.py').read_bytes()==b'x=2\n'
    assert installer.install(target,package) is None
    installer.rollback(target,backup)
    assert not (target/'tools/new.py').exists()
    assert all((target/name).read_bytes()==data for name,data in before.items())


def test_unknown_code_is_not_overwritten(overlay):
    target,package,_=overlay;(target/'clipper/value.py').write_bytes(b'custom=99\n')
    with pytest.raises(ValueError,match='Kode lokal'):installer.install(target,package)
    assert (target/'clipper/value.py').read_bytes()==b'custom=99\n'
    assert not (target/'steezy_backups').exists()


def test_corrupt_payload_stops_before_writes(overlay):
    target,package,_=overlay;(package/'payload/tools/new.py').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='Paket rusak'):installer.install(target,package)
    assert (target/'clipper/value.py').read_bytes()==b'x=1\r\n'


def test_copy_failure_restores_existing_and_removes_new_files(overlay,monkeypatch):
    target,package,_=overlay;original=installer.atomic_copy;failed=False
    def broken(source,dest):
        nonlocal failed
        if source==package/'payload/tools/new.py' and not failed:
            failed=True;raise OSError('simulated disk error')
        return original(source,dest)
    monkeypatch.setattr(installer,'atomic_copy',broken)
    with pytest.raises(OSError,match='disk error'):installer.install(target,package)
    assert (target/'clipper/value.py').read_bytes()==b'x=1\r\n'
    assert not (target/'tools/new.py').exists()
    journal=next((target/'steezy_backups').glob('stage4-*/stage4-backup.json'))
    assert json.loads(journal.read_text())['status']=='restored'


def test_import_failure_after_copy_rolls_back(overlay,monkeypatch):
    target,package,_=overlay
    def probe(target,after=False):
        if after:raise ValueError('post-install import failed')
        return {'python':'3.12'}
    monkeypatch.setattr(installer,'probe_runtime',probe)
    with pytest.raises(ValueError,match='post-install'):installer.install(target,package)
    assert (target/'clipper/value.py').read_bytes()==b'x=1\r\n'
    assert not (target/'tools/new.py').exists()


def test_rollback_rejects_modified_file_before_restoring_anything(overlay):
    target,package,_=overlay;backup=installer.install(target,package)
    (target/'tools/new.py').write_bytes(b'user_change=1\n')
    with pytest.raises(ValueError,match='File berubah'):installer.rollback(target,backup)
    assert (target/'clipper/value.py').read_bytes()==b'x=2\n'


def test_prepared_journal_can_resume_rollback(overlay):
    target,package,_=overlay;backup=installer.install(target,package)
    journal=backup/'stage4-backup.json';record=json.loads(journal.read_text());record['status']='prepared'
    journal.write_text(json.dumps(record));(target/'tools/new.py').unlink()
    installer.rollback(target,backup)
    assert (target/'clipper/value.py').read_bytes()==b'x=1\r\n'


def test_rollback_refuses_replaced_directory_before_any_restore(overlay):
    target,package,_=overlay;backup=installer.install(target,package)
    new=target/'tools/new.py';new.unlink();new.mkdir()
    with pytest.raises(ValueError,match='berubah menjadi folder'):installer.rollback(target,backup)
    assert (target/'clipper/value.py').read_bytes()==b'x=2\n'
    assert new.is_dir()


@pytest.mark.parametrize('name',['../app.py','work/project.sqlite3','C:/app.py','clipper\\value.py','/app.py'])
def test_windows_and_data_paths_are_refused(tmp_path,name):
    with pytest.raises(ValueError):installer.safe_path(tmp_path,name)


def test_symlink_payload_cannot_change_other_files(overlay):
    target,package,_=overlay
    (target/'clipper/value.py').unlink();(target/'clipper/value.py').symlink_to(target/'app.py')
    with pytest.raises(ValueError,match='Symlink'):installer.install(target,package)
    assert (target/'app.py').read_bytes()==b'x=1\n'
