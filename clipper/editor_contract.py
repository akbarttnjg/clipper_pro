"""Canonical M1 editor contracts: explicit units, scopes, tracks and clocks.

Source words are immutable. All temporal edits are explicit commands; displayed
seconds are converted to integer microsecond ticks at the API boundary.
"""
import copy
import math
from fractions import Fraction

from .contracts import fingerprint

VERSION = '4.0.12-m1'
SCHEMA_VERSION = 1
TICKS_PER_SECOND = 1_000_000
TRACKS = ('video', 'captions', 'illustration', 'voice', 'music', 'sfx')
CURVE_ATTRIBUTES = {'scale': (1., 4.), 'x': (-1., 1.), 'y': (-1., 1.), 'opacity': (0., 1.)}
EASINGS = ('linear', 'hold', 'ease_in', 'ease_out', 'ease_in_out')
PANEL_ALIASES = {
    'Kata & ejaan': ('Teks', 'Subtitle dan ucapan'),
    'Potongan & ritme': ('Potongan', 'Batas dan susunan'),
    'Gaya keseluruhan': ('Tampilan', 'Profil'),
    'Tata teks & komposisi': ('Tampilan', 'Caption'),
    'Gaya Tahap 5 & keterbacaan': ('Tampilan', 'Template dan animasi'),
    'Brand kit & alternatif': ('Tampilan', 'Brand dan alternatif'),
    'Kamera, pembicara & area aman': ('Kamera', 'Pembicara dan area aman'),
    'Suara & musik': ('Audio', 'Suara dan musik'),
    'Ilustrasi & bukti analisis': ('Ilustrasi', 'Aset dan bukti'),
}
PROFILES = {
    'education': {'name': 'Edukasi / papan tulis', 'description': 'Materi utuh, subtitle di kiri, tanpa hook teks dan pan.',
        'settings': {'edit_style': 'lesson', 'source_kind': 'board', 'audience': 'students', 'layout': 'stream',
            'caption_style': 'clean', 'caption_template_policy': 'auto', 'motion_intensity': 'calm',
            'caption_position': 'left', 'caption_align': 'left', 'cold_open': False, 'title_card': False,
            'punch_zoom': False, 'trim_silence': False, 'preserve_material_pauses': True, 'broll_mode': 'off'}},
    'finance': {'name': 'Finansial / chart', 'description': 'Chart dan istilah terlihat; angka dan negasi tetap perlu ditinjau.',
        'settings': {'edit_style': 'lesson', 'source_kind': 'chart', 'audience': 'finance', 'layout': 'fit',
            'caption_style': 'editorial', 'caption_template_policy': 'auto', 'motion_intensity': 'calm',
            'cold_open': False, 'title_card': False, 'punch_zoom': False, 'preserve_material_pauses': True}},
    'podcast': {'name': 'Podcast / percakapan', 'description': 'Pergantian kalimat dan pembicara tetap dapat ditinjau.',
        'settings': {'edit_style': 'podcast', 'source_kind': 'podcast', 'layout': 'auto', 'caption_style': 'editorial',
            'caption_template_policy': 'auto', 'motion_intensity': 'calm', 'punch_zoom': False, 'cold_open': False}},
    'gaming': {'name': 'Gaming', 'description': 'Frame game dipertahankan; deteksi event game adalah capability terpisah.',
        'settings': {'edit_style': 'energetic', 'source_kind': 'screen', 'layout': 'fit', 'caption_style': 'magazine',
            'caption_template_policy': 'auto', 'motion_intensity': 'balanced', 'punch_zoom': False, 'cold_open': False}},
    'screen': {'name': 'Layar / demonstrasi aplikasi', 'description': 'Teks layar dan jeda demonstrasi dijaga.',
        'settings': {'edit_style': 'lesson', 'source_kind': 'screen', 'layout': 'fit', 'caption_style': 'clean',
            'caption_template_policy': 'auto', 'motion_intensity': 'calm', 'punch_zoom': False, 'trim_silence': False,
            'preserve_material_pauses': True, 'cold_open': False, 'title_card': False}},
    'generative': {'name': 'Footage grafis / generatif', 'description': 'Tidak membuat anchor wajah fiktif; generator baru tidak dijalankan.',
        'settings': {'edit_style': 'balanced', 'source_kind': 'graphic', 'layout': 'fit', 'caption_style': 'narrative',
            'caption_template_policy': 'auto', 'motion_intensity': 'balanced', 'punch_zoom': False, 'cold_open': False}},
}


