"""Sparse M5 overrides, explicit kit revisions and source-clock finishing layers."""
import copy
from dataclasses import replace
from .finishing5_contract import VERSION,DEFAULTS,LEGACY,FIELDS,PRESETS,TEMPLATES,style,layers,effective
from .contracts import fingerprint
def assets(service):
    from .finishing5_assets import Assets
    if not hasattr(service,'_assets5'):service._assets5=Assets(service)
    return service._assets5
def origins(service,doc,cid,vid):
    v=service.variant(doc,cid,vid);s=v.get('finishing5',{});out={k:'inherited' for k in FIELDS}
    for layer in ('profile','brand'):
        for k in v.get('style_layers',{}).get(layer,{}):
            if k in out:out[k]=layer
    for layer in ('profile','brand'):
        for k in s.get('layers',{}).get(layer,{}):out[k]=layer
    for k in doc.get('settings_explicit_keys',[]):
        if k in out:out[k]='project'
    for k in doc['clips'][cid].get('settings',{}):
        if k in out:out[k]='clip'
    for k in v.get('override_keys',[]):
        if k in out:out[k]='manual'
    for k in v.get('settings',{}):
        if k in out and k not in v.get('override_keys',[]):out[k]='variant_saved'
    for k in s.get('style',{}):out[k]='manual'
    return out
def configure(service,doc,cid,vid,cfg):
    if not cid:return cfg
    v=service.variant(doc,cid,vid);state=v.get('finishing5',{})
    if not state.get('enabled'):
        # M5-only font IDs and Raster remain saved for reactivation. The
        # legacy engine receives compatible selections while M5 is disabled.
        from .font_catalog import FONTS
        saved=state.get('legacy_compatible',{});fallback={}
        for key,default in (('font_main','dm_sans'),('font_accent','dm_serif_italic')):
            if getattr(cfg,key) not in FONTS:fallback[key]=saved.get(key) if saved.get(key) in FONTS else default
        if cfg.caption_renderer=='raster':fallback['caption_renderer']=saved.get('caption_renderer','ass') if saved.get('caption_renderer','ass') in ('ass','auto','remotion') else 'ass'
        return replace(cfg,**fallback) if fallback else cfg
    combined={}
    for layer in ('profile','brand'):combined.update(state.get('layers',{}).get(layer,{}))
    for k in LEGACY:
        if k in doc.get('settings_explicit_keys',[]):combined[k]=doc['settings'][k]
        if k in doc['clips'][cid].get('settings',{}):combined[k]=doc['clips'][cid]['settings'][k]
        if k in v.get('settings',{}):combined[k]=v['settings'][k]
    combined.update(state.get('style',{}));style(combined);values={k:val for k,val in combined.items() if k in LEGACY};extra={**copy.deepcopy(DEFAULTS),**{k:val for k,val in combined.items() if k not in LEGACY}}
    from .editor_contract import track_state
    illustration_enabled=track_state(v.get('editor',{}))['illustration']['enabled']
    folder=assets(service).fonts_folder([values.get('font_main',cfg.font_main),values.get('font_accent',cfg.font_accent),*extra['fallback_fonts']],cfg.fonts_dir);resolved=[]
    for r in state.get('decorations',[]):
        if not illustration_enabled or not r.get('enabled',True) or r.get('opacity',1.)==0:continue
        row=copy.deepcopy(r)
        if row['kind']=='lower_third':
            speaker=next((s for s in extra['speaker_styles'] if s['speaker_id']==row['speaker_id']),None)
            if not speaker:raise ValueError('Identitas lower-third belum disetujui')
            row['text']=row.get('text') or speaker['label']
            if not row['text']:raise ValueError('Nama lower-third diperlukan')
        if row.get('asset_id'):
            a=assets(service).get(row['asset_id'])
            if a['permission']=='unknown':raise ValueError('Lengkapi izin aset: '+a['name'])
            if row['kind']=='video' and a['kind']!='video' or row['kind'] in ('logo','image') and a['kind']!='image':raise ValueError('Jenis aset tidak sesuai layer')
            row['asset']=a
        resolved.append(row)
    font_assets=[assets(service).get(k) for k in dict.fromkeys([values.get('font_main',cfg.font_main),values.get('font_accent',cfg.font_accent),*extra['fallback_fonts']]) if k.startswith('font-')]
    return replace(cfg,**values,fonts_dir=folder,finishing5=dict(enabled=True,style=extra,decorations=resolved,illustration_enabled=illustration_enabled,font_assets=font_assets,kit=state.get('kit'),origins=origins(service,doc,cid,vid)))
