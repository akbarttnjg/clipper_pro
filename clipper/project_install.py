"""Stdlib-only project relinker and non-overwriting CapCut draft registration."""
import argparse
import hashlib
import json
import os
import re
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


def normalized_path(value):
    value = str(value).replace('\\', '/')
    prefix = '//' if value.startswith('//') else ''
    return prefix + re.sub('/+', '/', value[len(prefix):]).rstrip('/')


def relocation_roots(manifest):
    old = normalized_path(manifest['created_root'])
    roots = [old]
    # Older Windows relinkers updated created_root but missed escaped paths.
    # Recover only packaged clean media under the same unique project folder.
    name = old.rsplit('/', 1)[-1]
    for value in manifest.get('source_files', []):
        value = normalized_path(value)
        if '/Media/' in value:
            prefix, filename = value.rsplit('/Media/', 1)
            if prefix.rsplit('/', 1)[-1] == name and re.fullmatch(r'\d{2}-video-clean\.mp4', filename):
                roots.append(prefix)
    return sorted(set(roots), key=len, reverse=True)


def rewrite_paths(value, roots, new, uri_replacements):
    if isinstance(value, dict):
        return {key: rewrite_paths(item, roots, new, uri_replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_paths(item, roots, new, uri_replacements) for item in value]
    if not isinstance(value, str):
        return value
    # CapCut stores text/font styles as a JSON string inside draft JSON.
    if value.lstrip().startswith(('{', '[')):
        try:
            inner = json.loads(value)
        except ValueError:
            pass
        else:
            rewritten = rewrite_paths(inner, roots, new, uri_replacements)
            if rewritten != inner:
                return json.dumps(rewritten, ensure_ascii=False)
    for old_uri, new_uri in uri_replacements:
        value = value.replace(old_uri, new_uri)
    normal = normalized_path(value)
    for old in roots:
        match = normal.casefold() if len(old) > 1 and old[1] == ':' else normal
        prefix = old.casefold() if len(old) > 1 and old[1] == ':' else old
        if match == prefix or match.startswith(prefix + '/'):
            return new + normal[len(old):]
    return value


def relink(root):
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    roots = relocation_roots(manifest)
    new = str(root.resolve()).replace('\\', '/')
    if roots != [new]:
        from urllib.parse import quote
        new_uri = root.resolve().as_uri()
        uris = [('file:///' + quote(old, safe='/:') if ':' in old[:3] else 'file://' + quote(old, safe='/'), new_uri) for old in roots]
        for p in root.rglob('*'):
            if p.is_file() and (p.suffix.lower() in ('.json', '.xml', '.tmp', '.bak') or p.name.startswith('edit-plan-')):
                text = p.read_text(encoding='utf-8')
                try:
                    data = json.loads(text)
                except ValueError:
                    replaced = text
                    for old_uri, new_uri in uris:
                        replaced = replaced.replace(old_uri, new_uri)
                    for old in roots:
                        replaced = replaced.replace(old, new)
                else:
                    rewritten = rewrite_paths(data, roots, new, uris)
                    replaced = json.dumps(rewritten, ensure_ascii=False, indent=2) if rewritten != data else text
                if text != replaced:
                    temp = p.with_name(p.name + '.relink-tmp')
                    temp.write_text(replaced, encoding='utf-8')
                    os.replace(temp, p)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['created_root'] = new
        atomic_json(manifest_path, manifest)
    missing = [p for p in manifest['source_files'] if not Path(p).is_file()]
    if missing:
        raise ValueError('Video sumber tidak ditemukan; kembalikan ke path ini:\n' + '\n'.join(missing))
    return manifest


def verify_package(root, editor):
    """Check the generated report and immutable assets before editor registration."""
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    path = root / 'verification.json'
    report = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    if not isinstance(report, dict):
        raise ValueError('Laporan pemeriksaan paket tidak valid. Ekspor ulang sebelum impor editor.')
    status = report.get('editors', {}).get(editor)
    if manifest.get('version', 0) >= 4 and (report.get('schema_version', 0) < 2 or not isinstance(status, dict)):
        raise ValueError('Laporan pemeriksaan paket tidak tersedia. Ekspor ulang sebelum impor editor.')
    if status and status.get('structural_status') != 'passed':
        raise ValueError('Paket ' + status.get('editor', editor) + ' belum lengkap:\n' + '\n'.join(status.get('issues', [])))
    for record in report.get('files', []):
        relative = Path(record['path'])
        target = (root / relative).resolve()
        if relative.is_absolute() or not target.is_relative_to(root.resolve()):
            raise ValueError('Path pemeriksaan di luar paket: ' + str(relative))
        # JSON/XML editor files are rewritten when the package is relocated.
        # Media, reference video and fonts retain their content identities.
        if relative.parts[0] not in ('Media', 'Reference', 'Fonts') or relative.suffix == '.json':
            continue
        if not target.is_file():
            raise ValueError('Aset paket hilang: ' + str(relative))
        digest = hashlib.sha256()
        with target.open('rb') as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                digest.update(block)
        if 'sha256:' + digest.hexdigest() != record['content_id']:
            raise ValueError('Isi aset paket berubah: ' + str(relative) + '. Pulihkan berkas atau ekspor ulang.')


def install_capcut(root, draft_root, individual=False, check_running=True):
    if check_running and os.name == 'nt':
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq CapCut.exe', '/FO', 'CSV'], capture_output=True)
        if b'capcut.exe' in r.stdout.lower():
            raise ValueError('Tutup CapCut sepenuhnya sebelum memasang proyek.')
    verify_package(root, 'capcut')
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
    sources = sorted(p for p in (root / 'CapCut').glob('CLIP_*') if re.fullmatch(r'CLIP_\d{2,}', p.name)) if individual else [root / 'CapCut' / 'CLIPPER_ALL_TIMELINES']
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
        verify_package(root, 'resolve')
        relink(root)
        print('Path aset siap. Buka Resolve > Workspace > Console > Lua, lalu jalankan:')
        print('dofile([[' + str(root / 'DaVinci' / 'IMPORT_RESOLVE.lua').replace('\\','/') + ']])')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('GAGAL: ' + str(exc), file=sys.stderr)
        sys.exit(1)
