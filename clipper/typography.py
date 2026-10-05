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


@lru_cache(maxsize=64)
def optical_factor(fonts_dir, family):
    """Equal visible capital height across families, not equal nominal point size."""
    reference = font(fonts_dir,100,'dm_sans').getbbox('H')[3] - font(fonts_dir,100,'dm_sans').getbbox('H')[1]
    box = font(fonts_dir,100,family).getbbox('H')
    return max(.78,min(1.32,reference/max(1,box[3]-box[1])))


def protected_pair(left, right):
    from .transcript_correction import PROTECTED
    a,b = token(left['word'].split()[-1]),token(right['word'].split()[0])
    return (a in PROTECTED or (a,b) in {('stop','loss'),('take','profit'),('time','frame'),
        ('risk','reward'),('drop','base'),('base','drop'),('rally','base'),('base','rally'),
        ('supply','demand'),('support','resistance')})


def groups(words, cfg):
    # Optimize adjacent phrase boundaries together to avoid orphan words.
    runs, current = [], []
    for w in display_units(words):
        if current and (w.get('part') != current[-1].get('part')
                or w['start']-current[-1]['end'] > cfg.caption_gap_s
                or current[-1].get('sentence_end')
                or re.search(r'[!?;:]$|(?<!\d)\.$', current[-1]['word'])):
            runs.append(current); current = []
        current.append(w)
    if current:
        runs.append(current)
    weak = set('yang dan di ke dari untuk dengan karena kalau bahwa akan sudah belum bisa agar atau tapi namun jadi sebagai tidak bukan harus perlu butuh pengen ingin mau lebih sangat'.split())
    result = []
    for run in runs:
        n = len(run); costs = [float('inf')]*(n+1); paths = [None]*(n+1); costs[n] = 0
        for a in range(n-1,-1,-1):
            for b in range(a+1,min(n,a+max(4,cfg.editorial_words+1))+1):
                count = b-a
                if count>1 and run[b-1]['end']-run[a]['start'] > max(3.4,cfg.editorial_phrase_s+.6):
                    break
                penalty = (count-4.5)**2*.3 + (9 if count==1 else 0)
                characters = sum(len(w['word']) for w in run[a:b])+count-1
                duration = max(.05,run[b-1]['end']-run[a]['start'])
                penalty += max(0,characters/duration-22)*.12
                if b<n and protected_pair(run[b-1],run[b]):
                    penalty += 80
                if b<n and token(run[b-1]['word']) in weak:
                    penalty += 8
                # Source-grounded phrases from the editorial review must stay
                # together when they fit; a long phrase can still wrap safely.
                if b<n and run[b-1].get('meaning_group') is not None and run[b-1].get('meaning_group') == run[b].get('meaning_group'):
                    penalty += 24
                if b<n and token(run[b]['word']) in {'jadi','tapi','namun','karena','kalau'}:
                    penalty -= 2
                if a>0 and token(run[a]['word']) in {'nya','lah','pun'}:
                    penalty += 6
                if re.search(r'[,;.!?]$',run[b-1]['word']) and not re.search(r'\d[,.]$',run[b-1]['word']):
                    penalty -= 1.4
                value = penalty+costs[b]
                if value<costs[a]:
                    costs[a],paths[a] = value,b
        a=0
        while a<n:
            b=paths[a] or a+1
            result.append(run[a:b]);a=b
    return result


def balanced_rows(phrase, measures, space, width, max_rows, emphasis):
    from itertools import combinations
    n=len(phrase); best=None; best_score=float('inf')
    weak={'yang','dan','di','ke','dari','untuk','dengan','tidak','bukan','harus','butuh','akan'}
    for count in range(1,min(max_rows,n)+1):
        for cuts in combinations(range(1,n),count-1):
            bounds=(0,*cuts,n)
            rows=[list(range(a,b)) for a,b in zip(bounds,bounds[1:])]
            widths=[sum(measures[i] for i in row)+space*(len(row)-1) for row in rows]
            if max(widths)>width:
                continue
            score=count*.13+sum((w/max(widths)-1)**2 for w in widths)*.8
            if count==1 and n>4: score+=.5
            for row in rows:
                if len(row)==1 and n>2 and row[0] not in emphasis: score+=1.8
                if row[-1]<n-1 and token(phrase[row[-1]]['word']) in weak: score+=2.2
                if row[-1]<n-1 and protected_pair(phrase[row[-1]],phrase[row[-1]+1]): score+=20
            if score<best_score: best,best_score=rows,score
    return best


