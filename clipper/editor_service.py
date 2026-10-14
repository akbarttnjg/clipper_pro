"""Canonical editor commands. Legacy endpoints call these same contracts.

Read-only diffs run the real command validators inside a rolled-back transaction.
Preview requests refer to immutable server-created snapshots, never client JSON.
"""
import copy
import math
import re
import uuid
from dataclasses import asdict

from . import editor_contract as ec
from .config import validate_overrides
from .contracts import fingerprint
from .project_store import Conflict, at, differences

ATTRIBUTE_GROUPS = {
    'warna': ('accent_hex', 'base_hex', 'caption_backdrop'),
    'font': ('font_main', 'font_accent', 'accent_font', 'caption_scale'),
    'template': ('style_preset', 'caption_style', 'caption_template_policy', 'caption_composition'),
    'gerak': ('motion_intensity', 'semantic_emphasis', 'caption_seed'),
    'komposisi': ('layout', 'caption_position', 'caption_align', 'safe_placement', 'material_share', 'framing_x'),
    'audio': ('music_path', 'sfx_path', 'music_db', 'sfx_db', 'audio_normalize', 'audio_target_lufs', 'audio_peak_db', 'sfx_mode'),
}
STYLE_FIELDS = set().union(*(set(v) for k, v in ATTRIBUTE_GROUPS.items() if k != 'audio'))
HELP = {
    'accent_hex': ('Warna aksen', 'Warna penekanan, misalnya #F6CF69; mengubahnya hanya membuat override warna.', 'RGB hex', 'Tampilan'),
    'base_hex': ('Warna teks utama', 'Warna teks biasa, misalnya #FFFFFF. Kontras diperiksa bersama latar.', 'RGB hex', 'Tampilan'),
    'caption_style': ('Gaya teks', 'Template pilihan dipakai saat policy manual; auto dapat memilih template lain.', 'pilihan', 'Tampilan'),
    'caption_position': ('Posisi', 'Auto mencari ruang; kiri/kanan/bawah memilih anchor yang akan diperiksa pada preview.', 'anchor', 'Tampilan'),
    'caption_align': ('Perataan teks', 'Contoh: rata kiri untuk materi papan. Perataan berbeda dari posisi keseluruhan.', 'pilihan', 'Tampilan'),
    'caption_backdrop': ('Latar teks', 'Menambahkan bidang kontras; periksa apakah materi sumber masih terlihat.', 'aktif/nonaktif', 'Tampilan'),
    'motion_intensity': ('Gerak', 'Tenang, seimbang, atau dinamis mengubah intensitas template; preview dahulu.', 'pilihan', 'Tampilan'),
    'layout': ('Komposisi', 'Utuh dalam frame, fill, atau materi+pembicara mempunyai crop yang berbeda.', 'pilihan', 'Tampilan'),
    'semantic_emphasis': ('Penekanan makna', 'Menjaga angka/negasi sebagai frasa penekanan; off mematikan penekanan.', 'aktif/nonaktif', 'Tampilan'),
    'caption_template_policy': ('Pemilihan template', 'auto memilih template dari isi; manual memakai template pilihan.', 'pilihan', 'Tampilan'),
    'caption_scale': ('Ukuran teks', '1 berarti ukuran bawaan. Contoh: 1,1 memperbesar 10%.', 'kali', 'Tampilan'),
    'caption_seed': ('Alternatif desain', 'Angka yang sama menghasilkan keputusan desain yang sama pada masukan yang sama.', 'bilangan bulat', 'Tampilan'),
    'audio_target_lufs': ('Loudness suara', 'Target berlaku saat normalisasi aktif. Contoh: −16 LUFS.', 'LUFS', 'Audio'),
    'audio_peak_db': ('Batas puncak audio', 'Batas true peak, misalnya −1,5 dBTP.', 'dBTP', 'Audio'),
    'music_db': ('Volume musik', 'Angka lebih rendah mengecilkan musik. Contoh: −28 dB.', 'dB', 'Audio'),
    'sfx_db': ('Volume efek suara', 'Efek suara juga bergantung pada pilihan mode dan berkas SFX.', 'dB', 'Audio'),
    'framing_x': ('Geser komposisi', '−1 ke kiri, 0 di tengah, 1 ke kanan. Tidak membuat keyframe otomatis.', 'fraksi', 'Kamera'),
    'material_share': ('Porsi materi', '0,6 berarti sekitar 60% ruang komposisi untuk materi.', 'fraksi', 'Kamera'),
    'font_main': ('Font utama', 'Berkas font harus tersedia; font pilihan dan font yang dipakai dicatat terpisah.', 'font', 'Tampilan'),
    'font_accent': ('Font aksen', 'Dipakai hanya jika template dan aturan penekanan memakai aksen.', 'font', 'Tampilan'),
    'audio_normalize': ('Normalisasi audio', 'Aktifkan untuk memakai target loudness dan batas puncak.', 'aktif/nonaktif', 'Audio'),
}


