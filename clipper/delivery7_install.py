"""Stdlib-only extracted delivery verification and portable project preparation."""
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
from urllib.parse import quote


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return 'sha256:'+h.hexdigest()


def safe(root,name):
    value=Path(name);target=root/value
    if value.is_absolute() or '..' in value.parts or '\\' in name or ':' in name or not target.resolve().is_relative_to(root.resolve()):raise ValueError('Path di luar paket: '+name)
    if any(p.is_symlink() for p in [target,*target.parents] if p.is_relative_to(root)):raise ValueError('Symlink tidak diizinkan: '+name)
    return target


def verify(root):
    root=Path(root).resolve();manifest=json.loads((root/'delivery.json').read_text(encoding='utf-8'))
    receipt_path=root/'preparation.json';receipt=json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    if receipt and receipt.get('manifest_content_id')!=digest(root/'delivery.json'):raise ValueError('Receipt persiapan berbeda dari manifest')
    for row in manifest['files']:
        path=safe(root,row['path']);expected=receipt.get('rewritten',{}).get(row['path'],row['content_id'])
        if not path.is_file() or digest(path)!=expected:raise ValueError('Berkas hilang/berubah: '+row['path'])
    return manifest,receipt


def rewrite(folder,old,new):
    """Rewrite native absolute references only; relative manifest paths stay stable."""
    helper=Path(__file__) if Path(__file__).name=='EDITOR_RELINK_HELPER.py' else Path(__file__).with_name('EDITOR_RELINK_HELPER.py')
    if not helper.is_file():
        # The installed application uses the shared, tested relinker directly.
        from clipper import project_install as module
    else:
        spec=importlib.util.spec_from_file_location('clipper_portable_relink',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    new=str(new).replace('\\','/');old=str(old).replace('\\','/')
    old_uri=('file:///'+quote(old,safe='/:')) if ':' in old[:3] else ('file://'+quote(old,safe='/'))
    new_uri=('file:///'+quote(new,safe='/:')) if ':' in new[:3] else ('file://'+quote(new,safe='/'))
    changes={}
    for path in sorted(Path(folder).rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ('.json','.xml','.fcpxml','.otio','.tmp','.bak','.lua','.comp'):continue
        if path.name in ('delivery.json','preparation.json'):continue
        text=path.read_text(encoding='utf-8')
        try:data=json.loads(text)
        except ValueError:
            after=text.replace(old_uri,new_uri).replace(old,new)
        else:
            value=module.rewrite_paths(data,[old],new,[(old_uri,new_uri)])
            after=json.dumps(value,ensure_ascii=False,indent=2) if value!=data else text
        if text!=after:
            temporary=path.with_name(path.name+'.prepare-tmp');temporary.write_text(after,encoding='utf-8');os.replace(temporary,path)
            changes[path.relative_to(folder).as_posix()]=digest(path)
    return changes


def prepare(root):
    root=Path(root).resolve();manifest,previous=verify(root)
    before=previous.get('prepared_root',manifest['created_root']);rewritten=dict(previous.get('rewritten',{}))
    if str(root).replace('\\','/')!=before:rewritten.update(rewrite(root,before,str(root)))
    receipt={'schema_version':1,'manifest_content_id':digest(root/'delivery.json'),'prepared_root':str(root).replace('\\','/'),'rewritten':rewritten}
    pending=root/'preparation.json.tmp';pending.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(pending,root/'preparation.json')
    verify(root);return receipt


def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args();root=Path(__file__).resolve().parent
    if args.check:verify(root);print('Seluruh anggota dan checksum paket M7 lulus.')
    else:prepare(root);print('Path siap. CapCut 4.7.0: Editors/PASANG_CAPCUT.cmd (gunakan --individual bila wrapper ditolak). Resolve 18.6.6: Editors/DaVinci. Baca BACA_DULU.md.')

if __name__=='__main__':main()