def emphasis_indices(words, keywords=()):
    semantic = {i for i, w in enumerate(words) if w.get('meaning_emphasis')}
    if semantic:
        # Keep a short meaningful phrase, including its negation, emphasized.
        return semantic
    # Prefer a complete keyword phrase; retain a preceding negation in fallback.
    tokens = [token(w['word']) for w in words]
    for phrase in sorted(keywords,key=lambda x:len(str(x).split()),reverse=True):
        target = [token(s) for s in str(phrase).split()]
        if len(target)<2:
            continue
        for a in range(len(words)-len(target)+1):
            if tokens[a:a+len(target)] == target:
                return set(range(a,a+len(target)))
    keys = {token(k) for phrase in keywords for k in str(phrase).split()}
    scores = []
    for i, w in enumerate(words):
        t = token(w["word"])
        if not t or t in STOP or not (t in keys or re.search(r'\d', t) or (not keys and t in STRONG)):
            continue
        score = 10 * (t in keys) + 5 * bool(re.search(r"\d", t)) + min(len(t), 12) / 12
        scores.append((score, i))
    selected = {i for _, i in sorted(scores, reverse=True)[:1]}
    if selected:
        from .transcript_correction import PROTECTED
        i = next(iter(selected))
        if i>0 and token(words[i-1]['word']) in PROTECTED:
            selected.add(i-1)
    return selected


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


def scene_groups(words, cfg, anchors):
    # Composition cuts must not duplicate a word or turn a phrase into a flash.
    return groups(words, cfg)


def phrase_anchor(phrase, anchors, cfg):
    if not anchors:
        return None
    start, end = phrase[0]['start'], phrase[-1]['end']
    touching = [a for a in anchors if a.get('start', -1) < end and a.get('end', -1) > start]
    chosen = max(touching, key=lambda a: min(end, a['end'])-max(start, a['start'])) if touching else min(anchors, key=lambda a: abs(a['time']-(start+end)/2))
    anchor = dict(chosen)
    anchor['end'] = max(end+.16, anchor.get('end', end))
    if len(touching)>1 and cfg.caption_position=='auto':
        from .placement import choose_panel
        boxes = [b for a in touching for b in a.get('protected', [])]
        panel_box, pos, _ = choose_panel(boxes, cfg.target_w, cfg.target_h, anchor.get('panel'))
        anchor.update(panel=panel_box, position=pos, protected=boxes)
    return anchor


def make_plan(words, cfg, keywords=(), position="bottom", anchors=None):
    from .motion import IDS
    if cfg.caption_style in IDS:
        return kinetic_plan(words, cfg, keywords, position, anchors)
    phrases = scene_groups(words, cfg, anchors)
    plans = []
    for idx, phrase in enumerate(phrases):
        pos = position
        anchor = None
        if anchors:
            # One placement per phrase: never chase the face mid-word.
            mid = (phrase[0]["start"] + phrase[-1]["end"]) / 2
            pos = min(anchors, key=lambda a: abs(a["time"] - mid))["position"]
        if cfg.caption_position != "auto":
            pos = cfg.caption_position
        x, y, width, height = panel(cfg, pos)
        if anchors:
            middle = (phrase[0]['start'] + phrase[-1]['end']) / 2
            anchor = phrase_anchor(phrase, anchors, cfg)
            if anchor and anchor.get('panel') and cfg.caption_position == 'auto':
                x, y, width, height = anchor['panel']
                pos = anchor['position']
        emph = emphasis_indices(phrase, keywords)
        scale = max(.5, min(1.5, cfg.caption_scale))
        base = int(min(cfg.target_w, cfg.target_h) * (.067 if pos in ('left', 'right') else .066) * scale)
        families = [cfg.font_accent if i in emph and cfg.accent_font else cfg.font_main for i in range(len(phrase))]
        # Measure at the largest animation scale, so the pop stays inside its panel.
        for fs in range(max(18, base), 5, -1):
            sizes = [round(fs * optical_factor(cfg.fonts_dir,families[i]) * (1.18 if i in emph and cfg.caption_style == "editorial" else 1)) for i in range(len(phrase))]
            rows, space = _wrap(phrase, sizes, width / 1.035, cfg, families)
            total_h = sum(max(v[1] for v in row) * 1.42 for row in rows)
            if len(rows) <= 2 and total_h <= height and all(v[2] <= width / 1.035 for row in rows for v in row):
                break
        if total_h > height or any(v[2] > width / 1.035 for row in rows for v in row):
            raise ValueError("Teks terlalu panjang untuk area subtitle. Pecah kata atau perbaiki transkrip.")
        start = phrase[0]["start"]
        next_start = phrases[idx + 1][0]["start"] if idx + 1 < len(phrases) else phrase[-1]["end"]
        end = max(start + .02, min(phrase[-1]["end"] + .16, next_start))
        if anchor:
            end = min(end, anchor.get('end', end))
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
                               "word_ids":w.get('word_ids',[]),"token_ids":w.get('token_ids',[]),
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
                      "placement_source": 'auto' if cfg.caption_position == 'auto' else 'manual',
                      "protected": anchor.get('protected', []) if anchor and cfg.caption_position == 'auto' else [], "words": placed})
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
        w = {**original, 'word_ids':original.get('source_word_ids',[original.get('word_id')]),
             'token_ids':[original.get('token_id',original.get('word_id'))]}
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
                prior['token_ids'] += w['token_ids']
                prior['meaning_emphasis'] = prior.get('meaning_emphasis',False) or w.get('meaning_emphasis',False)
                continue
        units.append(w)
    return units


