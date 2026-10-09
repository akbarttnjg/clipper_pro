"""Conservative transcript checks, independent of the LLM's own score.

These checks detect obvious unfinished phrases; they do not prove semantic
completeness. Re-review supplies surrounding context and remains reviewable.
"""
import re
from .typography import token

VERSION = 3


def segments_from_words(words):
    segments, current = [], []
    for i, w in enumerate(words):
        current.append(w)
        gap = words[i + 1]['start'] - w['end'] if i + 1 < len(words) else 10
        sentence = bool(re.search(r'[.!?]["\u201d\u2019]*$', w['word'].strip()))
        if sentence or gap >= .8 or len(current) >= 36 or i == len(words) - 1:
            segments.append({'id': len(segments), 'start': current[0]['start'],
                'end': current[-1]['end'], 'text': ' '.join(x['word'].strip() for x in current),
                'natural_end': sentence or gap >= .8})
            current = []
    return segments


def audit(clip, words, max_duration=120):
    selected = [w for w in words if w['end'] > clip['start'] and w['start'] < clip['end']]
    after = [w for w in words if w['start'] >= clip['end']][:18]
    issues = []
    if not selected:
        return ['Tidak ada ucapan di dalam batas clip.']
    first, last = selected[0], selected[-1]
    text = ' '.join(w['word'].strip() for w in selected)
    tail = text[-220:].lower()
    last_token = token(last['word'])
    if first['start'] < clip['start'] - .025 or last['end'] > clip['end'] + .025:
        issues.append('Batas memotong waktu pengucapan kata.')
    if last_token in {'dari', 'untuk', 'dengan', 'adalah', 'yaitu', 'karena', 'kalau',
                      'yang', 'dan', 'atau', 'bahwa', 'sehingga', 'ketika', 'misalnya'}:
        issues.append('Penutup menggantung pada kata "' + last['word'] + '".')
    elif after and after[0]['start'] - last['end'] < .8 and not re.search(r'[.!?]["\u201d\u2019]*$', last['word']):
        issues.append('Ucapan berlanjut tepat sesudah batas akhir; periksa kalimat penutup.')
    if re.search(r'(yang pertama|yang kedua|yang ketiga|yang keempat|ada [2345] cara)[^.!?]{0,90}$', tail):
        issues.append('Penutup masih berada pada rincian daftar atau janji pembahasan.')
    if re.match(r'^(biar|supaya|karena|ketika|atau|yang)\b', text.lower()):
        issues.append('Pembuka mungkin membutuhkan kalimat sebelumnya.')
    if re.search(r'(?:(?:gue|gua|saya|aku) (?:pengen|ingin|mau) (?:tahu|tau)|pertanyaannya|gimana menurut (?:kalian|kamu))[^.!?]{0,45}[,.?]?$', tail):
        issues.append('Penutup membuka pertanyaan baru; akhiri pada kesimpulan sebelumnya atau sertakan jawabannya.')
    # A pause or an ASR full stop is not proof that a promised numbered list
    # has delivered its remaining items. Keep this a review flag, not a rewrite.
    promises=re.findall(r'\b(?:ada|berikut|terdapat)\s+([2-5]|dua|tiga|empat|lima)\s+(?:cara|langkah|alasan|hal|tips|prinsip)\b',text.lower())
    nums={'dua':2,'tiga':3,'empat':4,'lima':5}
    ordinals={1:r'pertama|kesatu',2:r'kedua',3:r'ketiga',4:r'keempat',5:r'kelima'}
    for promised in promises:
        count=nums.get(promised,int(promised) if promised.isdigit() else 0)
        found=[i for i in range(1,count+1) if re.search(r'\b(?:'+ordinals[i]+r')\b',text.lower())]
        if found and len(found)<count:
            issues.append(f'Pembuka menjanjikan {count} rincian, tetapi penanda urutannya belum lengkap. Periksa jawaban sebelum menyetujui.')
    if clip['end'] - clip['start'] > max_duration + .05:
        issues.append(f'Durasi melewati batas pilihan {max_duration:g} detik.')
    source_tokens = {token(w['word']) for w in words}
    for acronym, expansion in re.findall(r'\b([A-Z]{2,8})\s*\(([^)]+)\)', clip.get('reason', '')):
        if any(token(w) not in source_tokens for w in expansion.split()):
            issues.append(f'Penjabaran {acronym} tidak didukung kata-kata dalam transkrip.')
    return list(dict.fromkeys(issues))


def annotate(clip, words, max_duration=120, verified=False):
    c = dict(clip)
    issues = [] if c.get('selection_source') == 'full' else audit(c, words, max_duration)
    old = c.get('boundary_review', {})
    c['boundary_review'] = {'version': VERSION, 'issues': issues,
        'status': 'needs_review' if issues else ('checked' if verified or old.get('status') == 'checked' else 'candidate')}
    return c


def snap_words(start, end, words, duration):
    """Expand a user/AI range only enough to avoid cutting through a word."""
    for w in words:
        if w['start'] < start < w['end']:
            start = max(0., w['start'] - .06)
        if w['start'] < end < w['end']:
            end = min(duration, w['end'] + .1)
    return start, end