def tick(seconds):
    if isinstance(seconds, bool):
        raise ValueError('Waktu harus berupa angka detik')
    value = float(seconds)
    if not math.isfinite(value) or abs(value) > 86400:
        raise ValueError('Waktu tidak valid atau melebihi 24 jam')
    return round(value*TICKS_PER_SECOND)


def seconds(ticks):
    return ticks/TICKS_PER_SECOND


def rate(value):
    if isinstance(value, bool):
        raise ValueError('Kecepatan harus berupa angka')
    number = float(value)
    if not math.isfinite(number) or not .25 <= number <= 4:
        raise ValueError('Kecepatan harus 0,25–4 kali')
    fraction = Fraction(str(number)).limit_denominator(10000)
    return {'numerator': fraction.numerator, 'denominator': fraction.denominator}


def speed(value):
    if isinstance(value, bool):
        raise ValueError('Kecepatan harus berupa angka')
    if isinstance(value, dict):
        a, b = value.get('numerator'), value.get('denominator')
        if type(a) is not int or type(b) is not int or b <= 0:
            raise ValueError('Rasio kecepatan tidak valid')
        return float(Fraction(a, b))
    return float(value)


def equivalent(key, left, right):
    if key.endswith('_hex') and isinstance(left, str) and isinstance(right, str):
        return left.casefold() == right.casefold()
    return left == right


def validate_curve(attribute, points, duration):
    if attribute not in CURVE_ATTRIBUTES or not isinstance(points, list) or not 1 <= len(points) <= 100:
        raise ValueError('Kurva harus mempunyai 1–100 keyframe pada atribut yang didukung')
    lo, hi = CURVE_ATTRIBUTES[attribute]
    result, prior = [], -1
    for row in points:
        if not isinstance(row, dict):
            raise ValueError('Keyframe harus berupa objek')
        t = row.get('time_tick') if 'time_tick' in row else tick(row.get('time', -1))
        value = row.get('value')
        if type(t) is not int or not prior < t <= tick(duration) or t < 0 or isinstance(value, bool):
            raise ValueError('Waktu keyframe harus berurutan dan di dalam timeline')
        value = float(value)
        easing = row.get('easing', 'linear')
        if not math.isfinite(value) or not lo <= value <= hi or easing not in EASINGS:
            raise ValueError('Nilai atau easing keyframe tidak valid')
        result.append({'time_tick': t, 'value': value, 'easing': easing})
        prior = t
    return result


def ease(u, name):
    u = min(1., max(0., u))
    return {'hold': lambda: 0., 'linear': lambda: u, 'ease_in': lambda: u*u,
            'ease_out': lambda: 1-(1-u)*(1-u), 'ease_in_out': lambda: u*u*(3-2*u)}[name]()


def sample_curve(points, time_tick, default):
    if not points:
        return default
    if time_tick <= points[0]['time_tick']:
        return points[0]['value']
    for a, b in zip(points, points[1:]):
        if time_tick < b['time_tick']:
            u = ease((time_tick-a['time_tick'])/(b['time_tick']-a['time_tick']), a['easing'])
            return a['value']+(b['value']-a['value'])*u
    return points[-1]['value']