def snapshot(service,pid,cid,vid):
    d=service.store.get(pid);v=service.variant(d,cid,vid);cfg=service.config(d,cid,vid);state=v.get('finishing5',{});a=assets(service)
    from .font_catalog import FONTS
    fonts=[dict(id=k,**r,source='bundled') for k,r in FONTS.items()]+[dict(id=r['id'],**r['metadata'],label=r['name'],source='local_import') for r in a.list() if r['kind']=='font']
    gallery=copy.deepcopy(state.get('gallery',{}))
    for r in gallery.get('items',[]):r['url']=service.register_file(pid,r.get('absolute_file'));r['stale']=gallery.get('dependency')!=service.dependency(d,cid,vid)
    cover=copy.deepcopy(state.get('cover'))
    if cover:cover['url']=service.register_file(pid,cover.get('path'));cover['stale']=cover.get('dependency')!=service.dependency(d,cid,vid)
    asset_rows=[{**r,'url':service.register_file(pid,r['path'])} for r in a.list()]
    return dict(version=VERSION,project_id=pid,revision=d['revision'],enabled=state.get('enabled',False),style=effective(cfg),origins=origins(service,d,cid,vid),decorations=state.get('decorations',[]),fonts=fonts,assets=asset_rows,kits=a.kits(),templates=TEMPLATES,presets=PRESETS,gallery=gallery,cover=cover,source_caption_detection=source_caption_candidates(service,d,cid,vid,cfg))
def apply_command(service,doc,cid,vid,op,revision):
    kind=op.get('op','')
    if not kind.startswith('m5_'):return None
    if not cid:raise ValueError('Pilih klip M5')
    if op.get('targets') is not None or op.get('scope')=='project':
        from .editor_service import targets,check_lock
        requested=op.get('targets') if op.get('targets') is not None else [{'clip_id':c,'variant_id':v} for c,clip in doc['clips'].items() if clip.get('included',True) for v in clip['variants']]
        selected=targets(service,doc,cid,vid,{'targets':requested,'include_excluded':op.get('include_excluded',False)});touched=[]
        command={k:v for k,v in op.items() if k not in ('targets','scope')}
        for c,v in selected:check_lock(service,doc,c,v,command)
        for c,v in selected:touched.extend(apply_command(service,doc,c,v,command,revision)['touched'])
        return {'touched':touched}
    v=service.variant(doc,cid,vid)
    if 'finishing5' not in v:
        legacy=service.config(doc,cid,vid)
        v['finishing5']=dict(enabled=True,style={},layers={},decorations=[],legacy_compatible={k:getattr(legacy,k) for k in ('font_main','font_accent','caption_renderer')})
    s=v['finishing5']
    if kind=='m5_enable':
        if type(op.get('enabled')) is not bool:raise ValueError('Enabled harus boolean')
        s['enabled']=op['enabled']
    elif kind=='m5_style':
        values=style(op.get('values'));current=effective(service.config(doc,cid,vid))
        for k,val in values.items():
            if current.get(k)==val:continue
            if k.endswith('_hex') and isinstance(val,str) and str(current.get(k)).lower()==val.lower():continue
            if k in LEGACY:v.setdefault('settings',{})[k]=val;v['override_keys']=sorted(set(v.get('override_keys',[]))|{k})
            else:s.setdefault('style',{})[k]=val
        s['enabled']=True
    elif kind=='m5_reset':
        keys=op.get('keys')
        if not isinstance(keys,list) or not keys or set(keys)-FIELDS:raise ValueError('Pilih field reset yang valid')
        for k in keys:
            if k in LEGACY:v.get('settings',{}).pop(k,None);v['override_keys']=sorted(set(v.get('override_keys',[]))-{k})
            else:s.get('style',{}).pop(k,None)
    elif kind in ('m5_preset','m5_kit'):
        if kind=='m5_preset':
            p=next((r for r in PRESETS if r['id']==op.get('preset_id')),None)
            if not p:raise ValueError('Preset tidak dikenal')
            values=p['values'];layer='profile'
        else:
            kit=assets(service).kit(op.get('kit_id'))
            if kit['revision']!=op.get('kit_revision'):raise ValueError('Kit berubah; tinjau revision terbaru')
            for key,digest in kit['asset_digests'].items():
                if assets(service).get(key)['sha256']!=digest:raise ValueError('Digest aset kit berubah')
            values=kit.get('effective_style',kit['style']);layer='brand';s['kit']={k:kit.get(k) for k in ('id','revision','name','parent_id','parent_revision','asset_digests','asset_metadata','glossary','license')}
            if op.get('include_layers',True):s['decorations']=copy.deepcopy(kit['layers'])
        if type(op.get('replace_manual',False)) is not bool:raise ValueError('Replace manual harus boolean')
        if op.get('replace_manual'):
            for k in values:v.get('settings',{}).pop(k,None);s.get('style',{}).pop(k,None)
            v['override_keys']=sorted(set(v.get('override_keys',[]))-set(values))
        s.setdefault('layers',{})[layer]=copy.deepcopy(values);s['enabled']=True
    elif kind=='m5_layers':
        s['decorations']=layers(op.get('values'))
        if any(r['end']>doc['source']['info']['duration']+.001 for r in s['decorations']):raise ValueError('Layer di luar durasi sumber')
    else:raise ValueError('Perintah M5 tidak dikenal')
    cfg=configure(service,doc,cid,vid,service.base);approved={r['speaker_id'] for r in effective(cfg)['speaker_styles']}
    if any(r['kind']=='lower_third' and r['speaker_id'] not in approved for r in s.get('decorations',[])):raise ValueError('Speaker lower-third belum disetujui')
    s['revision']=revision+1;return {'touched':[(cid,vid)]}
