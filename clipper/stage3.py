"""Stage 3 invariants shared by correction, story review and the Studio API.

Original ASR is immutable. Text approval and measured word timing are separate
events; a phrase interval never masquerades as aligned individual words.
"""
import copy
import math
import re
from .contracts import fingerprint

VERSION = '4.0.3'
PROTECTED = set(('tidak bukan jangan belum tanpa kurang lebih kecuali mungkin bisa harus wajib boleh pasti '
                 'tak nggak gak enggak not no never may must can cannot jika kalau apabila selama asalkan '
                 'hanya minimal maksimal setidaknya hingga sampai kecuali unless only').split())
NUMBER_WORDS = set('nol satu dua tiga empat lima enam tujuh delapan sembilan sepuluh sebelas belas puluh ratus ribu juta miliar triliun setengah seperempat'.split())
UNIT_ALIASES = {
    '%': 'persen', 'percent': 'persen', 'persen': 'persen',
    'rp': 'rupiah', 'rupiah': 'rupiah', '$': 'dolar', 'usd': 'dolar', 'dollar': 'dolar', 'dolar': 'dolar',
    'kg': 'kg', 'kilogram': 'kg', 'gram': 'gram', 'gr': 'gram', 'mg': 'mg', 'ton': 'ton',
    'km': 'km', 'kilometer': 'km', 'meter': 'meter', 'm': 'meter', 'cm': 'cm', 'mm': 'mm',
    'ml': 'ml', 'liter': 'liter', 'l': 'liter', 'detik': 'detik', 'menit': 'menit', 'jam': 'jam',
    'hari': 'hari', 'minggu': 'minggu', 'bulan': 'bulan', 'tahun': 'tahun',
    'lot': 'lot', 'pip': 'pip', 'pips': 'pip', 'bps': 'bps', 'hz': 'hz', 'mhz': 'mhz', 'ghz': 'ghz',
    'kb': 'kb', 'mb': 'mb', 'gb': 'gb', 'tb': 'tb', '°c': 'celsius', 'celsius': 'celsius',
}
LEXEMES = re.compile(r'(?<!\w)[+-]?\d+(?:[.,:/]\d+)*|°c|[%$]|[^\W\d_]+', re.I)


def fact_signature(text):
    # ASR sometimes splits decimal punctuation from its following digits.
    text = re.sub(r'(?<=\d)([.,])\s+(?=\d)', r'\1', str(text)).casefold()
    text = re.sub(r'\b(xau|eur|gbp|usd)\s+(usd|jpy)\b', r'\1\2', text)
    facts = []
    for match in LEXEMES.finditer(text):
        value = match.group()
        if re.match(r'[+-]?\d', value): facts.append(('angka', value))
        elif value in NUMBER_WORDS: facts.append(('angka_terucap', value))
        elif value in UNIT_ALIASES: facts.append(('satuan', UNIT_ALIASES[value]))
        elif value in PROTECTED: facts.append(('syarat_negasi', value))
    return facts


def fact_review(before, after):
    a, b = fact_signature(before), fact_signature(after)
    categories = sorted({kind for kind, _ in a + b if [x for x in a if x[0] == kind] != [x for x in b if x[0] == kind]})
    if a != b and not categories: categories = ['urutan_fakta']
    return {'requires_confirmation': a != b, 'categories': categories, 'before_facts': a, 'after_facts': b,
            'message': 'Angka, satuan, negasi atau syarat berubah. Dengarkan sumber dan setujui perubahan fakta secara khusus.' if a != b else ''}


def approval_stamp(take, revision, ids, before, after):
    return fingerprint([VERSION, take, revision, ids, before, after, fact_review(before, after)])


def validate_alignment(text, words, start, end, *, method='manual'):
    if not isinstance(words, list) or not 1 <= len(words) <= 80:
        raise ValueError('Timing harus memuat 1–80 kata.')
    if not math.isfinite(start) or not math.isfinite(end) or start >= end:
        raise ValueError('Rentang audio tidak valid.')
    result = []; previous = start
    for row in words:
        if not isinstance(row, dict) or not isinstance(row.get('word'), str) or not row['word'].strip():
            raise ValueError('Setiap timing harus mempunyai teks kata.')
        a, b = row.get('start'), row.get('end')
        if type(a) not in (int, float) or type(b) not in (int, float) or not all(math.isfinite(x) for x in (a, b)) or not previous <= a < b <= end:
            raise ValueError('Timing kata harus berurutan, tidak tumpang tindih, dan berada dalam rentang audio.')
        if method == 'whisperx' and (type(row.get('score')) not in (int, float) or not math.isfinite(row['score']) or not 0 < row['score'] <= 1):
            raise ValueError('Alignment belum mempunyai bukti skor untuk setiap kata; hasil parsial tidak diterapkan.')
        result.append({k: row[k] for k in ('word', 'start', 'end', 'score') if k in row}); previous = b
    if ' '.join(w['word'].strip() for w in result).split() != str(text).split():
        raise ValueError('Teks timing harus sama dengan frasa yang disetujui. Timing tidak boleh mengubah transkrip.')
    return result


