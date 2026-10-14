"""Per-shot proposals with source protection, honest speaker fallbacks and motion."""
import copy
import math
import numpy as np
from . import camera4_contract as c


def active_evidence(source,observation,settings,cfg,folder):
    if settings['active_speaker']=='off':return {'status':'disabled'}
    windows=[];budget=min(60.,cfg.visual_talknet_budget_s)
    for shot in observation['shots']:
        rows=[r for r in observation['frames'] if r['shot_id']==shot['shot_id']]
        ids=sorted({f['track_id'] for r in rows for f in r['faces']})
        if len(ids)<2:continue
        start=shot['start']
        while start+1<shot['end'] and budget>=1:
            end=min(shot['end'],start+3,budget+start)
            tracks=[{'track_id':i,'observations':[f for r in rows if start-.05<=r['time']<=end+.05 for f in r['faces'] if f['track_id']==i]} for i in ids]
            tracks=[t for t in tracks if len(t['observations'])>=2]
            if len(tracks)>=2:windows.append({'start':start,'end':end,'tracks':tracks});budget-=end-start
            start=end
    if not windows:return {'status':'not_needed_or_insufficient_visual_evidence'}
    from .camera4_observe import backend
    return backend('talknet',{'source':str(source),'source_content_id':observation['media_content_id'],'windows':windows},cfg,folder)


def subjects(rows,regions,width,height):
    groups={}
    for row in rows:
        for f in row['faces']:groups.setdefault(f['track_id'],[]).append(f)
    result=[]
    for ident,items in groups.items():
        # A fixed subject crop includes all measured head positions in the shot.
        x=min(f['box'][0] for f in items);y=min(f['box'][1] for f in items);right=max(f['box'][0]+f['box'][2] for f in items);bottom=max(f['box'][1]+f['box'][3] for f in items)
        result.append({'id':ident,'box':[x,y,right-x,bottom-y],'observations':[{'time':f['time'],'box':f['box']} for f in items],
            'visibility':len(items)/max(1,len(rows)),'confidence':None,'identity':'human_source_region' if any(f.get('association')=='human_source_region' for f in items) else 'geometric_track; not_voice_identity'})
    for region in regions:
        if region['kind']=='subject' and region['id'] not in groups:result.append({'id':region['id'],'box':c.pixels(region['box'],width,height),'observations':[],
            'visibility':1.,'confidence':None,'identity':'human_source_region'})
    return result


def speaker(subjects,words,a,b,active,settings):
    voices=sorted({w['speaker_id'] for w in words if w.get('speaker_id') and w['start']<b and w['end']>a})
    units=[w for w in words if w.get('speaker_id') and w['start']<b and w['end']>a]
    overlap=any(x['speaker_id']!=y['speaker_id'] and min(x['end'],y['end'])-max(x['start'],y['start'])>.05 for i,x in enumerate(units) for y in units[i+1:])
    result={'selected':None,'reason':'no_face_or_detector_unavailable','voice_ids':voices,'overlap':overlap,'confidence':None}
    credible=[s for s in subjects if s['visibility']>=.70]
    if overlap:return {**result,'reason':'overlapping_voices_preserve_grid'}
    mapped=[l['track_id'] for l in settings['speaker_links'] if l['speaker_id'] in voices]
    if len(voices)==1 and len(set(mapped))==1:
        chosen=next((s for s in credible if s['id']==mapped[0]),None)
        if chosen:return {**result,'selected':chosen['id'],'reason':'human_reviewed_voice_face_link'}
        return {**result,'reason':'reviewed_voice_is_offscreen_or_occluded'}
    ranks=[]
    if active.get('status')=='ready':
        for s in credible:
            scores=[r['score'] for r in active.get('scores',[]) if r['track_id']==s['id'] and a<=r['time']<b and any(w['start']<=r['time']<w['end'] for w in active.get('audio_windows',[])) and type(r.get('score')) in (int,float) and math.isfinite(r['score'])]
            if len(scores)>=2:ranks.append((float(np.median(scores)),s['id']))
    ranks.sort(reverse=True)
    if len(ranks)>=2 and ranks[0][0]>=.65 and ranks[0][0]-ranks[1][0]>=.18:return {**result,'selected':ranks[0][1],'reason':'measured_local_ASD_margin; uncalibrated','confidence':None}
    if len(subjects)==1 and len(credible)==1 and not voices:return {**result,'selected':credible[0]['id'],'reason':'single_visible_subject; voice_identity_unknown'}
    return {**result,'reason':'uncertain_active_speaker_preserve_all' if subjects else result['reason']}


