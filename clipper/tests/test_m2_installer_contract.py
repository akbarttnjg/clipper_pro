"""Installer contract rejection and raw-vs-text checks use real temporary files."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from tools import complete_installer as installer,build_m2_release


def contract(tmp_path,*,binary=False):
    target=tmp_path/'machine';package=tmp_path/'package';target.mkdir();package.mkdir();(target/'app.py').write_bytes(b'# app\n');(target/'clipper').mkdir()
    name='docs/releases/archive.zip' if binary else 'clipper/fixture.py';old=b'old\r\nbytes' if binary else b'VALUE = 1\n';new=b'new binary' if binary else b'VALUE = 2\n'
    dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(old);source=package/'payload'/name;source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(new)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    manifest={'schema_version':1,'version':'4.0.13','files':[{'path':name,'sha256':sha(new),'baseline_checksum':'sha256' if binary else 'sha256-lf','allowed_text_sha256':[sha(old),sha(new)]}],'guards':[{'path':'app.py','allowed_text_sha256':[sha(b'# app\n')]}]}
    (package/'manifest.json').write_text(json.dumps(manifest));return target,package,manifest,dest


def test_raw_binary_checksum_rejects_crlf_normalization_collision(tmp_path):
    target,package,manifest,dest=contract(tmp_path,binary=True);dest.write_bytes(b'old\nbytes')
    with pytest.raises(ValueError,match='archive.zip'):installer.preflight(target,package,runtime=False,stopped=False)
    assert not (target/'steezy_backups').exists()


def test_raw_binary_checksum_accepts_only_verified_exact_bytes(tmp_path):
    target,package,_,_=contract(tmp_path,binary=True)
    assert len(installer.preflight(target,package,runtime=False,stopped=False)[1])==1


def test_legacy_manifest_without_mode_keeps_crlf_text_compatibility(tmp_path):
    target,package,manifest,dest=contract(tmp_path);manifest['files'][0].pop('baseline_checksum');(package/'manifest.json').write_text(json.dumps(manifest));dest.write_bytes(b'VALUE = 1\r\n')
    assert installer.preflight(target,package,runtime=False,stopped=False)[1]


@pytest.mark.parametrize('problem',['nonobject_manifest','nonobject_row','missing_path','hash_integer','baseline_hash_integer','unknown_mode','duplicate_between_lists','preserved_collision','bad_preserved_type'])
def test_malformed_contract_rejected_before_any_backup_or_copy(tmp_path,problem):
    target,package,manifest,dest=contract(tmp_path);before=dest.read_bytes()
    if problem=='nonobject_manifest':manifest=[]
    elif problem=='nonobject_row':manifest['files']=[None]
    elif problem=='missing_path':manifest['files'][0].pop('path')
    elif problem=='hash_integer':manifest['files'][0]['sha256']=12
    elif problem=='baseline_hash_integer':manifest['files'][0]['allowed_text_sha256']=[12]
    elif problem=='unknown_mode':manifest['files'][0]['baseline_checksum']='ignore'
    elif problem=='duplicate_between_lists':manifest['guards'].append({'path':'CLIPPER/fixture.py','allowed_text_sha256':['0'*64]})
    elif problem=='preserved_collision':manifest['preserved_local_files']=['clipper/fixture.py']
    else:manifest['preserved_local_files']='docs/releases/m0_fixture.zip'
    (package/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):installer.install(target,package)
    assert dest.read_bytes()==before;assert not (target/'steezy_backups').exists()


@pytest.mark.parametrize('list_name',['payload_paths','guard_paths'])
def test_builder_rejects_reintroduction_of_mutable_fixture(tmp_path,list_name):
    root=tmp_path/'producer';release=root/'docs/releases';release.mkdir(parents=True)
    baseline={'payload_paths':[],'guard_paths':[]};baseline[list_name].append('docs/releases/m0_fixture.zip');(release/'m2_base_hashes.json').write_text(json.dumps(baseline))
    output=tmp_path/'package'
    with patch.object(build_m2_release,'ROOT',root),pytest.raises(ValueError,match='Fixture lokal lama'):build_m2_release.build(output,'0'*40)
    assert not output.exists();assert not output.with_suffix('.zip').exists()