def apply_alignments(words, document, clip_id=None):
    result = copy.deepcopy(words); take = document.get('transcript_id')
    patches = document.get('alignment_overrides', {})
    shared = list(patches.get('shared', {}).values())
    local = list(patches.get('clips', {}).get(clip_id, {}).values())
    for row in result:
        ids = row.get('source_word_ids', [row.get('word_id')])
        for patch in shared + local:
            if patch.get('transcript_id') != take or patch.get('origin_word_ids') != ids or patch.get('text') != row['word']: continue
            try: aligned = validate_alignment(row['word'], patch['words'], patch['audio_start'], patch['audio_end'], method=patch['method'])
            except (KeyError, ValueError, TypeError): continue
            row.update(aligned_words=aligned, alignment_method=patch['method'], alignment_provenance=patch.get('provenance', {}))
    return result


def alignment_window(word, all_words, duration):
    ids=word.get('source_word_ids',[word.get('word_id')])
    index=next((i for i,w in enumerate(all_words) if w.get('source_word_ids',[w.get('word_id')])==ids),None)
    a=max(0.,word['start']-.75);b=min(duration,word['end']+.75)
    if index is not None:
        if index>0:a=max(a,all_words[index-1].get('aligned_words',[all_words[index-1]])[-1]['end'] if all_words[index-1].get('aligned_words') else all_words[index-1]['end'])
        if index+1<len(all_words):b=min(b,all_words[index+1].get('aligned_words',[all_words[index+1]])[0]['start'] if all_words[index+1].get('aligned_words') else all_words[index+1]['start'])
    return a,b


def store_alignment(group,patch):
    for key,old in list(group.items()):
        if old['transcript_id']==patch['transcript_id'] and set(old['origin_word_ids'])&set(patch['origin_word_ids']):del group[key]
    group[fingerprint([patch['transcript_id'],patch['origin_word_ids']])]=patch


def expand_aligned(words):
    result = []
    for row in words:
        aligned = row.get('aligned_words')
        if aligned:
            try: aligned = validate_alignment(row['word'], aligned, aligned[0]['start'], aligned[-1]['end'], method=row.get('alignment_method', 'manual'))
            except (KeyError, ValueError, TypeError): aligned = None
        if aligned:
            for token in aligned:
                result.append({**row, **token, 'aligned_words': None, 'timing_status': 'manual' if row.get('alignment_method') == 'manual' else 'aligned'})
        else:
            status='phrase_span' if len(row['word'].split())>1 or len(row.get('source_word_ids',[]))>1 else 'inherited_span' if row.get('correction') or row.get('manually_edited') else 'asr'
            result.append({**row, 'timing_status':status})
    return result


def rejection_rows(report):
    rows = []
    for index, row in enumerate(report.get('rejections', [])):
        key = 'reject-' + fingerprint([report.get('analysis_revision'), report.get('round'), index, row])[:24]
        rows.append({**row, 'rejection_id': key})
    return rows


def chapter_plan(segments, duration, candidates=(), coverage_ranges=()):
    """Bounded chapters grounded in transcript topics and source pauses."""
    if not segments: return []
    target = max(120., duration / 24); groups = []; current = []
    for segment in segments:
        if current and (segment['start'] - current[-1]['end'] >= 8 or segment['end'] - current[0]['start'] > target):
            groups.append(current); current = []
        current.append(segment)
    if current: groups.append(current)
    # Long recordings can contain many pauses; combine neighbours to bound UI data.
    while len(groups) > 32:
        i = min(range(len(groups)-1), key=lambda n: groups[n+1][-1]['end']-groups[n][0]['start'])
        groups[i:i+2] = [groups[i] + groups[i+1]]
    result = []
    for index, group in enumerate(groups):
        a, b = group[0]['start'], group[-1]['end']
        speech = sum(s['end'] - s['start'] for s in group)
        seen = sum(max(0., min(s['end'], y)-max(s['start'], x)) for s in group for x, y in coverage_ranges)
        clips = [c for c in candidates if a <= (c['start']+c['end'])/2 <= b]
        result.append({'chapter_id': 'chapter-'+str(index+1), 'start': a, 'end': b,
            'label': group[0]['text'][:100], 'segment_count': len(group), 'speech_seconds': round(speech, 2),
            'reviewed_speech_seconds': round(min(speech, seen), 2), 'candidate_count': len(clips),
            'story_kinds': sorted({c.get('story_kind', 'manual') for c in clips}),
            'status': 'reviewed' if speech and seen >= speech-.05 else 'pending'})
    return result