def layout(shot,observations,settings,words,active,width,height):
    a,b=shot['start'],shot['end'];rows=[r for r in observations['frames'] if a-.001<=r['time']<b+.001 and r['shot_id']==shot['shot_id']]
    regions=[r for r in settings['regions'] if r['start']<=a+1e-6 and r['end']>=b-1e-6]
    people=subjects(rows,regions,width,height);decision=speaker(people,words,a,b,active,settings)
    protected=[]
    for s in people:
        x,y,w,h=s['box'];left=max(0,x-w*.12);top=max(0,y-h*.28);right=min(width,x+w*1.12);bottom=min(height,y+h*1.12)
        protected.append({'id':s['id'],'kind':'face','box':[left,top,right-left,bottom-top]})
    for r in regions:
        if r['kind']!='subject':protected.append({'id':r['id'],'kind':r['kind'],'box':c.pixels(r['box'],width,height)})
    for row in rows:
        for i,ocr in enumerate(row.get('ocr',[])):
            if ocr.get('confidence',0)>=.8 and ocr.get('box'):protected.append({'id':'ocr-'+str(i),'kind':'ocr','box':c.box(ocr['box'],width,height),'text':ocr.get('text'),'confidence':ocr['confidence']})
    material=[r['box'] for r in protected if r['kind'] in ('material','hud','ocr')]
    locked=next((c.pixels(r['box'],width,height) for r in regions if r['kind']=='crop'),None)
    area=[0,0,width,height];main=None
    if material:
        x=min(r[0] for r in material);y=min(r[1] for r in material);right=max(r[0]+r[2] for r in material);bottom=max(r[1]+r[3] for r in material);main=[x,y,right-x,bottom-y]
    kind=settings['layout'];override=next((o for o in settings['shot_overrides'] if o['shot_id']==shot['shot_id']),None)
    if override:
        kind=override['layout']
        if override.get('subject_ids'):
            if any(i not in {s['id'] for s in people} for i in override['subject_ids']):raise ValueError('ID subjek override tidak ditemukan pada shot')
            people=[s for s in people if s['id'] in override['subject_ids']]
    if kind=='auto':kind='screen' if main and settings['profile']!='gaming' else 'gameplay' if settings['profile']=='gaming' and main else 'grid' if len(people)>1 and decision['selected'] is None else 'subject' if decision['selected'] else 'fit'
    fallback=[]
    if len(rows)>=2 and len({r.get('content_id') for r in rows})==1:fallback.append('sampled_pixels_unchanged_preserve_source_geometry')
    if kind=='subject' and decision['selected'] is None:kind='grid' if len(people)>1 else 'fit';fallback.append('subject_unconfirmed_preserve_visible_source')
    if kind=='grid' and len(people)<2:kind='fit';fallback.append('insufficient_distinct_subjects')
    if kind in ('screen','gameplay') and main is None:main=area;fallback.append('material_unconfirmed_full_source')
    if kind=='pip' and (not people or not main):kind='fit';fallback.append('pip_needs_disjoint_reviewed_material_and_subject')
    if len(people)>4 and kind=='grid':kind='fit';fallback.append('more_than_four_subjects_preserve_frame')
    return {'shot_id':shot['shot_id'],'start':a,'end':b,'layout':kind,'subjects':people,'speaker':decision,
        'source_size':[width,height],'material':main,'crop_lock':locked,'protected_source':protected,'fallbacks':fallback,
        'background':settings['background'],'motion':settings['motion'],'keyframes':settings['keyframes'],'safe_margins':settings['safe_margins']}


