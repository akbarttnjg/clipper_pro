"""Build and verify the Stage 4 offline overlay from a pinned checkout."""
import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(output, source_commit, verification=None, source_origin='github'):
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('Gunakan SHA commit lengkap yang memuat kode paket.')
    if source_origin not in {'github', 'local'}:
        raise ValueError('Asal commit harus github atau local.')
    output = Path(output).resolve()
    archive = output.with_suffix('.zip')
    if output.exists() or archive.exists():
        raise ValueError('Pilih nama paket baru; hasil lama tidak ditimpa.')
    baseline = json.loads((ROOT/'docs/releases/stage4_base_hashes.json').read_text(encoding='utf-8'))
    output.mkdir(parents=True)
    files=[]
    for name in sorted(baseline['payload_paths']):
        source=ROOT/name
        if not source.is_file() or source.is_symlink():
            raise ValueError('Sumber payload hilang atau symlink: '+name)
        data=source.read_bytes();dest=output/'payload'/name
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        text_hash=digest(data.replace(b'\r\n',b'\n'))
        files.append({'path':name,'sha256':digest(data),'text_sha256':text_hash,
                      'allowed_text_sha256':sorted(set(baseline['allowed_hashes'].get(name,[])+[text_hash]))})
    guards=[]
    for name in sorted(baseline['guard_paths']):
        source=ROOT/name
        allowed=baseline['allowed_hashes'][name]+[digest(source.read_bytes().replace(b'\r\n',b'\n'))]
        guards.append({'path':name,'allowed_text_sha256':sorted(set(allowed))})
    manifest={'schema_version':1,'version':'4.0.4','release_id':'stage4-20261007',
              'source_commit':source_commit,'source_origin':source_origin,
              'integrates_commits':[baseline['main_commit'],baseline['stage3_commit']],
              'requires_installation':'Studio 4.0.2 main 2b02a58 or matching Studio 4.0.3 installation',
              'offline_update':True,'files':files,'guards':guards,
              'data_directories_untouched':['work','clips','uploads','.venv','models'],
              'pending_acceptance':['Windows CMD and RTX 3050 hardware', 'TalkNet on synchronized two-person raw footage',
                                    'Real OCR and visual-model decision accuracy', 'SAM video mask quality and performance',
                                    'CapCut/DaVinci desktop import of new layouts']}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copyfile(ROOT/'tools/stage4_installer.py',output/'stage4_installer.py')
    shutil.copyfile(ROOT/'docs/TAHAP_4_KAMERA_AREA_AMAN.md',output/'PANDUAN_TAHAP_4.md')
    for name,flag in [('CEK_SEBELUM_UPGRADE.cmd','--check'),('UPGRADE_TAHAP_4.cmd',''),
                      ('PULIHKAN_UPGRADE_TAHAP_4.cmd','--rollback')]:
        text=('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\n'
              'where py >nul 2>nul\r\nif errorlevel 1 (\r\n'
              '  python "%~dp0stage4_installer.py" '+flag+' %*\r\n'
              ') else (\r\n  py -3 "%~dp0stage4_installer.py" '+flag+' %*\r\n)\r\n'
              'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
        (output/name).write_bytes(text.encode('utf-8'))
    (output/'BACA_DULU.txt').write_text(
        'Clipper Studio 4.0.4 - Tahap 4 kamera dan area aman\n\n'
        '1. Ekstrak seluruh ZIP ke folder baru. Jangan tempel payload secara manual.\n'
        '2. Hentikan antrean dan tutup server mesin lama dengan Ctrl+C.\n'
        '3. Jalankan CEK_SEBELUM_UPGRADE.cmd. Target normal: C:\\AI\\clipper.\n'
        '4. Jika lulus, jalankan UPGRADE_TAHAP_4.cmd pada target yang sama.\n'
        '5. Jalankan JALANKAN_PRO.cmd dari mesin lama; Ctrl+F5 di browser.\n'
        '6. Untuk rollback kode, tutup mesin dan jalankan PULIHKAN_UPGRADE_TAHAP_4.cmd.\n\n'
        'Paket memperbarui kode offline, tanpa pip atau unduhan model.\n'
        'Tracking dasar dan area manual bisa dipakai langsung. Model visual tambahan\n'
        'hanya dipakai bila lingkungan, bobot dan uji sampelnya sudah siap.\n'
        'Baca PANDUAN_TAHAP_4.md dan verification untuk bukti dan batas pengujian.\n',encoding='utf-8')
    if verification:
        shutil.copytree(verification,output/'verification')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(output.rglob('*')):
            if path.is_file():z.write(path,output.name+'/'+path.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip()
        if bad:raise ValueError('CRC ZIP gagal: '+bad)
        for row in files:
            data=z.read(output.name+'/payload/'+row['path'])
            if digest(data)!=row['sha256']:raise ValueError('Checksum ZIP gagal: '+row['path'])
    report={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive.read_bytes()),
            'source_commit':source_commit,'payload_files':len(files),'guard_files':len(guards),'zip_crc':'passed'}
    print(json.dumps(report,indent=2));return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True);parser.add_argument('--source-commit',required=True)
    parser.add_argument('--verification')
    parser.add_argument('--source-origin',choices=['github','local'],default='github')
    args=parser.parse_args();build(args.output,args.source_commit,args.verification,args.source_origin)
