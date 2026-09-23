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
Style: Editorial,DejaVu Sans,60,&H00FFFFFF,&H00FFFFFF,&H80202020,&H90000000,-1,0,0,0,100,100,0,0,1,1.0,1.0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for phrase in plan["phrases"]:
        for w in phrase["words"]:
            start = w["start"] if cfg.caption_style == "editorial" else phrase["start"]
            end = phrase["end"]
            if end - start < .02:
                continue
            paint = color(cfg.accent_hex if w["emphasis"] else cfg.base_hex)
            dur_ms = max(1, int((end - start) * 1000))
            enter = min(120, max(1, dur_ms // 3))
            fade = min(65, dur_ms // 4)
            # Each word occupies a fixed measured box; later words never shift it.
            anim = (f"\\fscx96\\fscy96\\blur1.4\\t(0,{enter},\\fscx100\\fscy100\\blur0)"
                    if cfg.caption_style == "editorial" else "")
            tags = f"\\an5\\pos({w['x']},{w['y']})\\fs{w['size']}\\c{paint}\\fad({fade},{fade}){anim}"
            events.append(f"Dialogue: 0,{ts(start)},{ts(end)},Editorial,,0,0,0,,{{{tags}}}{safe(w['text'])}")
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    dst.with_suffix(".caption-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(dst)
