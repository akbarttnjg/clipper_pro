"""Auditable, context-gated spelling correction; raw ASR is always retained.

No language model is permitted to invent numeric values or rewrite sentences.
Uncertain spans can be listened to again, with source IDs retained across merges.
"""
import copy
import difflib
import re

VERSION = '4.0.3'
PROTECTED = set('tidak bukan jangan belum tanpa kurang lebih kecuali mungkin bisa harus wajib boleh pasti tak nggak gak enggak not no never may must can cannot'.split())
FINANCE = set('trading trader forex emas gold pair pasar chart candlestick candle lot pip pips broker scalping timeframe bullish bearish support resistance xauusd eurusd gbpusd'.split())
BUILTINS = {
    'XAUUSD': ('hausd', 'xausd', 'xauusd', 'xau usd', 'xauus d'),
    'EURUSD': ('eurusd', 'eur usd'),
    'GBPUSD': ('gbpusd', 'gbp usd'),
    'USDJPY': ('usdjpy', 'usd jpy'),
    'timeframe': ('timeframe', 'time frame'),
    'stop loss': ('stoploss',),
    'bearish': ('beris', 'bearis', 'bearish'),
    'bullish': ('bulis', 'bullis', 'bullish'),
    'zona': ('jona',),
    'supply': ('suplai',),
    'demand': ('demen',),
    'drop base drop': ('drop based drop', 'drop bes drop'),
    'rally base rally': ('rally based rally', 'reli bes reli'),
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
            from .stage3 import fact_review
            if fact_review(alias,canonical)['requires_confirmation']:
                raise ValueError('Kamus tidak boleh mengubah angka, satuan, urutan negasi atau syarat.')
            entries.append((canonical, tuple(norm(x) for x in alias.split()), False))
    meanings={}
    for canonical,alias,_ in entries:
        if alias in meanings and meanings[alias]!=canonical:raise ValueError('Alias kamus ambigu: satu pengucapan menunjuk dua istilah berbeda.')
        meanings[alias]=canonical
    return entries


def prompt(cfg):
    from .correction_memory import glossary
    terms = list(dict.fromkeys(e[0] for e in parse_glossary(cfg.glossary) + parse_glossary(glossary(cfg))))
    if cfg.audience == 'finance':
        terms += list(BUILTINS)
    # Vocabulary hint, not an instruction to manufacture these words in silence.
    return ', '.join(terms)[:900]


def glossary_entries(cfg):
    from .correction_memory import glossary
    entries=parse_glossary(glossary(cfg))+parse_glossary(cfg.glossary)
    meanings={}
    for canonical,alias,_ in entries:
        if alias in meanings and meanings[alias]!=canonical:raise ValueError('Alias ambigu antara kamus proyek dan memori istilah: '+' '.join(alias))
        meanings[alias]=canonical
    return entries


def correct_words(words, cfg):
    if not cfg.transcript_correction:
        return copy.deepcopy(words), []
    from .correction_memory import glossary
    # Explicit project approvals take priority over the built-in vocabulary.
    entries = glossary_entries(cfg)
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
            new.pop('aligned_words',None);new.pop('alignment_method',None)
            new.update(raw_word=original.get('raw_word', text), correction='context_glossary' if built_in else 'user_glossary',
                       source_word_ids=source_ids(span))
            changes.append({'word_id': original.get('word_id'), 'start': original['start'], 'end': span[-1]['end'],
                            'before': text, 'after': replacement, 'reason': new['correction']})
        result.append(new); i += count
    return result, changes


def refine(transcript, cfg):
    result = copy.deepcopy(transcript)
    raw = copy.deepcopy(transcript.get('raw_words', transcript['words']))
    result['raw_words'] = raw
    # Keep second-pass ASR fixes if already present; glossary can be reapplied safely.
    base = copy.deepcopy(transcript.get('heard_words', raw))
    manual=[w for w in transcript['words'] if w.get('manually_edited')]
    # Explicit overrides survive a fresh glossary pass, including merged spans.
    for override in manual:
        ids=set(source_ids([override]))
        indices=[i for i,w in enumerate(base) if set(source_ids([w])) & ids]
        if indices and indices==list(range(indices[0],indices[-1]+1)):
            covered=set(source_ids(base[indices[0]:indices[-1]+1]))
            if covered==ids:
                base[indices[0]:indices[-1]+1]=[copy.deepcopy(override)]
    result['words'], changes = correct_words(base, cfg)
    # Timing survives a glossary pass only when both text and source lineage match.
    aligned={(tuple(source_ids([w])),w['word']):w for w in transcript['words'] if w.get('aligned_words')}
    for word in result['words']:
        prior=aligned.get((tuple(source_ids([word])),word['word']))
        if prior:
            for key in ('aligned_words','alignment_method','alignment_provenance'):word[key]=copy.deepcopy(prior.get(key))
    result['text'] = ' '.join(w['word'] for w in result['words'])
    from .boundaries import segments_from_words
    result['segments'] = segments_from_words(result['words'])
    uncertain = review_queue(result['words'], cfg, transcript.get('ocr_suggestions', []))
    result['correction_report'] = {'version': VERSION, 'changes': transcript.get('asr_corrections', []) + changes,
                                    'review': uncertain, 'second_pass': transcript.get('second_pass', {})}
    return result


def source_ids(words):
    return list(dict.fromkeys(i for w in words for i in w.get('source_word_ids', [w.get('word_id')]) if i is not None))


def suspect_reason(word):
    if word.get('manually_edited'):
        return ''
    token = norm(word['word'])
    if word.get('probability', 1) < .5:
        return 'Keyakinan audio rendah'
    aliases = {norm(a) for canonical, variants in BUILTINS.items() for a in variants if norm(a) != norm(canonical)}
    if token in aliases:
        return 'Ejaan mirip istilah khusus'
    if len(token) > 22 or re.search(r'([a-z])\1{3,}', token):
        return 'Bentuk kata tidak lazim'
    if word['end'] - word['start'] > 2.8:
        return 'Durasi kata tidak lazim'
    return ''


def review_queue(words, cfg, ocr=()):
    rows = []
    for w in words:
        reason = suspect_reason(w)
        if reason and not w.get('correction'):
            token = norm(w['word'])
            suggestions = [k for k, variants in BUILTINS.items() if any(norm(a) == token for a in variants) and norm(k) != token]
            rows.append({'word_id': w.get('word_id'), 'source_word_ids': source_ids([w]),
                         'text': w['word'], 'start': w['start'], 'end': w['end'],
                         'reason': reason, 'suggestions': suggestions, 'evidence': 'audio',
                         'listen_start': max(0, w['start']-2), 'listen_end': w['end']+2})
    # OCR is advisory even when confident; it cannot hear the speaker.
    active = {i for w in words if not w.get('manually_edited') for i in source_ids([w])}
    rows += [dict(r) for r in ocr if r.get('word_id') in active]
    return sorted(rows, key=lambda r: (r['start'], str(r.get('word_id'))))


def recheck_ranges(words, duration, limit=12):
    if limit <= 0:
        return []
    suspects = sorted((w for w in words if suspect_reason(w) and len(norm(w['word'])) > 2
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
    """Align 1–4 token spans. Merge IDs without inventing word timestamps.

    The second pass must cover the same audible interval and improve confidence.
    Numeric/negation tokens and manual corrections are never changed here.
    """
    result, changes, replacements = copy.deepcopy(words), [], {}
    if not heard:
        return result, changes
    indices = [i for i, w in enumerate(words) if w['end'] > heard[0]['start']-.2 and w['start'] < heard[-1]['end']+.2]
    original = [words[i] for i in indices]
    matcher = difflib.SequenceMatcher(None, [norm(w['word']) for w in original], [norm(w['word']) for w in heard], autojunk=False)
    for op, a, b, c, d in matcher.get_opcodes():
        if op != 'replace' or not (1 <= b-a <= 4 and 1 <= d-c <= 4):
            continue
        old_span, new_span = original[a:b], heard[c:d]
        old, new = old_span[0], new_span[0]
        if any(w.get('manually_edited') for w in old_span):
            continue
        old_p = sum(w.get('probability', 1) for w in old_span) / len(old_span)
        new_p = min(w.get('probability', 0) for w in new_span)
        if old_p >= .75 or new_p < max(.80, old_p+.20):
            continue
        before = ' '.join(w['word'] for w in old_span)
        after = ' '.join(w['word'].strip('.,!?;:') for w in new_span)
        from .stage3 import fact_signature
        if fact_signature(before) or fact_signature(after):
            continue
        if (difflib.SequenceMatcher(None, norm(before), norm(after)).ratio() < .75
                or abs(old['start']-new['start']) > .45
                or abs(old_span[-1]['end']-new_span[-1]['end']) > .55
                or any(y['start']-x['end'] > .6 for x,y in zip(old_span,old_span[1:]))):
            continue
        suffix = re.search(r'[.,!?;:]+$', old_span[-1]['word'])
        replacement = after + (suffix.group() if suffix else '')
        ids = source_ids(old_span)
        replacements[indices[a]] = (len(old_span), {**old, 'end': old_span[-1]['end'],
            'word': replacement, 'raw_word': before, 'correction': 'audio_recheck',
            'source_word_ids': ids, 'probability': new_p, 'aligned_words':None, 'alignment_method':None})
        changes.append({'word_id': old.get('word_id'), 'source_word_ids': ids,
                        'start': old['start'], 'end': old_span[-1]['end'],
                        'before': before, 'after': replacement, 'reason': 'audio_recheck',
                        'evidence': {'old_probability': old_p, 'new_probability': new_p,
                                     'heard_start': new['start'], 'heard_end': new_span[-1]['end']}})
    for index in sorted(replacements, reverse=True):
        count, word = replacements[index]
        result[index:index+count] = [word]
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
