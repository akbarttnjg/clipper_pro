"""Source-segment clip selection with explicit, nonduplicating fallback."""
import math
import re
from .typography import valid_words, token, STOP
from . import editorial


def segments_from_words(words):
    segments, cur = [], []
    for w in valid_words(words):
        if cur and (w['start'] - cur[-1]['end'] > .55 or len(cur) >= 22):
            segments.append(cur)
            cur = []
        cur.append(w)
        if re.search(r'[.!?]$', w['word']):
            segments.append(cur)
            cur = []
    if cur:
        segments.append(cur)
    return [{'id': i, 'start': s[0]['start'], 'end': s[-1]['end'],
             'text': ' '.join(w['word'] for w in s), 'words': s} for i, s in enumerate(segments)]


def _chunks(segments):
    i = 0
    while i < len(segments):
        j, count = i, 0
        while j < len(segments) and count + len(segments[j]['words']) <= 320:
            count += len(segments[j]['words'])
            j += 1
        j = max(j, i + 1)
        yield segments[i:j]
        if j == len(segments):
            break
        k, overlap = j, 0
        while k > i + 1 and overlap < 80:
            k -= 1
            overlap += len(segments[k]['words'])
        i = max(i + 1, k)


def _overlap(a, b):
    inter = max(0, min(a['end'], b['end']) - max(a['start'], b['start']))
    return inter / max(.001, min(a['end'] - a['start'], b['end'] - b['start']))


def _clean(raw, duration, cfg):
    cleaned = []
    for item in raw if isinstance(raw, list) else []:
        try:
            a, b = float(item['start']), float(item['end'])
            if not math.isfinite(a) or not math.isfinite(b):
                continue
            a, b = max(0., a), min(duration, b)
            if b - a < cfg.min_clip_s or b - a > cfg.max_clip_s + .01:
                continue
            raw_score = float(item.get('score', 50))
            value = max(0, min(100, int(raw_score))) if math.isfinite(raw_score) else 50
            title = str(item.get('title') or 'Cuplikan').strip()[:100]
            cleaned.append({**item, 'start': round(a, 3), 'end': round(b, 3), 'title': title,
                            'hook': str(item.get('hook') or title)[:120],
                            'reason': str(item.get('reason') or '')[:400], 'score': value})
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
    picked = []
    for c in sorted(cleaned, key=lambda x: x['score'], reverse=True):
        if not any(_overlap(c, old) > .3 for old in picked):
            picked.append(c)
        if len(picked) >= cfg.num_clips:
            break
    return picked


def _ground(raw, segments, cfg):
    by_id = {s['id']: s for s in segments}
    out = []
    for c in raw:
        try:
            a, b = int(c['start_segment']), int(c['end_segment'])
            if a > b or a not in by_id or b not in by_id:
                continue
            chosen = [s for s in segments if a <= s['id'] <= b]
            start, end = chosen[0]['start'], chosen[-1]['end']
            if not cfg.min_clip_s <= end - start <= cfg.max_clip_s:
                continue
            evidence = ' '.join(s['text'] for s in chosen)
            evidence_tokens = {token(w) for w in evidence.split()}
            keywords = c.get('keywords', [])
            if not isinstance(keywords, list):
                keywords = []
            keywords = [str(k)[:80] for k in keywords[:6] if str(k).strip()
                        and all(token(w) in evidence_tokens for w in str(k).split())]
            out.append({**c, 'start': start, 'end': end, 'keywords': keywords,
                        'source_excerpt': evidence, 'selection_source': 'ollama_local'})
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _fallback(segments, duration, cfg):
    raw = []
    target = min(cfg.max_clip_s, max(cfg.min_clip_s, 35.))
    for i, first in enumerate(segments):
        choices = [s for s in segments[i:] if cfg.min_clip_s <= s['end'] - first['start'] <= cfg.max_clip_s]
        if not choices:
            continue
        last = min(choices, key=lambda s: abs(s['end'] - first['start'] - target))
        chosen = [s for s in segments[i:] if s['id'] <= last['id']]
        text = ' '.join(s['text'] for s in chosen)
        terms = [w for w in text.split() if token(w) not in STOP]
        raw.append({'start': first['start'], 'end': last['end'],
                    'title': ' '.join(first['text'].split()[:9]), 'hook': '',
                    'reason': 'Pilihan berbasis segmen transkrip; tinjau isi karena analisis Ollama tidak tersedia.',
                    'score': 40, 'keywords': terms[:4], 'selection_source': 'heuristic', 'source_excerpt': text})
    return _clean(raw, duration, cfg)


def score(transcript, cfg):
    words = valid_words(transcript.get('words', []))
    if not words:
        return []
    duration = float(transcript.get('duration', 0))
    duration = max(duration if math.isfinite(duration) else 0., words[-1]['end'])
    segments = segments_from_words(words)
    candidates, errors = [], []
    try:
        for chunk in _chunks(segments):
            try:
                candidates.extend(_ground(editorial.candidates(chunk, cfg), chunk, cfg))
            except (RuntimeError, ValueError) as exc:
                errors.append(str(exc))
                break
    finally:
        editorial.release(cfg)
    selected = _clean(candidates, duration, cfg)
    if not selected:
        selected = _fallback(segments, duration, cfg)
        errors.append('Fallback berbasis segmen digunakan. Preview sebelum publikasi.')
    if errors:
        for c in selected:
            c['warnings'] = errors
    return selected
