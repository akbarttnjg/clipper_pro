"""Cumulative M7/M8->M8-M9 overlay and safe rollback checkpoints."""
import contextlib,hashlib,io,json,shutil,sqlite3,zipfile
from pathlib import Path
import pytest
from tools import build_m9_release as builder,build_m8_release,complete_installer as installer
from .test_m8_installer import machine,hashes


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    path=tmp_path_factory.mktemp('m9-installer')/'M8_M9'
    with contextlib.redirect_stdout(io.StringIO()):builder.build(path,'1'*40)
    return path


def test_M7_to_cumulative_check_install_repeat_exact_rollback(package,machine):
    target,private=machine;before=hashes(target)
    installer.install(target,package,dry_run=True);assert hashes(target)==before
    backup=installer.install(target,package);record=json.loads((backup/'complete-backup.json').read_text())
    assert record['version']=='4.0.20' and record['baseline_capabilities']['m7'] and not record['baseline_capabilities']['m9']
    assert installer.install(target,package) is None
    installer.rollback(target,backup);assert hashes(target)==before
    assert all((target/n).read_bytes()==v for n,v in private.items())


def test_intermediate_pinned_M8_is_accepted_and_rollback_returns_M8(package,machine,tmp_path):
    target,_=machine;m8=tmp_path/'M8'
    with contextlib.redirect_stdout(io.StringIO()):build_m8_release.build(m8,'0'*40)
    installer.install(target,m8);before=hashes(target);backup=installer.install(target,package)
    assert json.loads((backup/'complete-backup.json').read_text())['baseline_capabilities']['m8']
    installer.rollback(target,backup);assert hashes(target)==before and not (target/'clipper/m9.py').exists()


@pytest.mark.parametrize('name',['clipper/m9.py','clipper/render.py','static/studio4.js'])
def test_code_collision_does_not_overwrite(package,machine,name):
    target,_=machine;path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('local work');before=hashes(target)
    with pytest.raises(ValueError,match='Kode lokal berbeda'):installer.install(target,package)
    assert hashes(target)==before


def test_corrupt_payload_rejected(package,machine,tmp_path):
    target,_=machine;bad=tmp_path/'bad';shutil.copytree(package,bad);(bad/'payload/clipper/m9.py').write_text('corrupt');before=hashes(target)
    with pytest.raises(ValueError,match='Paket rusak'):installer.install(target,bad)
    assert hashes(target)==before


@pytest.mark.parametrize('fault',['copy','runtime'])
def test_failure_rolls_back_all_source(package,machine,monkeypatch,fault):
    target,_=machine;before=hashes(target);original=installer.atomic_copy;counter=[0]
    def copy(src,dst):
        if 'payload' in Path(src).parts:
            counter[0]+=1
            if counter[0]==9:raise OSError('injected M9 failure')
        return original(src,dst)
    def probe(*a,after=False,**kw):
        if after:raise OSError('injected M9 failure')
        return {'work_dir':str(target/'work')}
    monkeypatch.setattr(installer,'atomic_copy',copy) if fault=='copy' else monkeypatch.setattr(installer,'probe_runtime',probe)
    with pytest.raises(OSError,match='injected'):installer.install(target,package)
    assert hashes(target)==before


def test_used_M9_requires_explicit_checkpoint_and_preserves_latest(package,machine):
    target,_=machine;backup=installer.install(target,package);database=target/'work/studio4.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE m9_tracks(id TEXT)');db.execute("INSERT INTO m9_tracks VALUES('recorded')");db.execute("INSERT INTO sentinel VALUES('after')")
    before=hashes(target)
    with pytest.raises(ValueError,match='restore-project-state'):installer.rollback(target,backup)
    assert hashes(target)==before
    installer.rollback(target,backup,restore_project_state=True)
    with sqlite3.connect(database) as db:assert db.execute('SELECT COUNT(*) FROM sentinel').fetchone()[0]==1
    with sqlite3.connect(backup/'data/studio4-latest-before-rollback.sqlite3') as db:assert db.execute('SELECT COUNT(*) FROM m9_tracks').fetchone()[0]==1


def test_active_capture_and_unresolved_external_inference_block_reinstall(package,machine):
    target,_=machine;installer.install(target,package);database=target/'work/studio4.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE m9_items(kind TEXT,data TEXT)');db.execute('INSERT INTO m9_items VALUES(?,?)',('recording','{"status":"capturing"}'))
    before=hashes(target)
    with pytest.raises(ValueError,match='rekaman M9'):installer.install(target,package,dry_run=True)
    assert hashes(target)==before
    with sqlite3.connect(database) as db:
        db.execute('UPDATE m9_items SET data=?',('{"status":"paused"}',));db.execute('CREATE TABLE m9_resource_holds(state TEXT)');db.execute("INSERT INTO m9_resource_holds VALUES('submission_unknown')")
    with pytest.raises(ValueError,match='inference M9'):installer.install(target,package,dry_run=True)


def test_no_prior_database_new_M9_state_is_checkpointed_before_restore(package,machine):
    target,_=machine;database=target/'work/studio4.sqlite3';database.unlink();backup=installer.install(target,package)
    with sqlite3.connect(database) as db:db.execute('CREATE TABLE m9_chunks(id TEXT)');db.execute("INSERT INTO m9_chunks VALUES('new')")
    with pytest.raises(ValueError,match='restore-project-state'):installer.rollback(target,backup)
    installer.rollback(target,backup,restore_project_state=True);assert not database.exists()
    with sqlite3.connect(backup/'data/studio4-latest-before-rollback.sqlite3') as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_all_89_IDs_crc_payload_and_frozen_M8_producer(package,tmp_path):
    with zipfile.ZipFile(package.with_suffix('.zip')) as z:
        assert z.testzip() is None;manifest=json.loads(z.read(package.name+'/manifest.json'))
        assert manifest['version']=='4.0.20' and not manifest['complete_milestone_acceptance']
        assert len(manifest['requirements']['M8'])==44 and len(manifest['requirements']['M9'])==45
        for row in manifest['files']:assert hashlib.sha256(z.read(package.name+'/payload/'+row['path'])).hexdigest()==row['sha256']
        assert not any('.env' in r['path'] or r['path'].endswith(('.mp4','.onnx','.wav','.ttf')) for r in manifest['files'])
    old=tmp_path/'old-M8'
    with contextlib.redirect_stdout(io.StringIO()):build_m8_release.build(old,'2'*40)
    assert 'api_m9' not in (old/'payload/clipper/api_studio.py').read_text()
    assert '4.0.19-m8' in (old/'payload/app.py').read_text()
