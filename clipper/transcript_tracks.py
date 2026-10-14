"""M2 source-clock tracks. Imported cues never masquerade as measured words."""
import copy
import hashlib
import json
import math
import re

VERSION = '4.0.15.1'
MAX_BYTES = 10 * 1024 * 1024
LANGUAGES = {'ind': 'id', 'eng': 'en', 'zho': 'zh', 'jpn': 'ja', 'kor': 'ko', 'indonesian':'id', 'english':'en', 'chinese':'zh', 'japanese':'ja', 'korean':'ko', 'arabic':'ar', 'spanish':'es', 'french':'fr', 'german':'de', 'portuguese':'pt', 'hindi':'hi', 'russian':'ru'}


def effective_units(words, duration):
    """Project a source-clock view without rewriting the immutable ASR take."""
    from .stage3 import validate_alignment
    result = copy.deepcopy(words)
    for word in result:
        if not isinstance(word, dict):raise ValueError('Unit transkrip harus berupa objek')
        if word.get('aligned_words'):
            aligned = validate_alignment(word['word'], word['aligned_words'], 0, duration,
                method=word.get('alignment_method', 'manual'))
            word['start'] = aligned[0]['start']
            word['end'] = aligned[-1]['end']
            word['aligned_words'] = aligned
    return result


def number(value, label='waktu'):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + ' harus angka hingga')
    return float(value)


def language(value):
    if not isinstance(value, str): raise ValueError('Kode bahasa tidak valid')
    value = LANGUAGES.get(value.lower(), value.lower())
    if not re.fullmatch(r'[a-z]{2,3}(?:-[a-z]{2})?', value):
        raise ValueError('Kode bahasa tidak valid')
    return value


def identity(value):
    if type(value) not in (int, str) or (isinstance(value, str) and not 1 <= len(value) <= 250):
        raise ValueError('ID kata/cue tidak valid')
    return value


def timestamp(text):
    m = re.fullmatch(r'(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{3})', text.strip())
    if not m: raise ValueError('Timestamp SRT/VTT tidak valid: ' + text[:60])
    h, mi, sec, ms = m.groups()
    if int(mi) >= 60 or int(sec) >= 60: raise ValueError('Menit/detik di luar batas')
    return int(h or 0) * 3600 + int(mi) * 60 + int(sec) + int(ms) / 1000


def stamp(value, vtt=False):
    n = round(value * 1000); h, n = divmod(n, 3600000); m, n = divmod(n, 60000); s, n = divmod(n, 1000)
    return f'{h:02d}:{m:02d}:{s:02d}{"." if vtt else ","}{n:03d}'


