"""Stage 4 evidence in source coordinates, separate from output composition.

Face identity is geometric tracking, not biometric recognition. Neural backends
are local, isolated and optional. Uncertain speech never chooses the largest face.
"""
import copy
import math
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from .contracts import fingerprint
from .dependency_cache import content_id
from .storage import read_json, write_json
from . import placement

VERSION = '4.0.4-visual2'
KINDS = ('speaker', 'podcast', 'board', 'screen', 'chart', 'graphic', 'unknown')


def iou(a, b):
    area = placement.overlap(a, b)
    return area/max(1., a[2]*a[3]+b[2]*b[3]-area)


def union(boxes):
    x=min(b[0] for b in boxes);y=min(b[1] for b in boxes)
    return [x,y,max(b[0]+b[2] for b in boxes)-x,max(b[1]+b[3] for b in boxes)-y]


def validate_controls(value, duration):
    if not isinstance(value, dict):raise ValueError('Koreksi visual harus berupa objek')
    allowed={'pins','protected','ocr_edits','speaker_track','speaker_evidence','sam_enabled','sam_box','sam_time','sam_span'}
    if set(value)-allowed:raise ValueError('Bidang koreksi visual tidak dikenal')
    result=copy.deepcopy(value)
    for key in ('pins','protected'):
        rows=result.get(key,[])
        if not isinstance(rows,list) or len(rows)>100:raise ValueError('Maksimal 100 area visual')
        for row in rows:
            if not isinstance(row,dict) or set(row)-{'id','start','end','box','kind'}:raise ValueError('Area visual tidak valid')
            a,b=float(row.get('start',0)),float(row.get('end',duration))
            if not all(math.isfinite(t) for t in (a,b)) or not 0<=a<b<=duration+.05:raise ValueError('Waktu area harus di dalam sumber')
            box=row.get('box')
            if not isinstance(box,list) or len(box)!=4:raise ValueError('Area memakai x y lebar tinggi dalam persen')
            x,y,w,h=map(float,box)
            if not all(math.isfinite(v) for v in (x,y,w,h)) or not (0<=x<100 and 0<=y<100 and 1<=w<=100 and 1<=h<=100 and x+w<=100.001 and y+h<=100.001):raise ValueError('Area harus seluruhnya berada dalam gambar')
            if row.get('kind','crop' if key=='pins' else 'manual') not in ('crop','speaker','material','manual'):raise ValueError('Jenis area tidak valid')
            row.update(start=a,end=b,box=[x,y,w,h],id=str(row.get('id',fingerprint(row)[:16]))[:80])
    track=result.get('speaker_track','auto')
    if not isinstance(track,str) or track!='auto' and not __import__('re').fullmatch(r'face-[0-9]{4}',track):raise ValueError('Identitas pembicara tidak valid')
    if result.get('speaker_evidence') is not None and not __import__('re').fullmatch(r'[0-9a-f]{64}',str(result['speaker_evidence'])):raise ValueError('Identitas bukti wajah tidak valid')
    if 'sam_enabled' in result and type(result['sam_enabled']) is not bool:raise ValueError('Status SAM harus boolean')
    edits=result.get('ocr_edits',{})
    if not isinstance(edits,dict) or len(edits)>100:raise ValueError('Koreksi OCR tidak valid')
    for key,text in edits.items():
        if not isinstance(key,str) or not isinstance(text,str) or len(text)>240:raise ValueError('Koreksi OCR maksimal 240 karakter')
    if 'sam_box' in result:
        checked=validate_controls({'protected':[{'box':result['sam_box']}]},duration)
        result['sam_box']=checked['protected'][0]['box']
    if 'sam_time' in result:
        t=float(result['sam_time'])
        if not math.isfinite(t) or not 0<=t<duration:raise ValueError('Frame SAM harus di dalam sumber')
        result['sam_time']=t
    if 'sam_span' in result and result['sam_span'] is not None:
        span=result['sam_span']
        if not isinstance(span,list) or len(span)!=2:raise ValueError('Rentang SAM memakai mulai dan selesai')
        a,b=map(float,span)
        if not all(math.isfinite(t) for t in (a,b)) or not 0<=a<b<=duration or b-a>6:raise ValueError('Rentang SAM maksimal enam detik di dalam sumber')
        if 'sam_time' in result and not a<=result['sam_time']<b:raise ValueError('Frame prompt SAM harus di dalam rentang mask')
        result['sam_span']=[a,b]
    return result


