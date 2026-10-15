"""Offline M6 overlay on byte-verified repaired M0-M5 GitHub sources."""
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

def digest(data):return hashlib.sha256(data).hexdigest()

def build(output,source_commit,verification=None):
    if not re.fullmatch(r'[0-9a-f]{40}',source_commit):raise ValueError('SHA commit sumber harus lengkap')
    output=Path(output).resolve();archive=output.with_suffix('.zip')
    if output.exists() or archive.exists():raise ValueError('Pilih nama paket baru; paket lama tidak ditimpa')
    base=json.loads((ROOT/'docs/releases/m6_base_hashes.json').read_text(encoding='utf-8'))
    output.mkdir(parents=True);files=[]
    for name in base['payload_paths']:
        data=installer.safe_path(ROOT,name).read_bytes();dest=installer.safe_path(output/'payload',name)
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        binary=name.endswith('.zip');current=digest(data if binary else data.replace(b'\r\n',b'\n'))
        files.append({'path':name,'sha256':digest(data),'baseline_checksum':'sha256' if binary else 'sha256-lf',
            'allowed_text_sha256':sorted(set(base['allowed_hashes'].get(name,[])+[current]))})
    guards=[{'path':n,'baseline_checksum':'sha256-lf','allowed_text_sha256':base['allowed_hashes'][n]} for n in base['guard_paths']]
    manifest={'schema_version':1,'version':'4.0.17','milestone':'M6','release_id':'m6-complete-20261015','installer_revision':1,
        'source_commit':source_commit,'source_origin':'local implementation; not pushed to GitHub',
        'baseline_github_commit':base['base_commit'],'requires_installation':'Repaired M0-M5 4.0.16.1, GitHub 9681af5; not a full environment installer',
        'install_command':'PASANG_M6_4_0_17.cmd','offline_update':True,'files':files,'guards':guards,
        'preserved_local_files':['docs/releases/m0_fixture.zip'],
        'data_directories_untouched':['work','clips','uploads','.venv','ClipperModels','models','clipper/fonts'],
        'specification_basis':{'document':'Arsitektur_Clipper_Pro_Terpadu_120_Halaman (2).pdf','pages':120,
            'sha256':'76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36','milestone_page':52,'audio_chain_page':63,'requirement_pages':[101,102],
            'packages':['M6.1','M6.2','M6.3','M6.4','M6.5'],'requirements':['AU'+str(i).zfill(2) for i in range(1,16)]},
        'implementation_status':'M6.1-M6.5 implemented with local audio execution; G6 human/model/target acceptance remains pending',
        'pending_acceptance':['Original Indonesian and code-switch speech listening, quiet words, negation, numbers and meaningful pauses',
            'Actual Demucs runtime/weights inference and perceptual separation quality','Windows native browser and i5-12500H/RTX3050 4GB',
            'CapCut native regression; M6 nonlinear mix uses preserved export plus WAV stems; Resolve text remains deferred']}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    installer.load_manifest(output)
    shutil.copyfile(ROOT/'tools/complete_installer.py',output/'complete_installer.py')
    for name,dest in [('docs/UPGRADE_4_0_17_M6.md','PANDUAN_M6.md'),('docs/LAPORAN_M6.md','LAPORAN_M6.md'),('docs/M6_REQUIREMENTS.json','M6_REQUIREMENTS.json')]:
        shutil.copyfile(ROOT/name,output/dest)
    for name,flag in [('CEK_SEBELUM_UPGRADE.cmd','--check'),('PASANG_M6_4_0_17.cmd',''),('PULIHKAN_M6_4_0_17.cmd','--rollback')]:
        command=('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\nwhere py >nul 2>nul\r\nif errorlevel 1 (\r\n'
            '  python "%~dp0complete_installer.py" '+flag+' %*\r\n) else (\r\n'
            '  py -3 "%~dp0complete_installer.py" '+flag+' %*\r\n)\r\nset "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
        (output/name).write_bytes(command.encode())
    (output/'BACA_DULU.txt').write_text('CLIPPER PRO 4.0.17 M6 - AUDIO, MUSIK DAN MIX\n\n'
        'Dasar: perbaikan M0-M5 4.0.16.1 yang sudah diupload di GitHub.\n'
        '1. Ekstrak ZIP ke folder baru di luar folder mesin.\n'
        '2. Hentikan antrean dan tutup server dengan Ctrl+C.\n'
        '3. Jalankan CEK_SEBELUM_UPGRADE.cmd; isi folder mesin lama.\n'
        '4. Jika lulus, jalankan PASANG_M6_4_0_17.cmd.\n'
        '5. Jalankan JALANKAN_PRO.cmd pada mesin lama lalu Ctrl+F5.\n'
        '6. Buka EDIT > Audio > M6. Aktifkan pada rasio pilihan dan simpan.\n'
        '7. Buat A/B 8 detik, dengarkan ucapan, lalu render dua rasio.\n\n'
        'Tidak ada unduhan model/musik atau pemasangan dependensi otomatis.\n'
        'Denoise, WPE, EQ, ducking, limiter dan meter memakai NumPy/FFmpeg lokal.\n'
        'Demucs opsional memerlukan runtime dan repo bobot lokal lengkap.\n'
        'Kode dan SQLite dicadangkan. Video, model, environment dan font\n'
        'pribadi dipertahankan. Jangan salin payload secara manual.\n'
        'PANDUAN_M6.md menjelaskan setelan, uji dengar, ekspor dan rollback.\n'
        'G6 video asli, Demucs nyata dan native Windows belum dinyatakan lulus.\n',encoding='utf-8')
    tests=('@echo off\r\nsetlocal\r\nset /p "CLIPPER_M6_TEST_TARGET=Folder mesin: "\r\n'
        'cd /d "%CLIPPER_M6_TEST_TARGET%"\r\nif errorlevel 1 (pause& exit /b 1)\r\n'
        'if not exist ".venv\\Scripts\\python.exe" (echo Python mesin tidak ditemukan.& pause& exit /b 1)\r\n'
        'if not exist "m6-test-results" mkdir "m6-test-results"\r\n'
        '".venv\\Scripts\\python.exe" -m pytest clipper/tests/test_m6_contract.py clipper/tests/test_m6_dsp.py clipper/tests/test_m6_service.py clipper/tests/test_m6_safety.py clipper/tests/test_m6_media.py clipper/tests/test_m6_installer.py -q --junitxml="m6-test-results\\junit-%RANDOM%.xml"\r\n'
        'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
    (output/'JALANKAN_UJI_M6.cmd').write_bytes(tests.encode())
    if verification:shutil.copytree(verification,output/'verification')
    # Stable timestamps and permissions make the same inputs reproducible.
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(output.rglob('*')):
            if p.is_file():
                info=zipfile.ZipInfo(output.name+'/'+p.relative_to(output).as_posix(),date_time=(2026,10,15,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,p.read_bytes())
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('CRC paket gagal')
        for row in files:
            if digest(z.read(output.name+'/payload/'+row['path']))!=row['sha256']:raise ValueError('Checksum payload gagal: '+row['path'])
    result={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':digest(archive.read_bytes()),'payload_files':len(files),'guards':len(guards),
        'source_commit':source_commit,'baseline_github_commit':base['base_commit'],'milestone':'M6','zip_crc':'passed'}
    print(json.dumps(result,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source-commit',required=True);p.add_argument('--verification')
    args=p.parse_args();build(args.output,args.source_commit,args.verification)