def targets(service, doc, cid, vid, op, *, temporal=False):
    requested = op.get('targets')
    if requested is None:
        requested = [{'clip_id': cid, 'variant_id': v} for v in ('portrait', 'landscape')] if temporal and not op.get('separate_editorial_version', False) else [{'clip_id': cid, 'variant_id': vid}]
    if not isinstance(requested, list) or not 1 <= len(requested) <= 500:
        raise ValueError('Pilih 1–500 target klip/rasio secara eksplisit')
    result = []
    for row in requested:
        if not isinstance(row, dict):
            raise ValueError('Target harus menyebut klip dan rasio')
        c, v = row.get('clip_id'), row.get('variant_id')
        service.variant(doc, c, v)
        if not doc['clips'][c].get('included', True) and not op.get('include_excluded', False):
            raise ValueError('Klip dikecualikan: pilih ulang atau nyatakan include_excluded secara eksplisit')
        if (c, v) not in result:
            result.append((c, v))
    if temporal and len({c for c, _ in result}) != 1:
        raise ValueError('Edit waktu berlaku pada satu sumber klip; salin atribut secara terpisah')
    return result


def check_lock(service, doc, cid, vid, op):
    kind = op.get('op')
    tracks = {'m2_timing':'captions','m2_speaker':'captions','m2_track_display':'captions','correct_word': 'captions', 'correct_token': 'captions', 'correct_phrase': 'captions', 'align_words': 'captions',
        'caption_visibility': 'captions', 'cut_speech': 'video', 'timeline': 'video', 'bounds': 'video',
        'editor_segments': 'video', 'segment_edit': 'video', 'keyframes': 'video', 'visual_controls': 'video',
        'asset_enabled': 'illustration', 'asset_timing': 'illustration', 'asset_replace': 'illustration', 'asset_metadata': 'illustration'}
    track = tracks.get(kind)
    if kind.startswith('m5_'):
        track='illustration' if kind=='m5_layers' else 'captions'
    elif kind in ('settings', 'style', 'profile', 'preset_batch', 'brand_apply', 'paste_attributes', 'reset_overrides'):
        keys = set(op.get('values', {})) | set(op.get('keys', []))
        track = 'music' if keys and keys <= set(ATTRIBUTE_GROUPS['audio']) else 'captions'
    if not track or not cid:
        return
    requested = op.get('targets') or [{'clip_id': cid, 'variant_id': vid}]
    if kind in ('editor_segments', 'segment_edit', 'cut_speech', 'bounds', 'caption_visibility') and not op.get('separate_editorial_version'):
        requested = [{'clip_id': cid, 'variant_id': v} for v in ('portrait', 'landscape')]
    for target in requested:
        variant = service.variant(doc, target['clip_id'], target['variant_id'])
        if ec.track_state(variant.get('editor', {}))[track]['locked']:
            raise ValueError('Track '+track+' terkunci. Buka kunci sebelum mengedit.')


