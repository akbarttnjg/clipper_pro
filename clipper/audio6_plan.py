"""Sample-clock audio events follow the approved M1 clock and exact source words."""
import copy
import math
import re
from .audio6_contract import RATE,MAX_SECONDS,effective
from .contracts import fingerprint

def slices(plan):
    clock=plan.get('editor',{}).get('clock')
    if clock:
        return [{'source_start':r['source_start_tick']/1e6,'source_end':r['source_end_tick']/1e6,
            'start':r['output_start_frame']/clock['fps'],'end':r['output_end_frame']/clock['fps'],
            'reverse':r['reverse'],'kind':r['kind'],'id':r['logical_segment_id']} for r in clock['slices']]
    return [{**r,'reverse':False,'id':str(i)} for i,r in enumerate(plan['spans'])]

def events(plan,row):
    duration=plan['duration'];start=row['start'];end=row['end'];out=[]
    if row['beat_snap']:
        beat=60/row['beat_bpm'];snapped=max(0.,row['beat_offset']+round((start-row['beat_offset'])/beat)*beat)
        end+=snapped-start;start=snapped
    if row['timebase']=='output':
        a=max(0.,start);b=min(end,duration)
        if b>a:out.append({'start':a,'end':b,'asset_start':row['asset_start']+a-start,'asset_seconds':b-a,'rate':1.,'reverse':False,'clock':'output','fade_duration':end-start,'fade_position_start':a-start,'fade_position_end':b-start})
    else:
        for piece in slices(plan):
            if piece.get('kind')=='freeze':continue  # Same silence policy as the source voice.
            left=max(start,piece['source_start']);right=min(end,piece['source_end'])
            if left>=right:continue
            scale=(piece['end']-piece['start'])/(piece['source_end']-piece['source_start'])
            if piece['reverse']:a=piece['start']+(piece['source_end']-right)*scale;b=piece['start']+(piece['source_end']-left)*scale
            else:a=piece['start']+(left-piece['source_start'])*scale;b=piece['start']+(right-piece['source_start'])*scale
            b=min(duration,b)
            if b>a:out.append({'start':a,'end':b,'asset_start':row['asset_start']+left-start,'asset_seconds':right-left,'rate':1/scale,'reverse':piece['reverse'],'clock':'M1_source_mapping','slice':piece['id'],'fade_duration':end-start,'fade_position_start':right-start if piece['reverse'] else left-start,'fade_position_end':left-start if piece['reverse'] else right-start})
    return [{**r,'start_sample':round(r['start']*RATE),'end_sample':round(r['end']*RATE),'requested_start':row['start'],'beat_snapped':row['beat_snap']} for r in out]

def source_words(plan,cfg=None):
    """All effective source speech, independent of caption visibility/translation."""
    original=(cfg.audio6 or {}).get('source_speech') if cfg is not None else None
    if original is None:return copy.deepcopy(plan.get('speech_words',plan.get('words',plan.get('display_words',[]))))
    out=[]
    for piece in slices(plan):
        if piece.get('kind')=='freeze':continue
        scale=(piece['end']-piece['start'])/(piece['source_end']-piece['source_start'])
        for row in original:
            left=max(row['start'],piece['source_start']);right=min(row['end'],piece['source_end'])
            if right<=left:continue
            if piece['reverse']:a=piece['start']+(piece['source_end']-right)*scale;b=piece['start']+(piece['source_end']-left)*scale
            else:a=piece['start']+(left-piece['source_start'])*scale;b=piece['start']+(right-piece['source_start'])*scale
            a=max(0.,a);b=min(plan['duration'],b)
            if b>a:out.append({**copy.deepcopy(row),'start':a,'end':b,'source_start':row['start'],'source_end':row['end'],'audio_instance':piece['id']})
    return sorted(out,key=lambda r:(r['start'],r['end']))

def logical_spans(plan):
    """Actual editorial joins; internal ramp slices are one logical segment."""
    if not plan.get('editor',{}).get('clock'):return plan['spans']
    out=[]
    for row in slices(plan):
        a=max(0.,row['start']);b=min(plan['duration'],row['end'])
        if b<=a:continue
        if out and out[-1]['id']==row['id'] and abs(out[-1]['end']-a)<1e-6:out[-1]['end']=b
        else:out.append({'start':a,'end':b,'id':row['id']})
    return out

def speech_intervals(plan,cfg=None):
    out=[]
    for r in source_words(plan,cfg):
        a=max(0.,r['start']);b=min(plan['duration'],r['end'])
        if b>a:out.append([a,b])
    return out

def build(plan,cfg):
    if not 0<plan['duration']<=MAX_SECONDS:raise ValueError(f'Budget M6 maksimal {MAX_SECONDS} detik per klip; pecah klip lebih panjang')
    s=effective(cfg);state=cfg.audio6;tracks=state.get('track_state',{});out=[];notes=[]
    from .transcript_correction import PROTECTED
    critical=[w for w in source_words(plan,cfg) if re.search(r'\d',w['word']) or set(re.findall(r'\w+',w['word'].casefold()))&set(PROTECTED)]
    for row in state.get('tracks',[]):
        owner='music' if row['role']=='music' else 'sfx' if row['role']=='sfx' else 'voice'
        if not row['enabled'] or row['muted'] or not tracks.get(owner,True) or owner=='sfx' and not s['sfx_enabled']:continue
        for event in events(plan,row):
            if owner=='sfx' and not row['reviewed'] and any(event['start']<w['end'] and event['end']>w['start'] for w in critical):
                raise ValueError('SFX '+row['id']+' menutupi angka/negasi; tinjau cue dan tandai reviewed')
            out.append({**copy.deepcopy(row),**event,'owner':owner})
        if row['beat_snap']:notes.append({'track_id':row['id'],'decision':'explicit beat grid','requested_start':row['start'],'actual_starts':[r['start'] for r in out if r['id']==row['id']]})
    speech=speech_intervals(plan,cfg)+[[r['start'],r['end']] for r in out if r['owner']=='voice']
    return {'version':'4.0.17-m6','settings':s,'events':out,'speech_intervals':speech,'notes':notes,
        'timebase':'output_seconds; original source clock and event samples retained','duration_samples':round(plan['duration']*RATE),
        'revision_context':copy.deepcopy(plan.get('audio6_context',{'source_revision':plan.get('revision',0),'direct_render':True})),
        'snapshot_digest':fingerprint([state,plan.get('audio6_context'),plan.get('editor',{}).get('clock'),plan['spans'],source_words(plan,cfg)]),
        'chain':['source_gain_and_reviewed_cuts','optional_restoration_and_voice_effect','music_SFX_voice_tracks','approved_M5_censor','final_mix_normalization','oversampled_limiter','actual_PCM_and_encoded_meter'],
        'gate_g6':'pending_real_speech_listening'}