def parse(text, fmt, source_id, duration, *, source_language='und', offset=0, provider='user_import'):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES: raise ValueError('Subtitle maksimum 10 MB')
    duration = number(duration, 'durasi'); offset = number(offset, 'offset')
    if duration <= 0: raise ValueError('Durasi sumber tidak valid')
    fmt = str(fmt).lower().lstrip('.'); lang = language(source_language); cues = []; metadata = {}
    if fmt == 'json':
        data = json.loads(text)
        if not isinstance(data, dict) or data.get('schema_version', 1) != 1: raise ValueError('Schema track harus 1')
        if data.get('source_id') not in (None, source_id): raise ValueError('Identitas sumber track berbeda')
        if data.get('timebase', 'source_seconds') != 'source_seconds': raise ValueError('Track harus menggunakan source_seconds')
        lang = language(data.get('language', lang)); metadata = copy.deepcopy(data.get('metadata', {}))
        words = copy.deepcopy(data.get('words'))
        if not isinstance(words, list) or not words: raise ValueError('JSON harus memiliki words')
        cues = copy.deepcopy(data.get('cues', []))
        if not isinstance(cues, list): raise ValueError('JSON cues harus berupa daftar')
        for w in words:
            if not isinstance(w, dict): raise ValueError('Baris kata tidak valid')
            w.setdefault('word', w.get('text')); w.setdefault('word_id', w.get('id'))
            w.setdefault('probability', None); w.setdefault('timing_status', 'imported_unmeasured')
    elif fmt in ('srt', 'vtt'):
        words = []
        blocks = re.split(r'\n\s*\n', text.lstrip('\ufeff').replace('\r\n', '\n').strip())
        for block in blocks:
            lines = block.splitlines()
            if not lines or lines[0].startswith(('WEBVTT', 'NOTE', 'STYLE', 'REGION')): continue
            ti = next((i for i, line in enumerate(lines) if '-->' in line), None)
            if ti is None: raise ValueError('Cue tidak memiliki timestamp')
            left, right = lines[ti].split('-->', 1)
            start = timestamp(left); end = timestamp(right.strip().split()[0])
            raw = '\n'.join(lines[ti+1:]); speaker = None
            voice = re.search(r'<v(?:\.\w+)*\s+([^>]+)>', raw)
            if voice: speaker = voice.group(1).strip()
            body = re.sub(r'<[^>]*>', '', raw).strip()
            named = re.match(r'^\[([^\]]+)\]\s*', body)
            if named: speaker = named.group(1); body = body[named.end():]
            if not body: raise ValueError('Teks cue kosong')
            cid = lines[0].strip() if ti else str(len(cues) + 1)
            cid = cid or str(len(cues)+1)
            wid = 'cue:' + cid
            cues.append({'cue_id': cid, 'start': start, 'end': end, 'text': body, 'speaker_id': speaker, 'origin_word_ids': [wid]})
            words.append({'word_id': wid, 'word': body, 'start': start, 'end': end, 'probability': None,
                'speaker_id': speaker, 'timing_status': 'cue_unaligned', 'cue_id': cid})
    else: raise ValueError('Pilih SRT, VTT, atau JSON')
    if not words or len(words) > 250000: raise ValueError('Jumlah kata/cue tidak valid')
    seen = set()
    for w in words:
        wid = identity(w.get('word_id'))
        if wid in seen: raise ValueError('ID kata/cue harus unik')
        seen.add(wid)
        if not isinstance(w.get('word'), str) or not w['word'].strip() or len(w['word']) > 10000: raise ValueError('Teks kata tidak valid')
        w['start'] = number(w.get('start')) + offset; w['end'] = number(w.get('end')) + offset
        if not 0 <= w['start'] < w['end'] <= duration + 0.00001: raise ValueError('Timestamp di luar durasi sumber')
        p = w.get('probability')
        if p is not None and not 0 <= number(p, 'confidence') <= 1: raise ValueError('Confidence harus 0–1 atau null')
        w['probability'] = p; w.setdefault('confidence_kind', 'imported_probability' if p is not None else 'not_measured')
        w.setdefault('source_word_ids', [wid]); w.setdefault('speaker_id', None)
        if not isinstance(w['source_word_ids'],list) or not w['source_word_ids'] or len(w['source_word_ids'])>250000:raise ValueError('Lineage kata tidak valid')
        for origin in w['source_word_ids']:identity(origin)
        if len(set(w['source_word_ids']))!=len(w['source_word_ids']):raise ValueError('Lineage kata harus unik')
        if w.get('aligned_words'):
            from .stage3 import validate_alignment
            aligned=copy.deepcopy(w['aligned_words'])
            if not isinstance(aligned,list) or any(not isinstance(part,dict) for part in aligned):raise ValueError('Alignment JSON tidak valid')
            for part in aligned:
                part['start']=number(part.get('start'))+offset;part['end']=number(part.get('end'))+offset
            w['aligned_words']=validate_alignment(w['word'],aligned,0,duration,method=w.get('alignment_method','manual'))
        speaker=w.get('speaker_id')
        if speaker is not None and (not isinstance(speaker,str) or not 1<=len(speaker)<=100 or '\n' in speaker):raise ValueError('Speaker track tidak valid')
    if any(words[i]['start'] < words[i-1]['start'] for i in range(1, len(words))): raise ValueError('Track tidak berurutan')
    if not cues: cues = cues_from_words(words)
    else:
        cue_seen = set()
        for c in cues:
            if not isinstance(c, dict): raise ValueError('Baris cue tidak valid')
            cid = identity(c.get('cue_id'))
            if cid in cue_seen: raise ValueError('ID cue harus unik')
            cue_seen.add(cid); c['start'] = number(c.get('start')) + offset; c['end'] = number(c.get('end')) + offset
            if not 0 <= c['start'] < c['end'] <= duration + .00001: raise ValueError('Cue di luar durasi sumber')
            if not isinstance(c.get('text'), str) or not c['text'].strip(): raise ValueError('Teks cue kosong')
        validate_cues(words, cues)
    overlaps = any(cues[i]['start'] < cues[i-1]['end'] for i in range(1, len(cues)))
    return {'words': words, 'raw_words': copy.deepcopy(words), 'heard_words': copy.deepcopy(words), 'cues': cues,
        'segments': copy.deepcopy(cues), 'duration': duration, 'language': lang, 'timebase': 'source_seconds',
        'source_id': source_id, 'text': ' '.join(w['word'] for w in words), 'metadata': metadata,
        'warnings': ['overlapping_cues_need_review'] if overlaps else [],
        'provenance': {'provider': provider, 'format': fmt, 'offset_seconds': offset, 'input_sha256': hashlib.sha256(text.encode()).hexdigest()},
        'runtime_receipt': {'provider': provider, 'inference_performed': False, 'actual_device': None, 'actual_model': None}}


