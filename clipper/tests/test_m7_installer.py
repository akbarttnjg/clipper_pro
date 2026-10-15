"""M6→M7 upgrade: baseline collisions, byte recovery and SQLite checkpoints."""
import contextlib,hashlib,io,json,shutil,sqlite3,subprocess,sys,zipfile
from pathlib import Path
import pytest
from tools import build_m7_release as builder,complete_installer as installer
from .frozen_release import _restore,_fixture_path
ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture(scope='module')
def package(tmp_path_factory):
    path=tmp_path_factory.mktemp('m7-installer')/'M6_M7'
    with contextlib.redirect_stdout(io.StringIO()):builder.build(path,'0'*40)
    return path

def restore_m6(target):
    fixture=ROOT/'docs/releases/m7_m6_producer.zip';meta=json.loads(fixture.with_name('m7_m6_producer_provenance.json').read_text())
    _restore(target,fixture,meta)
    for name,digest in meta['external_files'].items():
        data=(ROOT/name).read_bytes();assert hashlib.sha256(data).hexdigest()==digest
        p=_fixture_path(target,name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    return target

@pytest.fixture
def machine(tmp_path,monkeypatch):
    target=restore_m6(tmp_path/'machine');private={'.env':b'private env','.env.pro':b'private pro env','uploads/source.mp4':b'original media',
        'clips/prior.mp4':b'previous final','models/local.bin':b'private model','clipper/fonts/Personal.ttf':b'private font','docs/releases/m0_fixture.zip':b'local historical archive'}
    for name,data in private.items():p=target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    work=target/'work';work.mkdir(exist_ok=True)
    with sqlite3.connect(work/'studio4.sqlite3') as db:
        db.execute('CREATE TABLE projects(id TEXT,document TEXT)');db.execute('CREATE TABLE preserved(note TEXT)');db.execute("INSERT INTO preserved VALUES('before')")
    monkeypatch.setattr(installer,'probe_runtime',lambda *a,**k:{'python':'explicit runtime protocol double; separate native probe supplied','work_dir':str(work)})
    monkeypatch.setattr(installer,'require_stopped',lambda:None)
    return target,private


def hashes(root):return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and not {'steezy_backups','__pycache__'}&set(p.parts)}


def test_check_install_reinstall_rollback_exactly_preserves_private_files(package,machine):
    target,private=machine;before=hashes(target);installer.install(target,package,dry_run=True);assert hashes(target)==before and not (target/'steezy_backups').exists()
    backup=installer.install(target,package);record=json.loads((backup/'complete-backup.json').read_text())
    assert record['version']=='4.0.18' and record['baseline_version']=='4.0.17-m6'
    assert record['baseline_capabilities']['m6'] and not record['baseline_capabilities']['m7'];assert installer.install(target,package) is None
    for name,data in private.items():assert (target/name).read_bytes()==data
    installer.rollback(target,backup);assert hashes(target)==before

@pytest.mark.parametrize('name',['clipper/pipeline.py','clipper/delivery7.py'])
def test_baseline_or_new_path_local_collision_is_rejected_before_backup(package,machine,name):
    target,_=machine;p=target/name;p.write_text('local change');before=hashes(target)
    with pytest.raises(ValueError,match='Kode lokal berbeda'):installer.install(target,package)
    assert hashes(target)==before and not (target/'steezy_backups').exists()


def test_corrupted_payload_is_rejected_before_any_target_write(package,machine,tmp_path):
    bad=tmp_path/'bad';shutil.copytree(package,bad);p=bad/'payload/clipper/delivery7.py';p.write_bytes(p.read_bytes()+b'corruption')
    target,_=machine;before=hashes(target)
    with pytest.raises(ValueError,match='Paket rusak'):installer.install(target,bad)
    assert hashes(target)==before