def kinetic_plan(words, cfg, keywords=(), position='bottom', anchors=None):
    from .motion import frames
    phrases = scene_groups(words, cfg, anchors)
    W, H = cfg.target_w, cfg.target_h
    plans = []
    for idx, phrase in enumerate(phrases):
        middle = (phrase[0]['start']+phrase[-1]['end'])/2
        pos = position
        anchor = None
        if anchors:
            anchor = phrase_anchor(phrase, anchors, cfg)
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
        base = round(min(W,H)*(.073 if side else .070)*cfg.caption_scale)
        for fs in range(max(18,base), 7, -1):
            accent_size = 1.20 if cfg.caption_style in ('magazine','impact') else 1.15
            families = [cfg.font_accent if i in emphasis and cfg.accent_font else cfg.font_main for i in range(len(phrase))]
            sizes = [round(fs*optical_factor(cfg.fonts_dir,families[i])*(accent_size if i in emphasis else 1.)) for i in range(len(phrase))]
            measures = [font(cfg.fonts_dir,sizes[i],families[i]).getlength(w['word']) for i,w in enumerate(phrase)]
            space = fs*.29
            rows = balanced_rows(phrase, measures, space, width*.9, 2 if height<H*.2 else 3, emphasis)
            if rows is None:
                continue
            heights = [max(sizes[i] for i in row)*1.18 for row in rows]
            if len(rows)<=3 and sum(heights)<=height*.88 and max(measures)<=width*.88:
                break
        if rows is None or len(rows)>3 or max(measures)>width*.9 or sum(heights)>height:
            raise ValueError('Frasa terlalu panjang. Pecah teks pada transkrip atau kurangi ukuran teks.')
        start = phrase[0]['start']
        following = phrases[idx+1][0]['start'] if idx+1<len(phrases) else phrase[-1]['end']+.12
        end = max(start+.02,min(phrase[-1]['end']+.14,following))
        if anchor:
            end = min(end, anchor.get('end', end))
        cy = y+(height-sum(heights))*(.5 if side or use_anchor else .8)
        placed=[]
        for row,rh in zip(rows,heights):
            row_width=sum(measures[i] for i in row)+space*(len(row)-1)
            cx=row_left(x,width,row_width,alignment(cfg,pos))
            reveal=max(0,min(phrase[i]['start'] for i in row)-start-.055)
            for i in row:
                w=phrase[i]; size=sizes[i]
                word_reveal = min(max(0,end-start-.65),max(reveal,w['start']-start-.06) if i in emphasis else reveal)
                kind,samples=frames(cfg.caption_style,end-start,max(0,word_reveal),idx,i in emphasis,cfg,position=pos)
                wx, wy = cx+measures[i]/2, cy+rh/2
                # Keep the entire animation inside the chosen empty-space panel.
                for sample in samples:
                    half_w = measures[i]*sample['scale']/2
                    half_h = size*sample['scale']*.66
                    sample['dx'] = round(max(x+half_w-wx, min(sample['dx'], x+width-half_w-wx)), 3)
                    sample['dy'] = round(max(y+half_h-wy, min(sample['dy'], y+height-half_h-wy)), 3)
                placed.append({'text':w['word'],'word_id':w.get('word_id'),'word_ids':w.get('word_ids',[]),
                    'token_ids':w.get('token_ids',[]),
                    'start':w['start'],'end':w['end'],'x':round(cx+measures[i]/2,3),'y':round(cy+rh/2,3),
                    'baseline':round(cy+rh*.8,3), **font_info(families[i]), 'size':size,
                    'ass_size':sum(font(cfg.fonts_dir,size,families[i]).getmetrics()),'width':measures[i],
                    'emphasis':i in emphasis,
                    'motion':kind,'keyframes':samples})
                cx+=measures[i]+space
            cy+=rh
        plans.append({'start':start,'end':end,'position':pos,'panel':list(panel_box),'alignment':alignment(cfg,pos),
                      'placement_source':'auto' if cfg.caption_position == 'auto' else 'manual',
                      'protected': anchor.get('protected', []) if use_anchor else [], 'words':placed})
    return {'version':4,'timebase':'output_seconds','width':W,'height':H,'font':FONTS[cfg.font_main]['family'],
            'font_main':cfg.font_main,'font_accent':cfg.font_accent,'contrast':cfg.caption_backdrop,
            'template':cfg.caption_style,'motion_intensity':cfg.motion_intensity,'phrases':plans}