def _set_segments(service, doc, c, v, rows):
    variant = service.variant(doc, c, v)
    rows = ec.validate_segments(rows, doc['clips'][c], doc.get('editor_cameras', {}))
    clock = ec.build_clock(rows, service.config(doc, c, v).output_fps)
    editor = variant.setdefault('editor', {'schema_version': ec.SCHEMA_VERSION})
    editor['segments'] = rows
    # Keep a safe legacy read projection, never use it as the advanced render clock.
    variant['timeline'] = {'keep_spans': sorted([ [ec.seconds(r['source_start_tick']), ec.seconds(r['source_end_tick'])] for r in rows if r['kind'] == 'body'])}
    for attribute, points in editor.get('curves', {}).items():
        if any(point['time_tick'] > ec.tick(clock['duration']) for point in points):
            raise ValueError('Edit membuat keyframe melewati akhir timeline. Pindahkan/hapus keyframe dahulu.')
    editor['clock_digest'] = clock['digest']
    return clock


def _edit_segment(rows, operation):
    rows = copy.deepcopy(rows)
    selected = next((i for i, row in enumerate(rows) if row['id'] == operation.get('segment_id')), None)
    action = operation.get('action')
    if action == 'reorder':
        order = operation.get('order')
        if not isinstance(order, list) or len(order) != len(rows) or len(set(order)) != len(order) or set(order) != {r['id'] for r in rows}:
            raise ValueError('Urutan harus memuat setiap potongan tepat satu kali')
        return [next(r for r in rows if r['id'] == ident) for ident in order]
    if selected is None:
        raise ValueError('Potongan tidak ditemukan pada timeline aktif')
    row = rows[selected]
    if action == 'split':
        at_tick = operation['source_tick'] if 'source_tick' in operation else ec.tick(operation.get('source_time', -1))
        if type(at_tick) is not int or not row['source_start_tick'] < at_tick < row['source_end_tick'] or row.get('speed_curve') or row['kind'] != 'body':
            raise ValueError('Split harus di dalam potongan biasa tanpa ramp; hapus ramp dahulu')
        left, right = copy.deepcopy(row), copy.deepcopy(row)
        left['source_end_tick'] = at_tick
        right.update(id=row['id']+'-b-'+fingerprint(at_tick)[:6], source_start_tick=at_tick)
        rows[selected:selected+1] = [right, left] if row['reverse'] else [left, right]
    elif action == 'delete':
        rows.pop(selected)
    elif action == 'join':
        if selected+1 >= len(rows):
            raise ValueError('Pilih potongan yang mempunyai potongan berikutnya')
        other = rows[selected+1]
        if any(row.get(k) != other.get(k) for k in ('kind', 'speed_ratio', 'reverse', 'camera_id')) or row.get('speed_curve') or other.get('speed_curve') or row['kind'] != 'body':
            raise ValueError('Join memerlukan kamera, arah dan kecepatan yang sama tanpa ramp')
        contiguous = other['source_end_tick'] == row['source_start_tick'] if row['reverse'] else row['source_end_tick'] == other['source_start_tick']
        if not contiguous:
            raise ValueError('Potongan sumber tidak bersambung; jangan menyisipkan ucapan yang telah dipotong')
        row.update(source_start_tick=min(row['source_start_tick'], other['source_start_tick']), source_end_tick=max(row['source_end_tick'], other['source_end_tick']))
        rows[selected:selected+2] = [row]
    elif action == 'update':
        values = operation.get('values')
        allowed = {'source_start_tick', 'source_end_tick', 'speed', 'speed_ratio', 'speed_curve', 'reverse', 'camera_id', 'kind', 'freeze_duration_tick'}
        if not isinstance(values, dict) or not values or set(values)-allowed:
            raise ValueError('Atribut potongan tidak valid')
        if 'speed' in values:
            row.pop('speed_ratio', None)
        row.update(values)
    elif action == 'duplicate':
        duplicate = copy.deepcopy(row)
        duplicate['id'] = row['id']+'-d-'+fingerprint(operation)[:6]
        rows.insert(selected+1, duplicate)
    else:
        raise ValueError('Aksi potongan tidak dikenal')
    return rows