def build(observation,settings,words,active):
    width,height=observation['source_size'];segments=[]
    for shot in observation['shots']:
        boundaries={shot['start'],shot['end']}
        for r in settings['regions']:
            boundaries.update(t for t in (r['start'],r['end']) if shot['start']<t<shot['end'])
        for win in active.get('audio_windows',[]):boundaries.update(t for t in (win['start'],win['end']) if shot['start']<t<shot['end'])
        last_voice=None
        for w in sorted(words,key=lambda w:w['start']):
            voice=w.get('speaker_id')
            if voice and last_voice and voice!=last_voice and shot['start']<w['start']<shot['end']:boundaries.add(w['start'])
            if voice:last_voice=voice
        if settings['mask']:boundaries.update(t for t in (settings['mask']['start'],settings['mask']['end']) if shot['start']<t<shot['end'])
        points=sorted(boundaries)
        for a,b in zip(points,points[1:]):segments.append(layout({**shot,'start':a,'end':b},observation,settings,words,active,width,height))
    if len(segments)>1000:raise ValueError('Terlalu banyak segmen layout; pilih rentang lebih pendek')
    return segments


def layers(segment,W,H,settings):
    width,height=segment['source_size'];area=[0,0,width,height];kind=segment['layout'];people=segment['subjects'];main=segment['material'];result=[]
    # Reserve a real caption band before M5. Material and heads stay out of it.
    left,top,right,bottom=settings['safe_margins']
    sx=math.ceil(W*left/2)*2;sy=math.ceil(H*top/2)*2
    ex=math.floor(W*(1-right)/2)*2;ey=math.floor(H*(1-bottom)/2)*2
    cw=ex-sx;safe_height=ey-sy
    caption_height=round(H*.18/2)*2;canvas=safe_height-caption_height
    if cw<2 or canvas<2:raise ValueError('Area aman terlalu kecil untuk gambar dan subtitle')
    def head(subject):
        return next((p['box'] for p in segment['protected_source'] if p['kind']=='face' and p['id']==subject['id']),subject['box'])
    def add(region,viewport,subject=None):
        region=c.box(region,width,height);x,y,w,h=region;left=int(x)//2*2;top=int(y)//2*2;right=min(width,math.ceil((x+w)/2)*2);bottom=min(height,math.ceil((y+h)/2)*2)
        region=[left,top,max(2,right-left),max(2,bottom-top)]
        path=[]
        if settings['motion']=='track' and subject and subject.get('observations'):
            first=subject['observations'][0]['box'];region=c.crop(area,first,viewport[2]/viewport[3]);path=c.smoothed_path(subject['observations'],region,settings,width,height)
            if any(c.intersection(row['box'],head(subject))!=head(subject) for row in path):region=area;path=[]
        if settings['motion']=='manual' and settings['keyframes']:path=[{'time':r['time'],'box':c.pixels(r['box'],width,height)} for r in settings['keyframes']]
        if subject:
            required=head(subject)
            if c.intersection(region,required)!=required:
                if segment.get('crop_lock'):raise ValueError('Crop terkunci memotong kepala subjek yang dipilih')
                region=area
            if any(c.intersection(point['box'],required)!=required for point in path):raise ValueError('Keyframe memotong kepala subjek yang dipilih; periksa kamera manual')
        viewport=[int(v)//2*2 for v in viewport];viewport[0]+=sx;viewport[1]+=sy
        if not (viewport[2]>=2 and viewport[3]>=2 and sx<=viewport[0] and sy<=viewport[1] and viewport[0]+viewport[2]<=ex and viewport[1]+viewport[3]<=sy+canvas):raise ValueError('Viewport kamera keluar dari area aman')
        result.append({'source_crop':region,'viewport':viewport,'path':path,'subject_id':subject['id'] if subject else None})
    if segment.get('crop_lock'):
        locked=segment['crop_lock']
        if any(p['kind'] in ('material','hud','ocr','protected') and c.intersection(locked,p['box'])!=p['box'] for p in segment['protected_source']):raise ValueError('Crop terkunci memotong materi/area terlindungi; periksa area manual sebelum render')
        selected=next((p for p in people if p['id']==segment['speaker']['selected']),None)
        add(locked,[0,0,cw,canvas],selected)
    elif kind=='grid':
        columns=2 if W>=H or len(people)>2 else 1;rows=math.ceil(len(people)/columns);vw=cw//columns//2*2;vh=canvas//rows//2*2
        for i,p in enumerate(people):
            region=p['box'] if p.get('identity')=='human_source_region' else head_region(p['box'],width,height)
            add(region,[(i%columns)*vw,(i//columns)*vh,vw,vh],p)
    elif kind in ('screen','gameplay'):
        if people:
            if W>=H:
                side=cw*.27;add(main,[side,0,cw-side,canvas]);add(c.crop(area,head(people[0]),side/canvas),[0,0,side,canvas],people[0])
            else:
                split=canvas*.65;add(main,[0,0,cw,split]);add(c.crop(area,head(people[0]),cw/(canvas-split)),[0,split,cw,canvas-split],people[0])
        else:add(main,[0,0,cw,canvas])
    elif kind=='pip':
        add(main,[0,0,cw,canvas]);inset=[cw*.73,canvas*.04,cw*.23,canvas*.28]
        projected=[c.projected(main,[0,0,cw,canvas],p['box']) for p in segment['protected_source']]
        if any(p and c.intersection(p,inset)[2]*c.intersection(p,inset)[3]>0 for p in projected):
            # Do not cover source HUD or writing with an inset; use separate tile.
            side=cw*.26;result=[];add(main,[0,0,cw-side,canvas]);add(c.crop(area,head(people[0]),side/canvas),[cw-side,0,side,canvas],people[0])
        else:add(c.crop(area,head(people[0]),inset[2]/inset[3]),inset,people[0])
    elif kind=='subject':
        chosen=next(p for p in people if p['id']==segment['speaker']['selected']);region=c.crop(area,head(chosen),cw/canvas)
        if c.intersection(region,head(chosen))!=head(chosen) or any(p['kind']!='face' and c.intersection(region,p['box'])!=p['box'] for p in segment['protected_source']):add(area,[0,0,cw,canvas],chosen)
        else:add(region,[0,0,cw,canvas],chosen)
    else:add(area,[0,0,cw,canvas])
    for p in segment['protected_source']:
        if p['kind'] in ('material','hud','ocr','protected') and not any(all(c.intersection(r,p['box'])==p['box'] for r in [layer['source_crop'],*[point['box'] for point in layer['path']]]) for layer in result):raise ValueError('Crop/keyframe memotong area materi atau HUD; periksa kamera sebelum mengaktifkannya')
    protected=[]
    for layer in result:
        # Protect the complete sampled motion envelope as well as static boxes.
        regions=[layer['source_crop'],*[r['box'] for r in layer['path']]]
        for region in regions:
            for p in segment['protected_source']:
                projected=c.projected(region,layer['viewport'],p['box'])
                if projected:protected.append({'kind':p['kind'],'box':projected})
    safe=[sx,sy,cw,safe_height]
    panel_left=max(W*.07,sx);panel_right=min(W*.93,ex)
    panel_top=sy+canvas+H*.01;panel_bottom=min(ey,sy+canvas+caption_height-H*.02)
    panel=[panel_left,panel_top,panel_right-panel_left,panel_bottom-panel_top]
    return {'layers':result,'protected_output':protected,'caption_panel':panel,'caption_height':caption_height,'safe_rect':safe}


def head_region(face,width,height):
    x,y,w,h=face;left=max(0,x-w*.45);top=max(0,y-h*.65);right=min(width,x+w*1.45);bottom=min(height,y+h*4)
    return [left,top,right-left,bottom-top]
