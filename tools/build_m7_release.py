"""Cumulative M6 repairs + M7 offline upgrade from exact GitHub 4.0.17."""
import argparse,hashlib,json,re,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __package__ in (None,''):sys.path.insert(0,str(ROOT))
from tools import complete_installer as installer


def sha(data):return hashlib.sha256(data).hexdigest()


def build(output,source_commit,verification=None):
    if not isinstance(source_commit,str) or not re.fullmatch('[0-9a-f]{40}',source_commit):raise ValueError('SHA commit sumber harus lengkap')
    output=Path(output).resolve();archive=output.with_suffix('.zip')
    if output.exists() or archive.exists():raise ValueError('Paket lama tidak ditimpa; pilih nama baru')
    base=json.loads((ROOT/'docs/releases/m7_base_hashes.json').read_text());files=[];output.mkdir(parents=True)
    for name in base['payload_paths']:
        source=installer.safe_path(ROOT,name);data=source.read_bytes();target=installer.safe_path(output/'payload',name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        binary=name.endswith('.zip');canonical=sha(data if binary else data.replace(b'\r\n',b'\n'))
        files.append({'path':name,'sha256':sha(data),'baseline_checksum':'sha256' if binary else 'sha256-lf',
            'allowed_text_sha256':sorted(set(base['allowed_hashes'].get(name,[])+[canonical]))})
    guards=[{'path':n,'baseline_checksum':'sha256' if n.endswith('.zip') else 'sha256-lf','allowed_text_sha256':base['allowed_hashes'][n]} for n in base['guard_paths']]
    manifest={'schema_version':1,'version':'4.0.18','milestone':'M6 repairs + M7','release_id':'m6-repairs-m7-20261016','installer_revision':1,
        'source_commit':source_commit,'baseline_github_commit':base['base_commit'],'source_origin':'local implementation; not pushed',
        'requires_installation':'M6 4.0.17 matching GitHub 14b89fa; cumulative six audited M6 fixes included',
        'install_command':'PASANG_M6_M7_4_0_18.cmd','offline_update':True,'files':files,'guards':guards,
        'preserved_local_files':['docs/releases/m0_fixture.zip'],
        'data_directories_untouched':['work','clips','uploads','.venv','ClipperModels','models','clipper/fonts'],
        'specification_basis':{'document':'Arsitektur_Clipper_Pro_Terpadu_120_Halaman.pdf','pages':120,
            'sha256':'76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36','milestone_page':53,
            'editor_contract_page':64,'requirement_pages':[104,105],'requirements':['EX'+str(i).zfill(2) for i in range(1,14)]},
        'm6_repairs':['M6-A01','M6-A02','M6-A03','M6-A04','M6-A05','M6-A06'],
        'pending_acceptance':['G6 original speech listening and actual Demucs inference','CapCut Desktop 4.7.0 native import/save/edit/render regression',
            'Resolve Free 18.6.6 native import; EX05 text/font remains explicit backlog','Premiere / Final Cut target native exchange import',
            'Windows/i5-12500H/40GB/RTX3050 4GB/NVENC native hardware checks']}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');installer.load_manifest(output)
    shutil.copy2(ROOT/'tools/complete_installer.py',output/'complete_installer.py')
    for src,dest in [('docs/UPGRADE_4_0_18_M6_M7.md','PANDUAN_M6_M7.md'),('docs/LAPORAN_M7.md','LAPORAN_M7.md'),('docs/M7_REQUIREMENTS.json','M7_REQUIREMENTS.json')]:shutil.copy2(ROOT/src,output/dest)
    for name,flag in [('CEK_SEBELUM_UPGRADE.cmd','--check'),('PASANG_M6_M7_4_0_18.cmd',''),('PULIHKAN_M6_M7_4_0_18.cmd','--rollback')]:
        (output/name).write_bytes(('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\nwhere py >nul 2>nul\r\nif errorlevel 1 (\r\n  python "%~dp0complete_installer.py" '+flag+' %*\r\n) else (\r\n  py -3 "%~dp0complete_installer.py" '+flag+' %*\r\n)\r\nset "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n').encode())
    (output/'BACA_DULU.txt').write_text('CLIPPER PRO 4.0.18 - PERBAIKAN M6 + M7\n\n'
        'Dasar: M6 4.0.17 yang sudah dipasang di GitHub 14b89fa.\n'
        '1. Ekstrak ZIP ini ke folder baru, di luar folder mesin.\n'
        '2. Hentikan antrean dan server Clipper (Ctrl+C).\n'
        '3. Jalankan CEK_SEBELUM_UPGRADE.cmd; isi folder mesin yang berisi app.py.\n'
        '4. Bila lulus, jalankan PASANG_M6_M7_4_0_18.cmd.\n'
        '5. Buka JALANKAN_PRO.cmd pada mesin lama, tekan Ctrl+F5 di browser.\n'
        '6. Render ulang final revisi aktif agar memakai perbaikan M6 dan sidecar M7.\n'
        '7. PERIKSA / EKSPOR > M7 > Periksa paket > Buat paket M7.\n\n'
        'Tidak ada unduhan model, musik, API berbayar, atau perubahan environment otomatis.\n'
        'Kode dan SQLite dicadangkan; sumber/model/font pribadi tetap di tempatnya.\n'
        'Jangan salin payload manual. Rollback dijelaskan di PANDUAN_M6_M7.md.\n'
        'G6/G7 native/human acceptance belum dinyatakan lulus. EX05 text/font backlog.\n',encoding='utf-8')
    (output/'JALANKAN_UJI_M6_M7.cmd').write_bytes(('@echo off\r\nsetlocal\r\nset /p "CLIPPER_M7_TEST_TARGET=Folder mesin: "\r\ncd /d "%CLIPPER_M7_TEST_TARGET%"\r\nif errorlevel 1 (pause& exit /b 1)\r\n'
        'if not exist ".venv\\Scripts\\python.exe" (echo Python mesin tidak ditemukan.& pause& exit /b 1)\r\n'
        'if not exist "m7-test-results" mkdir "m7-test-results"\r\n'
        '".venv\\Scripts\\python.exe" -m pytest clipper/tests/test_m6_audit_repairs.py clipper/tests/test_m6_media.py clipper/tests/test_m7_contract.py clipper/tests/test_m7_media.py clipper/tests/test_m7_service.py clipper/tests/test_m7_e2e.py clipper/tests/test_m7_installer.py -q --junitxml="m7-test-results\\junit-%RANDOM%.xml"\r\nset "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n').encode())
    if verification:shutil.copytree(verification,output/'verification')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(output.rglob('*')):
            if path.is_symlink():raise ValueError('Symlink paket dilarang')
            if path.is_file():
                info=zipfile.ZipInfo(output.name+'/'+path.relative_to(output).as_posix(),date_time=(2026,10,16,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,path.read_bytes())
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('CRC upgrade gagal')
        for row in files:
            if sha(z.read(output.name+'/payload/'+row['path']))!=row['sha256']:raise ValueError('Checksum payload gagal')
    value={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),'payload_files':len(files),'guards':len(guards),
        'source_commit':source_commit,'baseline_github_commit':base['base_commit'],'zip_crc':'passed'}
    print(json.dumps(value,indent=2));return value


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source-commit',required=True);p.add_argument('--verification');a=p.parse_args();build(a.output,a.source_commit,a.verification)