def apply_editor_command(service, doc, cid, vid, op, *, revision=0):
    kind = op.get('op')
    if kind not in ('profile', 'inherit_field', 'editor_segments', 'segment_edit', 'cut_speech', 'caption_visibility', 'track', 'keyframes', 'paste_attributes', 'editor_comment', 'camera_register', 'camera_remove'):
        return None
    touched = set()
    if kind in ('editor_segments', 'segment_edit', 'cut_speech'):
        rows = ec.segments_for(doc['clips'][cid], service.variant(doc, cid, vid))
        if kind == 'editor_segments':
            rows = op.get('segments')
        elif kind == 'segment_edit':
            rows = _edit_segment(rows, op)
        else:
            ids = op.get('origin_word_ids')
            if op.get('transcript_id') != doc.get('transcript_id') or op.get('transcript_revision') != doc.get('transcript_revision') or not isinstance(ids, list) or not ids:
                raise ValueError('Potong ucapan memerlukan identitas dan revisi transkrip aktif')
            words = service.store.heard_by_ids(doc['transcript_id'], ids)
            if {w['word_id'] for w in words} != set(ids):
                raise ValueError('Kata sumber tidak ditemukan')
            if any(w['end']<=doc['clips'][cid]['start'] or w['start']>=doc['clips'][cid]['end'] for w in words):
                raise ValueError('Kata sumber berada di luar klip yang diedit')
            windows = sorted([(ec.tick(w['start']), ec.tick(w['end'])) for w in words])
            for a, b in windows:
                remaining = []
                for row in rows:
                    x, y = row['source_start_tick'], row['source_end_tick']
                    if b <= x or a >= y:
                        remaining.append(row)
                        continue
                    if row.get('speed_curve') or row['kind'] != 'body':
                        raise ValueError('Potong ucapan pada ramp/freeze perlu diubah melalui potongan timeline dahulu')
                    parts = []
                    if x < a:
                        parts.append({**row, 'source_end_tick': a})
                    if b < y:
                        parts.append({**row, 'id': row['id']+'-'+fingerprint([a,b])[:6], 'source_start_tick': b})
                    remaining.extend(reversed(parts) if row['reverse'] else parts)
                rows = remaining
        for c, v in targets(service, doc, cid, vid, op, temporal=True):
            _set_segments(service, doc, c, v, rows)
            touched.add((c, v))
    elif kind == 'caption_visibility':
        ids = op.get('origin_word_ids')
        if op.get('transcript_id') != doc.get('transcript_id') or not isinstance(ids, list) or not 1 <= len(ids) <= 100 or type(op.get('hidden')) is not bool:
            raise ValueError('Pilih 1–100 kata dari transkrip aktif dan status hidden')
        heard = service.store.heard_by_ids(doc['transcript_id'], ids)
        clip = doc['clips'][cid]
        if {w['word_id'] for w in heard} != set(ids) or any(w['end'] <= clip['start'] or w['start'] >= clip['end'] for w in heard):
            raise ValueError('Kata berada di luar klip aktif')
        for c, v in targets(service, doc, cid, vid, op, temporal=True):
            editor = service.variant(doc, c, v).setdefault('editor', {'schema_version': 1})
            previous = set(editor.get('hidden_caption_word_ids', []))
            editor['hidden_caption_word_ids'] = sorted(previous | set(ids) if op['hidden'] else previous-set(ids), key=str)
            touched.add((c, v))
    elif kind == 'track':
        name, values = op.get('track'), op.get('values')
        if name not in ec.TRACKS or not isinstance(values, dict) or not values or set(values)-{'mute','solo','locked'} or any(type(v) is not bool for v in values.values()):
            raise ValueError('Track dan status mute/solo/kunci tidak valid')
        for c, v in targets(service, doc, cid, vid, op):
            editor = service.variant(doc, c, v).setdefault('editor', {'schema_version': 1})
            editor.setdefault('tracks', {}).setdefault(name, {}).update(values)
            touched.add((c, v))
    elif kind == 'keyframes':
        variant = service.variant(doc, cid, vid)
        duration = ec.build_clock(ec.segments_for(doc['clips'][cid], variant), service.config(doc,cid,vid).output_fps)['duration']
        points = op.get('points')
        attribute = op.get('attribute')
        if points != []:
            points = ec.validate_curve(attribute, points, duration)
        elif attribute not in ec.CURVE_ATTRIBUTES:
            raise ValueError('Atribut keyframe tidak valid')
        variant.setdefault('editor', {'schema_version': 1}).setdefault('curves', {})[attribute] = points
        touched.add((cid, vid))
    elif kind in ('profile', 'paste_attributes'):
        if kind == 'profile':
            profile = ec.PROFILES.get(op.get('profile_id'))
            if profile is None:
                raise ValueError('Profil footage tidak dikenal')
            values = validate_overrides(profile['settings'])
            # title_card is already disabled by Studio, not an editable user field.
        else:
            clipboard, keys = op.get('clipboard'), op.get('keys')
            allowed = set().union(*map(set, ATTRIBUTE_GROUPS.values()))
            if not isinstance(clipboard, dict) or clipboard.get('schema_version') != 1 or not isinstance(keys, list) or not keys or set(keys)-allowed:
                raise ValueError('Pilih atribut clipboard yang didukung')
            data = clipboard.get('values', {})
            if set(keys)-set(data):
                raise ValueError('Clipboard tidak mempunyai atribut yang dipilih')
            values = validate_overrides({k: data[k] for k in keys})
            if set(values) != set(keys):
                raise ValueError('Clipboard mengandung nilai yang tidak didukung')
        for c, v in targets(service, doc, cid, vid, op):
            variant = service.variant(doc, c, v)
            keep = set(variant.get('override_keys', [])) if op.get('preserve_manual', True) else set()
            applied = {k: val for k, val in values.items() if k not in keep}
            if kind == 'profile':
                variant.setdefault('style_layers', {})['profile'] = values
                for key in values:
                    if key not in keep:
                        variant['settings'].pop(key,None)
                if not op.get('preserve_manual',True):
                    variant['override_keys'] = sorted(set(variant.get('override_keys',[]))-set(values))
                variant['footage_profile'] = op['profile_id']
                origin = {'scope': 'profile', 'id': op['profile_id']}
            else:
                variant['settings'].update(applied)
                variant['override_keys'] = sorted(set(variant.get('override_keys', [])) | set(applied))
                origin = {'scope': 'ratio', 'clipboard': clipboard.get('source')}
            variant.setdefault('setting_origins', {}).update({k: origin for k in applied})
            touched.add((c, v))
    elif kind == 'inherit_field':
        keys = op.get('keys')
        allowed = set().union(*map(set, ATTRIBUTE_GROUPS.values()))
        if not isinstance(keys,list) or not keys or set(keys)-allowed:
            raise ValueError('Pilih kolom yang memiliki nilai induk')
        for c,v in targets(service,doc,cid,vid,op):
            variant=service.variant(doc,c,v)
            for key in keys:
                variant['settings'].pop(key,None)
                variant.get('setting_origins',{}).pop(key,None)
            variant['override_keys']=sorted(set(variant.get('override_keys',[]))-set(keys))
            touched.add((c,v))
    elif kind == 'editor_comment':
        comments = doc.setdefault('editor_comments', {})
        action = op.get('action', 'add')
        if action == 'add':
            text, timestamp = op.get('text'), op.get('source_tick')
            clip = doc['clips'][cid]
            if not isinstance(text,str) or not 1 <= len(text.strip()) <= 2000 or type(timestamp) is not int or not ec.tick(clip['start']) <= timestamp < ec.tick(clip['end']):
                raise ValueError('Komentar memerlukan teks dan waktu sumber dalam klip')
            ident = 'comment-'+fingerprint([doc['project_id'],cid,vid,revision,timestamp,text.strip()])[:20]
            comments[ident] = {'id': ident, 'clip_id': cid, 'variant_id': vid, 'source_tick': timestamp, 'text': text.strip(), 'revision': revision+1, 'resolved': False}
        elif action in ('resolve','delete'):
            row = comments.get(op.get('comment_id'))
            if not row or row['clip_id'] != cid:
                raise ValueError('Komentar tidak ditemukan pada klip aktif')
            if row['revision'] != revision and not op.get('review_stale', False):
                raise ValueError('Komentar berasal dari revisi lama. Tinjau konteks sebelum menyelesaikan.')
            if action == 'delete':
                del comments[row['id']]
            else:
                row.update(resolved=True, reviewed_at_revision=revision+1)
        else:
            raise ValueError('Aksi komentar tidak valid')
    elif kind == 'camera_register':
        from .editor_media import camera_record
        row = camera_record(service, doc, op)
        doc.setdefault('editor_cameras', {})[row['id']] = row
    elif kind == 'camera_remove':
        key = op.get('camera_id')
        if key not in doc.get('editor_cameras', {}):
            raise ValueError('Kamera tidak ditemukan')
        for clip in doc['clips'].values():
            if any(r.get('camera_id') == key for v in clip['variants'].values() for r in v.get('editor', {}).get('segments', [])):
                raise ValueError('Kamera masih dipakai timeline; ganti sudut dahulu')
        del doc['editor_cameras'][key]
    return {'touched': list(touched)}


