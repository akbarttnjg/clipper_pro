"""Real frozen M5 tree, real file/SQLite recovery; native runtime probes doubled."""
import contextlib,hashlib,io,json,sqlite3,subprocess,sys,zipfile
from pathlib import Path
import pytest
from tools import build_m6_release as builder,complete_installer as installer
from .frozen_release import _restore

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture(scope='module')
def package(tmp_path_factory):
    path=tmp_path_factory.mktemp('m6-package')/'M6-package'
    with contextlib.redirect_stdout(io.StringIO()):builder.build(path,'0'*40)
    return path

@pytest.fixture
def machine(tmp_path,monkeypatch):
    meta=json.loads((ROOT/'docs/releases/m6_m5_base_provenance.json').read_text())
    target=_restore(tmp_path/'machine',ROOT/'docs/releases/m6_m5_base.zip',meta)
    private={'.env':b'private local env','.env.pro':b'private pro env','uploads/original.mp4':b'private source','clips/final.mp4':b'prior final',
        'models/weights.bin':b'private weights','clipper/fonts/Personal.ttf':b'private font','docs/releases/m0_fixture.zip':b'local historical archive'}
    for name,data in private.items():p=target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    work=target/'work';work.mkdir(exist_ok=True)
    with sqlite3.connect(work/'studio4.sqlite3') as db:
        db.execute('CREATE TABLE projects(id TEXT,document TEXT)');db.execute('CREATE TABLE preserved(note TEXT)');db.execute("INSERT INTO preserved VALUES('before')")
    monkeypatch.setattr(installer,'probe_runtime',lambda *a,**k:{'python':'explicit native-runtime protocol double','work_dir':str(work)})
    monkeypatch.setattr(installer,'require_stopped',lambda:None)
    return target,private

def hashes(target):
    return {p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file() and p.name!='.clipper-install.lock' and not {'steezy_backups','__pycache__'}&set(p.parts)}

def test_install_check_reinstall_exact_rollback_preserves_private_files_SQLite(package,machine):
    target,private=machine;before=hashes(target)
    installer.install(target,package,dry_run=True);assert hashes(target)==before and not (target/'steezy_backups').exists()
    backup=installer.install(target,package);record=json.loads((backup/'complete-backup.json').read_text())
    assert record['version']=='4.0.17' and record['baseline_version']=='4.0.16.1'
    assert record['baseline_capabilities']['m5'] and not record['baseline_capabilities']['m6']
    assert installer.install(target,package) is None
    for name,data in private.items():assert (target/name).read_bytes()==data
    installer.rollback(target,backup);assert hashes(target)==before

@pytest.mark.parametrize('name',['clipper/audio6.py','clipper/transcribe.py'])
def test_local_collision_or_baseline_change_rejected_before_backup(package,machine,name):
    target,_=machine;p=target/name;p.write_text('unknown local source');before=hashes(target)
    with pytest.raises(ValueError,match='Kode lokal berbeda'):installer.install(target,package)
    assert hashes(target)==before and not (target/'steezy_backups').exists()

def test_payload_corruption_is_rejected_before_first_write(package,machine,tmp_path):
    import shutil
    bad=tmp_path/'bad-package';shutil.copytree(package,bad);p=bad/'payload/clipper/audio6.py';p.write_bytes(p.read_bytes()+b'broken')
    target,_=machine;before=hashes(target)
    with pytest.raises(ValueError,match='Paket rusak'):installer.install(target,bad)
    assert hashes(target)==before and not (target/'steezy_backups').exists()