def output_rect(row,W,H):
    x,y,w,h=[row['rect'][i]*(W if i%2==0 else H)/100 for i in range(4)];p=min(W,H)*.04;a=row.get('anchor','manual')
    if a=='top_left':x,y=p,p
    elif a=='top_right':x,y=W-p-w,p
    elif a=='bottom_left':x,y=p,H-p-h
    elif a=='bottom_right':x,y=W-p-w,H-p-h
    elif a=='center':x,y=(W-w)/2,(H-h)/2
    return [round(x),round(y),round(w),round(h)]
def map_time(plan,source_start,source_end):
    from .editor_contract import output_to_source
    fps=plan['fps'];clock=plan.get('editor',{}).get('clock');windows=[];start=None
    for frame in range(round(plan['duration']*fps)):
        t=frame/fps
        if clock:r=output_to_source(clock,t);src=r['source_time'] if r else None
        else:
            span=next((s for s in plan['spans'] if s['start']<=t<s['end']),None);src=span['source_start']+t-span['start'] if span else None
        on=src is not None and source_start<=src<source_end
        if on and start is None:start=frame
        if not on and start is not None:windows.append((start/fps,frame/fps));start=None
    if start is not None:windows.append((start/fps,round(plan['duration']*fps)/fps))
    return windows
def source_at(plan,t):
    from .editor_contract import output_to_source
    if plan.get('editor',{}).get('clock'):
        r=output_to_source(plan['editor']['clock'],t);return r['source_time'] if r else None
    s=next((s for s in plan['spans'] if s['start']<=t<s['end']),None)
    return s['source_start']+t-s['start'] if s else None
def caption_config(plan,cfg):
    if not cfg.finishing5:return cfg
    state=copy.deepcopy(cfg.finishing5);mapped=[]
    for row in state['style'].get('source_captions',[]):
        for a,b in map_time(plan,row['start'],row['end']):mapped.append({**row,'start':a,'end':b})
    state['style']['source_captions']=mapped;return replace(cfg,finishing5=state)
