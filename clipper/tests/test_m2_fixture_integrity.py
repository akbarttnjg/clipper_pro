"""Frozen test data must work without reading a user's mutable QA archive."""
import hashlib
import json
from pathlib import Path
import zipfile
from unittest.mock import patch
import pytest
from . import frozen_release
from tools import build_m0_release


def fixture_archive(path, contents=None, *, source_commit='a'*40, hashes=None, extra=None):
    contents = contents or {'app.py': b'VALUE = 1\n', 'clipper/fixture.py': b'VALUE = 2\n'}
    info = {'base_commit': source_commit, 'raw_sha256': hashes if hashes is not None else {n:hashlib.sha256(b).hexdigest() for n,b in contents.items()}}
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as zipped:
        for name,data in contents.items():zipped.writestr(name,data)
        zipped.writestr('__provenance__.json',json.dumps(info))
        if extra is not None:zipped.writestr(*extra)
    expected = {'source_commit': source_commit,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'files':len(info['raw_sha256'])}
    return expected


def test_versioned_fixture_ignores_mutable_local_archive(tmp_path,monkeypatch):
    release=tmp_path/'releases';path=release/'m2_m0_fixture.zip';expected=fixture_archive(path)
    (release/'m2_m0_fixture_provenance.json').write_text(json.dumps(expected))
    legacy=release/'m0_fixture.zip';legacy.write_bytes(b'not even a zip; user evidence must be preserved')
    monkeypatch.setattr(frozen_release,'RELEASES',release)
    with patch('tools.freeze_m0_baseline.export_baseline',side_effect=AssertionError('No git access or legacy regeneration allowed')):
        target=frozen_release.restore(tmp_path/'target')
    assert (target/'app.py').read_bytes()==b'VALUE = 1\n'
    assert legacy.read_bytes()==b'not even a zip; user evidence must be preserved'


@pytest.mark.parametrize('problem',['missing_archive','missing_metadata','bad_archive_sha','wrong_commit','wrong_count'])
def test_versioned_fixture_fails_closed_without_legacy_fallback(tmp_path,monkeypatch,problem):
    release=tmp_path/'releases';path=release/'m2_m0_fixture.zip';expected=fixture_archive(path)
    metadata=release/'m2_m0_fixture_provenance.json';metadata.write_text(json.dumps(expected))
    fixture_archive(release/'m0_fixture.zip')
    if problem=='missing_archive':path.unlink()
    elif problem=='missing_metadata':metadata.unlink()
    elif problem=='bad_archive_sha':path.write_bytes(path.read_bytes()+b'tampered')
    else:
        expected['source_commit' if problem=='wrong_commit' else 'files']='b'*40 if problem=='wrong_commit' else 99
        metadata.write_text(json.dumps(expected))
    monkeypatch.setattr(frozen_release,'RELEASES',release);target=tmp_path/'target'
    with pytest.raises(ValueError):frozen_release.restore(target)
    assert not target.exists()


def test_corrupt_later_member_does_not_extract_earlier_valid_member(tmp_path):
    path=tmp_path/'fixture.zip';expected=fixture_archive(path,hashes={'app.py':hashlib.sha256(b'VALUE = 1\n').hexdigest(),'clipper/fixture.py':'0'*64})
    target=tmp_path/'target'
    with pytest.raises(ValueError,match='file checksum'):frozen_release._restore(target,path,expected)
    assert not target.exists()


@pytest.mark.parametrize('name',['../outside.py','/absolute.py','clipper/../../outside.py','work/data.sqlite3','ClipperModels/model.bin','clipper\\escape.py'])
def test_unsafe_fixture_members_rejected_without_extraction(tmp_path,name):
    path=tmp_path/'fixture.zip';expected=fixture_archive(path,{'app.py':b'valid','clipper/valid.py':b'valid',name:b'unsafe'})
    target=tmp_path/'target'
    with pytest.raises(ValueError):frozen_release._restore(target,path,expected)
    assert not target.exists();assert not (tmp_path/'outside.py').exists()


@pytest.mark.parametrize('extra',[('unrecorded.txt',b'x'),('APP.PY',b'duplicate case')])
def test_extra_or_case_colliding_members_rejected(tmp_path,extra):
    path=tmp_path/'fixture.zip';expected=fixture_archive(path,extra=extra)
    with pytest.raises(ValueError,match='members mismatch'):frozen_release._restore(tmp_path/'target',path,expected)
    assert not (tmp_path/'target').exists()


def test_existing_destination_symlink_is_not_followed(tmp_path):
    path=tmp_path/'fixture.zip';expected=fixture_archive(path);target=tmp_path/'target';target.mkdir();outside=tmp_path/'outside';outside.mkdir()
    (target/'clipper').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='Symlink'):frozen_release._restore(target,path,expected)
    assert not (target/'app.py').exists();assert list(outside.iterdir())==[]


def test_legacy_release_without_m2_snapshot_still_works(tmp_path,monkeypatch):
    release=tmp_path/'releases';fixture_archive(release/'m0_fixture.zip');monkeypatch.setattr(frozen_release,'RELEASES',release)
    target=frozen_release.restore(tmp_path/'target');assert (target/'clipper/fixture.py').read_bytes()==b'VALUE = 2\n'


def test_m0_builder_uses_its_frozen_producer_not_current_installation(tmp_path):
    producer=tmp_path/'producer';fixture_archive(producer/'docs/releases/m0_fixture.zip')
    def complete_build_double(*args,**kwargs):
        assert kwargs['version']=='4.0.11' and kwargs['base_file']=='m0_base_hashes.json'
        return {'tested':True}
    with patch.dict(complete_build_double.__globals__,{'ROOT':producer}),patch.object(build_m0_release,'export_baseline',side_effect=AssertionError('Historical fixture must not regenerate')),patch.object(build_m0_release,'complete_build',complete_build_double):
        # Only building is replaced: the selected producer path check is real.
        assert build_m0_release.build(tmp_path/'output','0'*40)=={'tested':True}

