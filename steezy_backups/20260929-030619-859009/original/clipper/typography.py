"""Measured phrase layouts. Coordinates and times refer to the final output video."""
from __future__ import annotations
import math
import re
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont
from .font_catalog import FONTS, measured, info as font_info

STOP = set("yang dan di ke dari untuk dengan karena kalau bahwa adalah itu ini juga saya kamu kita mereka dia anda sebuah pada dalam akan sudah belum bisa agar atau tapi namun jadi maka sebagai sangat lebih hanya tidak bukan telah the a an and or to of in on for is are it this that you your i we they with as at be do does so just have has my".split())
STOP.update('gue gua lo lu kalian nih sih dong lah kok tuh deh kan gitu begitu nah ya iya eh oh enggak nggak gak mau punya'.split())
STRONG = set('risiko penghasilan pendapatan modal biaya untung rugi investasi strategi disiplin gagal berhasil pertumbuhan uang waktu tujuan alasan bukti solusi masalah rahasia money risk growth cost income profit loss strategy'.split())
STRONG.update('skill keterampilan pendidikan kualitas pelanggan hasil tabungan bisnis keuntungan kebebasan konsisten konsistensi'.split())


def token(text):
    return re.sub(r"[^\w%]", "", str(text).lower())


@lru_cache(maxsize=96)
def font(fonts_dir, size, family='sans'):
    if family in FONTS:
        return measured(fonts_dir, family, size)
    name = {'serif':'DejaVuSerif-Bold.ttf', 'regular':'DejaVuSans.ttf'}.get(family, 'DejaVuSans-Bold.ttf')
    return ImageFont.truetype(str(Path(fonts_dir) / name), size)


def valid_words(words):
    out = []
    for w in words:
        try:
            a, b = float(w["start"]), float(w["end"])
            t = str(w["word"]).strip()
            if t and math.isfinite(a) and math.isfinite(b) and a >= 0 and b > a:
                out.append({**w, "word": t, "start": a, "end": b})
        except (TypeError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda w: w["start"])


def groups(words, cfg):
    result, current = [], []
    for w in display_units(words):
        if current and (len(current) >= cfg.editorial_words
                        or w.get('part') != current[-1].get('part')
                        or w["start"] - current[-1]["end"] > cfg.caption_gap_s
                        or w["end"] - current[0]["start"] > cfg.editorial_phrase_s
                        or (len(current) >= 3 and re.search(r"[.!?;:]$", current[-1]["word"]))):
            result.append(current)
            current = []
        current.append(w)
    if current:
        result.append(current)
    return result


def emphasis_indices(words, keywords=()):
    keys = {token(k) for phrase in keywords for k in str(phrase).split()}
    scores = []
    for i, w in enumerate(words):
        t = token(w["word"])
        if not t or t in STOP or not (t in keys or re.search(r'\d', t) or (not keys and t in STRONG)):
            continue
        score = 10 * (t in keys) + 5 * bool(re.search(r"\d", t)) + min(len(t), 12) / 12
        scores.append((score, i))
    return {i for _, i in sorted(scores, reverse=True)[:1]}


def _wrap(words, sizes, width, cfg, families=None):
    rows, row, occupied = [], [], 0.0
    space = font(cfg.fonts_dir, min(sizes)).getlength(" ")
    for i, (w, size) in enumerate(zip(words, sizes)):
        measured = font(cfg.fonts_dir, size, families[i] if families else 'sans').getlength(w["word"])
        if row and occupied + space + measured > width:
            rows.append(row)
            row, occupied = [], 0.0
        row.append((w, size, measured))
        occupied += measured + (space if len(row) > 1 else 0)
    if row:
        rows.append(row)
    return rows, space


def panel(cfg, position):
    W, H = cfg.target_w, cfg.target_h
    if position in ("left", "right") and W > H:
        return (W * (.045 if position == "left" else .535), H * .25, W * .42, H * .46)
    # Room for platform controls on the right and captions below, especially in 9:16.
    return (W * .07, H * (.65 if H > W else .70), W * .80, H * (.19 if H > W else .23))


def alignment(cfg, position):
    if cfg.caption_align != 'auto':
        return cfg.caption_align
    return position if position in ('left', 'right') else 'center'


def row_left(x, width, row_width, align):
    if align == 'left':
        return x
    if align == 'right':
        return x + width - row_width
    return x + (width - row_width) / 2


