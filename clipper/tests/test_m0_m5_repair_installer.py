"""Cumulative installer on frozen real trees; native probes are explicit doubles."""
import contextlib,hashlib,io,json,sqlite3
from pathlib import Path
import pytest
from tools import build_m0_m5_repair_release as builder,complete_installer as installer
from .frozen_release import restore_m1,restore_m2,restore_m3_producer,restore_m4_audit,restore_m4_fixed_producer,restore_m5_producer
from .test_m1_installer import restore_baseline

@pytest.fixture(scope='module')
def package(tmp_path_factory):
    path=tmp_path_factory.mktemp('cumulative')/'package'
    with contextlib.redirect_stdout(io.StringIO()):builder.build(path,'0'*40)
    return path

def base(path,name):
    if name=='m0':restore_baseline(path)
    elif name=='m1':restore_m1(path)
    elif name=='m2':restore_m2(path)
    elif name=='m3':restore_m2(path);restore_m3_producer(path)
    elif name=='m4':restore_m4_audit(path)
    elif name=='m4-fixed':restore_m4_fixed_producer(path)
    elif name=='m5':restore_m5_producer(path)
    return path

def hashes(target):
    return {p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file() and p.name!='.clipper-install.lock' and 'steezy_backups' not in p.parts}

def runtime_double(monkeypatch,target):
    monkeypatch.setattr(installer,'probe_runtime',lambda *a,**kw:{'python':'explicit native runtime protocol double','work_dir':str(target/'work')})
    monkeypatch.setattr(installer,'require_stopped',lambda:None)

def seed(target):
    files={'.env':b'private env','uploads/user.mp4':b'original source','clips/final.mp4':b'prior final','models/weights.bin':b'private weights','clipper/fonts/Personal.ttf':b'private font','docs/releases/m0_fixture.zip':b'unknown local archive'}
    for name,data in files.items():p=target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    work=target/'work';work.mkdir(exist_ok=True)
    with sqlite3.connect(work/'studio4.sqlite3') as db:db.execute('CREATE TABLE projects(id TEXT,document TEXT)');db.execute('CREATE TABLE preserved(note TEXT)');db.execute("INSERT INTO preserved VALUES('before')")
    return files

@pytest.mark.parametrize('name',['m0','m1','m2','m3','m4','m4-fixed','m5'])
def test_each_baseline_check_install_reinstall_and_exact_rollback(package,tmp_path,monkeypatch,name):
    target=base(tmp_path/name,name);files=seed(target);runtime_double(monkeypatch,target);before=hashes(target)
    installer.install(target,package,dry_run=True);assert hashes(target)==before
    backup=installer.install(target,package);assert backup and '4.0.16.1' in (target/'static/index.html').read_text()
    assert installer.install(target,package) is None
    for path,data in files.items():assert (target/path).read_bytes()==data
    installer.rollback(target,backup);assert hashes(target)==before

@pytest.mark.parametrize('name,requires_state',[('m4',True),('m4-fixed',True),('m5',False)])
def test_M5_data_rollback_uses_verified_baseline_capabilities(package,tmp_path,monkeypatch,name,requires_state):
    target=base(tmp_path/name,name);seed(target);runtime_double(monkeypatch,target);backup=installer.install(target,package);dbpath=target/'work/studio4.sqlite3'
    with sqlite3.connect(dbpath) as db:
        db.execute('INSERT INTO projects VALUES(?,?)',('new',json.dumps({'clips':{'c':{'variants':{'square':{'finishing5':{'enabled':True,'style':{'base_hex':'#112233'}}}}}}})))
        db.execute('CREATE TABLE assets5(id TEXT,data TEXT)');db.execute("INSERT INTO assets5 VALUES('new','{}')")
    if requires_state:
        before=hashes(target)
        with pytest.raises(ValueError,match='restore-project-state'):installer.rollback(target,backup)
        assert hashes(target)==before
        installer.rollback(target,backup,restore_project_state=True)
        with sqlite3.connect(backup/'data/studio4-latest-before-rollback.sqlite3') as db:assert db.execute('SELECT count(*) FROM assets5').fetchone()[0]==1
    else:
        installer.rollback(target,backup)
        with sqlite3.connect(dbpath) as db:assert db.execute('SELECT count(*) FROM assets5').fetchone()[0]==1


def test_unknown_local_edit_rejected_before_first_write(package,tmp_path,monkeypatch):
    target=base(tmp_path/'m5','m5');seed(target);runtime_double(monkeypatch,target);p=target/'clipper/finishing5_plan.py';p.write_text(p.read_text()+'\n# unknown local edit\n');before=hashes(target)
    with pytest.raises(ValueError,match='Kode lokal berbeda'):installer.install(target,package)
    assert hashes(target)==before and not (target/'steezy_backups').exists()

@pytest.mark.parametrize('fault',['copy','post-probe'])
def test_interrupted_install_restores_all_code_and_database(package,tmp_path,monkeypatch,fault):
    target=base(tmp_path/'m5','m5');seed(target);runtime_double(monkeypatch,target);before=hashes(target);original=installer.atomic_copy;count=0
    def failing_copy(source,dest):
        nonlocal count
        if 'payload' in Path(source).parts:
            count+=1
            if count==11:raise OSError('controlled copy fault')
        return original(source,dest)
    def failing_probe(*args,after=False,**kw):
        if after:raise OSError('controlled post-probe fault')
        return {'work_dir':str(target/'work')}
    monkeypatch.setattr(installer,'atomic_copy',failing_copy if fault=='copy' else original)
    if fault=='post-probe':monkeypatch.setattr(installer,'probe_runtime',failing_probe)
    with pytest.raises(OSError,match='controlled'):installer.install(target,package)
    assert hashes(target)==before