def ffmpeg_curve(points, default):
    """The same interpolation used by sample_curve, expressed as numeric FFmpeg data."""
    if not points:
        return str(float(default))
    expression = str(points[-1]['value'])
    for a, b in reversed(list(zip(points, points[1:]))):
        start, end = seconds(a['time_tick']), seconds(b['time_tick'])
        u = f'((t-{start:.9f})/{end-start:.9f})'
        easing = a['easing']
        term = '0' if easing == 'hold' else u if easing == 'linear' else f'({u}*{u})' if easing == 'ease_in' else (
            f'(1-(1-{u})*(1-{u}))' if easing == 'ease_out' else f'({u}*{u}*(3-2*{u}))')
        value = f'({a["value"]:.9f}+({b["value"]-a["value"]:.9f})*{term})'
        expression = f'if(lt(t,{end:.9f}),{value},{expression})'
    return f'if(lte(t,{seconds(points[0]["time_tick"]):.9f}),{points[0]["value"]:.9f},{expression})'


def segments_for(clip, variant):
    saved = variant.get('editor', {}).get('segments')
    if saved:
        return copy.deepcopy(saved)
    spans = variant.get('timeline', {}).get('keep_spans') or [[clip['start'], clip['end']]]
    return [{'id': 'span-'+fingerprint([i, a, b])[:16], 'source_start_tick': tick(a),
             'source_end_tick': tick(b), 'speed_ratio': rate(1.), 'reverse': False,
             'camera_id': 'primary', 'kind': 'body'} for i, (a, b) in enumerate(spans)]


def validate_segments(rows, clip, cameras=()):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError('Timeline harus mempunyai 1–200 potongan')
    valid_cameras = {'primary', *cameras}
    left, right = tick(clip['start']), tick(clip['end'])
    result, identifiers = [], set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError('Potongan harus berupa objek')
        a = row.get('source_start_tick') if 'source_start_tick' in row else tick(row.get('start', -1))
        b = row.get('source_end_tick') if 'source_end_tick' in row else tick(row.get('end', -1))
        kind = row.get('kind', 'body')
        if type(a) is not int or type(b) is not int or not left <= a < b <= right or kind not in ('body', 'freeze'):
            raise ValueError('Potongan harus berada di dalam batas sumber klip')
        identifier = row.get('id') or 'span-'+fingerprint([i, a, b, kind])[:16]
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 80 or identifier in identifiers:
            raise ValueError('Identitas potongan kosong atau ganda')
        identifiers.add(identifier)
        ratio = rate(speed(row.get('speed_ratio', row.get('speed', 1.))))
        reverse = row.get('reverse', False)
        camera = row.get('camera_id', 'primary')
        if type(reverse) is not bool or not isinstance(camera,str) or camera not in valid_cameras:
            raise ValueError('Reverse atau sumber kamera tidak valid')
        segment = {'id': identifier, 'source_start_tick': a, 'source_end_tick': b,
                   'speed_ratio': ratio, 'reverse': reverse, 'camera_id': camera, 'kind': kind}
        if kind == 'freeze':
            freeze = row.get('freeze_duration_tick') if 'freeze_duration_tick' in row else tick(row.get('freeze_duration', 1.))
            if type(freeze) is not int or not tick(.1) <= freeze <= tick(30):
                raise ValueError('Freeze harus 0,1–30 detik')
            segment['freeze_duration_tick'] = freeze
            segment['reverse'] = False
        ramp = row.get('speed_curve')
        if ramp:
            if kind == 'freeze' or not isinstance(ramp, list) or not 2 <= len(ramp) <= 20:
                raise ValueError('Ramp harus mempunyai 2–20 titik pada potongan biasa')
            points, prior = [], -1
            for point in ramp:
                if not isinstance(point,dict):raise ValueError('Setiap titik ramp harus berupa objek')
                at = point.get('source_offset_tick') if 'source_offset_tick' in point else tick(point.get('offset', -1))
                val = speed(point.get('speed_ratio', point.get('speed', 1.)))
                rate(val)
                if type(at) is not int or not prior < at <= b-a or at < 0:
                    raise ValueError('Titik ramp harus berurutan di dalam rentang sumber')
                points.append({'source_offset_tick': at, 'speed_ratio': rate(val)})
                prior = at
            if points[0]['source_offset_tick'] != 0 or points[-1]['source_offset_tick'] != b-a:
                raise ValueError('Ramp harus mempunyai titik pada awal dan akhir potongan')
            segment['speed_curve'] = points
        result.append(segment)
    return result