def make_plan(words, cfg, keywords=(), position="bottom", anchors=None):
    from .motion import IDS
    if cfg.caption_style in IDS:
        return kinetic_plan(words, cfg, keywords, position, anchors)
    phrases = groups(words, cfg)
    plans = []
    for idx, phrase in enumerate(phrases):
        pos = position
        if anchors:
            # One placement per phrase: never chase the face mid-word.
            mid = (phrase[0]["start"] + phrase[-1]["end"]) / 2
            pos = min(anchors, key=lambda a: abs(a["time"] - mid))["position"]
        if cfg.caption_position != "auto":
            pos = cfg.caption_position
        x, y, width, height = panel(cfg, pos)
        if anchors:
            middle = (phrase[0]['start'] + phrase[-1]['end']) / 2
            anchor = next((a for a in anchors if a.get('start', -1) <= middle < a.get('end', -1)), None)
            if anchor and anchor.get('panel') and cfg.caption_position == 'auto':
                x, y, width, height = anchor['panel']
                pos = anchor['position']
        emph = emphasis_indices(phrase, keywords)
        scale = max(.5, min(1.5, cfg.caption_scale))
        base = int(min(cfg.target_w, cfg.target_h) * (.067 if pos in ('left', 'right') else .066) * scale)
        families = [cfg.font_accent if i in emph and cfg.accent_font else cfg.font_main for i in range(len(phrase))]
        # Measure at the largest animation scale, so the pop stays inside its panel.
        for fs in range(max(18, base), 5, -1):
            sizes = [round(fs * (1.20 if i in emph and cfg.caption_style == "editorial" else 1)) for i in range(len(phrase))]
            rows, space = _wrap(phrase, sizes, width / 1.035, cfg, families)
            total_h = sum(max(v[1] for v in row) * 1.42 for row in rows)
            if len(rows) <= 2 and total_h <= height and all(v[2] <= width / 1.035 for row in rows for v in row):
                break
        if total_h > height or any(v[2] > width / 1.035 for row in rows for v in row):
            raise ValueError("Teks terlalu panjang untuk area subtitle. Pecah kata atau perbaiki transkrip.")
        start = phrase[0]["start"]
        next_start = phrases[idx + 1][0]["start"] if idx + 1 < len(phrases) else phrase[-1]["end"]
        end = max(start + .02, min(phrase[-1]["end"] + .16, next_start))
        # Bottom-locked composition: one-line and two-line phrases share the last baseline.
        cy = y + height * .88 - total_h
        placed = []
        flat = 0
        for row in rows:
            row_w = sum(v[2] for v in row) + space * (len(row) - 1)
            rh = max(v[1] for v in row) * 1.42
            baseline = cy + rh * .78
            cx = row_left(x, width, row_w, alignment(cfg, pos))
            for w, size, measured in row:
                placed.append({"text": w["word"], "word_id": w.get("word_id"),
                               "start": w["start"], "end": w["end"],
                               "x": round(cx + measured / 2, 2), "y": round(baseline - size * .36, 2),
                               "baseline": round(baseline, 2), **font_info(families[flat]),
                               "ass_size": sum(font(cfg.fonts_dir, size, families[flat]).getmetrics()),
                               "size": size, "width": measured, "emphasis": flat in emph})
                cx += measured + space
                flat += 1
            cy += rh
        plans.append({"start": start, "end": end, "position": pos,
                      "panel": [x, y, width, height], "alignment": alignment(cfg, pos),
                      "placement_source": 'auto' if cfg.caption_position == 'auto' else 'manual', "words": placed})
    return {"version": 2, "timebase": "output_seconds", "width": cfg.target_w,
            "height": cfg.target_h, "font": "DejaVu Sans", "phrases": plans}


def display_units(words):
    """Keep ASR decimal fragments, currencies and number units together for display.

    Original transcript/timing objects are never modified. No missing digit is
    inferred and no numeric value is changed.
    """
    units = []
    suffixes = {'juta','miliar','milyar','triliun','ribu','persen','%','rupiah','tahun','bulan','kali'}
    for original in valid_words(words):
        w = {**original, 'word_ids':[original.get('word_id')]}
        if units:
            prior = units[-1]; a, b = prior['word'], w['word']
            close = w['start'] - prior['end'] <= .65 and w.get('part') == prior.get('part')
            currency = a.lower() in ('rp','rp.','$','usd') and bool(re.match(r'^\d', b))
            decimal = bool(re.search(r'\d[.,]?$', a) and re.fullmatch(r'[.,]\d+[.,]?', b))
            suffix = bool(re.search(r'\d[.,]?$', a)) and token(b) in suffixes
            percent = b == '%' and bool(re.search(r'\d$', a))
            if close and (currency or decimal or suffix or percent):
                prior['word'] = (a.rstrip('.') if currency else a.rstrip('.,') if decimal else a) + ('' if currency or decimal or percent else ' ') + b
                prior['end'] = max(prior['end'], w['end'])
                prior['word_ids'] += w['word_ids']
                continue
        units.append(w)
    return units


