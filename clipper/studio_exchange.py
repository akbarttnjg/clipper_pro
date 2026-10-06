"""C0 records for the exact decisions used by Studio 4's renderer."""
import copy
from pathlib import Path
from . import analysis_adapter as adapter
from .contracts import envelope,fingerprint
from .dependency_cache import asset_id,content_id


def render_words(transcript,document,clip,cfg):
    words=[w for w in transcript['words'] if w['end']>clip['start'] and w['start']<clip['end']]
    def ids(w):return w.get('source_word_ids',[w['word_id']])
    selected={i for w in words for i in ids(w)}
    scoped={**transcript,'words':words,'raw_words':[w for w in transcript['raw_words'] if w['word_id'] in selected]}
    if 'heard_words' in scoped:scoped['heard_words']=[w for w in scoped['heard_words'] if set(ids(w))&selected]
    snapshot=adapter.transcript_snapshot(scoped,cfg,source_id=document['source']['source_id'],transcript_id=document['transcript_id'],
        revision=document['transcript_revision'],input_fingerprint=fingerprint(words),audio_stream_id=cfg.audio_stream_id,
        clip_span=(clip['start'],clip['end']))
    return [{ 'word':t['text'],'start':t['source_start'],'end':t['source_end'],'word_id':t['token_id'],
        'token_id':t['token_id'],'source_word_ids':t['origin_word_ids'],'origin_word_ids':t['origin_word_ids'],
        'manually_edited':t['correction_status']=='manual','timing_status':t.get('timing_status','asr'),
        'alignment_method':t.get('alignment_method')} for t in snapshot['payload']['display_tokens']]


def records(plan,result,document,clip_id,variant_id,cfg,media):
    source_id=media['source_id'];key=result['fingerprint'];revision=plan['revision'];fps={'numerator':plan['fps'],'denominator':1}
    timeline=envelope('EditTimeline',source_id,{'project_id':document['project_id'],'clip_id':clip_id,'variant_id':variant_id,
        'revision':revision,'fps':fps,'spans':plan['spans'],'shots':plan['shots'],
        'actual_broll_events':[{**e,'asset_offset':e.get('source_asset_start',e.get('asset_start',0))} for e in plan.get('broll',[])],
        'skipped_intervals':[e for e in plan.get('broll_schedule',[]) if e['status']!='scheduled'],
        'settings_revision':document['clips'][clip_id]['variants'][variant_id]['timeline_revision'],
        'corrections_revision':document['transcript_revision'],'duration_frames':plan['duration_frames']},key,producer='B-4')
    phrases=copy.deepcopy(plan.get('captions',{}).get('phrases',[]))
    for phrase in phrases:
        phrase.update(phrase_id='phrase-'+fingerprint([variant_id,[w['word_id'] for w in phrase['words']]])[:24],
            token_references=list(dict.fromkeys(t for w in phrase['words'] for t in w.get('token_ids',[w['word_id']]))),
            origin_word_ids=list(dict.fromkeys(i for w in phrase['words'] for i in w.get('word_ids',[]))),
            start_frame=round(phrase['start']*plan['fps']),end_frame=round(phrase['end']*plan['fps']),
            coordinate_space='output_canvas_pixels',width=plan['width'],height=plan['height'])
    captions=envelope('CaptionPlan',source_id,{'variant_id':variant_id,'timeline_revision':revision,'fps':fps,
        'phrases':phrases,'qc':plan['caption_checks'],'animation_timebase':'seconds_relative_to_phrase'},key,producer=adapter.VERSION)
    manifest=envelope('RenderManifest',source_id,{'output_id':result['output_content_id'],'variant_id':variant_id,'revision':revision,
        'renderer_version':result['render_version'],'file':result['absolute_file'],'qc':result['qc'],'status':'validated',
        'dependency_hashes':{'render':key,'project_inputs':result['dependency'],'source':source_id,'working_source':media['payload']['working_content_id'],
            'assets':{e['asset']['path']:asset_id(e['asset']['path'],fresh=True) for e in plan.get('broll',[])},
            'fonts':{p.name:content_id(p) for p in Path(cfg.fonts_dir).glob('*.ttf')}},
        'compatible_editor_evidence':{'status':'not_tested_in_native_editors','structural_report':'Created during project export'}},key,producer='B-4')
    return {'media_context':media,'edit_timeline':timeline,'caption_plan':captions,
        'scene_analysis':adapter.scene_analysis(plan,media,input_fingerprint=key),'render_manifest':manifest}
