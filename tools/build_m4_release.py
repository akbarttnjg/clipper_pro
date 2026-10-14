"""Reproducible offline M4 overlay on the pinned, verified M2 GitHub upload."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
if __package__ in (None,''):sys.path.insert(0,str(ROOT))
from tools import complete_installer as installer
LEGACY_FIXTURE='docs/releases/m0_fixture.zip'


def digest(data):return hashlib.sha256(data).hexdigest()


def build(output,source_commit,verification=None):
    if not re.fullmatch(r'[0-9a-f]{40}',source_commit):raise ValueError('SHA commit sumber harus lengkap')
    output=Path(output).resolve();archive=output.with_suffix('.zip')
    if output.exists() or archive.exists():raise ValueError('Pilih nama paket baru; paket lama tidak ditimpa')
    baseline=json.loads((ROOT/'docs/releases/m4_base_hashes.json').read_text())
    if LEGACY_FIXTURE in baseline['payload_paths']+baseline['guard_paths']:raise ValueError('Fixture lokal lama tidak boleh menjadi payload/guard')
    output.mkdir(parents=True);files=[]
    for name in baseline['payload_paths']:
        source=installer.safe_path(ROOT,name);data=source.read_bytes();dest=installer.safe_path(output/'payload',name)
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        binary=source.suffix=='.zip';current=digest(data if binary else data.replace(b'\r\n',b'\n'))
        allowed=baseline.get('allowed_raw_hashes' if binary else 'allowed_hashes',{}).get(name,[])
        files.append({'path':name,'sha256':digest(data),'text_sha256':digest(data.replace(b'\r\n',b'\n')),
            'baseline_checksum':'sha256' if binary else 'sha256-lf','allowed_text_sha256':sorted(set(allowed+[current]))})
    guards=[{'path':name,'baseline_checksum':'sha256' if name.endswith('.zip') else 'sha256-lf',
        'allowed_text_sha256':baseline['allowed_raw_hashes' if name.endswith('.zip') else 'allowed_hashes'][name]} for name in baseline['guard_paths']]
    manifest={'schema_version':1,'version':'4.0.15','milestone':'M4','release_id':'m4-complete-20261014',
        'source_commit':source_commit,'source_origin':'local','baseline_github_commit':baseline['base_commit'],
        'accepted_baseline_github_commits':[baseline['base_commit'],*baseline.get('additional_base_commits',[])],
        'requires_installation':'Verified M3 4.0.14, M2 GitHub upload or original M2; cumulative M3 included',
        'install_command':'PASANG_M4_4_0_15.cmd','offline_update':True,'files':files,'guards':guards,
        'preserved_local_files':[LEGACY_FIXTURE],
        'data_directories_untouched':['work','clips','uploads','.venv','ClipperModels','models'],
        'specification_basis':{'document':'Arsitektur_Clipper_Pro_Terpadu_120_Halaman (2).pdf','pages':120,
            'sha256':'76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36','milestone_page':49,'requirement_pages':[92,93,94],
            'packages':['M4.1','M4.2','M4.3','M4.4','M4.5','M4.6']},
        'implementation_status':'Six workflow packages implemented; real composition corpus acceptance G4 remains pending',
        'pending_acceptance':['Real composition corpus G4','Actual native face/ASD/OCR/SAM/object-planar tracking corpus',
            'Windows browser, original media, native OpenCV/NVENC and CapCut regression','Resolve text remains deferred']}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    installer.load_manifest(output)
    shutil.copyfile(ROOT/'tools/complete_installer.py',output/'complete_installer.py')
    for source,dest in [('docs/UPGRADE_4_0_15_M4.md','PANDUAN_M4.md'),('docs/LAPORAN_M4.md','LAPORAN_M4.md'),('docs/M4_REQUIREMENTS.json','M4_REQUIREMENTS.json')]:
        shutil.copyfile(ROOT/source,output/dest)
    for name,flag in [('CEK_SEBELUM_UPGRADE.cmd','--check'),('PASANG_M4_4_0_15.cmd',''),('PULIHKAN_M4_4_0_15.cmd','--rollback')]:
        text=('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\nwhere py >nul 2>nul\r\nif errorlevel 1 (\r\n'
            '  python "%~dp0complete_installer.py" '+flag+' %*\r\n) else (\r\n'
            '  py -3 "%~dp0complete_installer.py" '+flag+' %*\r\n)\r\n'
            'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
        (output/name).write_bytes(text.encode())
    (output/'BACA_DULU.txt').write_text('CLIPPER PRO 4.0.15 M4\n\n'
        '1. Ekstrak ZIP ke folder baru di luar mesin lama.\n'
        '2. Hentikan antrean dan tutup server dengan Ctrl+C.\n'
        '3. Jalankan CEK_SEBELUM_UPGRADE.cmd; isi folder mesin lama.\n'
        '4. Setelah lulus, jalankan PASANG_M4_4_0_15.cmd.\n'
        '5. Jalankan mesin melalui JALANKAN_PRO.cmd, lalu Ctrl+F5.\n'
        '6. Buka EDIT > M4 Kamera. Simpan, analisis, periksa sumber, terima kamera.\n'
        '7. Preview dan render masing-masing rasio yang sudah ditinjau.\n\n'
        'Paket tidak mengunduh model atau memasang dependensi. Model lokal\n'
        'Model visual yang telah tersedia dipakai; area manual tetap tersedia.\n'
        'Kode dan SQLite dicadangkan; sumber video, model, font pribadi dan\n'
        'environment tidak ditimpa. Jangan menyalin payload secara manual.\n'
        'Fixture m0_fixture.zip lokal tetap dipertahankan tanpa diperiksa.\n'
        'Lihat PANDUAN_M4.md, LAPORAN_M4.md dan bukti uji di verification.\n'
        'Kualitas corpus G4, model lokal nyata dan Windows/GPU belum dinyatakan lulus.\n',encoding='utf-8')
    test=('@echo off\r\nsetlocal\r\nset /p "CLIPPER_M4_TEST_TARGET=Folder mesin: "\r\n'
        'if not exist "%CLIPPER_M4_TEST_TARGET%\\.venv\\Scripts\\python.exe" (echo Python mesin tidak ditemukan.& pause& exit /b 1)\r\n'
        'cd /d "%CLIPPER_M4_TEST_TARGET%"\r\n'
        'if not exist "m4-test-results" mkdir "m4-test-results"\r\n'
        '".venv\\Scripts\\python.exe" -m pytest clipper/tests -q --junitxml="m4-test-results\\junit-%RANDOM%.xml"\r\n'
        'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
    (output/'JALANKAN_UJI_M4.cmd').write_bytes(test.encode())
    if verification:shutil.copytree(verification,output/'verification')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(output.rglob('*')):
            if path.is_file():z.write(path,output.name+'/'+path.relative_to(output).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('CRC paket gagal')
        for row in files:
            if digest(z.read(output.name+'/payload/'+row['path']))!=row['sha256']:raise ValueError('Checksum payload gagal: '+row['path'])
    result={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive.read_bytes()),
        'payload_files':len(files),'guards':len(guards),'source_commit':source_commit,
        'baseline_github_commit':baseline['base_commit'],'milestone':'M4','zip_crc':'passed'}
    print(json.dumps(result,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source-commit',required=True);p.add_argument('--verification')
    a=p.parse_args();build(a.output,a.source_commit,a.verification)