def state(service, doc, cid, vid):
    variant = service.variant(doc, cid, vid)
    cfg = asdict(service.config(doc,cid,vid))
    fields = {}
    for key in sorted(STYLE_FIELDS | set(ATTRIBUTE_GROUPS['audio'])):
        if key not in cfg:
            continue
        manual = key in variant.get('override_keys', [])
        if manual:
            origin = {'scope': 'ratio', 'manual': True}
        elif key in doc.get('settings_explicit_keys',[]) and key not in variant.get('settings',{}):
            origin={'scope':'project'}
        elif key in variant.get('style_layers',{}).get('brand',{}):
            origin={'scope':'brand',**variant.get('brand_kit',{})}
        elif key in variant.get('style_layers',{}).get('profile',{}):
            origin={'scope':'profile','id':variant.get('footage_profile')}
        elif key in variant.get('setting_origins', {}):
            origin = variant['setting_origins'][key]
        elif key in variant.get('brand_kit', {}).get('applied_keys', []):
            origin = {'scope':'brand', 'id':variant['brand_kit']['id'], 'revision':variant['brand_kit']['revision']}
        elif key in variant.get('settings', {}):
            origin = {'scope': 'ratio', 'manual': False, 'legacy': True}
        elif key in doc['clips'][cid].get('settings', {}):
            origin = {'scope':'clip'}
        elif key in doc.get('settings', {}):
            origin = {'scope':'project', 'legacy': True}
        else:
            origin = {'scope':'engine'}
        parent = copy.deepcopy(doc)
        parent_variant = service.variant(parent,cid,vid)
        parent_variant['settings'].pop(key,None)
        parent_value = asdict(service.config(parent,cid,vid))[key]
        title, help_text, units, section = HELP.get(key,(key.replace('_',' '),'Nilai berlaku pada klip dan rasio yang dipilih.', 'pilihan', 'Audio' if key in ATTRIBUTE_GROUPS['audio'] else 'Tampilan'))
        fields[key] = {'value':cfg[key], 'origin':origin, 'manual':manual, 'parent':parent_value,
            'label':title, 'help':help_text, 'unit':units, 'section':section, 'scope':'rasio aktif'}
    clock = ec.build_clock(ec.segments_for(doc['clips'][cid],variant),cfg['output_fps'])
    return {'version':ec.VERSION, 'schema_version':1, 'revision':doc['revision'], 'clip_id':cid, 'variant_id':vid,
        'fields':fields, 'segments':ec.segments_for(doc['clips'][cid],variant), 'clock':clock,
        'tracks':ec.track_state(variant.get('editor',{})), 'curves':variant.get('editor',{}).get('curves',{}),
        'hidden_caption_word_ids':variant.get('editor',{}).get('hidden_caption_word_ids',[]),
        'profile':variant.get('footage_profile'), 'profiles':ec.PROFILES, 'aliases':ec.PANEL_ALIASES,
        'cameras':doc.get('editor_cameras',{}),
        'comments':[{**r,'stale':r['revision']!=doc['revision']} for r in doc.get('editor_comments',{}).values() if r['clip_id']==cid],
        'attribute_groups':ATTRIBUTE_GROUPS}