@pytest.mark.parametrize('fault',['copy','post-probe'])
def test_partial_copy_or_runtime_failure_restores_all_original_code(package,machine,monkeypatch,fault):
    target,_=machine;before=hashes(target);original=installer.atomic_copy;count=0
    def copy(source,dest):
        nonlocal count
        if 'payload' in Path(source).parts:
            count+=1
            if count==11:raise OSError('injected M7 copy failure')
        return original(source,dest)
    def probe(*a,after=False,**k):
        if after:raise OSError('injected M7 post-probe failure')
        return {'work_dir':str(target/'work')}
    if fault=='copy':monkeypatch.setattr(installer,'atomic_copy',copy)
    else:monkeypatch.setattr(installer,'probe_runtime',probe)
    with pytest.raises(OSError,match='injected M7'):installer.install(target,package)
    assert hashes(target)==before

@pytest.mark.parametrize('state',['delivery','review','queued'])
def test_M7_state_requires_explicit_checkpoint_restore_and_keeps_latest_SQLite(package,machine,state):
    target,_=machine;backup=installer.install(target,package);database=target/'work/studio4.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO preserved VALUES('after')")
        if state=='delivery':db.execute('INSERT INTO projects VALUES(?,?)',('p',json.dumps({'exports':[{'version':'4.0.18-m7'}]})))
        elif state=='review':db.execute('CREATE TABLE reviews7(id TEXT)');db.execute("INSERT INTO reviews7 VALUES('r')")
        else:db.execute('CREATE TABLE jobs(id TEXT,kind TEXT,status TEXT)');db.execute("INSERT INTO jobs VALUES('j','delivery_m7','queued')")
    before=hashes(target)
    with pytest.raises(ValueError,match='restore-project-state'):installer.rollback(target,backup)
    assert hashes(target)==before
    installer.rollback(target,backup,restore_project_state=True)
    with sqlite3.connect(database) as db:assert db.execute('SELECT count(*) FROM preserved').fetchone()[0]==1
    with sqlite3.connect(backup/'data/studio4-latest-before-rollback.sqlite3') as db:assert db.execute('SELECT count(*) FROM preserved').fetchone()[0]==2 and db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_compatible_M6_edits_survive_code_only_rollback(package,machine):
    target,_=machine;backup=installer.install(target,package);database=target/'work/studio4.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('INSERT INTO projects VALUES(?,?)',('p',json.dumps({'clips':{'c':{'variants':{'portrait':{'audio6':{'enabled':True}}}}}})))
        db.execute("INSERT INTO preserved VALUES('compatible M6')")
    installer.rollback(target,backup)
    with sqlite3.connect(database) as db:assert db.execute('SELECT count(*) FROM preserved').fetchone()[0]==2


def test_actual_installed_Linux_M7_modules_import_without_download_or_model(package,machine):
    target,_=machine;installer.install(target,package)
    code="import sys;sys.path.insert(0,sys.argv[1]);import clipper.delivery7,clipper.delivery7_jobs,clipper.delivery7_review,clipper.api_delivery7,clipper.audio6;from clipper.pipeline import RENDER_VERSION;assert RENDER_VERSION=='4.0.18-m7'"
    result=subprocess.run([sys.executable,'-I','-c',code,str(target)],capture_output=True,text=True);assert result.returncode==0,result.stderr


def test_ZIP_CRC_payload_checksums_trace_and_private_exclusion(package):
    with zipfile.ZipFile(package.with_suffix('.zip')) as z:
        assert z.testzip() is None;manifest=json.loads(z.read(package.name+'/manifest.json'));assert manifest['version']=='4.0.18'
        for row in manifest['files']:assert hashlib.sha256(z.read(package.name+'/payload/'+row['path'])).hexdigest()==row['sha256']
        trace=json.loads(z.read(package.name+'/M7_REQUIREMENTS.json'));assert len(trace['requirements'])==13 and trace['gate_g7']=='pending_target_editor_acceptance'
        assert {r['id'] for r in trace['requirements']}=={'EX'+str(i).zfill(2) for i in range(1,14)}
        assert not any('.env' in r['path'] or r['path'].endswith(('.mp4','.th','.ttf')) for r in manifest['files'])