def kinetic_plan(words, cfg, keywords=(), position='bottom', anchors=None):
    from .motion import frames
    phrases = groups(words, cfg)
    W, H = cfg.target_w, cfg.target_h
    plans = []
    for idx, phrase in enumerate(phrases):
        middle = (phrase[0]['start']+phrase[-1]['end'])/2
        pos = position
        anchor = None
        if anchors:
            containing = [a for a in anchors if a.get('start', -1) <= middle < a.get('end', -1)]
            anchor = containing[0] if containing else min(anchors,key=lambda a:abs(a['time']-middle))
            pos = anchor['position']
        if cfg.caption_position != 'auto':
            pos = cfg.caption_position
        side = pos in ('left','right') and W > H
        panel_box = (W*(.055 if pos == 'left' else .54), H*.21, W*.385, H*.49) if side else (W*.085,H*(.57 if H>W else .62),W*.78,H*(.23 if H>W else .25))
        use_anchor = bool(anchor and anchor.get('panel') and cfg.caption_position == 'auto')
        if use_anchor:
            panel_box = anchor['panel']
            pos = anchor['position']
            side = pos in ('left', 'right') and W > H
        x,y,width,height = panel_box
        emphasis = emphasis_indices(phrase, keywords)
        focus = next(iter(emphasis), -1)
        # Natural reading order remains intact; a highlighted token may get its own row.
        line_indices = [list(range(len(phrase)))]
        if focus >= 0 and len(phrase) > 1:
            line_indices = [a for a in [list(range(focus)), [focus], list(range(focus+1,len(phrase)))] if a]
        base = round(min(W,H)*(.073 if side else .070)*cfg.caption_scale)
        for fs in range(max(18,base), 7, -1):
            accent_size = 1.60 if cfg.caption_style == 'impact' else 1.35
            sizes = [round(fs*(accent_size if i in emphasis else .83)) for i in range(len(phrase))]
            families = [cfg.font_accent if i in emphasis and cfg.accent_font else cfg.font_main for i in range(len(phrase))]
            measures = [font(cfg.fonts_dir,sizes[i],families[i]).getlength(w['word']) for i,w in enumerate(phrase)]
            space = fs*.29
            rows = []
            for indices in line_indices:
                row=[]; used=0
                for i in indices:
                    if row and used+space+measures[i] > width*.88:
                        rows.append(row);row=[];used=0
                    used += measures[i]+(space if row else 0);row.append(i)
                if row: rows.append(row)
            heights = [max(sizes[i] for i in row)*1.18 for row in rows]
            if len(rows)<=3 and sum(heights)<=height*.88 and max(measures)<=width*.88:
                break
        if len(rows)>3 or max(measures)>width*.88 or sum(heights)>height:
            raise ValueError('Frasa terlalu panjang. Pecah teks pada transkrip atau kurangi ukuran teks.')
        start = phrase[0]['start']
        following = phrases[idx+1][0]['start'] if idx+1<len(phrases) else phrase[-1]['end']+.12
        end = max(start+.02,min(phrase[-1]['end']+.14,following))
        cy = y+(height-sum(heights))*(.5 if side or use_anchor else .8)
        placed=[]
        for row,rh in zip(rows,heights):
            row_width=sum(measures[i] for i in row)+space*(len(row)-1)
            cx=row_left(x,width,row_width,alignment(cfg,pos))
            reveal=max(0,min(phrase[i]['start'] for i in row)-start-.055)
            for i in row:
                w=phrase[i]; size=sizes[i]
                kind,samples=frames(cfg.caption_style,end-start,reveal,idx,i in emphasis,cfg)
                placed.append({'text':w['word'],'word_id':w.get('word_id'),'word_ids':w.get('word_ids',[]),
                    'start':w['start'],'end':w['end'],'x':round(cx+measures[i]/2,3),'y':round(cy+rh/2,3),
                    'baseline':round(cy+rh*.8,3), **font_info(families[i]), 'size':size,
                    'ass_size':sum(font(cfg.fonts_dir,size,families[i]).getmetrics()),'width':measures[i],
                    'emphasis':i in emphasis,
                    'motion':kind,'keyframes':samples})
                cx+=measures[i]+space
            cy+=rh
        plans.append({'start':start,'end':end,'position':pos,'panel':list(panel_box),'alignment':alignment(cfg,pos),
                      'placement_source':'auto' if cfg.caption_position == 'auto' else 'manual','words':placed})
    return {'version':4,'timebase':'output_seconds','width':W,'height':H,'font':FONTS[cfg.font_main]['family'],
            'font_main':cfg.font_main,'font_accent':cfg.font_accent,'contrast':cfg.caption_backdrop,
            'template':cfg.caption_style,'motion_intensity':cfg.motion_intensity,'phrases':plans}
