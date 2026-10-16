"""M7->M8 overlay, code collisions, rollback checkpoints and frozen M7 producer."""
import contextlib,hashlib,io,json,shutil,sqlite3,subprocess,sys,zipfile
from pathlib import Path
import pytest
from tools import build_m8_release as builder,complete_installer as installer
from .frozen_release import _restore,_fixture_path
ROOT=Path(__file__).resolve().parents[2]


def restore_m7(target):
    fixture=ROOT/'docs/releases/m8_m7_producer.zip';meta=json.loads(fixture.with_name('m8_m7_producer_provenance.json').read_text())
    _restore(target,fixture,meta)
    for name,expected in meta['external_files'].items():
        data=(ROOT/name).read_bytes();assert hashlib.sha256(data).hexdigest()==expected
        path=_fixture_path(target,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return target


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    path=tmp_path_factory.mktemp('m8-installer')/'M8'
    with contextlib.redirect_stdout(io.StringIO()):builder.build(path,'0'*40)
    return path


@pytest.fixture
def machine(tmp_path,monkeypatch):
    target=restore_m7(tmp_path/'machine');private={'.env':b'private environment','.env.pro':b'private pro','uploads/source.mp4':b'source sentinel',
        'clips/prior.mp4':b'prior final','models/model.bin':b'private model','clipper/fonts/Personal.ttf':b'private font','docs/releases/m0_fixture.zip':b'private local fixture'}
    for name,data in private.items():path=target/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    work=target/'work';work.mkdir()
    with sqlite3.connect(work/'studio4.sqlite3') as db:
        db.execute('CREATE TABLE projects(id TEXT,document TEXT)');db.execute('CREATE TABLE sentinel(value TEXT)');db.execute("INSERT INTO sentinel VALUES('before')")
    monkeypatch.setattr(installer,'probe_runtime',lambda *a,**kw:{'python':'explicit runtime protocol double; native check supplied separately','work_dir':str(work)})
    monkeypatch.setattr(installer,'require_stopped',lambda:None)
    return target,private


def hashes(root):return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.name!='.clipper-install.lock' and not {'steezy_backups','__pycache__'}&set(p.parts)}


def test_check_install_idempotence_and_exact_code_rollback(package,machine):
    target,private=machine;before=hashes(target)
    installer.install(target,package,dry_run=True);assert hashes(target)==before and not (target/'steezy_backups').exists()
    backup=installer.install(target,package);record=json.loads((backup/'complete-backup.json').read_text())
    assert record['version']=='4.0.19' and record['baseline_capabilities']['m7'] and not record['baseline_capabilities']['m8']
    assert installer.install(target,package) is None
    installer.rollback(target,backup);assert hashes(target)==before
    assert all((target/name).read_bytes()==data for name,data in private.items())


@pytest.mark.parametrize('name',['clipper/m8.py','clipper/delivery7.py'])
def test_new_file_or_baseline_collision_rejected_without_target_change(package,machine,name):
    target,_=machine;path=target/name;path.write_text('local modification');before=hashes(target)
    with pytest.raises(ValueError,match='Kode lokal berbeda'):installer.install(target,package)
    assert hashes(target)==before and not (target/'steezy_backups').exists()


def test_corrupt_payload_rejected(package,machine,tmp_path):
    bad=tmp_path/'bad';shutil.copytree(package,bad);(bad/'payload/clipper/m8.py').write_text('corrupt')
    target,_=machine;before=hashes(target)
    with pytest.raises(ValueError,match='Paket rusak'):installer.install(target,bad)
    assert hashes(target)==before


@pytest.mark.parametrize('fault',['copy','runtime'])
def test_copy_failure_or_post_probe_restores_code(package,machine,monkeypatch,fault):
    target,_=machine;before=hashes(target);original=installer.atomic_copy;counter=[0]
    def copy(src,dst):
        if 'payload' in Path(src).parts:
            counter[0]+=1
            if counter[0]==8:raise OSError('injected M8 failure')
        return original(src,dst)
    def probe(*a,after=False,**kw):
        if after:raise OSError('injected M8 failure')
        return {'work_dir':str(target/'work')}
    monkeypatch.setattr(installer,'atomic_copy',copy) if fault=='copy' else monkeypatch.setattr(installer,'probe_runtime',probe)
    with pytest.raises(OSError,match='injected'):installer.install(target,package)
    assert hashes(target)==before


@pytest.mark.parametrize('table',['m8_accounts','m8_sessions','m8_publish','m8_records'])
def test_used_M8_state_requires_explicit_latest_checkpoint(package,machine,table):
    target,_=machine;backup=installer.install(target,package);database=target/'work/studio4.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE '+table+'(id TEXT)');db.execute('INSERT INTO '+table+" VALUES('m8-state')");db.execute("INSERT INTO sentinel VALUES('after')")
    before=hashes(target)
    with pytest.raises(ValueError,match='restore-project-state'):installer.rollback(target,backup)
    assert hashes(target)==before
    installer.rollback(target,backup,restore_project_state=True)
    with sqlite3.connect(database) as db:assert db.execute('SELECT COUNT(*) FROM sentinel').fetchone()[0]==1
    with sqlite3.connect(backup/'data/studio4-latest-before-rollback.sqlite3') as db:assert db.execute('SELECT COUNT(*) FROM sentinel').fetchone()[0]==2 and db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_new_database_after_install_has_safe_checkpoint_restore(package,machine):
    target,_=machine;database=target/'work/studio4.sqlite3';database.unlink()
    backup=installer.install(target,package)
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE m8_accounts(id TEXT)');db.execute("INSERT INTO m8_accounts VALUES('new-state')")
    with pytest.raises(ValueError,match='restore-project-state'):installer.rollback(target,backup)
    installer.rollback(target,backup,restore_project_state=True)
    assert not database.exists()
    with sqlite3.connect(backup/'data/studio4-latest-before-rollback.sqlite3') as db:assert db.execute('SELECT COUNT(*) FROM m8_accounts').fetchone()[0]==1


def test_package_inventory_and_all_44_requirements(package):
    with zipfile.ZipFile(package.with_suffix('.zip')) as archive:
        assert archive.testzip() is None
        manifest=json.loads(archive.read(package.name+'/manifest.json'));assert manifest['version']=='4.0.19'
        for row in manifest['files']:assert hashlib.sha256(archive.read(package.name+'/payload/'+row['path'])).hexdigest()==row['sha256']
        trace=json.loads(archive.read(package.name+'/M8_REQUIREMENTS.json'));assert len(trace['requirements'])==44 and sum(trace['counts'].values())==44
        assert not any('.env' in row['path'] or row['path'].endswith(('.mp4','.wav','.ttf')) for row in manifest['files'])


def test_historical_M7_builder_uses_frozen_M7_code_not_future_M8(package,tmp_path):
    from tools import build_m7_release
    path=tmp_path/'old-m7'
    with contextlib.redirect_stdout(io.StringIO()):build_m7_release.build(path,'1'*40)
    assert 'api_m8' not in (path/'payload/clipper/api_studio.py').read_text()
    assert 'f6f1f6a' in (path/'manifest.json').read_text()
