"""Auditable, context-gated spelling correction; raw ASR is always retained.

No language model is permitted to invent numeric values or rewrite sentences.
Uncertain words can be listened to again by Whisper, then aligned one-to-one.
"""
import copy
import difflib
import re

VERSION = '3.2'
PROTECTED = set('tidak bukan jangan belum tanpa kurang lebih kecuali mungkin bisa harus wajib boleh pasti tak nggak gak enggak not no never may must can cannot'.split())
FINANCE = set('trading trader forex emas gold pair pasar chart candlestick candle lot pip pips broker scalping timeframe bullish bearish support resistance xauusd eurusd gbpusd'.split())
BUILTINS = {
    'XAUUSD': ('hausd', 'xausd', 'xauusd', 'xau usd', 'xauus d'),
    'EURUSD': ('eurusd', 'eur usd'),
    'GBPUSD': ('gbpusd', 'gbp usd'),
    'USDJPY': ('usdjpy', 'usd jpy'),
    'timeframe': ('timeframe', 'time frame'),
    'stop loss': ('stoploss',),
}


def norm(text):
    return re.sub(r'[^\w]', '', str(text)).casefold()


def parse_glossary(value):
    if len(value) > 6000:
        raise ValueError('Kamus maksimal 6.000 karakter.')
    entries = []
    lines = [s.strip() for s in value.splitlines() if s.strip()]
    if len(lines) > 80:
        raise ValueError('Kamus maksimal 80 istilah.')
    for line in lines:
        canonical, _, aliases = line.partition('=')
        canonical = canonical.strip()
        if not canonical or len(canonical) > 60 or len(canonical.split()) > 4:
            raise ValueError('Setiap istilah kamus harus 1–4 kata, maksimal 60 karakter.')
        variants = [canonical] + [s.strip() for s in aliases.split('|') if s.strip()]
        for alias in variants:
            if len(alias) > 60 or not 1 <= len(alias.split()) <= 4:
                raise ValueError('Alias kamus harus 1–4 kata. Pisahkan alias dengan |.')
            a, b = re.findall(r'\d+(?:[.,]\d+)*', alias), re.findall(r'\d+(?:[.,]\d+)*', canonical)
            if a != b or {norm(x) for x in alias.split()} & PROTECTED != {norm(x) for x in canonical.split()} & PROTECTED:
                raise ValueError('Kamus tidak boleh mengubah angka atau kata penyangkalan/kepastian.')
            entries.append((canonical, tuple(norm(x) for x in alias.split()), False))
    return entries


def prompt(cfg):
    terms = list(dict.fromkeys(e[0] for e in parse_glossary(cfg.glossary)))
    if cfg.audience == 'finance':
        terms += list(BUILTINS)
    # Vocabulary hint, not an instruction to manufacture these words in silence.
    return ', '.join(terms)[:900]


def correct_words(words, cfg):
    if not cfg.transcript_correction:
        return copy.deepcopy(words), []
    entries = parse_glossary(cfg.glossary)
    entries += [(canonical, tuple(norm(x) for x in alias.split()), True)
                for canonical, aliases in BUILTINS.items() for alias in aliases]
    entries.sort(key=lambda row: len(row[1]), reverse=True)
    tokens = [norm(w['word']) for w in words]
    result, changes = [], []
    i = 0
    while i < len(words):
        original = words[i]
        chosen = None
        # Manual word edits are authoritative.
        for canonical, alias, built_in in entries:
            count = len(alias)
            span = words[i:i+count]
            if tokens[i:i+count] != list(alias) or len(span) != count or any(w.get('manually_edited') for w in span):
                continue
            if any(b['start']-a['end'] > .6 or b.get('part') != a.get('part') for a, b in zip(span, span[1:])):
                continue
            if built_in and norm(canonical) != ''.join(alias):
                context = set(tokens[max(0, i-15):i+count+15]) & FINANCE
                if cfg.audience != 'finance' and len(context) < 2:
                    continue
            chosen = (canonical, count, built_in)
            break
        if chosen is None:
            result.append(dict(original)); i += 1; continue
        canonical, count, built_in = chosen
        span = words[i:i+count]
        text = ' '.join(w['word'] for w in span)
        # Preserve sentence marks for boundary detection. Display cleanup is later.
        suffix = re.search(r'[.,!?;:]+$', span[-1]['word'])
        replacement = canonical + (suffix.group() if suffix else '')
        new = {**original, 'word': replacement, 'end': span[-1]['end']}
        if text != replacement:
            new.update(raw_word=original.get('raw_word', text), correction='context_glossary' if built_in else 'user_glossary',
                       source_word_ids=[w.get('word_id') for w in span])
            changes.append({'word_id': original.get('word_id'), 'start': original['start'], 'end': span[-1]['end'],
                            'before': text, 'after': replacement, 'reason': new['correction']})
        result.append(new); i += count
    return result, changes