def pixels(box, W, H):
    return [box[0]*W/100,box[1]*H/100,box[2]*W/100,box[3]*H/100]


def track_faces(rows, *, gap=1.1):
    tracks={};next_id=1;last_time=None
    for row in rows:
        t=row['t']
        # Do not join identities across a shot cut or a discontinuous source span.
        if row.get('cut') or last_time is not None and t-last_time>gap:tracks={}
        previous=[(k,v) for k,v in tracks.items() if t-v['t']<=gap]
        used=set();observations=[]
        for f in sorted(row.get('faces',[]),key=lambda b:b[0]):
            matches=[]
            for key,old in previous:
                if key in used:continue
                b=old['box'];distance=math.hypot(f[0]+f[2]/2-b[0]-b[2]/2,f[1]+f[3]/2-b[1]-b[3]/2)/max(f[2],b[2],1)
                size=min(f[2]*f[3],b[2]*b[3])/max(f[2]*f[3],b[2]*b[3],1)
                if iou(f,b)>=.15 or distance<.70 and size>.5:matches.append((iou(f,b)-distance*.1,key))
            key=max(matches)[1] if matches else f'face-{next_id:04d}'
            if not matches:next_id+=1
            used.add(key);tracks[key]={'box':f,'t':t}
            observations.append({'track_id':key,'box':f,'confidence':float(row.get('face_confidence',{}).get(str(f),.8)),'time':t})
        row['tracks']=observations;last_time=t
    return rows


def merge_ocr(rows, min_confidence=.8):
    groups=[]
    for frame in rows:
        for item in frame.get('ocr',[]):
            if not item.get('text','').strip() or float(item.get('confidence',0))<min_confidence:continue
            norm=' '.join(item['text'].casefold().split())
            group=next((g for g in groups if g['normalized']==norm and frame['t']-g['end']<=2.1 and iou(g['box'],item['box'])>.45),None)
            if not group:
                group={'id':item.get('region_id') or 'ocr-'+fingerprint([norm,frame['t'],item['box']])[:16],'text':item['text'],'normalized':norm,'box':item['box'],
                       'start':frame['t'],'end':frame['t'],'confidence':item['confidence'],'observations':[]};groups.append(group)
            group['end']=frame['t'];group['observations'].append({'time':frame['t'],'box':item['box'],'confidence':item['confidence']})
            group['box']=union([o['box'] for o in group['observations']]);group['confidence']=min(o['confidence'] for o in group['observations'])
    for g in groups:g['confirmed_repeated']=len(g['observations'])>=2
    return groups


def component_runtime(key, cfg):
    from .runtime.state import runtime_root, safe_path
    root=Path(cfg.visual_runtime_root) if cfg.visual_runtime_root else runtime_root()
    try:
        active=read_json(root/'components'/key/'active.json',{}) or {}
        if not isinstance(active,dict) or not active.get('generation'):return None
        folder=safe_path(root/'generations',active['generation'])
        receipt=read_json(folder/'receipt.json',{}) or {}
        if not isinstance(receipt,dict):return None
    except (ValueError,TypeError,OSError):return None
    test=receipt.get('test',{})
    if not isinstance(test,dict):return None
    python=folder/'env'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not receipt.get('installed') or not test.get('passed') or test.get('level')!='sample' or not python.is_file():return None
    return {'directory':str(folder),'python':str(python),'generation':active['generation'],'source_commit':receipt.get('source',{}).get('commit'),
            'model_commit':receipt.get('weights',{}).get('commit'),'test_scope':test.get('detail')}


def runtime_signature(root=None):
    from .runtime.state import runtime_root,safe_path
    root=Path(root) if root else runtime_root();items=[]
    for key in ('yunet','rapidocr','talknet','smolvlm','qwen3-vl','sam2'):
        p=root/'components'/key/'active.json'
        if p.is_file():
            try:
                active=read_json(p,{}) or {};folder=safe_path(root/'generations',active['generation'])
                receipt=folder/'receipt.json'
                items.append([key,active['generation'],content_id(receipt) if receipt.is_file() else None])
            except (ValueError,TypeError,KeyError,OSError):items.append([key,'invalid_metadata',content_id(p)])
    return items


