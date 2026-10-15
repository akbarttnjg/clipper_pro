"""Historical builders never rebuild old releases from future checkout code."""
import importlib.util,json,tempfile,hashlib,zipfile
from pathlib import Path

def build(root,stem,builder_name,output,source_commit,verification=None):
    if not isinstance(source_commit,str) or len(source_commit)!=40 or any(c not in '0123456789abcdef' for c in source_commit):raise ValueError('SHA commit sumber harus lengkap')
    root=Path(root);fixture=root/'docs/releases'/(stem+'.zip');meta=json.loads(fixture.with_name(stem+'_provenance.json').read_text())
    if hashlib.sha256(fixture.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('Frozen producer checksum mismatch')
    with tempfile.TemporaryDirectory(prefix='clipper-frozen-producer-') as tmp:
        target=Path(tmp)
        from clipper.tests.frozen_release import _restore,_fixture_path
        _restore(target,fixture,meta)
        for n,digest in meta['external_files'].items():
            data=(root/n).read_bytes()
            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Frozen producer external archive changed: '+n)
            dest=_fixture_path(target,n);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        path=target/'tools'/builder_name;spec=importlib.util.spec_from_file_location('clipper_pinned_'+stem,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        result=module.build(output,meta['source_commit'],verification)
        result['frozen_producer_commit']=meta['source_commit'];return result
