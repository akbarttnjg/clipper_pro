"""ASS execution of a typography plan, using bundled, measured fonts."""
from __future__ import annotations
import json
from pathlib import Path
from .typography import make_plan
from .font_catalog import FONTS, measured, info as font_info


def ts(t):
    c = max(0, round(float(t) * 100))
    return f"{c // 360000}:{c // 6000 % 60:02d}:{c // 100 % 60:02d}.{c % 100:02d}"


def safe(text):
    return str(text).replace("\\", "／").replace("{", "(").replace("}", ")").replace("\n", " ").replace("\r", " ")


def color(hexval):
    h = hexval.lstrip("#")
    return "&H" + h[4:6] + h[2:4] + h[0:2] + "&"


def write_ass(words, path, cfg, hook="", keywords=(), position="bottom", anchors=None):
    plan = make_plan(words, cfg, keywords, position, anchors)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {cfg.target_w}
PlayResY: {cfg.target_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Editorial,DejaVu Sans,60,&H00FFFFFF,&H00FFFFFF,&H50101010,&H70000000,-1,0,0,0,100,100,0,0,1,2.0,2.5,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for phrase in plan["phrases"]:
        for w in phrase["words"]:
            start = phrase["start"]
            end = phrase["end"]
            if end - start < .02:
                continue
            paint = color(cfg.accent_hex if w["emphasis"] else cfg.base_hex)
            if w.get('keyframes'):
                family = w['family']
                bold = int(w.get('bold', False))
                for a,b in zip(w['keyframes'], w['keyframes'][1:]):
                    left,right = start+a['t'],min(end,start+b['t'])
                    if right<=left or a['opacity']<=0:
                        continue
                    alpha = round((1-a['opacity'])*255)
                    scale = a['scale']*100
                    tags = (f"\\an5\\pos({w['x']+a['dx']:.3f},{w['y']+a['dy']:.3f})"
                        f"\\fn{family}\\fs{w['ass_size']}\\b{bold}\\i{int(w.get('italic',False))}"
                        f"\\c{paint}\\alpha&H{alpha:02X}&\\fscx{scale:.3f}\\fscy{scale:.3f}"
                        f"\\3c&H15110D&\\4c&H000000&\\bord{min(cfg.target_w,cfg.target_h)/1080*1.8 if cfg.caption_backdrop else 0:.2f}"
                        f"\\shad{min(cfg.target_w,cfg.target_h)/1080*3 if cfg.caption_backdrop else 0:.2f}\\blur{a['blur']:.3f}")
                    events.append(f"Dialogue: 0,{ts(left)},{ts(right)},Editorial,,0,0,0,,{{{tags}}}{safe(w['text'])}")
                continue
            dur_ms = max(1, int((end - start) * 1000))
            enter = min(120, max(1, dur_ms // 3))
            fade = min(65, dur_ms // 4)
            # Each word occupies a fixed measured box; later words never shift it.
            active = max(0, round((w['start'] - start) * 1000))
            # Entire phrase is readable from the beginning; emphasis changes at spoken time.
            anim = (f"\\fscx100\\fscy100\\t({active},{active + enter},\\c{paint})"
                    if cfg.caption_style == "editorial" else "")
            family = w['family']
            initial = color(cfg.base_hex) if cfg.caption_style == 'editorial' else paint
            tags = f"\\an5\\pos({w['x']},{w['y']})\\fn{family}\\b{int(w.get('bold',False))}\\i{int(w.get('italic',False))}\\fs{w['ass_size']}\\c{initial}\\fad({fade},{fade}){anim}"
            events.append(f"Dialogue: 0,{ts(start)},{ts(end)},Editorial,,0,0,0,,{{{tags}}}{safe(w['text'])}")
    if hook and cfg.title_card:
        # A restrained top title for the first three seconds; no synthetic spoken claim.
        def font(folder, size):
            return measured(folder, cfg.font_main, size)
        label = safe(hook.strip())[:100]
        size = round(min(cfg.target_w, cfg.target_h) * .044)
        def title_rows(text, fs):
            rows=['']
            for word in text.split():
                line=(rows[-1]+' '+word).strip()
                if rows[-1] and font(cfg.fonts_dir,fs).getlength(line)>cfg.target_w*.78:
                    rows.append(word)
                else: rows[-1]=line
            return rows
        rows=title_rows(label,size)
        while size>14 and (len(rows)>2 or any(font(cfg.fonts_dir,size).getlength(r)>cfg.target_w*.78 for r in rows)):
            size-=1;rows=title_rows(label,size)
        end = min(3., max((p['end'] for p in plan['phrases']), default=3.))
        title_font = FONTS[cfg.font_main]
        tags = f"\\an8\\pos({cfg.target_w * .47},{cfg.target_h * .105})\\fn{title_font['family']}\\b{int(title_font['bold'])}\\i{int(title_font['italic'])}\\fs{size}\\c{color(cfg.base_hex)}\\bord2\\shad2\\fad(120,180)"
        shown='\\N'.join(rows)
        events.append(f"Dialogue: 1,{ts(0)},{ts(end)},Editorial,,0,0,0,,{{{tags}}}{shown}")
        plan['title'] = {'text': '\n'.join(rows), 'start': 0, 'end': end, 'size': size, **font_info(cfg.font_main),
                         'x': cfg.target_w * .47, 'y': cfg.target_h * .105}
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    dst.with_suffix(".caption-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(dst)
