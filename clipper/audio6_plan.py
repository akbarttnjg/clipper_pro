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
        if b>a:out.append({'start':a,'end':b,'asset_start':row['asset_start']+a-start,'asset_seconds':b-a,'rate':1.,'reverse':False,'clock':'output'})
    else:
        for piece in slices(plan):
            if piece.get('kind')=='freeze':continue  # Same silence policy as the source voice.
            left=max(start,piece['source_start']);right=min(end,piece['source_end'])
            if left>=right:continue
            scale=(piece['end']-piece['start'])/(piece['source_end']-piece['source_start'])
            if piece['reverse']:a=piece['start']+(piece['source_end']-right)*scale;b=piece['start']+(piece['source_end']-left)*scale
            else:a=piece['start']+(left-piece['source_start'])*scale;b=piece['start']+(right-piece['source_start'])*scale
            b=min(duration,b)
            if b>a:out.append({'start':a,'end':b,'asset_start':row['asset_start']+left-start,'asset_seconds':right-left,'rate':1/scale,'reverse':piece['reverse'],'clock':'M1_source_mapping','slice':piece['id']})
    return [{**r,'start_sample':round(r['start']*RATE),'end_sample':round(r['end']*RATE),'requested_start':row['start'],'beat_snapped':row['beat_snap']} for r in out]

def speech_intervals(plan):
    rows=plan.get('display_words',plan.get('words',[]));out=[]
    for r in rows:
        # The plan's outer word clocks are already output times. Nested
        # alignment may retain source evidence, so it is never interpreted here.
        a=max(0.,r['start']);b=min(plan['duration'],r['end'])
        if b>a:out.append([a,b])
    return out

def build(plan,cfg):
    if not 0<plan['duration']<=MAX_SECONDS:raise ValueError(f'Budget M6 maksimal {MAX_SECONDS} detik per klip; pecah klip lebih panjang')
    s=effective(cfg);state=cfg.audio6;tracks=state.get('track_state',{});out=[];notes=[]
    from .transcript_correction import PROTECTED
    critical=[w for w in plan.get('display_words',plan.get('words',[])) if re.search(r'\d',w['word']) or set(re.findall(r'\w+',w['word'].casefold()))&set(PROTECTED)]
    for row in state.get('tracks',[]):
        owner='music' if row['role']=='music' else 'sfx' if row['role']=='sfx' else 'voice'
        if not row['enabled'] or row['muted'] or not tracks.get(owner,True) or owner=='sfx' and not s['sfx_enabled']:continue
        for event in events(plan,row):
            if owner=='sfx' and not row['reviewed'] and any(event['start']<w['end'] and event['end']>w['start'] for w in critical):
                raise ValueError('SFX '+row['id']+' menutupi angka/negasi; tinjau cue dan tandai reviewed')
            out.append({**copy.deepcopy(row),**event,'owner':owner})
        if row['beat_snap']:notes.append({'track_id':row['id'],'decision':'explicit beat grid','requested_start':row['start'],'actual_starts':[r['start'] for r in out if r['id']==row['id']]})
    speech=speech_intervals(plan)+[[r['start'],r['end']] for r in out if r['owner']=='voice']
    return {'version':'4.0.17-m6','settings':s,'events':out,'speech_intervals':speech,'notes':notes,
        'timebase':'output_seconds; original source clock and event samples retained','duration_samples':round(plan['duration']*RATE),
        'revision_context':copy.deepcopy(plan.get('audio6_context',{'source_revision':plan.get('revision',0),'direct_render':True})),
        'snapshot_digest':fingerprint([state,plan.get('audio6_context'),plan.get('editor',{}).get('clock'),plan['spans'],plan.get('display_words',plan.get('words',[]))]),
        'chain':['source_gain_and_reviewed_cuts','optional_restoration_and_voice_effect','music_SFX_voice_tracks','approved_M5_censor','final_mix_normalization','oversampled_limiter','actual_PCM_and_encoded_meter'],
        'gate_g6':'pending_real_speech_listening'}
