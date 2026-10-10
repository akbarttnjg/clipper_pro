"""Glyph envelopes shared by layout, collision checks and the ASS baseline.

New directed plans store ink bounds relative to the libass line centre. Older
plans keep their conservative envelope, so saved exports remain compatible.
"""


def bounds(word, sample=None):
    sample = sample or {}
    scale = sample.get('scale', 1.)
    x = word['x'] + sample.get('dx', 0.)
    y = word['y'] + sample.get('dy', 0.)
    left, top, right, bottom = word.get('ink_box',
        [-word['width']/2, -word['size']*.66, word['width']/2, word['size']*.66])
    padding = word.get('ink_padding', 0.) + sample.get('blur', 0.) * 2
    return [x+left*scale-padding, y+top*scale-padding,
            (right-left)*scale+padding*2, (bottom-top)*scale+padding*2]


def metrics(font, text, width):
    ascent, descent = font.getmetrics()
    left, top, right, bottom = font.getbbox(text, anchor='ls')
    baseline_offset = (ascent-descent)/2
    return [left-width/2, top+baseline_offset, right-width/2, bottom+baseline_offset], baseline_offset, (top, bottom)
