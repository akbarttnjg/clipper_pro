"""Build and verify the Stage 3 offline overlay from a pinned checkout."""
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


def build(output, source_commit, verification=None):
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('Gunakan SHA commit GitHub lengkap yang memuat kode paket.')
    output = Path(output).resolve()
    archive = output.with_suffix('.zip')
    if output.exists() or archive.exists():
        raise ValueError('Pilih nama paket baru; hasil lama tidak ditimpa.')
    baseline = json.loads((ROOT/'docs/releases/stage3_base_hashes.json').read_text(encoding='utf-8'))
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
    manifest={'schema_version':1,'version':'4.0.3','release_id':'stage3-20261008',
              'source_commit':source_commit,'integrates_commits':[baseline['main_commit'],baseline['stage3_commit']],
              'requires_installation':'Studio 4.0.2 main 2b02a58 or the matching Stage 3 snapshot',
              'offline_update':True,'files':files,'guards':guards,
              'data_directories_untouched':['work','clips','uploads','.venv','models'],
              'pending_acceptance':['Windows CMD and NVENC hardware', 'Real local ASR and CTC accuracy',
                                    'Local Qwen story selection quality', 'Native editor import on user versions']}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copyfile(ROOT/'tools/stage3_installer.py',output/'stage3_installer.py')
    shutil.copyfile(ROOT/'docs/TAHAP_3_TRANSKRIP_CERITA.md',output/'PANDUAN_TAHAP_3.md')
    for name,flag in [('CEK_SEBELUM_UPGRADE.cmd','--check'),('UPGRADE_TAHAP_3.cmd',''),
                      ('PULIHKAN_UPGRADE_TAHAP_3.cmd','--rollback')]:
        text=('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\n'
              'where py >nul 2>nul\r\nif errorlevel 1 (\r\n'
              '  python "%~dp0stage3_installer.py" '+flag+' %*\r\n'
              ') else (\r\n  py -3 "%~dp0stage3_installer.py" '+flag+' %*\r\n)\r\n'
              'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
        (output/name).write_bytes(text.encode('utf-8'))
    (output/'BACA_DULU.txt').write_text(
        'Clipper Studio 4.0.3 - Tahap 3 transkrip dan cerita\n\n'
        '1. Ekstrak seluruh ZIP ke folder baru. Jangan tempel payload secara manual.\n'
        '2. Hentikan antrean dan tutup server mesin lama dengan Ctrl+C.\n'
        '3. Jalankan CEK_SEBELUM_UPGRADE.cmd. Target normal: C:\\AI\\clipper.\n'
        '4. Jika lulus, jalankan UPGRADE_TAHAP_3.cmd pada target yang sama.\n'
        '5. Jalankan JALANKAN_PRO.cmd dari mesin lama; Ctrl+F5 di browser.\n'
        '6. Untuk rollback kode, tutup mesin dan jalankan PULIHKAN_UPGRADE_TAHAP_3.cmd.\n\n'
        'Paket memperbarui kode offline, tanpa pip atau unduhan model.\n'
        'Koreksi/timing manual bisa dipakai langsung. Alignment otomatis membutuhkan\n'
        'WhisperX dan folder bobot Wav2Vec2 CTC lokal yang sesuai bahasa.\n'
        'Baca PANDUAN_TAHAP_3.md dan verification untuk bukti dan batas pengujian.\n',encoding='utf-8')
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
    args=parser.parse_args();build(args.output,args.source_commit,args.verification)
