import json
from pathlib import Path
import pytest
import steezy_pro_installer as installer


def fixture(tmp_path):
    target=tmp_path/'clipper';target.mkdir();(target/'clipper').mkdir()
    (target/'app.py').write_text('original')
    (target/'uploads').mkdir();(target/'uploads/source.mp4').write_bytes(b'user data')
    package=tmp_path/'package';(package/'payload/clipper').mkdir(parents=True)
    (package/'payload/app.py').write_text('updated')
    (package/'payload/clipper/new.py').write_text('new')
    files=[{'path':p.relative_to(package/'payload').as_posix(),'sha256':installer.digest(p)} for p in (package/'payload').rglob('*') if p.is_file()]
    (package/'manifest.json').write_text(json.dumps({'version':'2.0','files':files}))
    return target,package


def test_overlay_backup_and_guarded_rollback(tmp_path):
    target,package=fixture(tmp_path)
    before=(target/'uploads/source.mp4').read_bytes()
    installer.install(target,package,dry_run=True,install_deps=False)
    assert (target/'app.py').read_text()=='original'
    backup=installer.install(target,package,install_deps=False)
    assert (target/'app.py').read_text()=='updated'
    installer.rollback(target,backup)
    assert (target/'app.py').read_text()=='original'
    assert not (target/'clipper/new.py').exists()
    assert (target/'uploads/source.mp4').read_bytes()==before


def test_checksum_and_path_escape_rejected(tmp_path):
    target,package=fixture(tmp_path)
    (package/'payload/app.py').write_text('tampered')
    with pytest.raises(ValueError,match='rusak'):
        installer.install(target,package,install_deps=False)
    with pytest.raises(ValueError,match='aman'):
        installer.contained(target,'../outside')
    assert (target/'app.py').read_text()=='original'


def test_install_failure_restores_originals(tmp_path,monkeypatch):
    target,package=fixture(tmp_path)
    copy=installer.atomic_copy
    def fail(src,dst):
        if dst==target/'clipper/new.py':
            raise OSError('simulated disk failure')
        return copy(src,dst)
    monkeypatch.setattr(installer,'atomic_copy',fail)
    with pytest.raises(OSError):
        installer.install(target,package,install_deps=False)
    assert (target/'app.py').read_text()=='original'
    assert not (target/'clipper/new.py').exists()


def test_rollback_refuses_to_overwrite_later_changes(tmp_path):
    target,package=fixture(tmp_path)
    backup=installer.install(target,package,install_deps=False)
    (target/'app.py').write_text('edited after installation')
    with pytest.raises(ValueError,match='berubah'):
        installer.rollback(target,backup)
    assert (target/'app.py').read_text()=='edited after installation'
