"""M6 is opt-in per variant and uses M0 revisions, locks, history and M5 assets."""
import copy
from dataclasses import replace
from .audio6_contract import VERSION,DEFAULTS,effective,settings,tracks

def configure(service,doc,cid,vid,cfg):
    if not cid:return cfg
    variant=service.variant(doc,cid,vid);saved=variant.get('audio6')
    if saved is None:return cfg
    if not saved.get('enabled'):return replace(cfg,audio6=None)
    from .editor_contract import track_state
    from .finishing5_service import assets
    state=track_state(variant.get('editor',{}));values={**effective(replace(cfg,audio6=None)),**settings(saved.get('settings',{}))};resolved=[]
    for row in tracks(saved.get('tracks',[])):
        owner='music' if row['role']=='music' else 'sfx' if row['role']=='sfx' else 'voice'
        if row['enabled'] and not row['muted'] and state[owner]['enabled'] and (owner!='sfx' or values['sfx_enabled']):
            a=assets(service).get(row['asset_id'])
            if a['kind'] not in ('audio','video'):raise ValueError('Track M6 memerlukan aset audio/video bersuara')
            if a['permission']=='unknown':raise ValueError('Lengkapi izin aset audio: '+a['name'])
            row['asset']=a
        resolved.append(row)
    return replace(cfg,audio_normalize=values['normalize'],audio_target_lufs=values['target_lufs'],audio_peak_db=values['peak_db'],join_fade_ms=values['smooth_ms'],
        audio6={'enabled':True,'settings':values,'tracks':resolved,'track_state':{k:v['enabled'] for k,v in state.items()},'revision':saved.get('revision',0),'source_speech':copy.deepcopy([w for w in service.transcript(doc,cid,vid)['words'] if w['end']>doc['clips'][cid]['start'] and w['start']<doc['clips'][cid]['end']]) if doc.get('transcript_id') else []})

def affected_tracks(service,doc,cid,vid,op):
    kind=op['op']
    if kind=='m6_cleanup':return {'video','voice','captions'}
    before=service.config(doc,cid,vid);candidate=copy.deepcopy(doc)
    apply_command(service,candidate,cid,vid,{k:v for k,v in op.items() if k not in ('targets','scope')},doc.get('revision',0))
    after=service.config(candidate,cid,vid)
    b=before.audio6 or {};a=after.audio6 or {}
    if bool(a)!=bool(b):return {'voice','music','sfx'}
    changed={k for k in DEFAULTS if effective(before)[k]!=effective(after)[k]}
    out=set()
    if changed&{'normalize','target_lufs','peak_db','limiter'}:out|={'voice','music','sfx'}
    if changed&{'ducking','duck_db','duck_attack_ms','duck_release_ms','separation_background_db'}:out.add('music')
    if 'sfx_enabled' in changed:out.add('sfx')
    if changed&{'separation','model_directory','model_name'}:out|={'voice','music'}
    if changed-set({'ducking','duck_db','duck_attack_ms','duck_release_ms','separation_background_db','sfx_enabled','export_stems','target_lufs','peak_db','normalize','limiter'}):out.add('voice')
    for role,owner in [('music','music'),('sfx','sfx'),('voiceover','voice'),('reaction','voice'),('dubbing','voice')]:
        strip=lambda state:[{k:v for k,v in r.items() if k!='asset'} for r in state.get('tracks',[]) if r['role']==role]
        if strip(a)!=strip(b):
            out.add(owner)
            if owner=='voice' and (effective(before)['ducking'] or effective(after)['ducking']):out.add('music')
    return out

def apply_command(service,doc,cid,vid,op,revision):
    kind=op.get('op','')
    if not kind.startswith('m6_'):return None
    if not cid:raise ValueError('Pilih klip dan rasio M6')
    if kind=='m6_cleanup':
        from .audio6_cleanup import apply
        return apply(service,doc,cid,vid,op)
    if op.get('targets') is not None or op.get('scope')=='project':
        from .editor_service import targets,check_lock
        requested=op.get('targets') if op.get('targets') is not None else [{'clip_id':c,'variant_id':v} for c,clip in doc['clips'].items() if clip.get('included',True) for v in clip['variants']]
        selected=targets(service,doc,cid,vid,{'targets':requested});command={k:v for k,v in op.items() if k not in ('targets','scope')}
        for c,v in selected:check_lock(service,doc,c,v,command)
        touched=[]
        for c,v in selected:touched.extend(apply_command(service,doc,c,v,command,revision)['touched'])
        return {'touched':touched}
    v=service.variant(doc,cid,vid);s=v.setdefault('audio6',{'enabled':False,'settings':{},'tracks':[]})
    if kind=='m6_enable':
        if type(op.get('enabled')) is not bool:raise ValueError('Enabled M6 harus boolean')
        s['enabled']=op['enabled']
    elif kind=='m6_settings':s['settings'].update(settings(op.get('values')))
    elif kind=='m6_reset':
        keys=op.get('keys')
        if not isinstance(keys,list) or not keys or set(keys)-set(DEFAULTS):raise ValueError('Pilih field reset M6')
        for key in keys:s['settings'].pop(key,None)
    elif kind=='m6_tracks':s['tracks']=tracks(op.get('values'))
    else:raise ValueError('Perintah M6 tidak dikenal')
    configure(service,doc,cid,vid,service.base);s['revision']=revision+1
    return {'touched':[(cid,vid)]}

def snapshot(service,pid,cid,vid):
    from .finishing5_service import assets
    from .audio6_cleanup import proposals
    from .audio6_models import availability
    from .storage import read_json
    doc=service.store.get(pid);variant=service.variant(doc,cid,vid);cfg=service.config(doc,cid,vid);s=variant.get('audio6',{});values={**effective(cfg),**settings(s.get('settings',{}))}
    review=copy.deepcopy(s.get('review',{}))
    if review:
        review['stale']=review.get('dependency')!=service.dependency(doc,cid,vid)
        for key in ('master','before','processed','stem_archive','report_path'):
            if review.get(key):review[key+'_url']=service.register_file(pid,review[key])
    final=variant.get('result',{});plan=read_json(final.get('plan_path',''),{})
    final_audio=copy.deepcopy(plan.get('audio6',{}))
    for key in ('master','stem_archive'):
        if final_audio.get(key):final_audio[key+'_url']=service.register_file(pid,final_audio[key])
    if final_audio:final_audio['stale']=final.get('dependency')!=service.dependency(doc,cid,vid)
    return {'version':VERSION,'project_id':pid,'revision':doc['revision'],'enabled':s.get('enabled',False),
        'settings':values,'tracks':s.get('tracks',[]),'review':review,'final_audio':final_audio,
        'assets':[{**a,'url':service.register_file(pid,a['path'])} for a in assets(service).list() if a['kind'] in ('audio','video')],
        'model':availability(values),'cleanup':proposals(service,doc,cid,vid) if doc.get('transcript_id') else {'proposals':[]},
        'normalization_target_active':bool(cfg.audio6 and values['normalize']),'source_transcript_unchanged':True,
        'gate_g6':'pending_real_speech_listening'}