def backend(key, request, cfg, folder):
    runtime=component_runtime(key,cfg)
    if runtime is None:return {'status':'unavailable','component':key,'note':'Lingkungan, bobot dan uji sampel lokal diperlukan'}
    identity=fingerprint([VERSION,key,runtime,request]);cache=Path(folder)/('backend-'+identity+'.json')
    cached=read_json(cache,{}) or {}
    if cached.get('status')=='ready' and all(Path(a).is_file() for a in cached.get('artifacts',[])):return {**cached,'cache_reused':True}
    request={**request,'component':key,'directory':runtime['directory'],'output_dir':str(Path(folder).resolve()),'device':'cpu'}
    incoming=Path(folder)/('request-'+identity+'.json');outgoing=Path(folder)/('result-'+identity+'.json')
    write_json(incoming,request)
    env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'4','TOKENIZERS_PARALLELISM':'false'}
    command=[runtime['python'],str(Path(__file__).with_name('visual_worker.py')),str(incoming),str(outgoing)]
    try:
        result=subprocess.run(command,capture_output=True,timeout=cfg.visual_backend_timeout,env=env)
        data=read_json(outgoing,{}) or {}
        if result.returncode or data.get('status')!='ready':return {'status':'failed','component':key,'note':str(data.get('error','Worker visual gagal'))[-600:]}
        data.update(component=key,provenance=runtime,cache_key=identity,cache_reused=False)
        write_json(cache,data);return data
    except (OSError,subprocess.TimeoutExpired) as exc:return {'status':'failed','component':key,'note':str(exc)[-600:]}


def classify(group):
    face_count=max((len(r.get('tracks',[])) for r in group),default=0)
    panels=sum(bool(r.get('panel')) for r in group)/max(1,len(group))
    text_count=sum(len(r.get('texts',[])) for r in group)/max(1,len(group))
    if panels>=.6:return {'kind':'board','confidence':.78,'reason':'Panel materi konsisten sepanjang sampel; geometri tidak memastikan tulisan tangan'}
    if face_count>=2:return {'kind':'podcast','confidence':.85,'reason':'Dua atau lebih wajah terdeteksi; pembicara aktif memerlukan audio tersinkron'}
    if face_count==1 and text_count<4:return {'kind':'speaker','confidence':.82,'reason':'Satu lintasan wajah tanpa panel materi dominan'}
    if text_count>=4:return {'kind':'screen','confidence':.62,'reason':'Tulisan sumber rapat; layar aplikasi atau chart perlu konfirmasi visual'}
    return {'kind':'unknown','confidence':.35,'reason':'Bukti wajah dan materi terbatas; gambar utuh dipertahankan'}


def speaker(group, active=None, manual='auto'):
    by_id={}
    for row in group:
        for face in row.get('tracks',[]):by_id.setdefault(face['track_id'],[]).append(face)
    summaries=[]
    for key,items in by_id.items():
        summaries.append({'track_id':key,'box':union([f['box'] for f in items]),'center_box':np.median([f['box'] for f in items],axis=0).tolist(),
                          'visibility':len(items)/max(1,len(group)),'confidence':min(f['confidence'] for f in items)})
    credible=[s for s in summaries if s['visibility']>=.70 and s['confidence']>=.65]
    selected=next((s for s in credible if s['track_id']==manual),None) if manual!='auto' else None
    reason='Pilihan pembicara manual' if selected else 'Identitas pembicara belum pasti; seluruh tamu dipertahankan'
    if manual=='auto' and len(credible)==1 and len(summaries)==1:selected=credible[0];reason='Satu lintasan wajah konsisten'
    if manual=='auto' and len(credible)>1 and active and active.get('status')=='ready':
        observations=active.get('scores',[]);rank=[]
        for s in credible:
            scores=[]
            for sample in group:
                if active.get('audio_windows') and not any(w['start']<=sample['t']<w['end'] for w in active['audio_windows']):continue
                near=[r['score'] for r in observations if r['track_id']==s['track_id'] and abs(r['time']-sample['t'])<.12]
                if near:scores.append(float(np.median(near)))
            if len(scores)>=max(2,len(group)*.6):rank.append((float(np.median(scores)),s))
        rank.sort(key=lambda r:r[0],reverse=True)
        if len(rank)>1 and rank[0][0]>=.65 and rank[0][0]-rank[1][0]>=.18:selected=rank[0][1];reason='TalkNet dengan audio dan crop wajah tersinkron'
    return {'selected':selected,'tracks':summaries,'reason':reason,'method':'manual' if selected and manual!='auto' else 'talknet' if selected and reason.startswith('TalkNet') else 'single_track' if selected else 'preserve_all'}


