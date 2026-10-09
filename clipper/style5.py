"""Deterministic, measured caption direction. No wording or numbers are invented."""
from __future__ import annotations
import hashlib
import json
import math
from dataclasses import replace

VERSION='4.0.8'
PRESETS=(
    {'id':'rapi','name':'Rapi','description':'Frasa utuh, baseline stabil, aksen secukupnya.','settings':{'font_main':'dm_sans','font_accent':'dm_serif_italic','motion_intensity':'calm','caption_backdrop':True}},
    {'id':'ekspresif','name':'Ekspresif','description':'Hierarki dan arah gerak bervariasi dengan desain yang tersimpan.','settings':{'font_main':'dm_sans','font_accent':'dm_serif_italic','motion_intensity':'balanced','caption_backdrop':True}},
    {'id':'adaptif','name':'Adaptif','description':'Gerak lebih tenang saat materi atau ucapan rapat.','settings':{'font_main':'dm_sans','font_accent':'dm_serif_italic','motion_intensity':'balanced','caption_backdrop':True}},
)


def identity(phrase,seed):
    # Output dimensions are excluded: preview and final share design decisions.
    lineage=[{'ids':w.get('word_ids',w.get('source_word_ids',[w.get('word_id')])),
              'text':w['word'],'time':round(w['start'],4)} for w in phrase]
    return hashlib.sha256(json.dumps([VERSION,seed,lineage],ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def caption_plan(words,cfg,keywords=(),position='bottom',anchors=None):
    from .typography import groups,kinetic_plan,token
    parts=groups(words,cfg);output=[]
    for index,phrase in enumerate(parts):
        digest=identity(phrase,cfg.caption_seed);choice=int(digest[:8],16)
        touching=[a for a in anchors or [] if a.get('start',0)<phrase[-1]['end'] and a.get('end',float('inf'))>phrase[0]['start']]
        material=cfg.source_kind in ('board','screen','chart','graphic') or any(a.get('has_material') or any(p.get('kind') in ('material','panel') for p in a.get('protected',[])) for a in touching)
        cps=sum(len(w['word']) for w in phrase)/max(.02,phrase[-1]['end']-phrase[0]['start'])
        quiet=cfg.style_preset=='rapi' or (cfg.style_preset=='adaptif' and (material or cps>18))
        template=cfg.caption_style if cfg.caption_template_policy=='manual' else 'magazine' if quiet else ('magazine','slide','pop','blur')[choice%4]
        local=replace(cfg,style_preset='legacy',caption_style=template,
                      motion_intensity='calm' if quiet else cfg.motion_intensity,
                      caption_scale=cfg.caption_scale*(.85 if cfg.style_preset=='adaptif' and material else 1))
        local._motion_direction=('left','right','up','down')[(choice//4)%4]
        local._emphasis_disabled=not cfg.semantic_emphasis
        if not quiet and cfg.caption_align=='auto':local.caption_align=('left','center','right')[(choice//16)%3]
        local_words=[dict(w) for w in phrase]
        if cfg.semantic_emphasis:
            # Acoustic prominence supports a semantic candidate, never selects a
            # negation or number fragment independently from its context.
            from .typography import emphasis_indices
            semantic=emphasis_indices(local_words,keywords)
            from .transcript_correction import PROTECTED
            for i in list(semantic):
                if i>0 and token(local_words[i-1]['word'].split()[-1]) in PROTECTED:semantic.add(i-1)
            # A full keyword phrase keeps any preceding negation even without
            # an acoustic cue. Colors and font hierarchy protect that context.
            if semantic:
                for i in semantic:local_words[i]['meaning_emphasis']=True
        else:
            for w in local_words:w.pop('meaning_emphasis',None)
        following=parts[index+1][0]['start'] if index+1<len(parts) else max((a.get('end',phrase[-1]['end']+.12) for a in touching),default=phrase[-1]['end']+.12)
        planned=kinetic_plan(local_words,local,keywords if cfg.semantic_emphasis else (),position,anchors,_phrases=[local_words],_following=following)['phrases'][0]
        if index+1<len(parts):planned['end']=min(planned['end'],parts[index+1][0]['start'])
        if quiet:
            # All words appear together; stable reading baseline and no bounce.
            last=max(1,math.ceil((planned['end']-planned['start'])*cfg.output_fps))
            for w in planned['words']:
                w['motion']='still'
                w['keyframes']=[{'frame':f,'t':round(f/cfg.output_fps,6),'scale':1.,'dx':0.,'dy':0.,'opacity':opacity,'blur':0.}
                                for f,opacity in [(0,1.),(max(0,last-1),1.),(last,0.)]]
        if not cfg.semantic_emphasis:
            for w in planned['words']:w['emphasis']=False
        for w in planned['words']:
            w['color']=cfg.accent_hex if w['emphasis'] else cfg.base_hex
            ids=set(w.get('word_ids',[]));origin=[p for p in local_words if ids.intersection(p.get('word_ids',[]))]
            w['emphasis_evidence']={'semantic':any(p.get('meaning_emphasis') for p in origin),
                'acoustic_prominence':round(max((p.get('prosody_prominence',0.) for p in origin),default=0.),3),
                'protected_context':any(token(p['word'].split()[0]) in ('tidak','bukan','jangan','belum','never','not') for p in origin)}
        planned.update(phrase_id=digest[:20],design={'preset':cfg.style_preset,'quiet':quiet,'material':material,
                        'density_cps':round(cps,2),'template':local.caption_style,'direction':local._motion_direction,
                        'seed':cfg.caption_seed,'hierarchy':'phrase_then_focus','alignment':planned['alignment'],
                        'template_policy':cfg.caption_template_policy},source_word_ids=[wid for w in phrase for wid in w.get('word_ids',[]) if wid is not None])
        output.append(planned)
    result={'version':5,'timebase':'output_seconds','width':cfg.target_w,'height':cfg.target_h,
            'fps':cfg.output_fps,'font_main':cfg.font_main,'font_accent':cfg.font_accent,'font':cfg.font_main,
            'contrast':cfg.caption_backdrop,'preset':cfg.style_preset,'seed':cfg.caption_seed,
            'template':cfg.caption_style,'motion_intensity':cfg.motion_intensity,'phrases':output}
    result['readability']=readability(result,cfg)
    return result


def contrast(hexval):
    channels=[int(hexval[i:i+2],16)/255 for i in (1,3,5)]
    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
    luminance=sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))
    return (luminance+.05)/.05


def _overlap(a,b):
    x,y,w,h=a;bx,by,bw,bh=b
    return max(0,min(x+w,bx+bw)-max(x,bx))*max(0,min(y+h,by+bh)-max(y,by))


def readability(plan,cfg):
    """Per-phrase measured checks. A pass does not certify subjective aesthetics."""
    issues=[];rows=[];W,H=plan['width'],plan['height']
    for index,phrase in enumerate(plan.get('phrases',[])):
        text=' '.join(w['text'] for w in phrase['words']);duration=max(.02,phrase['end']-phrase['start']);cps=len(text)/duration
        row={'phrase_id':phrase.get('phrase_id',str(index)),'index':index,'start':phrase['start'],'end':phrase['end'],
             'text':text,'source_word_ids':phrase.get('source_word_ids',[]),'characters_per_second':round(cps,2),'issues':[]}
        def issue(code,message,fix,severity='warning'):
            item={'code':code,'severity':severity,'message':message,'fix':fix,'phrase_id':row['phrase_id'],'start':row['start'],'end':row['end']}
            row['issues'].append(item);issues.append(item)
        if cps>22:issue('reading_speed','Frasa terlalu cepat dibaca.','Perpanjang potongan bila ada jeda, atau pecah frasa; jangan hapus negasi atau angka.')
        if not cfg.caption_backdrop:issue('background_unknown','Kontras terhadap gambar bergerak belum dijamin.','Aktifkan latar/outline subtitle atau periksa frame sumber.')
        if min((contrast(w.get('color',cfg.base_hex)) for w in phrase['words']),default=21)<4.5:
            issue('contrast','Warna teks kurang kontras terhadap outline gelap.','Pilih putih atau aksen yang lebih terang.')
        if min((w['size']/min(W,H) for w in phrase['words']),default=1)<.030:
            issue('small_text','Huruf mengecil untuk menampung frasa.','Pecah frasa panjang atau pilih area subtitle yang lebih luas.')
        boxes=[];collision=False;overflow=False
        for word in phrase['words']:
            for sample in word.get('keyframes',[]) or [{'scale':1,'dx':0,'dy':0,'opacity':1}]:
                if sample.get('opacity',1)<=.05:continue
                hw=word['width']*sample['scale']/2;hh=word['size']*sample['scale']*.66
                box=[word['x']+sample['dx']-hw,word['y']+sample['dy']-hh,2*hw,2*hh]
                if box[0]<-.5 or box[1]<-.5 or box[0]+box[2]>W+.5 or box[1]+box[3]>H+.5:overflow=True
                if any(_overlap(box,p['box'])>1 for p in phrase.get('protected',[])):collision=True
            boxes.append([word['x']-word['width']/2,word['y']-word['size']*.50,word['width'],word['size']])
        if collision:issue('protected_collision','Animasi menyentuh wajah atau materi.','Gunakan penempatan otomatis atau pindahkan subtitle.','error')
        if overflow:issue('frame_overflow','Sebagian animasi keluar frame.','Kurangi ukuran atau ganti posisi subtitle.','error')
        if any(_overlap(a,b)>min(a[2]*a[3],b[2]*b[3])*.10 for i,a in enumerate(boxes) for b in boxes[i+1:]):
            issue('word_collision','Kotak kata saling bertumpuk.','Kurangi skala atau pecah frasa.','error')
        rows.append(row)
    return {'version':VERSION,'status':'needs_review' if issues else 'passed','issue_count':len(issues),
            'phrases':rows,'issues':issues,'scope':'measured_layout_reading_speed_animation_envelope',
            'note':'Kontras dihitung terhadap outline gelap; hasil pada gambar bergerak tetap perlu preview.'}


def annotate_prosody(words,voice_path):
    """Bounded PCM energy is supporting evidence, not an inference about meaning."""
    import array
    import wave
    try:
        with wave.open(str(voice_path),'rb') as audio:
            if audio.getsampwidth()!=2:return words
            rate=audio.getframerate();channels=audio.getnchannels();count=audio.getnframes()
            energies=[]
            for word in words:
                left=max(0,min(count,round(word['start']*rate)));right=max(left,min(count,round(word['end']*rate)))
                audio.setpos(left);samples=array.array('h',audio.readframes(min(right-left,rate*4)))
                energy=math.sqrt(sum(float(v)*v for v in samples)/max(1,len(samples)))
                energies.append(energy)
        from statistics import median
        baseline=median(energies) if energies else 0
        return [{**w,'prosody_prominence':round(min(1.,max(0.,(e/max(1.,baseline)-1)/2)),3),
                 'prosody_method':'pcm_rms_relative_to_clip_median'} for w,e in zip(words,energies)]
    except (OSError,ValueError,wave.Error):return words
