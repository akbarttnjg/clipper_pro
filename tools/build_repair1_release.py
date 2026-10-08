"""Build a checked offline repair overlay against the audited 4.0.6 baseline."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(output,source_commit,verification=None,source_origin='local'):
    if not re.fullmatch(r'[0-9a-f]{40}',source_commit):
        raise ValueError('SHA commit sumber harus lengkap.')
    if source_origin not in ('local','github'):
        raise ValueError('Asal sumber tidak dikenal.')
    output=Path(output).resolve();archive=output.with_suffix('.zip')
    if output.exists() or archive.exists():
        raise ValueError('Pilih nama paket baru.')
    baseline=json.loads((ROOT/'docs/releases/repair1_base_hashes.json').read_text())
    spec=importlib.util.spec_from_file_location('repair1_installer',ROOT/'tools/repair1_installer.py')
    installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
    output.mkdir(parents=True);files=[]
    for name in baseline['payload_paths']:
        source=installer.safe_path(ROOT,name)
        if not source.is_file():raise ValueError('Sumber payload hilang: '+name)
        data=source.read_bytes();destination=installer.safe_path(output/'payload',name)
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
        text_hash=digest(data.replace(b'\r\n',b'\n'))
        files.append({'path':name,'sha256':digest(data),'text_sha256':text_hash,
            'allowed_text_sha256':sorted(set(baseline['allowed_hashes'].get(name,[])+[text_hash]))})
    guards=[{'path':name,'allowed_text_sha256':baseline['allowed_hashes'][name]}
            for name in baseline['guard_paths']]
    manifest={'schema_version':1,'version':'4.0.7','release_id':'repair1-20261009',
        'source_commit':source_commit,'source_origin':source_origin,
        'baseline_github_commit':baseline['base_commit'],'files':files,'guards':guards,
        'requires_installation':'Clipper Studio 4.0.6 matching the audited baseline',
        'offline_update':True,'data_directories_untouched':['work','clips','uploads','.venv','ClipperModels','models'],
        'pending_acceptance':['Real Indonesian CTC alignment on Windows','Actual Remotion and Motion Canvas browser renders',
                              'Native CapCut and Resolve import/edit/reopen','Real-video framing/editorial improvement in later repair stages']}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    shutil.copyfile(ROOT/'tools/repair1_installer.py',output/'repair1_installer.py')
    shutil.copyfile(ROOT/'docs/PEMBENAHAN_1_STABILITAS.md',output/'PANDUAN_PEMBENAHAN_1.md')
    for name,flag in [('CEK_SEBELUM_UPGRADE.cmd','--check'),('UPGRADE_PEMBENAHAN_1.cmd',''),
                      ('PULIHKAN_PEMBENAHAN_1.cmd','--rollback')]:
        command=('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\n'
            'where py >nul 2>nul\r\nif errorlevel 1 (\r\n'
            '  python "%~dp0repair1_installer.py" '+flag+' %*\r\n'
            ') else (\r\n  py -3 "%~dp0repair1_installer.py" '+flag+' %*\r\n)\r\n'
            'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
        (output/name).write_bytes(command.encode('utf-8'))
    (output/'BACA_DULU.txt').write_text(
        'Clipper Studio 4.0.7 - Pembenahan 1: stabilitas dan alignment\n\n'
        '1. Ekstrak ZIP ke folder baru. Hentikan antrean dan server lama dengan Ctrl+C.\n'
        '2. Jalankan CEK_SEBELUM_UPGRADE.cmd. Pilih folder C:\\AI\\clipper.\n'
        '3. Jika lulus, jalankan UPGRADE_PEMBENAHAN_1.cmd pada folder yang sama.\n'
        '4. Jalankan JALANKAN_PRO.cmd dari mesin, lalu Ctrl+F5 di browser.\n'
        '5. Ulangi alignment kata yang telah disimpan. Periksa aligned dan errors.\n'
        '6. PULIHKAN_PEMBENAHAN_1.cmd mengembalikan kode sebelumnya.\n\n'
        'Paket tidak memasang pustaka atau mengunduh model. Backup kode dan database\n'
        'dibuat sebelum perubahan. Rollback kode mempertahankan edit proyek setelah upgrade.\n'
        'Rincian perbaikan, batas pengujian, dan tujuh tahap ada dalam panduan.\n',encoding='utf-8')
    if verification:
        shutil.copytree(verification,output/'verification')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as zip:
        for path in sorted(output.rglob('*')):
            if path.is_file():zip.write(path,output.name+'/'+path.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as zip:
        if zip.testzip():raise ValueError('CRC paket gagal.')
        for row in files:
            if digest(zip.read(output.name+'/payload/'+row['path']))!=row['sha256']:
                raise ValueError('Checksum payload gagal: '+row['path'])
    report={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive.read_bytes()),
            'payload_files':len(files),'guards':len(guards),'source_commit':source_commit,'zip_crc':'passed'}
    print(json.dumps(report,indent=2));return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True);parser.add_argument('--source-commit',required=True)
    parser.add_argument('--verification')
    parser.add_argument('--source-origin',choices=('local','github'),default='local')
    args=parser.parse_args();build(args.output,args.source_commit,args.verification,args.source_origin)