def controls_for(group,cfg,W,H):
    controls=cfg.visual_overrides or {};a,b=group[0]['t'],group[-1]['t']+cfg.visual_interval_s
    boxes=[];pins=[]
    for key,target in [('protected',boxes),('pins',pins)]:
        for p in controls.get(key,[]):
            if p['start']<b and p['end']>a:target.append({**p,'box':pixels(p['box'],W,H)})
    return pins,boxes


def analysis_folder(cfg):
    return Path(cfg.visual_cache_dir or Path(cfg.work_dir)/'visual4')


def collect(media,plan,cfg,info,sampler):
    folder=analysis_folder(cfg);folder.mkdir(parents=True,exist_ok=True)
    intervals=[[s['source_start'],min(s['source_end'],info['duration'])] for s in plan['spans']]
    source_id=content_id(media)
    evidence=Path(cfg.work_dir)/'source-evidence.json'
    evidence_id=cfg.visual_evidence_signature or (content_id(evidence) if evidence.is_file() else None)
    key=fingerprint([VERSION,source_id,intervals,cfg.visual_interval_s,cfg.visual_max_frames,cfg.ocr_enabled,info['width'],info['height'],cfg.visual_runtime_signature or runtime_signature(cfg.visual_runtime_root or None),evidence_id])
    path=folder/('observations-'+key+'.json');cached=read_json(path,{}) or {}
    if cached.get('key')==key:
        rows=cached['rows']
        for r in rows:r['hist']=np.asarray(r['hist'],dtype=np.float32) if r.get('hist') is not None else None
        return rows,{**cached['summary'],'cache_reused':True,'path':str(path)}
    rows=[];total=sum(b-a for a,b in intervals);step=max(cfg.visual_interval_s,total/max(1,cfg.visual_max_frames))
    for a,b in intervals:
        times=np.arange(a+.02,b,step)
        # Always inspect the final source moment, even for a short span.
        if not len(times) or b-times[-1]>.1:times=np.r_[times,max(a,b-.04)]
        for t in times:
            row=sampler(float(t))
            if row:rows.append(row)
    if cfg.ocr_enabled and rows:
        ocr=backend('rapidocr',{'source':str(media),'source_content_id':source_id,
                    'times':[r['t'] for i,r in enumerate(rows) if i%max(1,round(1/step))==0][:120]},cfg,folder)
        for r in rows:r['ocr']=next((f['texts'] for f in ocr.get('frames',[]) if abs(f['time']-r['t'])<.001),r.get('ocr',[]))
    else:ocr={'status':'disabled'}
    # A source OCR region keeps its ID when pins split a shot into shorter groups.
    regions=merge_ocr(rows)
    for row in rows:
        for item in row.get('ocr',[]):
            match=next((g for g in regions if g['normalized']==' '.join(item['text'].casefold().split()) and g['start']<=row['t']<=g['end'] and iou(g['box'],item['box'])>.2),None)
            if match:item['region_id']=match['id']
    previous=None
    for r in rows:
        r['cut']=bool(previous and r['hist'] is not None and previous['hist'] is not None and cv2.compareHist(previous['hist'],r['hist'],cv2.HISTCMP_BHATTACHARYYA)>.53)
        previous=r
    track_faces(rows,gap=step*2.2)
    summary={'version':VERSION,'source_content_id':source_id,'sample_interval_s':step,'sample_count':len(rows),'coverage':'sampled',
             'note':'Sampel mencakup seluruh rentang; bukan pemeriksaan setiap frame.','cache_reused':False,'key':key,'ocr_status':ocr.get('status')}
    serial=copy.deepcopy(rows)
    for r in serial:
        if r.get('hist') is not None:r['hist']=r['hist'].tolist()
    write_json(path,{'key':key,'rows':serial,'summary':summary})
    return rows,{**summary,'path':str(path)}