def map_layers(plan,cfg):
    if not cfg.finishing5:return
    from .finishing5_plan import overlap
    out=[];W,H=plan['width'],plan['height']
    for row in cfg.finishing5.get('decorations',[]):
        for a,b in map_time(plan,row['start'],row['end']):out.append({**copy.deepcopy(row),'source_interval':[row['start'],row['end']],'start':a,'end':b,'output_rect':output_rect(row,W,H)})
    for r in out:
        x,y,w,h=r['output_rect']
        if x<0 or y<0 or x+w>W or y+h>H:raise ValueError('Anchor layer menempatkan aset di luar canvas')
        if r['kind']=='video':
            if sum(v['end']-v['start'] for v in out if v['id']==r['id'])>30:raise ValueError('Budget B-roll inti maksimal 30 detik per layer')
            from .asset_rank import rerank
            a=r['asset'];candidates,notes=rerank([{'id':a['id'],'provider':'local','path':a['path'],'duration':a['metadata']['duration']}],r.get('reason') or r.get('text') or a['name'],' '.join(w['word'] for w in plan.get('display_words',[])),cfg)
            rank=candidates[0].get('visual_rank') if candidates else None
            import math
            if cfg.broll_ranker=='siglip2' and (not rank or type(rank.get('score')) not in (int,float) or not math.isfinite(rank['score'])):raise ValueError('SigLIP2 diwajibkan tetapi skor visual terukur belum tersedia. '+ '; '.join(notes))
            r['rank_evidence']=candidates[0].get('visual_rank') if candidates else None;r['rank_notes']=notes
        if r['kind']=='diagram':
            import re
            spoken=' '.join(w['word'] for w in plan.get('display_words',plan.get('words',[])))
            exact=lambda needle,haystack:re.search(r'(?<!\w)'+re.escape(needle)+r'(?!\w)',haystack,re.I) is not None
            if not exact(r['quote'],spoken) or any(not exact(t,r['quote']) for t in r['items']):raise ValueError('Diagram harus memakai seluruh item dari kutipan sumber')
            def numeric(value):
                token=format(value,'.15g')
                return any(re.search(r'(?<![\w+\-.,])'+re.escape(t)+r'(?:[.,]0+)?(?!\w|[.,]\d)',r['quote']) for t in {token,token.replace('.',',')})
            if r.get('values') and any(not numeric(v) for v in r['values']):raise ValueError('Angka diagram tidak ada dalam kutipan sumber')
            r['provenance']={'quote':r['quote'],'items':r['items'],'values':r.get('values')}
    for frame in range(round(plan['duration']*plan['fps'])):
        t=frame/plan['fps'];active=[r for r in out if r['start']<=t<r['end']]
        if len(active)>4:raise ValueError('Budget maksimal empat layer bersamaan')
        shot=next((s for s in plan['shots'] if s['start']<=t<s['end']),{});protected=shot.get('protected_output',[]);panels=[p['panel'] for p in plan.get('captions',{}).get('phrases',[]) if p['start']<=t<p['end']]
        for r in active:
            if any(overlap(r['output_rect'],b['box'])>.5 for b in protected) or any(overlap(r['output_rect'],p)>.5 for p in panels):raise ValueError('Layer '+r['id']+' menutupi wajah/materi/caption; pindahkan areanya')
            if r['kind']=='lower_third' and not any(w.get('speaker_id')==r['speaker_id'] and w['start']<=t<w['end']+.5 for w in plan.get('display_words',[])):raise ValueError('Lower-third tidak sesuai interval speaker yang disetujui')
        if sum(r['output_rect'][2]*r['output_rect'][3] for r in active)>W*H*.35:raise ValueError('Budget layer melebihi 35% canvas')
    plan['finishing5']=dict(version=VERSION,layers=out,style=effective(cfg),kit=cfg.finishing5.get('kit'),origins=cfg.finishing5.get('origins'),extra_seconds=0.,gate_g5='pending_real_corpus',source_mapping='M1_clock' if plan.get('editor') else 'edit_spans')

def source_caption_candidates(service,doc,cid,vid,cfg):
    """Conservative OCR geometry proposals; operator approval is mandatory."""
    report=service.variant(doc,cid,vid).get('camera4_report',{});receipt=report.get('receipts',{}).get('ocr',{})
    if receipt.get('status')!='ready':return {'status':'unavailable','reason':'Jalankan analisis M4 dengan OCR lokal siap, atau tandai area subtitle secara manual.','proposals':[]}
    from .camera4_service import signature
    if report.get('source_signature')!=signature(service,doc,cid,vid):return {'status':'stale','reason':'Bukti OCR berasal dari pengaturan/sumber lama.','proposals':[]}
    from .camera4_plan import layers as camera_layers
    W,H=report['source_size'];groups=[]
    from .finishing5_plan import overlap
    for frame in report.get('frames',[]):
        for value in frame.get('ocr',[]):
            box=value.get('box')
            if not box or len(box)!=4 or not all(type(n) in (int,float) for n in box):continue
            x,y,w,h=box
            if y<H*.50 or w<W*.15 or h>H*.20:continue
            row=next((g for g in groups if overlap(g['box'],box)/max(1,min(g['box'][2]*g['box'][3],w*h))>.7),None)
            if not row:row={'box':box,'times':[],'texts':[]};groups.append(row)
            row['times'].append(frame['time']);row['texts'].append(value.get('text',''))
    proposals=[]
    for g in groups:
        if len(set(g['times']))<2:continue
        a,b=min(g['times']),max(g['times'])+.5
        for segment in report.get('segments',[]):
            if segment['start']>=b or segment['end']<=a:continue
            built=camera_layers(segment,cfg.target_w,cfg.target_h,report['settings'])
            for layer in built['layers']:
                x,y,w,h=layer['source_crop'];vx,vy,vw,vh=layer['viewport'];gx,gy,gw,gh=g['box']
                if overlap([x,y,w,h],g['box'])<gw*gh*.98:continue
                s=min(vw/w,vh/h);ox=vx+(vw-w*s)/2+(gx-x)*s;oy=vy+(vh-h*s)/2+(gy-y)*s
                proposals.append({'rect':[ox/cfg.target_w*100,oy/cfg.target_h*100,gw*s/cfg.target_w*100,gh*s/cfg.target_h*100],
                    'start':max(a,segment['start']),'end':min(b,segment['end']),'provenance':'M4 sampled OCR; geometric subtitle candidate','approved':False,'observations':len(g['times']),'texts':g['texts']});break
    return {'status':'proposals' if proposals else 'no_candidate','proposals':proposals,'scope':'lower-frame OCR geometry; not a semantic subtitle classifier','approval':'operator_required'}
