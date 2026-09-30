"""Frame-aligned editorial decisions shared by the renderer and project exporters."""
from . import trim


def build(words, clip, cfg):
    fps = cfg.output_fps
    cw = [w for w in words if w['end'] > clip['start'] and w['start'] < clip['end']]
    body = (trim.keep_spans(cw, clip['start'], clip['end'], cfg) if cfg.trim_silence
            else [(clip['start'], clip['end'])])
    raw = [('body', a, b) for a, b in body]
    cold = clip.get('cold_open_span')
    if cfg.cold_open and cold and clip['start'] <= cold[0] < cold[1] <= clip['end'] and cold[0] >= clip['start'] + 4:
        # Quote is replayed in context in the main story, with an explicit source link in the plan.
        raw.insert(0, ('cold_open', cold[0], cold[1]))
    segments, mapped, cursor = [], [], 0
    for kind, a, b in raw:
        src = max(0, round(a * fps))
        count = max(1, round(b * fps) - src)
        a, b = src / fps, (src + count) / fps
        segments.append({'kind': kind, 'source_start': a, 'source_end': b,
                         'start_frame': cursor, 'duration_frames': count,
                         'start': cursor / fps, 'end': (cursor + count) / fps})
        for w in words:
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
            'revision': clip.get('revision', 0), 'warnings': []}
