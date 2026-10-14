"""Semantic phrases measured with final fonts/paint before protected placement."""
import copy,math,re
from pathlib import Path
from dataclasses import replace
from collections import Counter
from PIL import ImageFont
from .contracts import fingerprint
from .finishing5_contract import VERSION,TEMPLATES,effective
from .finishing5_assets import choose_font
from .caption_geometry import metrics,bounds
from .caption_readability import clear_time
def overlap(a,b):
    x,y,w,h=a;xx,yy,ww,hh=b
    return max(0,min(x+w,xx+ww)-max(x,xx))*max(0,min(y+h,yy+hh)-max(y,yy))
def role(rows):
    t=' '.join(r['word'] for r in rows).casefold()
    if re.search(r'\b(jadi|intinya|kesimpulan|akhirnya|therefore|conclusion)\b',t):return 'conclusion'
    if re.search(r'\b(pertama|kedua|ketiga|keempat|kelima|first|second|third)\b',t):return 'list'
    if re.search(r'\d|\b(tidak|bukan|belum|jangan|risiko|bahaya|not|never|warning)\b',t):return 'number_or_warning'
    return 'narration'
def units(words):
    from .typography import display_units,token
    from .transcript_correction import PROTECTED
    source=display_units(copy.deepcopy(words));out=[];i=0
    while i<len(source):
        r=source[i];i+=1
        while i<len(source) and source[i]['start']-r['end']<=.65 and r.get('part')==source[i].get('part'):
            n=source[i];ts=r['word'].split();last=token(ts[-1]);technical=bool(re.search(r'\d[.,%]?$',r['word'])) and token(n['word']) in {'kg','gram','km','m','cm','mm','ms','detik','liter','mb','gb','kb','hz','volt','watt','°c'}
            neg=last in PROTECTED or token(ts[0]) in PROTECTED and len(ts)<3 and (len(ts)==1 or bool(re.search(r'\d',n['word'])) or last in {'ada','punya','pernah','mau'})
            if not (technical or neg):break
            r['word']+=' '+n['word'];r['end']=max(r['end'],n['end']);r['word_ids']+=n.get('word_ids',[]);r['token_ids']+=n.get('token_ids',[]);i+=1
        out.append(r)
    return out
def phrases(words,cfg,s):
    from .typography import groups
    rows=units(words)
    return [[r] for r in rows] if s['granularity']=='word' else groups(rows,replace(cfg,style_preset='rapi',editorial_words=4,editorial_phrase_s=3.2))
def template_for(rows,cfg,s):
    r=role(rows);key=s['template_id']
    if cfg.caption_template_policy=='auto' and key!='custom':key={'conclusion':'quote','list':'stack','number_or_warning':'focus','narration':'editorial'}[r]
    chosen=s['builder'] if key=='custom' else next(t for t in TEMPLATES if t['id']==key)
    if not chosen:raise ValueError('Simpan builder sebelum memilih template custom')
    return {**chosen,'role':r}
def paint(s,cfg,color):
    f=min(cfg.target_w,cfg.target_h)/1080;on=cfg.caption_backdrop
    stroke=s['stroke_px']*f if on else 0.;shadow=s['shadow_px']*f if on else 0.;glow=s['glow_px']*f if on else 0.
    return dict(color=color,stroke=stroke,stroke_color=s['stroke_hex'],shadow=shadow,shadow_color=s['shadow_hex'],glow=glow,glow_color=s['glow_hex'],padding=stroke+shadow+2*glow+1)