@pytest.mark.parametrize('fault',['copy','post-probe'])
def test_copy_or_post_probe_failure_recovers_every_code_byte(package,machine,monkeypatch,fault):
    target,_=machine;before=hashes(target);original=installer.atomic_copy;count=0
    def copy(source,dest):
        nonlocal count
        if 'payload' in Path(source).parts:
            count+=1
            if count==9:raise OSError('controlled M6 copy failure')
        return original(source,dest)
    def probe(*a,after=False,**k):
        if after:raise OSError('controlled M6 post-probe failure')
        return {'work_dir':str(target/'work')}
    if fault=='copy':monkeypatch.setattr(installer,'atomic_copy',copy)
    else:monkeypatch.setattr(installer,'probe_runtime',probe)
    with pytest.raises(OSError,match='controlled M6'):installer.install(target,package)
    assert hashes(target)==before

@pytest.mark.parametrize('mode',['settings','audio-job'])
def test_M6_state_or_pending_job_requires_latest_checkpoint_before_database_restore(package,machine,mode):
    target,_=machine;backup=installer.install(target,package);dbfile=target/'work/studio4.sqlite3'
    with sqlite3.connect(dbfile) as db:
        db.execute("INSERT INTO preserved VALUES('after-M6')")
        if mode=='settings':db.execute('INSERT INTO projects VALUES(?,?)',('p',json.dumps({'clips':{'c':{'variants':{'portrait':{'audio6':{'enabled':False,'settings':{'source_gain_db':3}}}}}}})))
        else:db.execute('CREATE TABLE jobs(id TEXT,kind TEXT,status TEXT)');db.execute("INSERT INTO jobs VALUES('j','audio_m6','queued')")
    before=hashes(target)
    with pytest.raises(ValueError,match='restore-project-state'):installer.rollback(target,backup)
    assert hashes(target)==before
    installer.rollback(target,backup,restore_project_state=True)
    with sqlite3.connect(backup/'data/studio4-latest-before-rollback.sqlite3') as db:assert db.execute('SELECT count(*) FROM preserved').fetchone()[0]==2 and db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    with sqlite3.connect(dbfile) as db:assert db.execute('SELECT count(*) FROM preserved').fetchone()[0]==1

def test_compatible_M5_edits_survive_code_only_rollback(package,machine):
    target,_=machine;backup=installer.install(target,package);dbfile=target/'work/studio4.sqlite3'
    with sqlite3.connect(dbfile) as db:
        db.execute('INSERT INTO projects VALUES(?,?)',('p',json.dumps({'clips':{'c':{'variants':{'portrait':{'finishing5':{'enabled':True}}}}}})))
        db.execute("INSERT INTO preserved VALUES('compatible-M5-edit')")
    installer.rollback(target,backup)
    with sqlite3.connect(dbfile) as db:assert db.execute('SELECT count(*) FROM preserved').fetchone()[0]==2

def test_actual_installed_Linux_M6_imports_without_model_runtime(package,machine):
    target,_=machine;installer.install(target,package)
    code="import sys;sys.path.insert(0,sys.argv[1]);import clipper.audio6,clipper.audio6_models,clipper.audio6_meter,clipper.audio6_draft,clipper.audio6_jobs,clipper.api_audio6;from clipper.pipeline import RENDER_VERSION;assert RENDER_VERSION=='4.0.17-m6'"
    result=subprocess.run([sys.executable,'-I','-c',code,str(target)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr

def test_ZIP_CRC_all_payload_hashes_trace_private_exclusion(package):
    with zipfile.ZipFile(package.with_suffix('.zip')) as z:
        assert z.testzip() is None;manifest=json.loads(z.read(package.name+'/manifest.json'));assert manifest['version']=='4.0.17'
        for row in manifest['files']:assert hashlib.sha256(z.read(package.name+'/payload/'+row['path'])).hexdigest()==row['sha256']
        trace=json.loads(z.read(package.name+'/M6_REQUIREMENTS.json'));assert len(trace['requirements'])==15 and trace['gate_g6']=='pending_real_corpus_listening'
        assert {r['id'] for r in trace['requirements']}=={'AU'+str(i).zfill(2) for i in range(1,16)}
        assert not any('.env' in r['path'] or r['path'].endswith(('.mp4','.th','.ttf')) for r in manifest['files'])
