"""ASS execution of a typography plan, using bundled, measured fonts."""
from __future__ import annotations
import json
from pathlib import Path
from .typography import make_plan


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
            dur_ms = max(1, int((end - start) * 1000))
            enter = min(120, max(1, dur_ms // 3))
            fade = min(65, dur_ms // 4)
            # Each word occupies a fixed measured box; later words never shift it.
            active = max(0, round((w['start'] - start) * 1000))
            # Entire phrase is readable from the beginning; emphasis changes at spoken time.
            anim = (f"\\fscx100\\fscy100\\t({active},{active + enter},\\c{paint})"
                    if cfg.caption_style == "editorial" else "")
            family = 'DejaVu Serif' if w.get('family') == 'serif' else 'DejaVu Sans'
            initial = color(cfg.base_hex) if cfg.caption_style == 'editorial' else paint
            tags = f"\\an5\\pos({w['x']},{w['y']})\\fn{family}\\fs{w['ass_size']}\\c{initial}\\fad({fade},{fade}){anim}"
            events.append(f"Dialogue: 0,{ts(start)},{ts(end)},Editorial,,0,0,0,,{{{tags}}}{safe(w['text'])}")
    if hook and cfg.title_card:
        # A restrained top title for the first three seconds; no synthetic spoken claim.
        from .typography import font
        label = safe(hook.strip())[:100]
        size = round(min(cfg.target_w, cfg.target_h) * .044)
        while size > 14 and font(cfg.fonts_dir, size).getlength(label) > cfg.target_w * .78:
            size -= 1
        end = min(3., max((p['end'] for p in plan['phrases']), default=3.))
        tags = f"\\an8\\pos({cfg.target_w * .47},{cfg.target_h * .105})\\fs{size}\\c{color(cfg.base_hex)}\\bord2\\shad2\\fad(120,180)"
        events.append(f"Dialogue: 1,{ts(0)},{ts(end)},Editorial,,0,0,0,,{{{tags}}}{label}")
        plan['title'] = {'text': label, 'start': 0, 'end': end, 'size': size,
                         'x': cfg.target_w * .47, 'y': cfg.target_h * .105}
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    dst.with_suffix(".caption-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(dst)
