"""Shared, frame-sampled typography motion for ASS and editable project exports."""
from __future__ import annotations
import math

TEMPLATES = (
    {'id': 'magazine', 'name': 'Editorial bertingkat', 'description': 'Kata penghubung kecil, penekanan serif besar, susunan tiga tingkat yang stabil.', 'motion': 'mixed'},
    {'id': 'narrative', 'name': 'Narasi bertingkat', 'description': 'Putih–kuning, frasa bertingkat, blur dan gerak halus.', 'motion': 'mixed'},
    {'id': 'pop', 'name': 'Pop lembut', 'description': 'Kata utama membesar sebentar, lalu menetap.', 'motion': 'pop'},
    {'id': 'slide', 'name': 'Geser terarah', 'description': 'Masuk dari kiri, kanan, atas, dan bawah per frasa.', 'motion': 'slide'},
    {'id': 'blur', 'name': 'Fokus tajam', 'description': 'Teks buram menjadi tajam dengan ukuran bertingkat.', 'motion': 'blur'},
    {'id': 'impact', 'name': 'Angka & penekanan', 'description': 'Nominal utuh dan kata penting besar, dengan aksen tegas.', 'motion': 'pop'},
)
IDS = tuple(t['id'] for t in TEMPLATES)


def frames(style, duration, reveal, index, emphasis, cfg, position='bottom'):
    """Times are relative to a phrase. Intermediate samples preserve easing in ASS.

    Each exporter consumes the same position/scale/alpha samples. Blur in CapCut
    native text has no verified mapping and is explicitly omitted there.
    """
    fps = cfg.output_fps
    last = max(1, math.ceil(duration * fps))
    first = min(last - 1, max(0, round(reveal * fps)))
    strength = {'calm': .65, 'balanced': 1., 'dynamic': 1.35}.get(cfg.motion_intensity, 1.)
    direction = position if position in ('left','right') else 'up'
    kind = {'magazine': 'pop' if emphasis else 'up', 'narrative': 'pop' if emphasis else 'blur',
            'pop': 'pop', 'slide': direction,
            'blur': 'blur', 'impact': 'pop'}.get(style, 'up')
    enter = min(max(2, round(.28 * fps)), max(1, (last-first)//2))
    leave = min(round(.1*fps), max(1, (last-first)//4))
    travel = min(cfg.target_w, cfg.target_h)*.035*strength
    samples = []
    times = sorted({0, first, *range(first, min(last, first+enter)+1),
                    max(first+enter, last-leave), *range(max(first, last-leave), last+1)})
    for f in times:
        u = max(0., min(1., (f-first)/enter))
        remain = (1-u)**3
        fade = max(0., min(1., (last-f)/max(1,leave)))
        alpha = (min(1., u*2.5) if kind != 'blur' else u) * fade
        scale, dx, dy, blur = 1., 0., 0., 0.
        if kind == 'pop':
            # Controlled overshoot, settling at exactly 1; no repeating bounce.
            scale = 1 - .13*strength*remain + .08*strength*math.sin(math.pi*u)*(1-u)
        elif kind == 'blur':
            blur = 7*min(cfg.target_w,cfg.target_h)/1080*remain*strength
            scale = 1+.045*strength*remain
        elif kind in ('left','right'):
            dx = (-1 if kind == 'left' else 1)*travel*remain
        else:
            dy = (1 if kind == 'up' else -1)*travel*remain
        if f < first:
            alpha = 0.
        samples.append({'frame':f, 't':round(f/fps,6), 'scale':round(scale,5),
                        'dx':round(dx,3), 'dy':round(dy,3), 'opacity':round(alpha,5), 'blur':round(blur,3)})
    return kind, samples