def make_draft(service, request):
    preview = service.changes(request, preview_only=True)
    return service.store.create_editor_draft(request['project_id'],request['expected_revision'],request,preview)


def commit_draft(service, pid, draft_id, expected_revision, operation_id, *, rebase=False):
    draft = service.store.editor_draft(pid,draft_id)
    request = {**copy.deepcopy(draft['request']), 'expected_revision':expected_revision, 'operation_id':operation_id}
    # The store owns idempotency. Replay the exact command even after its revision advanced.
    with service.store.connect() as db:
        prior=db.execute('SELECT request_hash FROM operations WHERE project_id=? AND operation_id=?',(pid,operation_id)).fetchone()
    if prior:
        if prior['request_hash']!=fingerprint(request):raise ValueError('ID operasi dipakai untuk perubahan berbeda')
        return service.changes(request)
    current = service.store.get(pid)
    if current['revision'] != expected_revision:
        raise Conflict(current['revision'])
    if draft['base_revision'] != expected_revision:
        if not rebase:
            raise Conflict(current['revision'],'Revisi berubah; tinjau diff dan pilih rebase untuk perubahan yang tidak bertabrakan')
        collisions = []
        for row in draft['diff']:
            if row['path'][-1] in ('timeline_revision','transcript_revision','revision','clock_digest'):continue
            exists,value = at(current,row['path'])
            if row['path'][-1]=='override_keys':
                before=set(row['before'] or []);after=set(row['after'] or []);changed=before^after
                if any((key in (value or []))!=(key in before) for key in changed):collisions.append(row['path'])
                continue
            if exists != row['before_exists'] or value != row['before']:
                collisions.append(row['path'])
        if collisions:
            raise Conflict(current['revision'],'Draf bertabrakan dengan revisi aktif; tinjau setiap kolom.',collisions)
    return service.changes(request)