def _ramp_rate(points, offset):
    if offset <= points[0]['source_offset_tick']:
        return speed(points[0]['speed_ratio'])
    for a, b in zip(points, points[1:]):
        if offset <= b['source_offset_tick']:
            u = (offset-a['source_offset_tick'])/(b['source_offset_tick']-a['source_offset_tick'])
            return speed(a['speed_ratio'])+(speed(b['speed_ratio'])-speed(a['speed_ratio']))*u
    return speed(points[-1]['speed_ratio'])


def build_clock(segments, fps):
    """Freeze a source/output map on the output frame grid once, for all consumers.

    Ramps use bounded source slices (at least four source frames). Each slice has
    one measured rate and exact output frame count shared by video and audio.
    """
    if type(fps) is not int or not 1 <= fps <= 120:
        raise ValueError('FPS timeline tidak valid')
    clock, frame_cursor = [], 0
    for segment in segments:
        a, b = segment['source_start_tick'], segment['source_end_tick']
        points = segment.get('speed_curve')
        if segment['kind'] == 'freeze':
            slices = [(a, b, 1., max(1, round(seconds(segment['freeze_duration_tick'])*fps)))]
        elif points:
            step = max(1, round(4*TICKS_PER_SECOND/fps))
            edges = sorted(set([a, b, *range(a, b, step), *(a+p['source_offset_tick'] for p in points)]))
            slices, exact = [], 0.
            for x, y in zip(edges, edges[1:]):
                value = _ramp_rate(points, (x+y)/2-a)
                prior = round(exact)
                exact += seconds(y-x)/value*fps
                frames = round(exact)-prior
                if frames:
                    slices.append((x, y, value, frames))
        else:
            value = speed(segment['speed_ratio'])
            slices = [(a, b, value, max(1, round(seconds(b-a)/value*fps)))]
        if segment['reverse']:
            slices.reverse()
        for x, y, value, frames in slices:
            clock.append({**segment, 'logical_segment_id': segment['id'],
                'source_start_tick': x, 'source_end_tick': y, 'render_speed': value,
                'output_start_frame': frame_cursor, 'duration_frames': frames,
                'output_end_frame': frame_cursor+frames})
            frame_cursor += frames
    if not frame_cursor or frame_cursor > fps*7200 or len(clock) > 600:
        raise ValueError('Timeline kosong atau terlalu rumit; batasi durasi/ramp atau pecah klip')
    return {'schema_version': SCHEMA_VERSION, 'time_base': {'numerator': 1, 'denominator': TICKS_PER_SECOND},
            'fps': fps, 'duration_frames': frame_cursor, 'duration': frame_cursor/fps,
            'slices': clock, 'digest': fingerprint([fps, clock])}


def source_to_output(clock, source_time, *, camera_id='primary'):
    at = tick(source_time)
    output = []
    for row in clock['slices']:
        a, b = row['source_start_tick'], row['source_end_tick']
        if row['camera_id'] == camera_id and a <= at < b:
            u = 0. if row['kind'] == 'freeze' else (b-at)/(b-a) if row['reverse'] else (at-a)/(b-a)
            output.append((row['output_start_frame']+u*row['duration_frames'])/clock['fps'])
    return output


def output_to_source(clock, output_time):
    frame = float(output_time)*clock['fps']
    for row in clock['slices']:
        if row['output_start_frame'] <= frame < row['output_end_frame']:
            u = (frame-row['output_start_frame'])/row['duration_frames']
            a, b = row['source_start_tick'], row['source_end_tick']
            at = a if row['kind'] == 'freeze' else min(b-1,b-(b-a)*u) if row['reverse'] else a+(b-a)*u
            return {'source_time': seconds(at), 'camera_id': row['camera_id'], 'segment_id': row['logical_segment_id']}
    return None


