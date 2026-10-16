"""Cumulative audit package: source guards, atomic install and downgrade gates."""
import contextlib
import io
import json
import shutil
import sqlite3
from pathlib import Path
import pytest
from tools import build_audit_22_release as builder, complete_installer as installer
from .test_m8_installer import machine, hashes


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    path=tmp_path_factory.mktemp('audit22-installer')/'Audit22'
    with contextlib.redirect_stdout(io.StringIO()):builder.build(path,'2'*40)
    return path


def test_M7_to_22_install_idempotence_and_exact_rollback(package,machine):
    target,private=machine;before=hashes(target)
    installer.install(target,package,dry_run=True)
    assert hashes(target)==before and not (target/'steezy_backups').exists()
    assert (target/'.clipper-install.lock').read_bytes()==b''
    backup=installer.install(target,package);record=json.loads((backup/'complete-backup.json').read_text())
    assert record['version']=='4.0.22' and not record['baseline_capabilities']['m9_audit_repairs']
    assert installer.install(target,package) is None
    installer.rollback(target,backup)
    assert hashes(target)==before and all((target/n).read_bytes()==v for n,v in private.items())


def test_exact_21_payload_is_accepted_and_restored(package,machine):
    target,_=machine
    import hashlib,zipfile
    producer=builder.ROOT/'docs/releases/audit_22_original_21_payload.zip'
    meta=json.loads(producer.with_name('audit_22_original_21_provenance.json').read_text())
    assert hashlib.sha256(producer.read_bytes()).hexdigest()==meta['sha256']
    with zipfile.ZipFile(producer) as z:
        assert set(z.namelist())==set(meta['members'])
        for name in z.namelist():
            data=z.read(name);assert hashlib.sha256(data).hexdigest()==meta['members'][name]
            path=installer.safe_path(target,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    for name,expected in meta['external_files'].items():
        data=(builder.ROOT/name).read_bytes();assert hashlib.sha256(data).hexdigest()==expected
        path=installer.safe_path(target,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    before=hashes(target);backup=installer.install(target,package)
    installer.rollback(target,backup)
    assert hashes(target)==before


@pytest.mark.parametrize('fault',['copy','runtime'])
def test_install_fault_rolls_back_exactly(package,machine,monkeypatch,fault):
    target,_=machine;before=hashes(target);original=installer.atomic_copy;counter=[0]
    def copy(src,dst):
        if 'payload' in Path(src).parts:
            counter[0]+=1
            if counter[0]==5:raise OSError('injected repair failure')
        return original(src,dst)
    def probe(*args,after=False,**kwargs):
        if after:raise OSError('injected repair failure')
        return {'work_dir':str(target/'work')}
    if fault=='copy':monkeypatch.setattr(installer,'atomic_copy',copy)
    else:monkeypatch.setattr(installer,'probe_runtime',probe)
    with pytest.raises(OSError,match='injected'):installer.install(target,package)
    assert hashes(target)==before


def test_new_restore_state_requires_explicit_checkpoint_downgrade(package,machine):
    target,_=machine;backup=installer.install(target,package);database=target/'work/studio4.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE m9_items(kind TEXT,data TEXT)')
        db.execute("INSERT INTO m9_items VALUES('restored_evidence',?)",(json.dumps({'restored_evidence_only':True}),))
    with pytest.raises(ValueError,match='state|State|restore-project-state'):installer.rollback(target,backup)
    installer.rollback(target,backup,restore_project_state=True)
    with sqlite3.connect(database) as db:assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='m9_items'").fetchone()


def test_manifest_has_all_nine_repairs_and_new_dependencies(package):
    manifest=installer.load_manifest(package)
    assert (package/manifest['install_command']).is_file()
    assert (package/'PULIHKAN_M8_M9_4_0_22.cmd').is_file()
    paths={r['path'] for r in manifest['files']}
    assert set(manifest['audit_findings_fixed'])=={'A01','A02','A03','A04','A05','A07','A08','A09','A10'}
    assert {'clipper/installation_lock.py','clipper/source_guard.py','clipper/source_lineage.py','clipper/runtime/manager.py'}<=paths
    assert (package/'complete_installer.py').read_bytes()==(builder.ROOT/'tools/complete_installer.py').read_bytes()