def refine(transcript, cfg):
    result = copy.deepcopy(transcript)
    raw = copy.deepcopy(transcript.get('raw_words', transcript['words']))
    result['raw_words'] = raw
    # Keep second-pass ASR fixes if already present; glossary can be reapplied safely.
    base = transcript.get('heard_words', raw)
    result['words'], changes = correct_words(base, cfg)
    result['text'] = ' '.join(w['word'] for w in result['words'])
    from .boundaries import segments_from_words
    result['segments'] = segments_from_words(result['words'])
    uncertain = [{'word_id': w.get('word_id'), 'text': w['word'], 'start': w['start'],
                  'reason': 'Keyakinan transkripsi rendah; dengarkan kata ini.'}
                 for w in result['words'] if w.get('probability', 1) < .5 and not w.get('correction')]
    result['correction_report'] = {'version': VERSION, 'changes': transcript.get('asr_corrections', []) + changes,
                                    'review': uncertain, 'second_pass': transcript.get('second_pass', {})}
    return result


def recheck_ranges(words, duration, limit=12):
    if limit <= 0:
        return []
    suspects = sorted((w for w in words if w.get('probability', 1) < .5 and len(norm(w['word'])) > 2
                       and not re.search(r'\d', w['word'])), key=lambda w: w.get('probability', 1))
    ranges = []
    for word in suspects:
        a, b = max(0, word['start']-3), min(duration, word['end']+3)
        if b-a < 1 or any(a < y and b > x for x, y in ranges):
            continue
        ranges.append((a, b))
        if len(ranges) >= limit:
            break
    return sorted(ranges)


def merge_recheck(words, heard):
    """Accept only a stronger aligned spelling alternative, never insert/delete."""
    result = copy.deepcopy(words)
    changes = []
    if not heard:
        return result, changes
    indices = [i for i, w in enumerate(words) if w['end'] > heard[0]['start']-.2 and w['start'] < heard[-1]['end']+.2]
    original = [words[i] for i in indices]
    matcher = difflib.SequenceMatcher(None, [norm(w['word']) for w in original], [norm(w['word']) for w in heard], autojunk=False)
    for op, a, b, c, d in matcher.get_opcodes():
        if op != 'replace' or b-a != 1 or d-c != 1:
            continue
        old, new = original[a], heard[c]
        before, after = norm(old['word']), norm(new['word'])
        if old.get('probability', 1) >= .6 or new.get('probability', 0) < max(.80, old.get('probability', 0)+.25):
            continue
        if re.search(r'\d', before+after) or before in PROTECTED or after in PROTECTED:
            continue
        if difflib.SequenceMatcher(None, before, after).ratio() < .5 or abs(old['start']-new['start']) > .45:
            continue
        suffix = re.search(r'[.,!?;:]+$', old['word'])
        replacement = new['word'].strip('.,!?;:') + (suffix.group() if suffix else '')
        result[indices[a]] = {**old, 'word': replacement, 'raw_word': old['word'], 'correction': 'audio_recheck',
                              'probability': new['probability']}
        changes.append({'word_id': old.get('word_id'), 'start': old['start'], 'end': old['end'],
                        'before': old['word'], 'after': replacement, 'reason': 'audio_recheck'})
    return result, changes


def refresh_saved(transcript, edits, cfg, clip_settings=None):
    """Apply the glossary to saved ASR without retranscribing or erasing edits."""
    from dataclasses import replace
    refined=refine(transcript,cfg)
    refined['correction_report']['source']='saved_transcript_glossary'
    old={(w['start'],w['end']):w['word'] for w in transcript['words']}
    updated={}
    for index,words in edits.items():
        marked=copy.deepcopy(words)
        for w in marked:
            if w['word']!=old.get((w['start'],w['end']),w['word']):
                w['manually_edited']=True
        local_cfg=replace(cfg,**(clip_settings or {}).get(str(index),{}))
        updated[index]=correct_words(marked,local_cfg)[0]
    return refined,updated
