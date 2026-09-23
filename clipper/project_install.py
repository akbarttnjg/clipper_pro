"""Stdlib-only project relinker and non-overwriting CapCut draft registration."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path


def atomic_json(path, value):
    temp = path.with_name(path.name + '.clipper-tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def relink(root):
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    old = manifest['created_root'].rstrip('/').replace('\\', '/')
    new = str(root.resolve()).replace('\\', '/')
    if old != new:
        from urllib.parse import quote
        # Exported references use forward slashes, including JSON-in-JSON text materials.
        old_uri = 'file:///' + quote(old, safe='/:') if ':' in old[:3] else 'file://' + quote(old, safe='/')
        new_uri = root.resolve().as_uri()
        for p in root.rglob('*'):
            if p.is_file() and (p.suffix.lower() in ('.json', '.xml', '.tmp', '.bak') or p.name.startswith('edit-plan-')):
                text = p.read_text(encoding='utf-8')
                replaced = text.replace(old_uri, new_uri).replace(old, new)
                if text != replaced:
                    temp = p.with_name(p.name + '.relink-tmp')
                    temp.write_text(replaced, encoding='utf-8')
                    os.replace(temp, p)
        manifest['created_root'] = new
        atomic_json(manifest_path, manifest)
    missing = [p for p in manifest['source_files'] if not Path(p).is_file()]
    if missing:
        raise ValueError('Video sumber tidak ditemukan; kembalikan ke path ini:\n' + '\n'.join(missing))
    return manifest


def install_capcut(root, draft_root, individual=False, check_running=True):
    if check_running and os.name == 'nt':
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq CapCut.exe', '/FO', 'CSV'], capture_output=True)
        if b'capcut.exe' in r.stdout.lower():
            raise ValueError('Tutup CapCut sepenuhnya sebelum memasang proyek.')
    manifest = relink(root)
    if manifest.get('capcut_status') != 'experimental-generated':
        raise ValueError('Draft CapCut tidak selesai dibuat: ' + str(manifest.get('capcut_error')))
    index = draft_root / 'root_meta_info.json'
    if not index.is_file():
        raise ValueError('Indeks proyek CapCut tidak ditemukan. Buka CapCut, buat satu proyek, tutup, lalu coba lagi.\n'
                         'Folder khusus: --draft-root "D:/path/proyek"')
    data = json.loads(index.read_text(encoding='utf-8'))
    if not isinstance(data.get('all_draft_store'), list):
        raise ValueError('Format indeks CapCut berbeda. Tidak ada perubahan dilakukan.')
    sources = sorted((root / 'CapCut').glob('CLIP_[0-9][0-9]')) if individual else [root / 'CapCut' / 'CLIPPER_ALL_TIMELINES']
    if not sources or any(not (p / 'draft_content.json').is_file() for p in sources):
        raise ValueError('Paket draft tidak lengkap.')
    backup = index.with_name('root_meta_info.clipper-backup-' + str(time.time_ns()) + '.json')
    shutil.copy2(index, backup)
    created = []
    try:
        for source in sources:
            dest = draft_root / ('Clipper-' + source.name + '-' + uuid.uuid4().hex[:8])
            # The folder is always new, never merged into an existing user project.
            shutil.copytree(source, dest)
            created.append(dest)
            meta = json.loads((dest / 'draft_meta_info.json').read_text(encoding='utf-8'))
            meta.update(draft_fold_path=str(dest.resolve()).replace('\\','/'),
                        draft_root_path=str(draft_root.resolve()).replace('\\','/'),
                        draft_json_file=str((dest/'draft_content.json').resolve()).replace('\\','/'),
                        draft_id=str(uuid.uuid4()).upper(), tm_draft_modified=int(time.time()*1e6))
            atomic_json(dest / 'draft_meta_info.json', meta)
            data['all_draft_store'].insert(0, meta)
        atomic_json(index, data)
    except Exception:
        # Only remove folders just created in this transaction; existing drafts are untouched.
        for dest in created:
            shutil.rmtree(dest)
        raise
    print(f'{len(created)} proyek ditambahkan. Cadangan indeks: {backup}')
    print('Buka CapCut dan periksa timeline, teks, framing, serta suara. Simpan kembali dari CapCut.')
    return created, backup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--capcut', action='store_true')
    parser.add_argument('--individual', action='store_true')
    parser.add_argument('--relink', action='store_true')
    parser.add_argument('--draft-root')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.capcut:
        draft_root = Path(args.draft_root) if args.draft_root else Path(os.environ.get('LOCALAPPDATA', '')) / 'CapCut/User Data/Projects/com.lveditor.draft'
        install_capcut(root, draft_root, args.individual)
    else:
        relink(root)
        print('Path aset siap. Buka Resolve > Workspace > Console > Lua, lalu jalankan:')
        print('dofile([[' + str(root / 'DaVinci' / 'IMPORT_RESOLVE.lua').replace('\\','/') + ']])')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('GAGAL: ' + str(exc), file=sys.stderr)
        sys.exit(1)