def candidates(cfg,s,touching,previous):
    W,H=cfg.target_w,cfg.target_h;v=s['manual_panel'];pos=cfg.caption_position
    if v:return [([v[i]*(W if i%2==0 else H)/100 for i in range(4)],pos)],True
    if pos!='auto':
        if pos in ('left','right'):
            width=W*(.82 if H>W else .43);x=W*.055 if pos=='left' else W*.90-width
            return [([x,H*(.56 if H>W else .20),width,H*(.27 if H>W else .63)],pos)],True
        return [([W*.055,H*(.60 if H>W else .65),W*.84,H*(.23 if H>W else .28)],'bottom')],True
    out=[previous] if previous else []
    out += [(a['panel'],a.get('position','bottom')) for a in touching if a.get('panel')]
    if H>W:out += [([W*.055,H*y,W*.84,H*.25],'bottom') for y in (.58,.34,.08)]
    else:
        out += [([W*x,H*y,W*.425,H*.62],pos) for x,pos in ((.055,'left'),(.47,'right')) for y in (.18,.07)]
        out += [([W*.055,H*y,W*.84,H*.30],'bottom') for y in (.61,.07)]
    return [(list(b),p) for b,p in out if b[0]>=W*.04 and b[1]>=H*.04 and b[0]+b[2]<=W*.91+.5 and b[1]+b[3]<=H*(.84 if H>W else .95)+.5],False
def mask_text(t,s):
    if s['censor_mode']=='off':return t,False
    if not s['censor_approved']:raise ValueError('Tinjau dan setujui kamus sensor dahulu')
    changed=False
    for term in sorted(s['censor_terms'],key=len,reverse=True):
        t,n=re.subn(r'(?<!\w)'+re.escape(term)+r'(?!\w)',lambda m:'•'*len(m.group()),t,flags=re.I);changed|=bool(n)
    return t,changed
def fit(rows,panel,pos,cfg,s,template,selected,extra):
    x,y,w,h=panel;W=cfg.target_w;entries=[]
    # A semantic atomic unit may wrap visually, but remains in one phrase with
    # one logical owner. Continuation glyphs never duplicate transcript IDs.
    for i,row in enumerate([*rows,*extra]):
        value,censored=mask_text(row['word'],s);emph=i in selected
        for j,fragment in enumerate(value.split()):
            r={**row,'continuation':j>0}
            if j:r.update(word_id=None,word_ids=[],token_ids=[])
            meta=choose_font(cfg.fonts_dir,cfg.font_accent if emph and cfg.accent_font else cfg.font_main,s['fallback_fonts'],fragment)
            entries.append((r,fragment,meta,emph,censored))
    align=cfg.caption_align if cfg.caption_align!='auto' else pos if pos in ('left','right') else 'center'
    from .typography import balanced_rows
    for size in range(round(W*.095*cfg.caption_scale),max(7,math.floor(W/s['display_width_px']*s['minimum_glyph_px']))-1,-1):
        sizes=[round(size*(template['accent_ratio'] if e[3] else 1.)) for e in entries];fonts=[ImageFont.truetype(str(Path(cfg.fonts_dir)/e[2]['file']),z) for z,e in zip(sizes,entries)]
        if min(min(f.getbbox('H')[3]-f.getbbox('H')[1],f.getbbox('a')[3]-f.getbbox('a')[1])*s['display_width_px']/W for f in fonts)<s['minimum_glyph_px']:continue
        widths=[f.getlength(e[1]) for f,e in zip(fonts,entries)];pad=paint(s,cfg,cfg.base_hex)['padding'];space=max(size*.28,pad*2+2)
        overhang=max(max(0,-f.getbbox(e[1],anchor='ls')[0],f.getbbox(e[1],anchor='ls')[2]-widths[i]) for i,(f,e) in enumerate(zip(fonts,entries)))
        motion=s['motion_budget']*min(W,cfg.target_h) if template['motion']!='still' and cfg.motion_intensity!='calm' else 0.
        layout=balanced_rows([e[0] for e in entries],widths,space,w-2*(pad+motion+overhang),template.get('max_rows',2),{i for i,e in enumerate(entries) if e[3]})
        if layout is None:continue
        ink=[metrics(fonts[i],e[1],widths[i]) for i,e in enumerate(entries)];heights=[max(ink[i][2][1] for i in line)-min(ink[i][2][0] for i in line) for line in layout];gap=max(size*template.get('line_gap',.23),pad*2+1);total=sum(heights)+gap*(len(layout)-1)
        if total+2*(pad+motion)>h:continue
        placed=[];cy=y+(h-total)/2
        for line,rh in zip(layout,heights):
            line_w=sum(widths[i] for i in line)+space*(len(line)-1);left=x+pad+motion+overhang if align=='left' else x+w-pad-motion-overhang-line_w if align=='right' else x+(w-line_w)/2;baseline=cy-min(ink[i][2][0] for i in line)
            for i in line:
                row,value,meta,emph,censored=entries[i];color=cfg.accent_hex if emph else cfg.base_hex;sp=next((r for r in s['speaker_styles'] if r['speaker_id']==row.get('speaker_id')),None)
                if sp and s['speaker_color']:color=sp['color']
                placed.append(dict(text=value,original_text=row['word'],word_id=row.get('word_id'),word_ids=row.get('word_ids',[]),token_ids=row.get('token_ids',[]),continuation=row.get('continuation',False),start=row['start'],end=row['end'],speaker_id=row.get('speaker_id'),x=round(left+widths[i]/2,3),y=round(baseline-ink[i][1],3),baseline=round(baseline,3),size=sizes[i],ass_size=sum(fonts[i].getmetrics()),width=widths[i],ink_box=ink[i][0],ink_padding=pad,emphasis=emph,color=color,paint=paint(s,cfg,color),censored=censored,decorative=bool(row.get('decorative')),**meta));left+=widths[i]+space
            cy+=rh+gap
        return placed,align,motion
    return None
