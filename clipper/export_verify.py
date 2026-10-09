"""Package completeness, per-track timing and separate native editor gates."""
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse
from PIL import ImageFont
from .dependency_cache import content_id
from .storage import read_json
from .timebase import interval_issues, video_track_ranges
from .project_install import normalized_path, relocation_roots


def package_path(root, value, created_root):
    """Resolve original export paths after extraction, including Windows URIs."""
    value = str(value or '').replace('\\', '/')
    if value.startswith('file:'):
        uri = urlparse(value)
        value = unquote(uri.path)
        if uri.netloc:
            value = '//' + uri.netloc + value
        if len(value) > 3 and value[0] == '/' and value[2] == ':':
            value = value[1:]
    value = normalized_path(value)
    roots = created_root if isinstance(created_root, list) else [created_root]
    for old in sorted([normalized_path(v) for v in [str(root), *roots] if v], key=len, reverse=True):
        match = value.casefold() if len(old) > 1 and old[1] == ':' else value
        prefix = old.casefold() if len(old) > 1 and old[1] == ':' else old
        if match.startswith(prefix + '/'):
            value = value[len(old)+1:]
            break
    path = Path(value)
    if not value or path.is_absolute() or ':' in value:
        raise ValueError('Aset berada di luar paket: ' + value)
    path = (Path(root) / path).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('Aset berada di luar paket: ' + value)
    return path


