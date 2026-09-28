"""Bundled font identities shared by Pillow, libass and editor exports."""
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont

FONTS = {
    'dm_sans': dict(label='DM Sans · SemiBold', file='DMSans-SemiBold.ttf', family='DM Sans', style='SemiBold', bold=False, italic=False),
    'dm_serif': dict(label='DM Serif Display', file='DMSerifDisplay-Regular.ttf', family='DM Serif Display', style='Regular', bold=False, italic=False),
    'dm_serif_italic': dict(label='DM Serif Display · Italic', file='DMSerifDisplay-Italic.ttf', family='DM Serif Display', style='Italic', bold=False, italic=True),
    'montserrat': dict(label='Montserrat · Bold', file='Montserrat-Bold.ttf', family='Montserrat', style='Bold', bold=True, italic=False),
    'bebas': dict(label='Bebas Neue', file='BebasNeue-Regular.ttf', family='Bebas Neue', style='Regular', bold=False, italic=False),
    'dejavu': dict(label='DejaVu Sans · Bold', file='DejaVuSans-Bold.ttf', family='DejaVu Sans', style='Bold', bold=True, italic=False),
    'dejavu_serif': dict(label='DejaVu Serif · Bold', file='DejaVuSerif-Bold.ttf', family='DejaVu Serif', style='Bold', bold=True, italic=False),
}


@lru_cache(maxsize=512)
def measured(folder, font_id, size):
    return ImageFont.truetype(str(Path(folder) / FONTS[font_id]['file']), size)


def info(font_id):
    return {'font_id': font_id, **FONTS[font_id]}
