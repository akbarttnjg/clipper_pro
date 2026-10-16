"""Cumulative M0-M9: nine verified audit repairs overlay from byte-verified GitHub M7."""
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


def build(output,source_commit,verification=None):
    if not isinstance(source_commit,str) or not re.fullmatch('[0-9a-f]{40}',source_commit):raise ValueError('Commit sumber harus SHA penuh')
    output=Path(output).resolve();archive=output.with_suffix('.zip')
    if output.exists() or archive.exists():raise ValueError('Paket lama tidak ditimpa; pilih nama baru')
    base=json.loads((ROOT/'docs/releases/audit_22_base_hashes.json').read_text());files=[];output.mkdir(parents=True)
    for name in base['payload_paths']:
        data=installer.safe_path(ROOT,name).read_bytes();target=installer.safe_path(output/'payload',name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        binary=name.endswith('.zip');canonical=sha(data if binary else data.replace(b'\r\n',b'\n'))
        files.append({'path':name,'sha256':sha(data),'baseline_checksum':'sha256' if binary else 'sha256-lf',
            'allowed_text_sha256':sorted(set(base['allowed_hashes'].get(name,[])+[canonical]))})
    guards=[{'path':n,'baseline_checksum':'sha256' if n.endswith('.zip') else 'sha256-lf','allowed_text_sha256':base['allowed_hashes'][n]} for n in base['guard_paths']]
    m8=json.loads((ROOT/'docs/M8_REQUIREMENTS.json').read_text());m9=json.loads((ROOT/'docs/M9_REQUIREMENTS.json').read_text())
    manifest={'schema_version':1,'version':'4.0.22','milestone':'M0-M9: nine verified audit repairs','release_id':'m0-m9-audit-repairs-20261016','installer_revision':1,
        'source_commit':source_commit,'source_origin':'local implementation; not pushed','baseline_github_commit':base['base_commit'],
        'audit_findings_fixed':['A01','A02','A03','A04','A05','A07','A08','A09','A10'],
        'source_baseline_release':'4.0.21',
        'accepted_intermediate_m8_commit':base['m8_commit'],'accepted_previous_m9_release':base['previous_release'],'requires_installation':'M7 f6f1f6a, pinned M8 2126a46, or exact M8-M9 4.0.20/4.0.21; file guards required',
        'install_command':'PASANG_M8_M9_4_0_22.cmd','offline_update':True,'files':files,'guards':guards,
        'preserved_local_files':['docs/releases/m0_fixture.zip'],
        'data_directories_untouched':['work','clips','uploads','.venv','ClipperModels','models','clipper/fonts'],
        'implementation_counts':{'M8':m8['counts'],'M9':m9['counts']},'complete_milestone_acceptance':False,
        'requirements':{'M8':[r['id'] for r in m8['requirements']],'M9':[r['id'] for r in m9['requirements']]},
        'specification_basis':m9['architecture'],'pending_acceptance':m8['pending_acceptance']+m9['pending_acceptance'],
        'render_pipeline_version':'4.0.18-m7','account_connections_posts_broadcasts_models_downloaded_by_installer':0}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');installer.load_manifest(output)
    shutil.copy2(ROOT/'tools/complete_installer.py',output/'complete_installer.py')
    for source,destination in [('docs/PERBAIKAN_M0_M9_4_0_22.md','PANDUAN_M8_M9.md'),('docs/LAPORAN_M9_4_0_21.md','LAPORAN_M9_AWAL_4_0_21.md'),
        ('docs/M8_REQUIREMENTS.json','M8_REQUIREMENTS.json'),('docs/M9_REQUIREMENTS.json','M9_REQUIREMENTS.json'),('docs/m9/COMMANDS.md','COMMANDS_M9.md')]:shutil.copy2(ROOT/source,output/destination)
    for name,flag in [('CEK_SEBELUM_UPGRADE.cmd','--check'),('PASANG_M8_M9_4_0_22.cmd',''),('PULIHKAN_M8_M9_4_0_22.cmd','--rollback')]:
        script='@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\nwhere py >nul 2>nul\r\nif errorlevel 1 (\r\n  python "%~dp0complete_installer.py" '+flag+' %*\r\n) else (\r\n  py -3 "%~dp0complete_installer.py" '+flag+' %*\r\n)\r\nset "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n'
        (output/name).write_bytes(script.encode())
    common='@echo off\r\nsetlocal\r\nset /p "CLIPPER_M9_MACHINE=Folder mesin Clipper: "\r\ncd /d "%CLIPPER_M9_MACHINE%"\r\nif errorlevel 1 (pause& exit /b 1)\r\nif not exist ".venv\\Scripts\\python.exe" (echo Python mesin tidak ditemukan.& pause& exit /b 1)\r\n'
    end='\r\nset "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n'
    (output/'CEK_M8_M9_RUNTIME.cmd').write_bytes((common+'".venv\\Scripts\\python.exe" -m clipper.m9_probe'+end).encode())
    tests=' '.join('clipper/tests/'+n for n in ['test_m8_contract.py','test_m8_service.py','test_m8_adversarial.py','test_m8_e2e.py','test_m8_installer.py',
        'test_m9_recording.py','test_m9_effects.py','test_m9_creative_providers.py','test_m9_installer.py',
        'test_m9_dubbing.py','test_m9_creative_context.py','test_audit_4_0_22.py','test_audit_4_0_22_boundaries.py','test_audit_22_installer.py'])
    (output/'JALANKAN_UJI_M8_M9.cmd').write_bytes((common+'if not exist "m8-m9-test-results" mkdir "m8-m9-test-results"\r\n".venv\\Scripts\\python.exe" -m pytest '+tests+' -q --junitxml="m8-m9-test-results\\junit-%RANDOM%.xml"'+end).encode())
    (output/'JALANKAN_WORKER_M8.cmd').write_bytes((common+'".venv\\Scripts\\python.exe" -m clipper.m8_cli worker'+end).encode())
    guide=(ROOT/'docs/PERBAIKAN_M0_M9_4_0_22.md').read_text(encoding='utf-8')
    (output/'BACA_DULU.txt').write_text(guide,encoding='utf-8')
    (output/'PANDUAN_PASANG_4_0_22.md').write_text(guide,encoding='utf-8')
    if verification:shutil.copytree(verification,output/'verification')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(output.rglob('*')):
            if path.is_symlink():raise ValueError('Symlink paket dilarang')
            if path.is_file():
                info=zipfile.ZipInfo(output.name+'/'+path.relative_to(output).as_posix(),(2026,10,16,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,path.read_bytes())
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('CRC paket gagal')
        for row in files:
            if sha(z.read(output.name+'/payload/'+row['path']))!=row['sha256']:raise ValueError('SHA payload ZIP gagal')
    result={'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),'source_commit':source_commit,
        'baseline_github_commit':base['base_commit'],'payload_files':len(files),'guard_files':len(guards),'zip_crc':'passed','complete_milestone_acceptance':False}
    print(json.dumps(result,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source-commit',required=True);p.add_argument('--verification');a=p.parse_args();build(a.output,a.source_commit,a.verification)
