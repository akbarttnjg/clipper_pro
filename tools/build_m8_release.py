"""Offline M8 overlay from exact byte-verified GitHub M7 4.0.18."""
import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if __package__ in (None,''):sys.path.insert(0,str(ROOT))
from tools import complete_installer as installer


def sha(data):return hashlib.sha256(data).hexdigest()


def _build_current_unsupported(output,source_commit,verification=None):
    if not isinstance(source_commit,str) or not re.fullmatch('[0-9a-f]{40}',source_commit):raise ValueError('SHA commit sumber harus lengkap')
    output=Path(output).resolve();archive=output.with_suffix('.zip')
    if output.exists() or archive.exists():raise ValueError('Pilih nama baru; paket lama tidak ditimpa')
    base=json.loads((ROOT/'docs/releases/m8_base_hashes.json').read_text(encoding='utf-8'))
    files=[];output.mkdir(parents=True)
    for name in base['payload_paths']:
        data=installer.safe_path(ROOT,name).read_bytes();target=installer.safe_path(output/'payload',name)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        binary=name.endswith('.zip');canonical=sha(data if binary else data.replace(b'\r\n',b'\n'))
        files.append({'path':name,'sha256':sha(data),'baseline_checksum':'sha256' if binary else 'sha256-lf',
                      'allowed_text_sha256':sorted(set(base['allowed_hashes'].get(name,[])+[canonical]))})
    guards=[{'path':name,'baseline_checksum':'sha256' if name.endswith('.zip') else 'sha256-lf','allowed_text_sha256':base['allowed_hashes'][name]} for name in base['guard_paths']]
    trace=json.loads((ROOT/'docs/M8_REQUIREMENTS.json').read_text(encoding='utf-8'))
    manifest={'schema_version':1,'version':'4.0.19','milestone':'M8','release_id':'m8-local-operational-20261016','installer_revision':1,
        'source_commit':source_commit,'source_origin':'local implementation; not pushed','baseline_github_commit':base['base_commit'],
        'requires_installation':'M7 4.0.18 matching GitHub f6f1f6a; exact source baseline guards',
        'install_command':'PASANG_M8_4_0_19.cmd','offline_update':True,'files':files,'guards':guards,
        'preserved_local_files':['docs/releases/m0_fixture.zip'],
        'data_directories_untouched':['work','clips','uploads','.venv','ClipperModels','models','clipper/fonts'],
        'specification_basis':trace['architecture'],'requirements':[r['id'] for r in trace['requirements']],
        'implementation_counts':trace['counts'],'release_scope':trace['release_scope'],'pending_acceptance':trace['pending_acceptance'],
        'render_pipeline_version':'4.0.18-m7','account_connections_or_posts_created_by_installer':0}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    installer.load_manifest(output)
    shutil.copy2(ROOT/'tools/complete_installer.py',output/'complete_installer.py')
    for src,dest in [('docs/UPGRADE_4_0_19_M8.md','PANDUAN_M8.md'),('docs/LAPORAN_M8.md','LAPORAN_M8.md'),('docs/M8_REQUIREMENTS.json','M8_REQUIREMENTS.json'),('docs/m8/COMMANDS.md','COMMANDS_M8.md')]:
        shutil.copy2(ROOT/src,output/dest)
    for name,flag in [('CEK_SEBELUM_UPGRADE.cmd','--check'),('PASANG_M8_4_0_19.cmd',''),('PULIHKAN_M8_4_0_19.cmd','--rollback')]:
        command=('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\nwhere py >nul 2>nul\r\nif errorlevel 1 (\r\n  python "%~dp0complete_installer.py" '+flag+' %*\r\n) else (\r\n  py -3 "%~dp0complete_installer.py" '+flag+' %*\r\n)\r\nset "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
        (output/name).write_bytes(command.encode())
    common='@echo off\r\nsetlocal\r\nset /p "CLIPPER_M8_MACHINE=Folder mesin Clipper: "\r\ncd /d "%CLIPPER_M8_MACHINE%"\r\nif errorlevel 1 (pause& exit /b 1)\r\nif not exist ".venv\\Scripts\\python.exe" (echo Python mesin tidak ditemukan.& pause& exit /b 1)\r\n'
    end='\r\nset "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n'
    (output/'CEK_M8_RUNTIME.cmd').write_bytes((common+'".venv\\Scripts\\python.exe" -c "from clipper.m8_contract import VERSION; import clipper.m8,clipper.api_m8,clipper.m8_cli; print(VERSION); print(\'Import M8 lulus; belum menghubungkan akun atau memposting.\')"'+end).encode())
    (output/'JALANKAN_UJI_M8.cmd').write_bytes((common+'if not exist "m8-test-results" mkdir "m8-test-results"\r\n".venv\\Scripts\\python.exe" -m pytest clipper/tests/test_m8_contract.py clipper/tests/test_m8_service.py clipper/tests/test_m8_adversarial.py clipper/tests/test_m8_e2e.py clipper/tests/test_m8_installer.py -q --junitxml="m8-test-results\\junit-%RANDOM%.xml"'+end).encode())
    (output/'JALANKAN_WORKER_M8.cmd').write_bytes((common+'".venv\\Scripts\\python.exe" -m clipper.m8_cli worker'+end).encode())
    (output/'BACA_DULU.txt').write_text('CLIPPER PRO 4.0.19 - M8\n\n'
        'Dasar: M7 4.0.18 GitHub f6f1f6a.\n'
        '1. Ekstrak ZIP ke folder baru di luar mesin.\n'
        '2. Hentikan antrean, server dan worker CLI.\n'
        '3. CEK_SEBELUM_UPGRADE.cmd, lalu PASANG_M8_4_0_19.cmd.\n'
        '4. Buka JALANKAN_PRO.cmd pada mesin lama dan Ctrl+F5.\n'
        '5. Header > Distribusi dan workspace M8. Mulai dengan profil handoff.\n'
        '6. Pilih final M7 > buat draf > periksa > setujui. ZIP handoff belum diposting.\n\n'
        'Tidak ada login akun, unggahan, unduhan model atau API berbayar otomatis.\n'
        'YouTube OAuth/API opsional memerlukan akses project dan consent Anda.\n'
        'Jadwal lokal memerlukan worker dan komputer aktif.\n'
        'Cakupan enam paket tersedia; seluruh acceptance M8 belum ditutup.\n'
        'Baca PANDUAN_M8.md, LAPORAN_M8.md dan M8_REQUIREMENTS.json.\n'
        'Windows/DPAPI/live API/native editor tetap membutuhkan validasi pengguna.\n',encoding='utf-8')
    if verification:shutil.copytree(verification,output/'verification')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as zipped:
        for path in sorted(output.rglob('*')):
            if path.is_symlink():raise ValueError('Symlink paket dilarang')
            if path.is_file():
                info=zipfile.ZipInfo(output.name+'/'+path.relative_to(output).as_posix(),date_time=(2026,10,16,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;zipped.writestr(info,path.read_bytes())
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip():raise ValueError('CRC upgrade gagal')
        for row in files:
            if sha(zipped.read(output.name+'/payload/'+row['path']))!=row['sha256']:raise ValueError('Checksum payload gagal')
    result={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),'source_commit':source_commit,
        'baseline_github_commit':base['base_commit'],'payload_files':len(files),'guard_files':len(guards),'zip_crc':'passed'}
    print(json.dumps(result,indent=2));return result


def build(output,source_commit,verification=None):
    from tools.frozen_producer import build as frozen
    return frozen(ROOT,'m9_m8_producer','build_m8_release.py',output,source_commit,verification)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source-commit',required=True);p.add_argument('--verification');args=p.parse_args();build(args.output,args.source_commit,args.verification)
