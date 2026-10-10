"""Build an offline overlay against the version-specific, verified baseline."""
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


def build(output,source_commit,verification=None,source_origin='local',*,version='4.0.8',base_file='complete_base_hashes.json'):
    if not re.fullmatch(r'[0-9a-f]{40}',source_commit):
        raise ValueError('SHA commit sumber harus lengkap.')
    if source_origin not in ('local','github'):
        raise ValueError('Asal sumber tidak dikenal.')
    output=Path(output).resolve();archive=output.with_suffix('.zip')
    if output.exists() or archive.exists():
        raise ValueError('Pilih nama paket baru.')
    baseline=json.loads((ROOT/'docs/releases'/base_file).read_text())
    spec=importlib.util.spec_from_file_location('complete_installer',ROOT/'tools/complete_installer.py')
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
    manifest={'schema_version':1,'version':version,'release_id':'typography10-20261010' if version=='4.0.10' else 'typography9-20261010' if version=='4.0.9' else 'complete-20261009',
        'source_commit':source_commit,'source_origin':source_origin,
        'baseline_github_commit':baseline['base_commit'],
        'accepted_baseline_github_commits':[baseline['base_commit'],*baseline.get('additional_base_commits',[])],
        'files':files,'guards':guards,
        'requires_installation':baseline.get('requires_installation','Clipper Studio 4.0.7 or the audited 4.0.8 upload matching known file hashes'),
        'offline_update':True,'data_directories_untouched':['work','clips','uploads','.venv','ClipperModels','models'],
        'pending_acceptance':['Real Indonesian CTC alignment and E5 inference on Windows','Actual Remotion and Motion Canvas browser renders when selected',
                              'Native CapCut and Resolve import/edit/reopen','Fresh detector/ASR on the original raw video and a full-device benchmark']}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    shutil.copyfile(ROOT/'tools/complete_installer.py',output/'complete_installer.py')
    if version != '4.0.10':
        shutil.copyfile(ROOT/'docs/PEMBENAHAN_LENGKAP.md',output/'PANDUAN_PEMBENAHAN_LENGKAP.md')
    for name,flag in [('CEK_SEBELUM_UPGRADE.cmd','--check'),('PASANG_PEMBENAHAN_LENGKAP.cmd',''),
                      ('PULIHKAN_PEMBENAHAN_LENGKAP.cmd','--rollback')]:
        command=('@echo off\r\nsetlocal\r\ncd /d "%~dp0."\r\n'
            'where py >nul 2>nul\r\nif errorlevel 1 (\r\n'
            '  python "%~dp0complete_installer.py" '+flag+' %*\r\n'
            ') else (\r\n  py -3 "%~dp0complete_installer.py" '+flag+' %*\r\n)\r\n'
            'set "RESULT=%ERRORLEVEL%"\r\npause\r\nexit /b %RESULT%\r\n')
        (output/name).write_bytes(command.encode('utf-8'))
    (output/'BACA_DULU.txt').write_text(
        'Clipper Studio 4.0.8 - Pembenahan Lengkap (tahap 2 sampai 7)\n\n'
        '1. Ekstrak ZIP ke folder baru. Hentikan antrean dan server dengan Ctrl+C.\n'
        '2. Jalankan CEK_SEBELUM_UPGRADE.cmd --target "C:\\AI\\clipper".\n'
        '3. Jika lulus, jalankan PASANG_PEMBENAHAN_LENGKAP.cmd pada folder yang sama.\n'
        '4. Jalankan JALANKAN_PRO.cmd dari mesin, lalu Ctrl+F5 di browser.\n'
        '5. Buka Periksa / ekspor, pilih klip, terapkan preset Adaptif atau Rapi.\n'
        '6. Klik Render seluruh pilihan untuk 9:16 + 16:9. Setelah selesai, buat satu paket.\n\n'
        'Jangan menyalin payload secara manual. Pemasang memeriksa dasar 4.0.7 atau 4.0.8 terverifikasi,\n'
        'mencadangkan kode dan database, lalu menerapkan perubahan secara atomik.\n'
        'Kode lokal berbeda akan ditolak sebelum penyalinan. Tidak mengunduh model.\n'
        'Rollback kode tersedia; koreksi proyek setelah upgrade tetap disimpan.\n'
        'Baca PANDUAN_PEMBENAHAN_LENGKAP.md untuk perubahan dan batas verifikasi.\n',encoding='utf-8')
    if version=='4.0.9':
        shutil.copyfile(ROOT/'docs/UPGRADE_4_0_9.md',output/'PANDUAN_UPGRADE_4_0_9.md')
        shutil.copyfile(output/'PASANG_PEMBENAHAN_LENGKAP.cmd',output/'PASANG_UPGRADE_4_0_9.cmd')
        shutil.copyfile(output/'PULIHKAN_PEMBENAHAN_LENGKAP.cmd',output/'PULIHKAN_UPGRADE_4_0_9.cmd')
        (output/'BACA_DULU.txt').write_text(
            'Clipper Studio 4.0.9 - Tipografi dan pembenahan audit\n\n'
            '1. Ekstrak ZIP ke folder baru. Hentikan antrean dan server dengan Ctrl+C.\n'
            '2. Jalankan CEK_SEBELUM_UPGRADE.cmd --target "C:\\AI\\clipper".\n'
            '3. Jika lulus, jalankan PASANG_UPGRADE_4_0_9.cmd --target "C:\\AI\\clipper".\n'
            '4. Jalankan JALANKAN_PRO.cmd dari mesin, lalu Ctrl+F5 di browser.\n'
            '5. Pilih preset Adaptif, Rapi, atau Ekspresif. Pilih Komposisi frasa Otomatis.\n'
            '6. Buat preview baru untuk dua rasio. Periksa keterbacaan, lalu render final.\n\n'
            'Paket mencakup pembenahan 4.0.8 sebelumnya. Tidak menimpa .env, proyek,\n'
            'video sumber, font pribadi atau model. Tidak mengunduh model saat pemasangan.\n'
            'MediaPipe opsional: pasang dari panel Komponen lalu jalankan uji sampel CPU.\n'
            'Perbaikan frasa, ukuran, dan posisi tetap aktif tanpa MediaPipe.\n'
            'Jika ada kode lokal berbeda, pemasang berhenti sebelum menimpa file.\n'
            'Rollback kode: PULIHKAN_UPGRADE_4_0_9.cmd --target "C:\\AI\\clipper".\n'
            'Baca PANDUAN_UPGRADE_4_0_9.md dan verification/ untuk bukti dan batas uji.\n',encoding='utf-8')
    if verification:
        shutil.copytree(verification,output/'verification')
    if version=='4.0.10':
        shutil.copyfile(ROOT/'docs/UPGRADE_4_0_10.md',output/'PANDUAN_UPGRADE_4_0_10.md')
        shutil.copyfile(output/'PASANG_PEMBENAHAN_LENGKAP.cmd',output/'PASANG_UPGRADE_4_0_10.cmd')
        shutil.copyfile(output/'PULIHKAN_PEMBENAHAN_LENGKAP.cmd',output/'PULIHKAN_UPGRADE_4_0_10.cmd')
        (output/'BACA_DULU.txt').write_text(
            'CLIPPER STUDIO 4.0.10 - LANJUTAN DARI 4.0.9\n\n'
            '1. Ekstrak ZIP ke folder baru, di luar folder mesin.\n'
            '2. Hentikan antrean dan tutup server mesin dengan Ctrl+C.\n'
            '3. Klik CEK_SEBELUM_UPGRADE.cmd. Isi folder mesin lama ketika diminta.\n'
            '4. Jika lulus, klik PASANG_UPGRADE_4_0_10.cmd; gunakan folder yang sama.\n'
            '5. Jalankan JALANKAN_PRO.cmd dari folder mesin. Tekan Ctrl+F5 pada browser.\n'
            '6. Pilih Adaptif atau Ekspresif, Komposisi Otomatis, template Otomatis.\n'
            '7. Buat preview baru untuk 9:16 dan 16:9 sebelum render yang panjang.\n\n'
            'Pemasang membutuhkan mesin 4.0.9 yang cocok dengan GitHub main 2e5d976.\n'
            'Tidak perlu memasang model baru untuk perbaikan tipografi utama.\n'
            'Kode lokal berbeda ditolak sebelum penyalinan. Kode dan database dicadangkan.\n'
            'Data proyek, .env, video, model, dan font pribadi tidak ditimpa.\n'
            'Rollback kode: klik PULIHKAN_UPGRADE_4_0_10.cmd.\n'
            'Baca PANDUAN_UPGRADE_4_0_10.md untuk pengaturan, hasil uji, dan batasnya.\n',encoding='utf-8')
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
