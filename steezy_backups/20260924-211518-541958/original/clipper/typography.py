"""Measured phrase layouts. Coordinates and times refer to the final output video."""
from __future__ import annotations
import math
import re
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont

STOP = set("yang dan di ke dari untuk dengan karena kalau bahwa adalah itu ini juga saya kamu kita mereka dia anda sebuah pada dalam akan sudah belum bisa agar atau tapi namun jadi maka sebagai sangat lebih hanya tidak bukan telah the a an and or to of in on for is are it this that you your i we they with as at be do does so just have has my".split())
STOP.update('gue gua lo lu kalian nih sih dong lah kok tuh deh kan gitu begitu nah ya iya eh oh enggak nggak gak mau punya'.split())
STRONG = set('risiko penghasilan pendapatan modal biaya untung rugi investasi strategi disiplin gagal berhasil pertumbuhan uang waktu tujuan alasan bukti solusi masalah rahasia money risk growth cost income profit loss strategy'.split())


def token(text):
    return re.sub(r"[^\w%]", "", str(text).lower())


@lru_cache(maxsize=96)
def font(fonts_dir, size, family='sans'):
    return ImageFont.truetype(str(Path(fonts_dir) / ('DejaVuSerif-Bold.ttf' if family == 'serif' else 'DejaVuSans-Bold.ttf')), size)


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
    for w in valid_words(words):
        if current and (len(current) >= cfg.editorial_words
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


def make_plan(words, cfg, keywords=(), position="bottom", anchors=None):
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
        emph = emphasis_indices(phrase, keywords)
        scale = max(.5, min(1.5, cfg.caption_scale))
        base = int(min(cfg.target_w, cfg.target_h) * (.067 if pos in ('left', 'right') else .066) * scale)
        families = ['serif' if i in emph and cfg.accent_font and cfg.caption_style == 'editorial'
                    and not re.search(r'\d', phrase[i]['word']) else 'sans' for i in range(len(phrase))]
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
            cx = x + (width - row_w) / 2
            for w, size, measured in row:
                placed.append({"text": w["word"], "word_id": w.get("word_id"),
                               "start": w["start"], "end": w["end"],
                               "x": round(cx + measured / 2, 2), "y": round(baseline - size * .36, 2),
                               "baseline": round(baseline, 2), "family": families[flat],
                               "ass_size": sum(font(cfg.fonts_dir, size, families[flat]).getmetrics()),
                               "size": size, "width": measured, "emphasis": flat in emph})
                cx += measured + space
                flat += 1
            cy += rh
        plans.append({"start": start, "end": end, "position": pos,
                      "panel": [x, y, width, height], "words": placed})
    return {"version": 2, "timebase": "output_seconds", "width": cfg.target_w,
            "height": cfg.target_h, "font": "DejaVu Sans", "phrases": plans}
