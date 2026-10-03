"""Project outputs and disposable previews have separate, explicit ownership."""
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote

LEGACY_PREVIEW = re.compile(r'^[a-f0-9]{12}-preview-\d+-[a-f0-9]{6}-r\d+-v\d+(?:\.(?:mp4|ass|srt|credits\.(?:json|txt)|subtitle-review\.json|qc\.json|filter\.txt|render\.log))?$')


def contained(root, relative):
    root = Path(root).resolve()
    rel = Path(relative)
    target = (root / rel).resolve()
    if rel.is_absolute() or '..' in rel.parts or not target.is_relative_to(root):
        raise ValueError('Path di luar folder proyek.')
    return target


def project_root(cfg):
    return contained(cfg.out_dir, cfg.job_id) if cfg.job_id and not cfg.preview_seconds else Path(cfg.out_dir)


def destinations(cfg, name):
    root = project_root(cfg)
    organized = bool(cfg.job_id and not cfg.preview_seconds)
    dirs = {key: root / folder if organized else root for key, folder in
            [('video', 'video'), ('text', 'subtitles'), ('report', 'reports')]}
    for folder in dirs.values():
        folder.mkdir(parents=True, exist_ok=True)
    return {key: folder / name for key, folder in dirs.items()}


def relative(cfg, path):
    return Path(path).resolve().relative_to(Path(cfg.out_dir).resolve()).as_posix()


def url(relative_path):
    return '/clips/' + quote(relative_path, safe='/')


def fingerprint(media, words, clip, cfg):
    def identity(value):
        p = Path(value)
        if value and p.is_file():
            s = p.stat()
            return [str(p.resolve()), s.st_size, s.st_mtime_ns]
        return value
    settings = asdict(cfg)
    for key in ('out_dir', 'work_dir', 'pexels_key'):
        settings.pop(key, None)
    assets = [identity(cfg.music_path), identity(cfg.sfx_path)]
    for scene in clip.get('_broll_recipe', {}).get('scenes', []):
        assets.append(identity(scene.get('asset', {}).get('path', '')))
    value = [identity(media), words, clip, settings, assets, 'preview-3.2']
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def disposable_files(work_root, out_root):
    """An allowlist: never include transcripts, decisions, sources, exports or stems."""
    work_root, out_root = Path(work_root), Path(out_root)
    seen = set()
    # New preview renders have their own subtree, one per persisted job.
    for folder in work_root.glob('*/cache/previews'):
        if folder.is_symlink() or not folder.resolve().is_relative_to(work_root.resolve()):
            continue
        for p in folder.rglob('*'):
            if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(folder.resolve()):
                seen.add(p)
    # 2.x / 3.1 previews can be identified without guessing based on "preview" alone.
    for p in out_root.glob('*'):
        if p.is_file() and not p.is_symlink() and LEGACY_PREVIEW.fullmatch(p.name):
            seen.add(p)
    for job in work_root.iterdir() if work_root.is_dir() else []:
        if not job.is_dir() or job.is_symlink() or not re.fullmatch('[a-f0-9]{12}', job.name):
            continue
        for folder in job.iterdir():
            if folder.is_dir() and not folder.is_symlink() and LEGACY_PREVIEW.fullmatch(folder.name):
                for p in folder.rglob('*'):
                    if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(folder.resolve()):
                        seen.add(p)
    return sorted(seen)


def cache_summary(work_root, out_root):
    files = disposable_files(work_root, out_root)
    return {'files': len(files), 'bytes': sum(p.stat().st_size for p in files),
            'description': 'Preview sementara, termasuk preview versi lama. Hasil final, transkrip, koreksi, audio proyek, dan model tetap disimpan.'}


def clear_previews(work_root, out_root):
    count = size = 0
    skipped = []
    for p in disposable_files(work_root, out_root):
        try:
            amount = p.stat().st_size
            p.unlink()
        except OSError:
            skipped.append(p.name)
            continue
        size += amount
        count += 1
        # Remove only now-empty cache directories, never a project root.
        parent = p.parent
        while parent != Path(work_root) and parent != Path(out_root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    return {'deleted_files': count, 'freed_bytes': size, 'skipped_files': skipped}


def organize_legacy(cfg):
    """Move recognized final sidecars; old URL resolver still locates moved files."""
    if not re.fullmatch('[a-f0-9]{12}', cfg.job_id):
        return {}
    moved = {}
    root = Path(cfg.out_dir)
    for p in root.glob(cfg.job_id + '-*'):
        if not p.is_file() or p.is_symlink() or LEGACY_PREVIEW.fullmatch(p.name):
            continue
        if p.suffix in ('.mp4', '.ass', '.srt'):
            bucket = 'video' if p.suffix == '.mp4' else 'subtitles'
        elif p.name.endswith(('.qc.json', '.credits.json', '.credits.txt', '.subtitle-review.json', '.filter.txt', '.render.log')):
            bucket = 'reports'
        else:
            continue
        target = contained(root, f'{cfg.job_id}/{bucket}/{p.name}')
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.rename(target)
        except OSError:
            continue  # A file open in a Windows editor can be retried later.
        moved[p.name] = target.relative_to(root).as_posix()
    return moved


def archive_previous(cfg, previous, current):
    """Keep the video folder current, retain superseded renders under history."""
    if not previous or previous.get('file') == current.get('file'):
        return
    relative_path = Path(previous.get('file', ''))
    if relative_path.parts[:2] != (cfg.job_id, 'video'):
        return  # Legacy flat files can be organized explicitly from the UI.
    root = project_root(cfg)
    stem = relative_path.stem
    for bucket in ('video', 'subtitles', 'reports'):
        for source in (root/bucket).glob(stem+'.*'):
            target = root/'history'/bucket/source.name
            if source.is_file() and not source.is_symlink() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    source.rename(target)
                except OSError:
                    # A video open in an editor may be locked on Windows. Keep
                    # it in place; the newly validated render is still usable.
                    continue