def copy_attributes(service, doc, cid, vid, keys):
    allowed = set().union(*map(set,ATTRIBUTE_GROUPS.values()))
    if not isinstance(keys,list) or not keys or set(keys)-allowed:
        raise ValueError('Pilih atribut gaya/audio yang didukung')
    cfg = asdict(service.config(doc,cid,vid))
    values = {k:cfg[k] for k in keys}
    return {'schema_version':1,'values':values,'source':{'project_id':doc['project_id'],'clip_id':cid,'variant_id':vid,'revision':doc['revision']},'digest':fingerprint(values)}


def replace_proposal(service, doc, data):
    """Literal replacement over effective rows; no ASR or implicit audio edits."""
    query,replacement = data.get('query'),data.get('replacement')
    if not isinstance(query,str) or not query.strip() or len(query)>120 or not isinstance(replacement,str) or not replacement.strip() or len(replacement)>120:
        raise ValueError('Pencarian dan pengganti harus berisi 1–120 karakter')
    scope = data.get('scope','clip')
    if scope not in ('clip','selected_clips','shared_utterance'):
        raise ValueError('Pilih cakupan klip, klip terpilih, atau ucapan bersama')
    cids = [None] if scope=='shared_utterance' else data.get('clip_ids') if scope=='selected_clips' else [data.get('clip_id')]
    if not isinstance(cids,list) or not 1<=len(cids)<=100 or len(set(cids))!=len(cids):
        raise ValueError('Pilih cakupan klip yang valid')
    operations,reviews = [],[]
    for cid in cids:
        if cid is not None and cid not in doc['clips']:
            raise ValueError('Klip tidak ditemukan')
        words = [w for w in service.transcript(doc,cid)['words'] if cid is None or w['end']>doc['clips'][cid]['start'] and w['start']<doc['clips'][cid]['end']]
        from .editor_search import phrase_groups
        for group in phrase_groups(words,query,replacement=replacement):
            after=group['after']
            if after==group['before']:
                continue
            op = {'op':'correct_phrase','clip_id':cid,'origin_word_ids':group['origin_word_ids'],'before':group['before'],'after':after,
                'scope':'shared_utterance' if cid is None else 'clip','transcript_id':doc['transcript_id'],'transcript_revision':doc['transcript_revision'],
                'protect_names':True}
            # Existing facts contract supplies exact stamps, shown to the operator before apply.
            operations.append(op)
    if len(operations)>100:
        raise ValueError('Lebih dari 100 perubahan. Persempit pencarian atau pilih lebih sedikit klip.')
    if operations:
        request={'project_id':doc['project_id'],'expected_revision':doc['revision'],'operations':operations}
        reviews=service.correction_review(request)['reviews']
    return {'revision':doc['revision'],'transcript_revision':doc['transcript_revision'],'scope':scope,'mode':'effective',
        'operations':operations,'reviews':reviews,'count':len(operations),'audio_changed':False}


