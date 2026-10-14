"""Historical release tests use frozen public sources, never future branch code."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile
from tools.complete_installer import safe_path

RELEASES = Path(__file__).resolve().parents[2] / 'docs/releases'


def _fixture_path(root, name):
    # The historical producer includes root-level launchers, changelogs and
    # public source archives beyond the installer's deliberately narrow list.
    if isinstance(name, str) and PurePosixPath(name).parts == (name,) and (
            name == 'LICENSE' or not name.startswith('.') and Path(name).suffix in
            {'.md', '.py', '.cmd', '.zip', '.toml', '.ini', '.ps1', '.sh'}):
        if any(c in name for c in ('\\', ':', '\0')) or name in ('.', '..'):
            raise ValueError('Frozen release path unsafe: ' + name)
        target = Path(root).resolve() / name
        if target.is_symlink():raise ValueError('Symlink tidak diizinkan: ' + name)
    else:
        target = safe_path(root, name)
    if target.exists() and not target.is_file():
        raise ValueError('Frozen release destination is not a file: ' + name)
    return target


def _restore(root, fixture, expected=None):
    """Validate the complete archive before creating any destination file."""
    root = Path(root)
    if not fixture.is_file() or fixture.is_symlink():
        raise ValueError('Frozen release fixture missing or unsafe: ' + fixture.name)
    if expected is not None and hashlib.sha256(fixture.read_bytes()).hexdigest() != expected['sha256']:
        raise ValueError('Frozen release archive checksum mismatch: ' + fixture.name)
    with zipfile.ZipFile(fixture) as zipped:
        info = json.loads(zipped.read('__provenance__.json'))
        hashes = info.get('raw_sha256')
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError('Frozen release file hashes missing')
        names = zipped.namelist()
        if len(set(n.casefold() for n in names)) != len(names) or set(names) != set(hashes) | {'__provenance__.json'}:
            raise ValueError('Frozen release archive members mismatch')
        if expected is not None:
            actual_commit = info.get('source_commit', info.get('base_commit'))
            if actual_commit != expected['source_commit'] or len(hashes) != expected['files']:
                raise ValueError('Frozen release provenance mismatch')
        files = []
        for name, digest in hashes.items():
            target = _fixture_path(root, name)
            member = zipped.getinfo(name)
            if member.is_dir() or (member.external_attr >> 16 & 0o170000) == 0o120000:
                raise ValueError('Frozen release member is not a regular file: ' + name)
            data = zipped.read(name)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('Frozen release file checksum mismatch: ' + name)
            files.append((target, data))
    root.mkdir(parents=True, exist_ok=True)
    for target, data in files:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def restore(root,*,producer=False):
    fixture=RELEASES/('m0_producer_fixture.zip' if producer else 'm0_fixture.zip')
    versioned=RELEASES/'m2_m0_fixture.zip'
    metadata=RELEASES/'m2_m0_fixture_provenance.json'
    if not producer and (versioned.exists() or metadata.exists()):
        if not metadata.is_file():raise ValueError('Frozen M2/M0 fixture provenance missing')
        return _restore(root,versioned,json.loads(metadata.read_text(encoding='utf-8')))
    if not fixture.is_file():
        if producer:raise ValueError('Frozen M0 producer fixture missing; restore the verified release test fixture before running historical installer checks.')
        from tools.freeze_m0_baseline import export_baseline
        export_baseline(fixture)
    return _restore(root,fixture)


def restore_m1(root):
    fixture=RELEASES/'m2_m1_fixture.zip'
    expected=json.loads(fixture.with_name('m2_fixture_provenance.json').read_text())
    return _restore(root,fixture,expected)


def restore_m2(root):
    fixture=RELEASES/'m3_m2_fixture.zip'
    expected=json.loads(fixture.with_name('m3_m2_fixture_provenance.json').read_text(encoding='utf-8'))
    return _restore(root,fixture,expected)


def restore_m3_producer(root):
    fixture=RELEASES/'m4_m3_producer.zip';expected=json.loads(fixture.with_name('m4_m3_producer_provenance.json').read_text())
    # Historical binary archives are content-addressed, unchanged prerequisites;
    # avoid recursively duplicating tens of megabytes inside every new fixture.
    binaries=[]
    for name,digest in expected['external_files'].items():
        source=Path(__file__).resolve().parents[2]/name
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise ValueError('Frozen M3 external archive changed: '+name)
        binaries.append((name,source.read_bytes()))
    root=_restore(root,fixture,expected)
    for name,data in binaries:
        target=_fixture_path(root,name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return root


def restore_m4_producer(root):
    fixture=RELEASES/"m5_m4_producer.zip";expected=json.loads(fixture.with_name("m5_m4_producer_provenance.json").read_text())
    binary=[]
    for name,digest in expected["external_files"].items():
        source=Path(__file__).resolve().parents[2]/name
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise ValueError("Frozen M4 external archive changed: "+name)
        binary.append((name,source.read_bytes()))
    root=_restore(root,fixture,expected)
    for name,data in binary:
        target=_fixture_path(root,name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return root


def restore_m4_audit(root):
    """Restore exact e6ed700 code for cumulative repair installation tests."""
    fixture=RELEASES/'m0_m4_repair_m4_fixture.zip'
    expected=json.loads(fixture.with_name('m0_m4_repair_m4_provenance.json').read_text())
    external=[]
    for name,digest in expected['external_files'].items():
        source=Path(__file__).resolve().parents[2]/name
        data=source.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Frozen M4 external archive changed: '+name)
        external.append((name,data))
    root=_restore(root,fixture,expected)
    for name,data in external:
        dest=_fixture_path(root,name);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    return root


def restore_repair_producer(root,stem):
    fixture=RELEASES/(stem+'.zip');expected=json.loads(fixture.with_name(stem+'_provenance.json').read_text())
    external=[]
    for name,digest in expected['external_files'].items():
        source=Path(__file__).resolve().parents[2]/name;data=source.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Frozen repair producer external archive changed: '+name)
        external.append((name,data))
    root=_restore(root,fixture,expected)
    for name,data in external:
        target=_fixture_path(root,name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return root


def restore_m5_producer(root):return restore_repair_producer(root,'m0_m5_repair_m5')


def restore_m4_fixed_producer(root):return restore_repair_producer(root,'m0_m5_repair_m4_fixed')
