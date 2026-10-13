"""Two independently checked caption bands, mapped through the exact edit clock."""
import copy
from dataclasses import replace
from . import typography
from .caption_geometry import bounds


def translation_words(track,plan,clip):
    words=copy.deepcopy(track['words'])
    if clip.get('_editor_clock'):
        from .editor_contract import remap_words
        words=remap_words(words,clip['_editor_clock'],[])
    mapped=[]
    for i,span in enumerate(plan['spans']):
        for w in words:
            a=max(w['start'],span['source_start']);b=min(w['end'],span['source_end'])
            if b<=a:continue
            mapped.append({**w,'start':span['start']+a-span['source_start'],'end':span['start']+b-span['source_start'],
                'word_id':str(w['word_id'])+':instance-'+str(i),'token_id':str(w['word_id'])+':instance-'+str(i)})
    return mapped


def make_plan(source_words,translated_words,cfg):
    plain=replace(cfg,style_preset='legacy',caption_style='clean',caption_position='auto',caption_align='center',caption_scale=min(1.,cfg.caption_scale))
    w,h=cfg.target_w,cfg.target_h
    def one(words,y,height):
        if not words:return typography.make_plan([],plain)
        anchors=[{'start':0.,'end':max(r['end'] for r in words)+1,'time':0.,'position':'bottom','panel':[w*.08,y,w*.84,height],'protected':[]}]
        return typography.make_plan(words,plain,anchors=anchors)
    original=one(source_words,h*.52,h*.17);translation=one(translated_words,h*.74,h*.14)
    phrases=[{**p,'language_track':'source'} for p in original['phrases']]+[{**p,'language_track':'translation'} for p in translation['phrases']]
    phrases.sort(key=lambda p:(p['start'],p['language_track']))
    return {**original,'phrases':phrases,'bilingual':True,'source_plan':original,'translation_plan':translation,
        'source_words':copy.deepcopy(source_words),'translation_words':copy.deepcopy(translated_words),'track_policy':'source_above_translation; no_cross_band_motion'}


def check(plan,cfg):
    from .caption_checks import inspect_caption_plan
    plain=replace(cfg,caption_position='auto',caption_align='center')
    source=inspect_caption_plan(plan['source_plan'],plain,plan['source_words'])
    translation=inspect_caption_plan(plan['translation_plan'],plain,plan['translation_words']);collisions=[]
    for a in plan['source_plan']['phrases']:
        for b in plan['translation_plan']['phrases']:
            if min(a['end'],b['end'])<=max(a['start'],b['start']):continue
            for left in a['words']:
                x,y,w,h=bounds(left)
                for right in b['words']:
                    xx,yy,ww,hh=bounds(right)
                    if x<xx+ww and xx<x+w and y<yy+hh and yy<y+h:collisions.append('Dua bahasa bertumpang tindih')
    return {'passed':source['passed'] and translation['passed'] and not collisions,'issues':source.get('issues',[])+translation.get('issues',[])+collisions,
        'source':source,'translation':translation,'geometry_checked':True,'quality':'technical_checks_only; human_language_review_required'}