def review_import(track, *, expected_language, language_checked=False, source_time_checked=False, overlaps_checked=False):
    blockers = []
    declared = track['language']; expected = language(expected_language)
    if declared == 'und' or expected == 'und': blockers.append('Nyatakan bahasa sumber sebelum memakai subtitle')
    elif declared != expected: blockers.append('Bahasa subtitle berbeda dari bahasa sumber')
    if language_checked is not True: blockers.append('Periksa bahasa subtitle dengan mendengarkan sumber')
    if source_time_checked is not True: blockers.append('Periksa offset pada awal, tengah, dan akhir sumber')
    if track.get('warnings') and overlaps_checked is not True: blockers.append('Tinjau cue yang bertumpang tindih')
    return {'ready': not blockers, 'blockers': blockers, 'declared_language': declared, 'expected_language': expected,
        'cue_count': len(track['cues']), 'word_count': len(track['words']), 'timebase': 'source_seconds',
        'word_timing_measured': False, 'confidence_measured': False}


def critical_review(words, glossary=''):
    rows = []; terms = [s.strip().casefold() for s in re.split(r'[,;\n]', glossary) if s.strip()]
    for w in words:
        text = w['word']; reasons = []; p = w.get('probability')
        if p is None: reasons.append('confidence_not_measured')
        elif p < .75: reasons.append('low_asr_confidence')
        if re.search(r'\d', text): reasons.append('number')
        if re.search(r'\b(tidak|bukan|jangan|belum|tanpa|never|not|no)\b', text, re.I): reasons.append('negation')
        if re.search(r'\b(persen|kg|km|usd|idr|rupiah|dollar|juta|miliar|percent)\b|[%$€]', text, re.I): reasons.append('unit')
        if any(t in text.casefold() for t in terms): reasons.append('domain_term')
        if re.search(r'\b[A-ZÀ-Ö][\w-]+', text): reasons.append('candidate_name')
        if w.get('timing_status') in ('cue_unaligned', 'weak_alignment', 'imported_unmeasured', 'partial_word_needs_review'): reasons.append('timing_needs_review')
        if reasons: rows.append({'word_id': w['word_id'], 'word': text, 'start': w['start'], 'end': w['end'],
            'probability': p, 'reasons': reasons, 'status': 'needs_listening'})
    return rows


def cues_from_words(words):
    groups = []
    for w in words:
        if (not groups or w.get('speaker_id') != groups[-1][-1].get('speaker_id') or
                w['start'] - groups[-1][-1]['end'] > .6 or w['end'] - groups[-1][0]['start'] > 5 or
                len(' '.join(x['word'] for x in groups[-1])) + len(w['word']) > 100): groups.append([])
        groups[-1].append(w)
    return [{'cue_id': str(i+1), 'start': g[0]['start'], 'end': max(w['end'] for w in g),
        'text': ' '.join(w['word'] for w in g), 'speaker_id': g[0].get('speaker_id'),
        'origin_word_ids': list(dict.fromkeys(x for w in g for x in w.get('source_word_ids', [w['word_id']])))} for i,g in enumerate(groups)]


def cue_rows(words, cue):
    refs=cue.get('origin_word_ids')
    if not isinstance(refs,list) or not refs:raise ValueError('Cue harus mempunyai origin_word_ids')
    for ref in refs:identity(ref)
    if len(set(refs))!=len(refs):raise ValueError('Lineage cue harus unik')
    refs=set(refs)
    rows=[w for w in words if w['word_id'] in refs or set(w.get('source_word_ids',[w['word_id']]))<=refs]
    linked={i for w in rows for i in [w['word_id'],*w.get('source_word_ids',[w['word_id']])]}
    if not rows or refs-linked:raise ValueError('Lineage cue tidak menunjuk kata efektif yang lengkap')
    return rows


