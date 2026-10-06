"""Regression checks for the incomplete existing Silero ONNX environment."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import pytest

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('repair_silero', REPO / 'tools/repair_silero_vad.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


@pytest.fixture
def existing(tmp_path, monkeypatch):
    monkeypatch.delenv('CLIPPER_RUNTIME_DIR', raising=False)
    monkeypatch.delenv('WORK_DIR', raising=False)
    target = tmp_path / 'engine with spaces'
    (target / 'clipper/runtime').mkdir(parents=True)
    (target / 'app.py').write_text('')
    (target / 'clipper/runtime/catalog.py').write_text('')
    root = target / 'work/runtime'
    directory = root / 'generations/silero-vad/runtime-existing'
    py = directory / 'env' / ('Scripts/python.exe' if repair.os.name == 'nt' else 'bin/python')
    py.parent.mkdir(parents=True)
    py.write_bytes(b'python-fixture')
    frozen = 'pip==25.0.1\nsilero-vad==6.2.3\ntorch==2.8.0\ntorchaudio==2.8.0\nsympy==1.14.0\n'
    (directory / 'installed-lock.txt').write_text(frozen)
    failed_sample = dict(passed=False, level='sample', detail="No module named 'numpy'", tested_at=123)
    receipt = dict(component='silero-vad', installed=True, generation='silero-vad/runtime-existing',
                   test=failed_sample, versions={'python': 'Python 3.12.10'},
                   artifacts=[dict(path='installed-lock.txt', hash=hashlib.sha256(frozen.encode()).hexdigest(), algorithm='sha256')])
    repair.write(directory / 'receipt.json', receipt)
    pointer = root / 'components/silero-vad/active.json'
    pointer.parent.mkdir(parents=True)
    repair.write(pointer, dict(generation=receipt['generation'], previous='silero-vad/older', enabled=False))
    with sqlite3.connect(root / 'runtime.sqlite3') as db:
        db.execute('CREATE TABLE jobs(status TEXT)')
    monkeypatch.setattr(repair.socket, 'create_connection', lambda *a, **k: (_ for _ in ()).throw(OSError('stopped')))
    return SimpleNamespace(target=target, root=root, directory=directory, py=py, frozen=frozen,
                           receipt=receipt, pointer=pointer, calls=[])


def runner_for(existing, change_old=False, fail_install=False, fail_check=False):
    freezes = [existing.frozen, existing.frozen + 'numpy==2.0.0\nonnxruntime==1.20.0\nprotobuf==5.0.0\n']
    if change_old:
        freezes[1] = freezes[1].replace('torch==2.8.0', 'torch==2.9.0')
    def runner(command, environment, **kwargs):
        args = [str(arg) for arg in command]
        existing.calls.append((args, environment, kwargs))
        assert args[0] == str(existing.py)
        if 'freeze' in args:
            return freezes.pop(0)
        if 'install' in args:
            constraint = Path(args[args.index('--constraint') + 1])
            assert constraint.read_text() == existing.frozen
            assert args[-2:] == ['numpy', 'onnxruntime']
            assert '--isolated' in args and '--only-binary=:all:' in args
            assert not any(a.startswith('torch') for a in args)
            if fail_install:
                raise RuntimeError('download interrupted')
            return 'installed light dependencies\n'
        if '-c' in args:
            if fail_check:
                raise RuntimeError('ONNX inference failed')
            return json.dumps(dict(passed=True, level='dependency-repair', device='cpu', providers=['CPUExecutionProvider']))
        raise AssertionError(args)
    return runner


def test_repair_uses_active_component_and_preserves_old_versions_pointer_and_failed_sample(existing, monkeypatch):
    monkeypatch.setenv('PYTHONPATH', '/unrelated/core/site-packages')
    before_pointer = existing.pointer.read_bytes()
    protected = existing.target / '.venv/keep'
    protected.parent.mkdir()
    protected.write_text('core untouched')
    result = repair.repair(existing.target, runner=runner_for(existing))
    assert result['existing_versions_preserved'] and result['sample_status_preserved']
    assert result['added_packages'] == {'numpy': '2.0.0', 'onnxruntime': '1.20.0', 'protobuf': '5.0.0'}
    receipt = repair.read(existing.directory / 'receipt.json')
    assert receipt['test'] == existing.receipt['test']
    assert receipt['diagnostic']['level'] == 'dependency-repair'
    assert receipt['artifacts'][0]['hash'] == hashlib.sha256((existing.directory / 'installed-lock.txt').read_bytes()).hexdigest()
    assert existing.pointer.read_bytes() == before_pointer
    assert protected.read_text() == 'core untouched'
    assert all('PYTHONPATH' not in env for _, env, _ in existing.calls)


def test_dry_run_does_not_call_pip_create_repair_or_write_metadata(existing):
    before = {p: p.read_bytes() for p in existing.root.rglob('*') if p.is_file()}
    assert repair.repair(existing.target, dry_run=True, runner=lambda *a, **k: pytest.fail('pip in dry run')) is None
    assert {p: p.read_bytes() for p in existing.root.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('busy', ['queued', 'running', 'cancel_requested'])
def test_busy_queue_blocks_package_mutation(existing, busy):
    with sqlite3.connect(existing.root / 'runtime.sqlite3') as db:
        db.execute('INSERT INTO jobs VALUES(?)', (busy,))
    with pytest.raises(ValueError, match='Antrean'):
        repair.repair(existing.target, runner=lambda *a, **k: pytest.fail('mutated busy environment'))


def test_running_server_blocks_package_mutation(existing, monkeypatch):
    monkeypatch.setattr(repair.socket, 'create_connection', lambda *a, **k: SimpleNamespace(close=lambda: None))
    with pytest.raises(ValueError, match='Hentikan server'):
        repair.repair(existing.target, runner=lambda *a, **k: pytest.fail('pip with server running'))


@pytest.mark.parametrize('generation', ['silero-vad/../../../outside', 'whisperx/runtime-existing', 'silero-vad/C:/outside'])
def test_wrong_or_escaping_generation_rejected(existing, generation):
    repair.write(existing.pointer, dict(generation=generation))
    with pytest.raises(ValueError):
        repair.repair(existing.target, runner=lambda *a, **k: pytest.fail('wrong environment'))


@pytest.mark.parametrize('kind', ['change', 'install', 'check'])
def test_failures_never_promote_sample_or_rewrite_old_lock(existing, kind):
    receipt_bytes = (existing.directory / 'receipt.json').read_bytes()
    with pytest.raises((RuntimeError, ValueError)):
        repair.repair(existing.target, runner=runner_for(existing, change_old=kind == 'change', fail_install=kind == 'install', fail_check=kind == 'check'))
    assert (existing.directory / 'receipt.json').read_bytes() == receipt_bytes
    assert (existing.directory / 'installed-lock.txt').read_text() == existing.frozen
    status = next((existing.root / 'repairs/silero-vad').glob('*/status.json'))
    assert repair.read(status)['status'] == 'failed'


def test_custom_runtime_matches_env_pro_override_without_executing_file(existing):
    (existing.target / '.env').write_text('WORK_DIR=unused\nHF_TOKEN=private\n')
    (existing.target / '.env.pro').write_text('WORK_DIR="work" # comment\nUNRELATED=$(bad command)\n')
    assert repair.runtime_root(existing.target) == existing.root
    assert repair.selected_environment(existing.target)[1] == existing.root
    (existing.target / '.env.pro').write_text('WORK_DIR=${EXTERNAL}\n')
    with pytest.raises(ValueError, match='--runtime'):
        repair.runtime_root(existing.target)
    assert repair.runtime_root(existing.target, str(existing.root)) == existing.root


def test_new_silero_plan_locks_both_onnx_dependencies(existing, monkeypatch):
    from clipper.runtime import install
    from clipper.runtime.state import read
    manager = SimpleNamespace(root=existing.root)
    monkeypatch.setattr(install, 'stable_package', lambda name: name if '==' in name else name + '==1.0.0')
    directory = existing.root / 'generations/silero-vad/new'
    directory.mkdir(parents=True)
    plan = install.plan(manager, {'component': 'silero-vad', 'options': {}}, directory)
    assert {'numpy==1.0.0', 'onnxruntime==1.0.0'}.issubset(plan['packages'])
    assert read(directory / 'plan.json')['packages'] == plan['packages']
