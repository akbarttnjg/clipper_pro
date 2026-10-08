"""Frame-aligned editorial decisions shared by the renderer and project exporters."""
from . import trim


def build(words, clip, cfg):
    fps = cfg.output_fps
    cw = [w for w in words if w['end'] > clip['start'] and w['start'] < clip['end']]
    body = (trim.keep_spans(cw, clip['start'], clip['end'], cfg) if cfg.trim_silence
            else [(clip['start'], clip['end'])])
    if clip.get('manual_keep_spans'):
        body = [(max(clip['start'], a), min(clip['end'], b)) for a,b in clip['manual_keep_spans'] if max(clip['start'],a)<min(clip['end'],b)]
    raw = [('body', a, b) for a, b in body]
    warnings = []
    cold = clip.get('cold_open_span')
    if cfg.cold_open and cold and clip['start'] <= cold[0] < cold[1] <= clip['end'] and cold[0] >= clip['start'] + 4:
        from .boundaries import segments_from_words, audit
        sentence = next((s for s in segments_from_words(cw) if s.get('natural_end')
            and abs(s['start'] - cold[0]) <= .15 and abs(s['end'] - cold[1]) <= .2), None)
        if (sentence and 1 <= sentence['end'] - sentence['start'] <= 6
                and clip['end'] - sentence['end'] >= 8
                and not audit({**clip, 'start': sentence['start'], 'end': sentence['end']}, words, 6)):
            a, b = sentence['start'], sentence['end']
            # Move the complete sentence once. The same source range is subtracted
            # from every retained body span before mapping captions/audio/exports.
            remainder = []
            for kind, left, right in raw:
                if right <= a or left >= b:
                    remainder.append((kind, left, right))
                else:
                    if left < a:
                        remainder.append((kind, left, a))
                    if right > b:
                        remainder.append((kind, b, right))
            raw = [('cold_open', a, b), *remainder]
        else:
            warnings.append('Kutipan pembuka dilewati: perlu kalimat utuh dan penutup tetap utuh. Urutan sumber dipertahankan.')
    segments, mapped, cursor = [], [], 0
    for kind, a, b in raw:
        # Membership follows the exact source interval. Frame rounding must not
        # duplicate the tail of a word into the following body span.
        source_a, source_b = a, b
        src = max(0, round(a * fps))
        count = max(1, round(b * fps) - src)
        a, b = src / fps, (src + count) / fps
        segments.append({'kind': kind, 'source_start': a, 'source_end': b,
                         'start_frame': cursor, 'duration_frames': count,
                         'start': cursor / fps, 'end': (cursor + count) / fps})
        for w in words:
            if w['end'] <= source_a or w['start'] >= source_b:
                continue
            left, right = max(a, w['start']), min(b, w['end'])
            if right > left:
                mapped.append({**w, 'source_start': w['start'], 'source_end': w['end'],
                    'start': cursor / fps + left - a, 'end': cursor / fps + right - a,
                    'part': kind})
        cursor += count
    if cfg.preview_seconds > 0:
        limit = min(cursor, round(cfg.preview_seconds * fps))
        kept = []
        for span in segments:
            if span['start_frame'] >= limit:
                break
            span = dict(span)
            span['duration_frames'] = min(span['duration_frames'], limit - span['start_frame'])
            span['end'] = (span['start_frame'] + span['duration_frames']) / fps
            span['source_end'] = span['source_start'] + span['duration_frames'] / fps
            kept.append(span)
        segments, cursor = kept, limit
        mapped = [{**w, 'end': min(w['end'], cursor / fps)} for w in mapped if w['start'] < cursor / fps]
    return {'version': 2, 'fps': fps, 'duration_frames': cursor, 'duration': cursor / fps,
            'width': cfg.target_w, 'height': cfg.target_h, 'spans': segments, 'words': mapped,
            'title': clip['title'], 'keywords': clip.get('keywords', []), 'shots': [],
            'revision': clip.get('revision', 0), 'warnings': warnings,
            'intelligence': clip.get('intelligence', {})}