def active_analysis(media,rows,cfg):
    if cfg.visual_active_speaker=='off':return {'status':'disabled'}
    if max((len(r.get('tracks',[])) for r in rows),default=0)<2:return {'status':'not_needed'}
    windows=[];budget=cfg.visual_talknet_budget_s
    # Windows have source timestamps and cannot bridge a cut or removed silence.
    groups=[];current=[]
    for r in rows:
        if current and (r.get('cut') or r['t']-current[-1]['t']>cfg.visual_interval_s*2.2):groups.append(current);current=[]
        current.append(r)
    if current:groups.append(current)
    for group in groups:
        start=group[0]['t'];end=group[-1]['t']
        while start+1<=end and budget>=1:
            last=min(end,start+3.,start+budget);items=[r for r in group if start-.02<=r['t']<=last+.02]
            ids=sorted({f['track_id'] for r in items for f in r.get('tracks',[])})
            tracks=[{'track_id':key,'observations':[f for r in items for f in r['tracks'] if f['track_id']==key]} for key in ids]
            if len(tracks)>1:windows.append({'start':start,'end':last,'tracks':tracks});budget-=last-start
            start=last
    if not windows:return {'status':'insufficient_evidence'}
    return backend('talknet',{'source':str(media),'source_content_id':content_id(media),'windows':windows},cfg,analysis_folder(cfg))


def split_groups(groups,boundaries,cfg,active):
    cuts={p[t] for p in (cfg.visual_overrides or {}).get('pins',[])+(cfg.visual_overrides or {}).get('protected',[]) for t in ('start','end')}
    if active.get('status')=='ready':
        previous=None
        for window in active.get('audio_windows',[]):
            times=[r for group in groups for r in group if window['start']<=r['t']<=window['end']]
            if not times:continue
            selected=speaker(times,active)['selected'];key=selected['track_id'] if selected else None
            if key!=previous:cuts.add(window['start'])
            # End of measured audio is a real boundary: never extrapolate a winner.
            cuts.add(window['end']);previous=key
    new_groups=[];new_boundaries=[boundaries[0]]
    for i,group in enumerate(groups):
        points=[boundaries[i],*sorted(c for c in cuts if boundaries[i]<c<boundaries[i+1]),boundaries[i+1]]
        for a,b in zip(points,points[1:]):
            subset=[r for r in group if a<=r['t']<b]
            if not subset:
                nearest=min(group,key=lambda r:abs(r['t']-(a+b)/2))
                subset=[{**nearest,'t':a,'tracks':nearest['tracks'] if abs(nearest['t']-a)<.6 else []}]
            new_groups.append(subset);new_boundaries.append(b)
    return new_groups,new_boundaries


def caption_envelopes(plan,cfg):
    """One safe envelope for every shot touched by a phrase, including motion."""
    if cfg.caption_position!='auto' or not cfg.safe_placement:return
    from .typography import groups
    for phrase in groups(plan.get('display_words',plan.get('words',[])),cfg):
        touching=[s for s in plan['shots'] if s['start']<phrase[-1]['end']+.16 and s['end']>phrase[0]['start']]
        if len(touching)<2:continue
        boxes=[b for s in touching for b in placement.protected_boxes(s,cfg.target_w,cfg.target_h)]
        # Include zoom's maximum extent, not only its first frame.
        for s in touching:
            if s.get('zoom_at') is not None:
                for b in placement.protected_boxes(s,cfg.target_w,cfg.target_h):
                    x,y,w,h=b['box'];z=1+cfg.zoom_amount
                    boxes.append({'kind':b['kind'],'box':[cfg.target_w/2+(x-cfg.target_w/2)*z,cfg.target_h/2+(y-cfg.target_h/2)*z,w*z,h*z]})
        selected,pos,clear=placement.choose_panel(boxes,cfg.target_w,cfg.target_h,touching[0].get('caption_panel'))
        for s in touching:
            if clear:s.update(caption_panel=list(selected),position=pos,protected_output=placement.protected_boxes(s,cfg.target_w,cfg.target_h))
            else:placement.reserve_band(s,cfg)
    plan.setdefault('visual_summary',{})['phrase_safety']='union_of_sampled_paths_and_zoom_envelopes'


