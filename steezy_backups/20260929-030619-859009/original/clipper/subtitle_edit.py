"""Conservative display-only cleanup. Source words and audio are never rewritten."""
import re

HESITATIONS = {'eee', 'eeee', 'emm', 'emmm', 'hmm', 'hmmm', 'uh', 'umm'}
REPEAT_FILLERS = {'nah', 'gitu', 'eee', 'emm', 'hmm'}


def clean(words, mode='safe'):
    result, changes, warnings = [], [], []
    for original in words:
        word = dict(original)
        text = str(word['word']).strip()
        norm = re.sub(r'[^\w]', '', text.lower())
        previous = result[-1] if result else None
        contiguous = previous and word.get('part') == previous.get('part') and word['start'] - previous['end'] <= .35
        repeated = contiguous and norm in REPEAT_FILLERS and re.sub(r'[^\w]', '', previous['word'].lower()) == norm
        if mode == 'safe' and (norm in HESITATIONS or repeated):
            changes.append({'word_id': word.get('word_id'), 'text': text, 'start': word['start'],
                            'end': word['end'], 'reason': 'hesitation' if norm in HESITATIONS else 'repeated_filler'})
            continue
        # Do not infer lost digits, change a spoken number, or remove negation/qualifiers.
        if (re.match(r'^[.,]\d', text) or re.search(r'\d', text) and word['end']-word['start'] > 3.5):
            warnings.append({'word_id': word.get('word_id'), 'text': text, 'start': word['start'],
                             'reason': 'Periksa angka/waktu ucapan pada sumber.'})
        result.append(word)
    # An all-hesitation excerpt is still inspectable and never becomes an empty render.
    if not result:
        return [dict(w) for w in words], [], warnings
    return result, changes, warnings
