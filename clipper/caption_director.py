"""Restrained, source-grounded compositions shared by both output ratios.

The director never rewrites speech. typography.py measures the geometry.
"""
from dataclasses import replace

VERSION='caption-director-4.0.10'


def focus(words,keywords=()):
    from .typography import emphasis_indices,protected_boundary
    selected=emphasis_indices(words,keywords)
    if not selected:return selected
    left,right=min(selected),max(selected)
    while left>0 and protected_boundary(words,left):left-=1
    while right+1<len(words) and protected_boundary(words,right+1):right+=1
    return set(range(left,right+1))


def compose(cfg,words,selected,quiet,choice):
    mode=cfg.caption_composition
    if mode=='auto':
        edge_focus=selected and (min(selected)==0 or max(selected)==len(words)-1)
        mode='quote' if quiet else 'focus' if edge_focus and 1<=len(selected)<=3 and len(words)<=6 else 'editorial'
    if mode=='focus' and (not selected or len(selected)>3):mode='editorial'
    template=cfg.caption_style if cfg.caption_template_policy=='manual' else (
        'magazine' if mode=='quote' else ('pop','blur')[choice%2] if mode=='focus' else ('magazine','slide','blur','narrative')[choice%4])
    local=replace(cfg,style_preset='legacy',caption_style=template,
                  motion_intensity='calm' if quiet or mode=='quote' else cfg.motion_intensity)
    local._director=True
    local._composition=mode
    local._accent_ratio=1.32 if mode=='focus' else 1.12 if mode=='editorial' else 1.05
    # Landscape at phone width needs larger source glyphs than min(W,H).
    local._base_font=round(cfg.target_w*(.0855 if cfg.target_h>cfg.target_w else .078)*cfg.caption_scale)
    local._whole_phrase=True
    local._motion_direction=('left','right','up','down')[(choice//4)%4]
    local._emphasis_disabled=not cfg.semantic_emphasis
    return local,mode


def focus_rows(count,selected):
    if not selected:return None
    left,right=min(selected),max(selected)+1
    return [list(range(a,b)) for a,b in ((0,left),(left,right),(right,count)) if b>a]


def default_panel(cfg):
    W,H=cfg.target_w,cfg.target_h
    return [W*.07,H*.53,W*.80,H*.27] if H>W else [W*.08,H*.52,W*.84,H*.32]


def visible_cap(word,fonts_dir,display_width,output_width):
    from .typography import font
    box=font(fonts_dir,int(word['size']),word.get('font_id','dm_sans')).getbbox('H')
    return max(0,box[3]-box[1])*display_width/output_width


def visible_lower(word,fonts_dir,display_width,output_width):
    from .typography import font
    box=font(fonts_dir,int(word['size']),word.get('font_id','dm_sans')).getbbox('a')
    return max(0,box[3]-box[1])*display_width/output_width


def readable(words,cfg):
    return all(visible_cap(w,cfg.fonts_dir,360,cfg.target_w)>=14 and
               visible_lower(w,cfg.fonts_dir,360,cfg.target_w)>=14 for w in words)