def validate_cues(words, cues):
    """One source track cannot use different facts in its word and cue views."""
    used=set()
    for cue in cues:
        rows=cue_rows(words,cue);ids={w['word_id'] for w in rows}
        if used&ids:raise ValueError('Kata mempunyai cue ganda dalam track yang sama')
        used.update(ids)
        if ' '.join(cue['text'].split())!=' '.join(' '.join(w['word'] for w in rows).split()):
            raise ValueError('Teks cue berbeda dari words yang dirujuk; periksa track JSON')
        if abs(cue['start']-min(w['start'] for w in rows))>.00101 or abs(cue['end']-max(w['end'] for w in rows))>.00101:
            raise ValueError('Waktu cue berbeda dari words yang dirujuk; periksa clock sumber')
        speakers={w.get('speaker_id') for w in rows}
        if len(speakers)!=1 or cue.get('speaker_id')!=next(iter(speakers)):
            raise ValueError('Speaker cue berbeda dari words yang dirujuk')
    if used!={w['word_id'] for w in words}:raise ValueError('Cue belum mencakup seluruh words')


def effective_cues(track):
    """Project current text/time/speakers without rewriting the immutable take.

    Preserve imported cue IDs while their lineage still partitions the words.
    Speaker changes can split a cue, with an explicit parent reference.
    """
    words=track['words'];original=track.get('cues') or []
    if not original:return cues_from_words(words)
    result=[];used=set()
    try:
        for cue in original:
            rows=cue_rows(words,cue);ids={w['word_id'] for w in rows}
            if used&ids:raise ValueError('Cue lineage overlaps')
            used.update(ids);groups=[]
            for row in rows:
                if not groups or groups[-1][-1].get('speaker_id')!=row.get('speaker_id'):groups.append([])
                groups[-1].append(row)
            for index,group in enumerate(groups):
                value={**copy.deepcopy(cue),'start':min(w['start'] for w in group),'end':max(w['end'] for w in group),
                    'text':' '.join(w['word'] for w in group),'speaker_id':group[0].get('speaker_id'),
                    'origin_word_ids':list(dict.fromkeys(i for w in group for i in w.get('source_word_ids',[w['word_id']])))}
                if len(groups)>1:
                    value['parent_cue_id']=cue['cue_id']
                    value['cue_id']='cue-'+hashlib.sha256(json.dumps([cue['cue_id'],index,value['origin_word_ids']],ensure_ascii=False).encode()).hexdigest()[:24]
                result.append(value)
        if used!={w['word_id'] for w in words}:raise ValueError('Cue lineage incomplete')
    except (KeyError,TypeError,ValueError):
        result=cues_from_words(words)
        for cue in result:cue['parent_cue_ids']=[c['cue_id'] for c in original if isinstance(c,dict) and 'cue_id' in c and set(c.get('origin_word_ids',[]))&set(cue['origin_word_ids'])]
    return sorted(result,key=lambda c:c['start'])


def export_track(track, fmt, *, metadata=None):
    cues = effective_cues(track); meta = {**track.get('metadata', {}), **(metadata or {})}
    if fmt == 'json':
        return json.dumps({'schema_version': 1, 'source_id': track['source_id'], 'timebase': 'source_seconds',
            'language': track['language'], 'duration': track['duration'], 'words': track['words'], 'cues': cues,
            'metadata': meta, 'provenance': track.get('provenance'), 'runtime_receipt': track.get('runtime_receipt')}, ensure_ascii=False, indent=2)
    if fmt == 'txt': return '\n'.join(f"[{stamp(c['start'], True)}] {('['+c['speaker_id']+'] ') if c.get('speaker_id') else ''}{c['text']}" for c in cues) + '\n'
    if fmt not in ('srt', 'vtt'): raise ValueError('Format ekspor tidak valid')
    lines = ['WEBVTT\n'] if fmt == 'vtt' else []
    for i,c in enumerate(cues):
        speaker = '[' + c['speaker_id'] + '] ' if c.get('speaker_id') else ''
        lines.append(f"{c.get('cue_id', str(i+1))}\n{stamp(c['start'], fmt=='vtt')} --> {stamp(c['end'], fmt=='vtt')}\n{speaker}{c['text']}\n")
    return '\n'.join(lines)