def track_state(editor):
    saved = editor.get('tracks', {})
    result = {name: {'mute': False, 'solo': False, 'locked': False, **saved.get(name, {})} for name in TRACKS}
    solo = {name for name, row in result.items() if row['solo']}
    for name, row in result.items():
        row['enabled'] = not row['mute'] and (not solo or name in solo)
    return result


def render_inputs(editor):
    """Locks/comments are editorial metadata, not pixel or audio dependencies."""
    values={}
    if editor.get('segments'):values['segments']=editor['segments']
    if any(editor.get('curves',{}).values()):values['curves']={k:v for k,v in editor['curves'].items() if v}
    if editor.get('hidden_caption_word_ids'):values['hidden_caption_word_ids']=editor['hidden_caption_word_ids']
    tracks={k:v['enabled'] for k,v in track_state(editor).items()}
    if not all(tracks.values()):values['enabled_tracks']=tracks
    return values


def remap_words(words, clock, hidden=()):
    hidden = set(hidden)
    result = []
    for row in clock['slices']:
        if row['kind'] == 'freeze':
            continue
        a, b = seconds(row['source_start_tick']), seconds(row['source_end_tick'])
        for word in words:
            left, right = max(a, word['start']), min(b, word['end'])
            if right <= left:
                continue
            duration = row['duration_frames']/clock['fps']
            start = row['output_start_frame']/clock['fps']
            if row['reverse']:
                left, right = start+(b-right)/(b-a)*duration, start+(b-left)/(b-a)*duration
            else:
                left, right = start+(left-a)/(b-a)*duration, start+(right-a)/(b-a)*duration
            aligned = []
            for token in word.get('aligned_words', []):
                x, y = max(a, token['start']), min(b, token['end'])
                if y <= x:
                    continue
                if row['reverse']:
                    x, y = start+(b-y)/(b-a)*duration, start+(b-x)/(b-a)*duration
                else:
                    x, y = start+(x-a)/(b-a)*duration, start+(y-a)/(b-a)*duration
                aligned.append({**copy.deepcopy(token), 'start': x, 'end': y})
            origins = word.get('source_word_ids', word.get('origin_word_ids', [word['word_id']]))
            token_ids=word.get('token_ids',[word.get('token_id',word['word_id'])])
            result.append({**copy.deepcopy(word), 'source_start': word['start'], 'source_end': word['end'],
                'source_word_ids': origins, 'origin_word_id': word['word_id'],
                'word_id': str(word['word_id'])+'@'+row['logical_segment_id'],
                'token_id':str(word.get('token_id',word['word_id']))+'@'+row['logical_segment_id'],
                'token_ids':[str(ident)+'@'+row['logical_segment_id'] for ident in token_ids],
                'source_token_ids':token_ids,
                'start': left, 'end': right, 'caption_hidden': bool(set(origins)&hidden),
                'editor_segment_id': row['logical_segment_id'],
                **({'aligned_words': aligned} if 'aligned_words' in word else {})})
    result.sort(key=lambda word: (word['start'], word['end']))
    joined = []
    for word in result:
        prior = joined[-1] if joined else None
        if prior and prior['word_id'] == word['word_id'] and abs(prior['end']-word['start']) < 1/clock['fps']:
            prior['end'] = max(prior['end'], word['end'])
            if 'aligned_words' in word:
                # Ramp slices may divide one aligned token; merge only touching pieces.
                for token in word['aligned_words']:
                    last = prior['aligned_words'][-1] if prior['aligned_words'] else None
                    if last and last['word'] == token['word'] and abs(last['end']-token['start']) < 1/clock['fps']:
                        last['end'] = max(last['end'],token['end'])
                    else:
                        prior['aligned_words'].append(token)
        else:
            joined.append(word)
    return joined