def validate_bundle(root, results):
    root = Path(root).resolve()
    manifest = read_json(root / 'manifest.json', {})
    if not isinstance(manifest, dict):
        manifest = {}
    roots = relocation_roots(manifest) if manifest.get('created_root') else []
    common = []
    checks = []
    inventory = {}
    editors = {}
    for key, label in (('capcut', 'CapCut'), ('resolve', 'DaVinci Resolve')):
        status = manifest.get(key + '_status', 'unknown')
        error = manifest.get(key + '_error')
        editors[key] = {'editor': label,
            'construction_status': 'failed' if status == 'failed' or error else 'generated' if status in ('experimental-generated', 'generated-unverified-in-editor') else 'unknown',
            'structural_status': 'pending', 'native_status': 'not_tested',
            'issues': ([str(error)] if error else [])}
        if status == 'failed' and not error:
            editors[key]['issues'].append('Pembuatan proyek gagal menurut manifest')
        if status == 'unknown':
            editors[key]['issues'].append('Status pembuatan proyek tidak tersedia')

    def required(value, issues, *, allow_empty=False):
        try:
            path = package_path(root, value, roots)
        except ValueError as exc:
            issues.append(str(exc)); return None
        label = path.relative_to(root).as_posix()
        if not path.is_file() or (not allow_empty and path.stat().st_size == 0):
            issues.append('Berkas wajib hilang atau kosong: ' + label); return None
        if label not in inventory:
            inventory[label] = {'path': label, 'bytes': path.stat().st_size,
                'content_id': content_id(path, fresh=True)}
        return path

    if not manifest:
        common.append('Manifest paket tidak tersedia atau tidak valid')
    if manifest.get('timelines') != len(results) or not results:
        common.append('Jumlah timeline pada manifest tidak sesuai hasil render')
    for filename in ('BACA_DULU.txt', 'PASANG_PROYEK.py', 'PASANG_CAPCUT.cmd', 'SIAPKAN_DAVINCI.cmd'):
        required(filename, common)
    reference = root / 'Reference'
    reference.mkdir(exist_ok=True)
    for i, result in enumerate(results, 1):
        name = f'{i:02d}'
        plan_path = required(f'edit-plan-{name}.json', common)
        plan = read_json(plan_path, {}) if plan_path else {}
        original = read_json(result.get('plan_path', ''), {})
        if not original:
            common.append(f'Klip {i}: rencana render tidak tersedia')
        if not isinstance(plan, dict) or not plan:
            common.append(f'Klip {i}: rencana paket tidak valid'); continue
        try:
            _, duration = video_track_ranges(plan)
        except (ValueError, KeyError, TypeError) as exc:
            common.append(f'Klip {i}: ' + str(exc)); duration = None
        if result.get('revision') is not None and plan.get('revision') != result['revision']:
            common.append(f'Klip {i}: revisi paket berbeda dari render')
        phrases = plan.get('captions', {}).get('phrases', [])
        checks.append({'clip': i, 'duration': plan.get('duration'), 'duration_us': duration,
            'width': plan.get('width'), 'height': plan.get('height'), 'fps': plan.get('fps'),
            'captions': len(phrases), 'broll_events': len(plan.get('broll', [])),
            'subtitle_qc': plan.get('caption_checks', {})})
        final = Path(result.get('absolute_file', ''))
        target = reference / f'{name}-reference.mp4'
        if final.is_file() and final.resolve() != target:
            shutil.copyfile(final, target)
        if required(f'Reference/{name}-reference.mp4', common):
            checks[-1]['reference_content_id'] = inventory[f'Reference/{name}-reference.mp4']['content_id']
            if result.get('output_content_id') and result['output_content_id'] != checks[-1]['reference_content_id']:
                common.append(f'Klip {i}: video Reference berbeda dari render final yang divalidasi')
        required(f'original-edit-plan-{name}.json', common)
        for suffix in ('captions.ass', 'captions.srt', 'credits.json', 'credits.txt'):
            required(f'Media/{name}-{suffix}', common, allow_empty=suffix == 'credits.txt' or not phrases and suffix == 'captions.srt')
        media = [plan.get('source', {}).get('path')]
        media += list(plan.get('audio', {}).get('stems', {}).values())
        if manifest.get('version',0)>=8:media.append(plan.get('audio',{}).get('mix'))
        media += [event.get('path') for event in plan.get('broll', [])]
        if not plan.get('audio', {}).get('stems'):
            common.append(f'Klip {i}: stem audio tidak tersedia')
        for path in media:
            required(path, common)
        fonts = {}
        for phrase in phrases:
            for word in phrase.get('words', []):
                filename = word.get('file') or {'regular': 'DejaVuSans.ttf', 'serif': 'DejaVuSerif-Bold.ttf'}.get(word.get('family'), 'DejaVuSans-Bold.ttf')
                fonts.setdefault(filename, []).append(word)
        title = plan.get('captions', {}).get('title')
        if title and title.get('file'):
            fonts.setdefault(title['file'], []).append(title)
        for filename, words in fonts.items():
            path = required('Fonts/' + filename, common)
            if path:
                try:
                    family, style = ImageFont.truetype(str(path), 24).getname()
                    if any(word.get('font_id') and (family, style) != (word.get('family'), word.get('style')) for word in words):
                        common.append(f'Identitas font berbeda: {filename} ({family} / {style})')
                    inventory['Fonts/' + filename].update(family=family, style=style)
                except (OSError, ValueError) as exc:
                    common.append('Font tidak dapat dibaca: ' + filename + ' / ' + str(exc))

        ri = editors['resolve']['issues']
        path = required(f'DaVinci/clip-{name}/timeline.xml', ri)
        if path:
            try:
                seq = ET.parse(path).find('.//sequence')
                if seq is None:
                    raise ValueError('Sequence XML tidak tersedia')
                total = int(seq.findtext('duration'))
                if total != plan['duration_frames']:
                    ri.append(f'Klip {i}: durasi XML berbeda dari rencana')
                tracks = seq.findall('./media/video/track') + seq.findall('./media/audio/track')
                if not tracks:
                    ri.append(f'Klip {i}: track XML tidak tersedia')
                for j, track in enumerate(tracks):
                    intervals = [(int(c.findtext('start')), int(c.findtext('end'))) for c in track.findall('clipitem')]
                    ri.extend(f'Klip {i} track {j+1}: {issue}' for issue in interval_issues(intervals, duration=total, contiguous=j == 0))
                for url in seq.findall('.//pathurl'):
                    required(url.text, ri)
            except (ET.ParseError, ValueError, TypeError, KeyError) as exc:
                ri.append(f'Klip {i}: XML tidak valid / ' + str(exc))
        required(f'DaVinci/clip-{name}/captions.srt', ri, allow_empty=not phrases)
        for j in range(len(phrases)):
            required(f'DaVinci/clip-{name}/text-{j+1:03d}.comp', ri)
        if title:
            required(f'DaVinci/clip-{name}/title.comp', ri)

        ci = editors['capcut']['issues']
        required(f'CapCut/CLIP_{name}/draft_meta_info.json', ci)
        path = required(f'CapCut/CLIP_{name}/draft_content.json', ci)
        if path:
            validate_capcut(path, plan, required, ci)

    required('DaVinci/IMPORT_RESOLVE.lua', editors['resolve']['issues'])
    ci = editors['capcut']['issues']
    combined = 'CapCut/CLIPPER_ALL_TIMELINES/'
    for filename in ('draft_content.json', 'draft_meta_info.json', 'Timelines/project.json'):
        required(combined + filename, ci)
    project = read_json(root / combined / 'Timelines/project.json', {})
    timelines = project.get('timelines', []) if isinstance(project, dict) else []
    if not isinstance(timelines, list) or len(timelines) != len(results):
        ci.append('Jumlah timeline wrapper CapCut tidak sesuai paket')
    elif timelines:
        ids = [row.get('id') for row in timelines if isinstance(row, dict)]
        if len(ids) != len(timelines) or any(not ident for ident in ids) or len(set(ids)) != len(ids) or project.get('main_timeline_id') not in ids:
            ci.append('Identitas timeline wrapper CapCut tidak valid')
        else:
            for ident in ids:
                required(combined + 'Timelines/' + ident + '/draft_content.json', ci)
    issues = list(dict.fromkeys(common))
    for editor in editors.values():
        editor['issues'] = list(dict.fromkeys(common + editor['issues']))
        editor['structural_status'] = 'failed' if editor['issues'] else 'passed'
        editor['import_status'] = 'blocked' if editor['issues'] else 'requires_local_import'
        issues.extend(editor['editor'] + ': ' + issue for issue in editor['issues'] if issue not in common)
    return {'schema_version': 2, 'structural_status': 'needs_review' if issues else 'passed',
        'issues': issues, 'editors': editors, 'timelines': checks, 'files': list(inventory.values()),
        'native_editor_status': 'not_tested', 'native_tests': [
            {'editor': e['editor'], 'status': e['import_status'], 'checks': ['media online', 'font / baseline', 'animation', 'B-roll offset', 'audio sync', 'duration']}
            for e in editors.values()],
        'comparison': 'Bandingkan ekspor editor dengan Reference/*.mp4 pada pembuka, tengah, pergantian B-roll dan penutup. Catat versi editor dan perbedaan nyata.',
        'limitations': ['Pemeriksaan struktur tidak membuktikan keberhasilan impor native.',
            'Blur/fade CapCut belum setara dengan ASS.',
            'Crop sumber native memerlukan pemeriksaan di editor.' if manifest.get('export_mode')=='native' else 'Framing sumber menyatu pada V1.']}