def render_summary(service, doc, requested):
    from .dependency_cache import asset_id
    from .font_catalog import FONTS
    from pathlib import Path
    result=[]
    for cid,vid in targets(service,doc,None,None,{'targets':requested,'include_excluded':True}):
        cfg=service.config(doc,cid,vid)
        variant=service.variant(doc,cid,vid)
        fonts={}
        for role in ('font_main','font_accent'):
            name=getattr(cfg,role)
            if cfg.finishing5:
                from .finishing5_assets import font_info
                spec=font_info(cfg.fonts_dir,name)
                fonts[role]={'selected':name,'installed':True,'family':spec['family'],'weight':spec['weight'],'files':[{'name':spec['file'],'digest':'sha256:'+spec['sha256']}]}
                continue
            spec=FONTS.get(name,{})
            fonts[role]={'selected':name,'installed':False,'files':[]}
            for path in Path(cfg.fonts_dir).glob('*'):
                if path.is_file() and path.suffix.lower() in ('.ttf','.otf') and (name.replace('_','').casefold() in path.stem.replace('_','').replace('-','').casefold() or str(spec.get('file','')).casefold()==path.name.casefold()):
                    fonts[role]['files'].append({'name':path.name,'digest':asset_id(path)})
            fonts[role]['installed']=bool(fonts[role]['files'])
        clock=ec.build_clock(ec.segments_for(doc['clips'][cid],variant),cfg.output_fps)
        result.append({'clip_id':cid,'variant_id':vid,'ratio':'9:16' if vid=='portrait' else '16:9',
            'revision':doc['revision'],'width':cfg.target_w,'height':cfg.target_h,'fps':cfg.output_fps,'duration':clock['duration'],
            'clock_digest':clock['digest'],'style_preset':cfg.style_preset,'profile':variant.get('footage_profile'),
            'duration_basis':'shared_editor_clock' if variant.get('editor',{}).get('segments') else 'source_bounds_before_optional_pause_or_hook_planning',
            'template':cfg.finishing5['style']['template_id'] if cfg.finishing5 else cfg.caption_style,'template_policy':cfg.caption_template_policy,'seed':cfg.caption_seed,'fonts':fonts,
            'finishing5':cfg.finishing5['style'] if cfg.finishing5 else None,
            'audio_normalize':cfg.audio_normalize,'audio_target_lufs':cfg.audio_target_lufs,'audio_peak_db':cfg.audio_peak_db,
            'caption_renderer_requested':cfg.caption_renderer,'encoder_requested':'h264_nvenc' if cfg.use_nvenc else 'libx264',
            'required_capabilities':['ffmpeg','libass']+(['remotion'] if cfg.caption_renderer=='remotion' else []),
            'dependency':service.dependency(doc,cid,vid,fresh=True),'tracks':ec.track_state(variant.get('editor',{})),
            'source_id':doc['source']['source_id'],'cost':{'kind':'local','currency':None,'amount':None,'note':'Tidak memanggil layanan berbayar untuk render ini; biaya listrik belum diukur.'}})
    return {'schema_version':1,'project_id':doc['project_id'],'revision':doc['revision'],'targets':result,'digest':fingerprint(result)}
