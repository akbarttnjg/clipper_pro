"""Pack only referenced font faces, with explicit licensing/provenance metadata."""
import copy,shutil
from pathlib import Path
from .dependency_cache import content_id
from .font_catalog import FONTS
from .storage import write_json


def names(plan):
    rows=[w for p in plan.get('captions',{}).get('phrases',[]) for w in p.get('words',[])]
    if plan.get('captions',{}).get('title'):rows.append(plan['captions']['title'])
    return sorted({w.get('file') or {'regular':'DejaVuSans.ttf','serif':'DejaVuSerif-Bold.ttf'}.get(w.get('family'),'DejaVuSans-Bold.ttf') for w in rows})


def freeze(plan,folder,base):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);rows=[]
    bundled={r['file'] for r in FONTS.values()}|{'DejaVuSans.ttf','DejaVuSans-Oblique.ttf','DejaVuSans-BoldOblique.ttf'}
    snapshots={Path(r['path']).name:r for r in plan.get('font_assets7',[])}
    custom={r['sha256']:r for r in plan.get('finishing5',{}).get('font_assets',[])}
    saved={r['file']:r for r in plan.get('m5_fonts',[]) if r.get('file')}
    for name in names(plan):
        if Path(name).name!=name or '\\' in name:raise ValueError('Nama font tidak aman')
        row=snapshots.get(name) or saved.get(name);source=Path(row['path']) if row and row.get('path') else Path(base)/name
        if not source.is_file():raise ValueError('Font final hilang: '+name)
        digest=content_id(source,fresh=True).removeprefix('sha256:')
        if row and row.get('sha256') and row['sha256']!=digest:raise ValueError('Font final berubah: '+name)
        metadata=custom.get(digest)
        if name not in bundled and (not metadata or metadata['permission']=='unknown'):raise ValueError('Izin bundel font perlu dilengkapi: '+name)
        dest=folder/name
        if dest.exists() and content_id(dest,fresh=True)!='sha256:'+digest:raise ValueError('Nama font bentrok antar klip: '+name)
        if source.resolve()!=dest.resolve():shutil.copy2(source,dest)
        rows.append({'file':name,'path':str(dest.resolve()),'sha256':digest,'permission':metadata['permission'] if metadata else 'bundled_open_license',
            'origin':metadata['origin'] if metadata else 'Clipper bundled font','license':metadata['license'] if metadata else 'See Font-Licenses and LICENSE-DejaVu.txt',
            'attribution':metadata.get('attribution','') if metadata else '',
            'snapshot_scope':'captured_at_render' if name in snapshots else 'M5_render_snapshot' if name in saved else 'current_font; native appearance requires comparison'})
    licenses=Path(__file__).parent/'font-licenses'
    if licenses.is_dir():shutil.copytree(licenses,folder/'Font-Licenses',dirs_exist_ok=True)
    dejavu=Path(__file__).parent/'fonts/LICENSE-DejaVu.txt'
    if dejavu.is_file():shutil.copy2(dejavu,folder/'LICENSE-DejaVu.txt')
    return rows