def caption_plan(words,cfg,keywords=(),position='bottom',anchors=None):
    s=effective(cfg);parts=phrases(words,cfg,s);out=[];previous=None
    from .caption_director import focus
    while parts:
        rows=parts.pop(0);a=rows[0]['start'];spoken_end=max(r['end'] for r in rows);following=parts[0][0]['start'] if parts else max(spoken_end+.14,max((r.get('end',0) for r in anchors or []),default=0));end=min(following,spoken_end+.18)
        touching=[r for r in anchors or [] if r.get('start',0)<end and r.get('end',math.inf)>a];protected=[b for r in touching for b in r.get('protected',[])]
        for r in s['source_captions']:
            if r['start']<end and r['end']>a:protected.append({'kind':'source_caption','box':[r['rect'][i]*(cfg.target_w if i%2==0 else cfg.target_h)/100 for i in range(4)]})
        template=template_for(rows,cfg,s);selected=focus(rows,keywords) if cfg.semantic_emphasis else set();options,locked=candidates(cfg,s,touching,previous);extra=[]
        if s['speaker_labels']:
            ids={r.get('speaker_id') for r in rows};sp=next((r for r in s['speaker_styles'] if r['speaker_id'] in ids and r['label']),None)
            if sp:extra.append(dict(word=sp['label']+':',start=a,end=end,decorative=True,speaker_id=sp['speaker_id']))
        if s['emoji']:
            full=' '.join(r['word'] for r in rows).casefold();icon=next((r['icon'] for r in s['emoji_map'] if r['keyword'].casefold() in full),None)
            if icon:extra.append(dict(word=icon,start=a,end=end,decorative=True))
        fitted=None
        for panel,pos in options:
            trial=fit(rows,panel,pos,cfg,s,template,selected,extra)
            if trial and not any(overlap(bounds(w),b['box'])>.5 for w in trial[0] for b in protected):fitted=(panel,pos,trial);break
        if not fitted:
            if len(rows)>1:
                cut=max(1,len(rows)//2);parts=[rows[:cut],rows[cut:],*parts];continue
            raise ValueError('Frasa tidak muat pada minimum glyph tanpa menutupi materi. Perbesar/pindahkan area caption; teks dan pilihan manual dipertahankan.')
        panel,pos,(placed,align,motion)=fitted;previous=(panel,pos);duration=end-a;last=max(1,math.ceil(duration*cfg.output_fps))
        for w in placed:
            enter=min(round(.1*cfg.output_fps),max(0,last-round(min(.35,duration*.6)*cfg.output_fps)));samples=[]
            for f in range(last):
                ease=1-(1-min(1.,f/max(1,enter)))**3;color=cfg.accent_hex if s['karaoke'] and w['start']<=a+f/cfg.output_fps<w['end'] else w['color']
                samples.append(dict(frame=f,t=round(f/cfg.output_fps,6),scale=1.,dx=round(motion*(1-ease),3) if template['motion']=='slide' else 0.,dy=round(motion*(1-ease),3) if template['motion']=='rise' else 0.,opacity=.98+.02*ease if template['motion']=='fade' else 1.,blur=0.,color=color))
            samples.append(dict(frame=last,t=round(last/cfg.output_fps,6),scale=1.,dx=0.,dy=0.,opacity=0.,blur=0.,color=w['color']));w.update(keyframes=samples,motion=template['motion'],meaning_role=template['role'],emphasis_evidence={'source':'semantic_phrase' if w['emphasis'] else 'none','original_text':w['original_text']})
        out.append(dict(start=a,end=end,phrase_id=fingerprint([VERSION,[(r.get('token_ids'),r['word'],r['start']) for r in rows]])[:24],words=placed,panel=panel,alignment=align,position=cfg.caption_position if locked else pos,protected=protected,placement_source='manual' if locked else 'final_ink_search',design=dict(template=template['id'],role=template['role'],alignment=align,reveal='whole_phrase',seed=cfg.caption_seed,policy=cfg.caption_template_policy),source_word_ids=[i for r in rows for i in r.get('word_ids',[])]))
    result=dict(version=6,m5_version=VERSION,timebase='output_seconds',keyframe_interpolation='hold',fps=cfg.output_fps,width=cfg.target_w,height=cfg.target_h,font_main=cfg.font_main,font_accent=cfg.font_accent,template=s['template_id'],contrast=cfg.caption_backdrop,phrases=out,effective_style=s,cues=dict(emphasis=sum(w['emphasis'] for p in out for w in p['words']),karaoke=sum(len(p['words']) for p in out) if s['karaoke'] else 0,emoji=sum(w.get('decorative',False) and w['text'] in [r['icon'] for r in s['emoji_map']] for p in out for w in p['words']) if s['emoji'] else 0,speaker_color=s['speaker_color'],speaker_labels=s['speaker_labels'],censor=sum(w['censored'] for p in out for w in p['words']) if s['censor_mode']!='off' else 0),censor_intervals=[[w['start'],w['end']] for p in out for w in p['words'] if w['censored']] if s['censor_mode']=='bleep_mask' else [])
    result['m5_checks']=check(result,cfg,words);return result
def check(plan,cfg,expected=None):
    s=effective(cfg);issues=[];rows=[];actual=[];warnings=[]
    for p in plan['phrases']:
        d=p['end']-p['start'];measure=[]
        for w in p['words']:
            if not w.get('decorative') and not w.get('continuation'):actual.extend(i for i in (w.get('token_ids') or [w.get('word_id')]) if i is not None)
            f=ImageFont.truetype(str(Path(cfg.fonts_dir)/w['file']),w['size']);glyph=min(f.getbbox('H')[3]-f.getbbox('H')[1],f.getbbox('a')[3]-f.getbbox('a')[1])*s['display_width_px']/cfg.target_w;c=clear_time(w,d)
            if glyph+.001<s['minimum_glyph_px']:issues.append('Minimum glyph gagal')
            if c['longest_contiguous_clear']<min(.25,d*.4):issues.append('Hold kontinu gagal')
            for k in w['keyframes']:
                if k['opacity']<.05:continue
                b=bounds(w,k);x,y,ww,hh=p['panel']
                if b[0]<x-.5 or b[1]<y-.5 or b[0]+b[2]>x+ww+.5 or b[1]+b[3]>y+hh+.5:issues.append('Final ink keluar panel')
                if b[0]<0 or b[1]<0 or b[0]+b[2]>cfg.target_w+.5 or b[1]+b[3]>cfg.target_h+.5:issues.append('Final ink keluar canvas')
                if any(overlap(b,r['box'])>.5 for r in p['protected']):issues.append('Final ink menutupi area terlindungi')
            measure.append(dict(token=w['text'],minimum_glyph_px=round(glyph,3),**c))
        rows.append(dict(phrase_id=p['phrase_id'],text=' '.join(w['text'] for w in p['words']),start=p['start'],end=p['end'],issues=[],clear_time_metrics=measure,role=p['design']['role'],characters_per_second=round(sum(len(w['text'])+1 for w in p['words'])/d,2)))
        row=rows[-1]
        if row['characters_per_second']>24:
            item=dict(code='reading_speed',severity='warning',phrase_id=p['phrase_id'],message='Ucapan cepat untuk dibaca pada layar kecil.',fix='Tinjau frasa pada preview; perluas jeda bila tersedia, tanpa menghapus angka/negasi.')
            row['issues'].append(item);warnings.append(item)
        if d<.4-1e-6:
            item=dict(code='short_phrase',severity='warning',phrase_id=p['phrase_id'],message='Frasa tampil kurang dari 0,4 detik.',fix='Pilih granularitas frasa atau perluas area/waktu baca.')
            row['issues'].append(item);warnings.append(item)
    if expected is not None:
        wanted=[i for w in expected for i in (w.get('token_ids') or [w.get('token_id',w.get('word_id'))]) if i is not None]
        if Counter(wanted)!=Counter(actual) or wanted!=actual:issues.append('Coverage/urutan logical word berubah')
    if not cfg.semantic_emphasis and any(w['emphasis'] for p in plan['phrases'] for w in p['words']):issues.append('Emphasis off masih aktif')
    if issues:raise ValueError('QC M5: '+'; '.join(dict.fromkeys(issues)))
    return dict(passed=True,status='needs_review' if warnings else 'pass',geometry_passed=True,readability_passed=not warnings,phrases=len(rows),phrase_rows=rows,issue_count=len(warnings),issues=warnings,validator_version=VERSION,inspection_state='completed',raster_contrast_status='pending_actual_raster',acceptance_g5='pending_user_corpus',checks=['final_ink','phone_glyph','continuous_clear_hold','logical_coverage','protected_geometry','toggle_off'])

def bilingual(source,translation,cfg,anchors=None):
    s=effective(cfg);options,_=candidates(cfg,s,anchors or [],None);last_error=None
    for panel,pos in options:
        x,y,w,h=panel;plans=[]
        try:
            for i,words in enumerate((source,translation)):
                state=copy.deepcopy(cfg.finishing5);state['style']['manual_panel']=[x/cfg.target_w*100,(y+h*i/2)/cfg.target_h*100,w/cfg.target_w*100,(h/2)/cfg.target_h*100]
                # Both independent tracks keep the chosen typography and exact
                # output clock. Each receives half the protected caption area.
                local=replace(cfg,finishing5=state)
                plans.append(caption_plan(words,local,anchors=anchors))
            phrases=[{**p,'language_track':track} for track,plan in zip(('source','translation'),plans) for p in plan['phrases']]
            phrases.sort(key=lambda p:(p['start'],p['language_track']))
            return {**plans[0],'phrases':phrases,'bilingual':True,'source_plan':plans[0],'translation_plan':plans[1],'source_words':copy.deepcopy(source),'translation_words':copy.deepcopy(translation),'track_policy':'two_protected_bands; independent logical coverage','censor_intervals':plans[0]['censor_intervals']}
        except ValueError as exc:last_error=exc
    raise ValueError('Dua bahasa memerlukan area lebih luas pada minimum glyph: '+str(last_error))