def describe(media,group,cfg,info,active,allow_vlm=True,source_bounds=None,observation_key=None):
    W,H=info['width'],info['height'];kind=classify(group);choice=speaker(group,active,(cfg.visual_overrides or {}).get('speaker_track','auto'))
    scope=(cfg.visual_overrides or {}).get('speaker_evidence')
    if scope and observation_key!=scope and (cfg.visual_overrides or {}).get('speaker_track','auto')!='auto':
        choice.update(selected=None,method='preserve_all',reason='Pilihan pembicara memakai bukti lama; periksa ulang setelah rentang atau detektor berubah')
    pins,manual=controls_for(group,cfg,W,H);ocr=merge_ocr(group)
    if source_bounds:
        a,b=source_bounds
        pins=[p for p in pins if p['start']<b and p['end']>a]
        manual=[p for p in manual if p['start']<b and p['end']>a]
    edits=(cfg.visual_overrides or {}).get('ocr_edits',{})
    for r in ocr:
        if r['id'] in edits:r.update(text=edits[r['id']],manually_edited=True)
    vlm={'status':'not_needed'}
    if cfg.visual_vlm!='off' and kind['confidence']<.75 and allow_vlm:
        key=cfg.visual_vlm if cfg.visual_vlm!='auto' else ('smolvlm' if component_runtime('smolvlm',cfg) else 'qwen3-vl')
        vlm=backend(key,{'source':str(media),'source_content_id':content_id(media),'time':group[len(group)//2]['t']},cfg,analysis_folder(cfg))
        answer=vlm.get('decision',{})
        if vlm.get('status')=='ready' and answer.get('kind') in KINDS and answer.get('confidence',0)>=.7:kind={**answer,'reason':'Konfirmasi model visual lokal: '+str(answer.get('reason',''))[:240]}
    elif cfg.visual_vlm!='off' and not allow_vlm:vlm={'status':'budget_exhausted','note':'Maksimal tiga frame meragukan per klip'}
    return {'scene':kind,'speaker':choice,'pins':pins,'protected':manual,'ocr':ocr,'vlm':vlm,
            'frame_times':[r['t'] for r in group]}


def report(plan,media,cfg):
    folder=analysis_folder(cfg);folder.mkdir(parents=True,exist_ok=True);shots=[]
    controls=cfg.visual_overrides or {};prompt_time=controls.get('sam_time')
    mask_index=next((i for i,s in enumerate(plan.get('shots',[])) if prompt_time is not None and s['source_start']<=prompt_time<s['source_end']),0 if prompt_time is None else None)
    for index,shot in enumerate(plan.get('shots',[])):
        visual=shot.get('visual',{});times=visual.get('frame_times',[]);t=times[len(times)//2] if times else (shot['source_start']+shot['source_end'])/2
        poster=folder/('frame-'+fingerprint([plan.get('visual_summary',{}).get('source_content_id'),t])[:24]+'.jpg')
        if not poster.is_file():
            cap=cv2.VideoCapture(str(media))
            try:
                cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read()
                if ok:
                    scale=min(1,1100/max(frame.shape[:2]));small=cv2.resize(frame,(round(frame.shape[1]*scale),round(frame.shape[0]*scale)))
                    cv2.imwrite(str(poster),small)
            finally:cap.release()
        entry={k:copy.deepcopy(shot.get(k)) for k in ('source_start','source_end','start','end','rect','face_rect','mode','caption_panel','composition_reason','protected_source','protected_output')}
        entry.update(id='shot-'+fingerprint([shot['source_start'],shot['source_end']])[:16],frame_time=t,visual=visual,poster_path=str(poster) if poster.is_file() else None,
                     coordinate_space='canonical_source_pixels',mask={'status':'disabled'})
        if index==mask_index and controls.get('sam_enabled'):
            selected=visual.get('speaker',{}).get('selected');box=pixels(controls['sam_box'],plan['source']['width'],plan['source']['height']) if controls.get('sam_box') else selected.get('box') if selected else None
            if box:
                request={'source':str(media),'source_content_id':plan.get('visual_summary',{}).get('source_content_id'),
                         'time':prompt_time if prompt_time is not None else t,'box':box}
                span=controls.get('sam_span')
                if span:
                    if shot['source_start']<=span[0]<span[1]<=shot['source_end']:
                        request['span']=span
                    else:
                        entry['mask']={'status':'invalid_range','note':'Rentang mask harus berada di dalam satu adegan sumber'}
                if entry['mask']['status']!='invalid_range':entry['mask']=backend('sam2',request,cfg,folder)
            else:entry['mask']={'status':'needs_box','note':'Tentukan area SAM atau pilih pembicara yang terlihat'}
        shots.append(entry)
    return {'version':VERSION,'summary':copy.deepcopy(plan.get('visual_summary',{})),'shots':shots,
            'source_size':[plan['source']['width'],plan['source']['height']],'output_size':[cfg.target_w,cfg.target_h],
            'note':'SAM opsional: frame acuan atau propagasi rentang terpilih maksimal enam detik. Mask disimpan terpisah; belum dikomposit ke render atau proyek editor.'}
