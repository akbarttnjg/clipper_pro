"""Freeze public application sources and derive an exact M0 upgrade contract."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BASE='6682f0b4e633af6ca830e63754ac3d46fc100bbf'
ROOT_FILES={'README.md','app.py','doctor_pro.py','requirements.txt','requirements-pro.txt',
            'JALANKAN_PRO.cmd','CEK_PRO.cmd','.gitignore','CEK_PEMBENAHAN.cmd'}


def run(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def hash_text(data):return hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()


def capture_sources(base=BASE):
    if not re.fullmatch('[0-9a-f]{40}',base):raise ValueError('Baseline SHA harus lengkap')
    tracked=run('ls-tree','-r','--name-only',base).decode().splitlines()
    names=[n for n in tracked if n.split('/')[0] in ('clipper','static','docs','tools') or n in ROOT_FILES]
    content={n:run('show',base+':'+n) for n in names}
    return names,content


def export_baseline(output,base=BASE):
    names,content=capture_sources(base)
    provenance={'base_commit':base,'normalized_sha256':{n:hash_text(v) for n,v in content.items()},
                'raw_sha256':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},
                'scope':'Public versioned application sources only; no user projects/config/models.'}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for n,v in sorted(content.items()):
            info=zipfile.ZipInfo(n,date_time=(2026,10,12,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,v)
        info=zipfile.ZipInfo('__provenance__.json',date_time=(2026,10,12,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,json.dumps(provenance,sort_keys=True,indent=2))
    return output,provenance


def freeze(base=BASE):
    names,content=capture_sources(base)
    output,provenance=export_baseline(ROOT/'docs/releases/m0_fixture.zip',base)
    changed=run('diff','--name-only',base).decode().splitlines()+run('ls-files','--others','--exclude-standard').decode().splitlines()
    payload=sorted({n for n in changed if (n.split('/')[0] in ('clipper','static','docs','tools') or n in ROOT_FILES)
                    and Path(ROOT/n).is_file() and not n.endswith('.zip')})
    payload=sorted(set(payload)|{'docs/releases/m0_fixture.zip','docs/releases/m0_base_hashes.json'})
    guarded=[n for n in names if ((n.startswith('clipper/') and '/tests/' not in n) or n.startswith('static/') or n in ROOT_FILES)
             and n not in payload and Path(n).suffix in ('.py','.js','.css','.html','.json','.ts','.tsx','.cjs','.cmd','.txt','.md')]
    contract={'base_commit':base,'payload_paths':payload,'guard_paths':guarded,
              'allowed_hashes':{n:[provenance['normalized_sha256'][n]] for n in sorted(set(payload+guarded)) if n in content},
              'requires_installation':'Clipper 4.0.10 matching GitHub 6682f0b; unknown local code rejected.',
              'pending_acceptance':['Windows taskkill/NTFS and GPU RTX 3050 Laptop 4GB',
                    'Indonesian original-source ASR/alignment accuracy on the selected audio stream',
                    'Native CapCut 4.7.0 import/edit/save/reopen/render regression',
                    'Resolve Free 18.6.6 text/font acceptance remains deferred by project policy']}
    (ROOT/'docs/releases/m0_base_hashes.json').write_text(json.dumps(contract,indent=2)+'\n')
    return {'baseline':base,'fixture_files':len(content),'fixture_bytes':output.stat().st_size,
            'fixture_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'payload_files':len(payload),'guards':len(guarded)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default=BASE);a=p.parse_args();print(json.dumps(freeze(a.base),indent=2))