def validate_capcut(path, plan, required, issues):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        tracks = data.get('tracks')
        if not isinstance(tracks, list) or not tracks:
            raise ValueError('Track CapCut tidak tersedia')
        _, total = video_track_ranges(plan)
        if data.get('duration') != total:
            issues.append('Durasi draft CapCut berbeda dari rencana')
        canvas = data.get('canvas_config', {})
        if (canvas.get('width'), canvas.get('height')) != (plan['width'], plan['height']):
            issues.append('Ukuran canvas CapCut berbeda dari rasio yang dipilih')
        if not any(t.get('type') == 'audio' and t.get('segments') for t in tracks):
            issues.append('Track audio CapCut tidak tersedia')
        if plan.get('captions', {}).get('phrases') and not any(t.get('type') == 'text' and t.get('segments') for t in tracks):
            issues.append('Track teks CapCut tidak tersedia')
        material_ids = {row['id'] for rows in data.get('materials', {}).values() if isinstance(rows, list)
            for row in rows if isinstance(row, dict) and 'id' in row}
        for j, track in enumerate(tracks):
            segments = track.get('segments', [])
            intervals = []
            for segment in segments:
                timerange = segment['target_timerange']
                a, d = timerange['start'], timerange['duration']
                intervals.append((a, a + d))
                if segment.get('material_id') not in material_ids:
                    issues.append(f'Track {j+1}: referensi material tidak ditemukan')
            issues.extend(f'CapCut track {j+1}: {issue}' for issue in interval_issues(intervals, duration=total,
                contiguous=j == 0 and track.get('type') == 'video'))
        for key in ('videos', 'audios'):
            for material in data.get('materials', {}).get(key, []):
                required(material.get('path'), issues)
        for material in data.get('materials', {}).get('texts', []):
            for style in json.loads(material['content']).get('styles', []):
                required(style.get('font', {}).get('path'), issues)
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        issues.append('Draft CapCut tidak valid: ' + str(exc))
