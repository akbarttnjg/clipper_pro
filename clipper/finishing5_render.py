"""Real ASS and Pillow execution of one M5 plan; bounded frame-held overlays."""
import copy,json,math,subprocess
from pathlib import Path
from functools import lru_cache
from PIL import Image,ImageDraw,ImageFont,ImageFilter,ImageColor
from .finishing5_assets import sha

def sample(word,t):
    return next((r for r in reversed(word['keyframes']) if r['t']<=t+1e-6),word['keyframes'][0])
@lru_cache(maxsize=128)
def font(path,size):return ImageFont.truetype(path,size)
def rgba(value,opacity=1.):return (*ImageColor.getrgb(value),max(0,min(255,round(opacity*255))))
def caption_frame(plan,cfg,t):
    # Supersampling preserves fractional glyph placement instead of rounding
    # every Pillow baseline to a whole pixel, particularly on phone previews.
    factor=2
    image=Image.new('RGBA',(plan['width']*factor,plan['height']*factor))
    for r in plan['effective_style']['source_captions']:
        if plan['effective_style']['source_caption_mode'] in ('cover','reconstruct') and r['start']<=t<r['end']:
            x,y,w,h=[r['rect'][i]*(plan['width'] if i%2==0 else plan['height'])/100*factor for i in range(4)];ImageDraw.Draw(image).rectangle([x,y,x+w,y+h],fill=(14,18,24,255))
    for p in plan['phrases']:
        if not p['start']<=t<p['end']:continue
        for w in p['words']:
            a=sample(w,t-p['start'])
            if a['opacity']<=0:continue
            path=str(Path(cfg.fonts_dir)/w['file']);original=font(path,w['size']);f=font(path,w['size']*factor);paint={**w['paint'],**{k:w['paint'][k]*factor for k in ('stroke','shadow','glow')}};x=(w['x']+a['dx']-w['width']/2)*factor;y=(w['y']+a['dy']+(original.getmetrics()[0]-original.getmetrics()[1])/2)*factor
            layer=Image.new('RGBA',image.size);d=ImageDraw.Draw(layer);stroke=round(paint['stroke']);opacity=a['opacity'];color=a.get('color',w['color'])
            if paint['glow']:
                glow=Image.new('RGBA',image.size);ImageDraw.Draw(glow).text((x,y),w['text'],font=f,anchor='ls',fill=rgba(paint['glow_color'],opacity),stroke_width=stroke,stroke_fill=rgba(paint['glow_color'],opacity));layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(paint['glow']/2)))
            if paint['shadow']:d=ImageDraw.Draw(layer);d.text((x+paint['shadow'],y+paint['shadow']),w['text'],font=f,anchor='ls',fill=rgba(paint['shadow_color'],opacity),stroke_width=stroke,stroke_fill=rgba(paint['shadow_color'],opacity))
            d.text((x,y),w['text'],font=f,anchor='ls',fill=rgba(color,opacity),stroke_width=stroke,stroke_fill=rgba(paint['stroke_color'],opacity));image.alpha_composite(layer)
    return image.resize((plan['width'],plan['height']),Image.Resampling.LANCZOS)
def write_ass(plan,path,cfg):
    from .captions_pro import ts,color,safe
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {plan['width']}
PlayResY: {plan['height']}
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: M5,DejaVu Sans,60,&H00FFFFFF,&H00FFFFFF,&H00141821,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
''';events=[]
    def event(layer,a,b,tags,value):
        if round(b*100)>round(a*100):events.append(f'Dialogue: {layer},{ts(a)},{ts(b)},M5,,0,0,0,,{{{tags}}}{value}')
    s=plan['effective_style']
    if s['source_caption_mode'] in ('cover','reconstruct'):
        for r in s['source_captions']:
            x,y,w,h=[round(r['rect'][i]*(plan['width'] if i%2==0 else plan['height'])/100) for i in range(4)]
            event(0,r['start'],r['end'],r'\an7\pos(0,0)\p1\c&H18120E&\bord0',f'm {x} {y} l {x+w} {y} {x+w} {y+h} {x} {y+h}')
    for p in plan['phrases']:
        for w in p['words']:
            paint=w['paint']
            # Merge identical neighboring frames without changing held timing.
            runs=[]
            for a,b in zip(w['keyframes'],w['keyframes'][1:]):
                if a['opacity']<=0:continue
                state={k:v for k,v in a.items() if k not in ('frame','t')}
                if runs and state==runs[-1][2]:runs[-1]=(runs[-1][0],b['t'],state)
                else:runs.append((a['t'],b['t'],state))
            for a,b,k in runs:
                left=p['start']+a;right=min(p['end'],p['start']+b)
                tags=(f"\\an5\\pos({w['x']+k['dx']:.3f},{w['y']+k['dy']:.3f})\\fn{w['family']}\\fs{w['ass_size']}\\b{int(w['bold'])}\\i{int(w['italic'])}"
                    f"\\c{color(k.get('color',w['color']))}\\alpha&H{round((1-k['opacity'])*255):02X}&\\bord{paint['stroke']:.3f}\\shad{paint['shadow']:.3f}\\3c{color(paint['stroke_color'])}\\4c{color(paint['shadow_color'])}\\blur0")
                if paint['glow']:event(1,left,right,tags+f"\\c{color(paint['glow_color'])}\\3c{color(paint['glow_color'])}\\bord{paint['stroke']+paint['glow']/2:.3f}\\blur{paint['glow']/2:.3f}\\shad0",safe(w['text']))
                event(2,left,right,tags,safe(w['text']))
    dst=Path(path);dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(header+'\n'.join(events)+'\n',encoding='utf-8');dst.with_suffix('.caption-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2));return str(dst)
def carrier(frame_fn,W,H,fps,duration,target,progress=None):
    """One RGBA frame in memory; real qtrle alpha, no hidden browser/model."""
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);pending=target.with_name(target.stem+'.pending.mov');log=target.with_suffix('.log');frames=round(duration*fps)
    with log.open('wb') as err:
        p=subprocess.Popen(['ffmpeg','-nostdin','-hide_banner','-v','error','-y','-f','rawvideo','-pix_fmt','rgba','-s',f'{W}x{H}','-r',str(fps),'-i','-','-an','-c:v','qtrle','-pix_fmt','argb','-threads','1',str(pending)],stdin=subprocess.PIPE,stderr=err)
        try:
            for i in range(frames):
                if progress and i%fps==0:progress(i/max(1,frames))
                p.stdin.write(frame_fn(i/fps).tobytes())
            p.stdin.close()
            if p.wait(timeout=max(60,duration*3)):raise ValueError('Render alpha M5 gagal: '+log.read_text()[-1200:])
            pending.replace(target)
        except BaseException:
            p.kill();p.wait();pending.unlink(missing_ok=True);raise
    return str(target.resolve())
def raster(plan,cfg,folder,duration):
    target=Path(folder)/'m5-captions.mov';path=carrier(lambda t:caption_frame(plan,cfg,t),plan['width'],plan['height'],cfg.output_fps,duration,target)
    return dict(engine='raster',status='ready',path=path,codec='qtrle',alpha=True,sha256=sha(path),plan_version=plan['version'],font_digests={w['font_id']:w['sha256'] for p in plan['phrases'] for w in p['words']})
def decorations(plan,cfg,folder):
    rows=plan.get('finishing5',{}).get('layers',[])
    if not rows:return
    images={};videos={};raw_paths=[]
    try:
        for r in rows:
            if r['kind'] in ('logo','image'):
                with Image.open(r['asset']['path']) as im:images[r['asset_id']]=im.convert('RGBA')
            if r['kind']=='video':
                # Disk-addressed frames follow the canonical source clock, so
                # freeze/reverse/reorder do not advance the stock independently.
                from .finishing5_service import source_at
                W,H=r['output_rect'][2:];times=[source_at(plan,f/cfg.output_fps)-r['source_interval'][0] for f in range(round(r['start']*cfg.output_fps),round(r['end']*cfg.output_fps))]
                if min(times)<-.001 or max(times)>=r['asset']['metadata']['duration']:raise ValueError('B-roll tidak mencakup interval sumber yang dipilih')
                first=math.floor(min(times)*cfg.output_fps);last=math.floor(max(times)*cfg.output_fps)+1;size=(last-first)*W*H*4
                if size+sum(p.stat().st_size for p in raw_paths)>512*1024*1024:raise ValueError('Budget cache B-roll 512 MB; perkecil area atau durasi layer')
                raw=Path(folder)/('m5-asset-'+str(len(raw_paths))+'.rgba');raw_paths.append(raw)
                subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',r['asset']['path'],'-vf',f'fps={cfg.output_fps},trim=start_frame={first}:end_frame={last},scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x101820','-an','-f','rawvideo','-pix_fmt','rgba',str(raw)],check=True,capture_output=True)
                if raw.stat().st_size!=size:raise ValueError('Frame aset B-roll tidak lengkap')
                videos[id(r)]=(raw.open('rb'),first);r['asset_playback']='canonical_source_clock; frame held'
        def draw(t):
            im=Image.new('RGBA',(plan['width'],plan['height']))
            for r in rows:
                if not r['start']<=t<r['end']:continue
                x,y,w,h=r['output_rect'];plate=Image.new('RGBA',(w,h))
                if r['kind'] in ('logo','image'):
                    src=images[r['asset_id']];src=src.copy();src.thumbnail((w,h),Image.Resampling.LANCZOS);plate.alpha_composite(src,((w-src.width)//2,(h-src.height)//2))
                elif r['kind']=='video':
                    from .finishing5_service import source_at
                    stream,first=videos[id(r)];frame=max(0,math.floor((source_at(plan,t)-r['source_interval'][0])*cfg.output_fps+1e-6)-first);stream.seek(frame*w*h*4);buf=stream.read(w*h*4)
                    if len(buf)!=w*h*4:raise ValueError('Decoder B-roll berhenti sebelum interval selesai')
                    plate=Image.frombytes('RGBA',(w,h),buf)
                else:
                    d=ImageDraw.Draw(plate);d.rounded_rectangle((0,0,w-1,h-1),radius=max(2,round(h*.06)),fill=(14,22,34,245));items=r.get('items',[r.get('text','')]);values=r.get('values')
                    if values:items=[f"{label}: {value:g} {r.get('unit','')}".strip() for label,value in zip(items,values)]
                    size=max(8,math.ceil(plan['width']/360*14/.53));f=font(str(Path(cfg.fonts_dir)/'DMSans-SemiBold.ttf'),size)
                    if size*len(items)*1.8>h*.9:raise ValueError('Area teks layer terlalu pendek pada minimum glyph layar kecil')
                    if any(f.getlength(v)>w*.90 for v in items):raise ValueError('Teks layer terlalu panjang; perbesar area, teks tidak dipotong')
                    for i,v in enumerate(items):
                        yy=h*.10+i*h*.80/max(1,len(items));d.text((w*.05,yy),v,font=f,fill='white')
                        if values:
                            maximum=max(abs(n) for n in values) or 1;bar=abs(values[i])/maximum*w*.8;d.rectangle((w*.05,yy+size*1.2,w*.05+bar,yy+size*1.38),fill='#F6CF69')
                alpha=r['opacity'];u=min(t-r['start'],r['end']-t);tr=r['transition'];dur=r['transition_s']
                if dur and tr!='cut':
                    phase=max(0,min(1,u/dur))
                    if tr=='fade':alpha*=phase
                    elif tr=='blur':plate=plate.filter(ImageFilter.GaussianBlur((1-phase)*min(w,h)*.025))
                    elif tr=='glitch' and phase<1:
                        # Deterministic short horizontal displacement within a layer.
                        shift=round((1-phase)*w*.02*(1 if round(t*cfg.output_fps)%2 else -1));shifted=Image.new('RGBA',plate.size);shifted.alpha_composite(plate,(shift,0));plate=shifted
                if alpha<1:plate.putalpha(plate.getchannel('A').point(lambda a:round(a*alpha)))
                im.alpha_composite(plate,(x,y))
            return im
        path=carrier(draw,plan['width'],plan['height'],cfg.output_fps,plan['duration'],Path(folder)/'m5-finishing.mov')
        plan['finishing5']['overlay']={'path':path,'sha256':sha(path),'codec':'qtrle','source_mapping':plan['finishing5']['source_mapping']}
    finally:
        for stream,_ in videos.values():stream.close()
        for p in raw_paths:p.unlink(missing_ok=True)
def censor_audio(plan,cfg,mix,folder):
    intervals=plan.get('captions',{}).get('censor_intervals',[])
    if not intervals:return mix
    from .render import run_audio
    windows=sorted(set((round(a,6),round(b,6)) for a,b in intervals));expr='+'.join(f'gte(t,{a})*lt(t,{b})' for a,b in windows);target=Path(folder)/'m5-censored.wav'
    graph=f"[0:a]volume=0:enable='{expr}'[v];[1:a]volume=0.08:enable='{expr}',volume=0:enable='not({expr})'[b];[v][b]amix=inputs=2:normalize=0[out]"
    run_audio(['-i',mix,'-f','lavfi','-i',f'sine=frequency=1000:sample_rate=48000:duration={plan["duration"]}','-filter_complex',graph,'-map','[out]','-t',plan['duration']],target,Path(folder)/'m5-censor.log')
    plan['audio']['uncensored_mix']=str(mix);plan['audio']['mix']=str(target);plan['audio']['censor']={'mode':'bleep_mask','intervals':windows,'dictionary_approved':True};return str(target)

def raster_report(video,plan,cfg):
    """Sample actual encoded paint colors; never certify all backgrounds/meaning."""
    try:import numpy as np
    except ImportError:return {'status':'unavailable','contrast_ratio':None,'reason':'NumPy belum tersedia','scope':'actual encoded raster sampling'}
    from .caption_geometry import bounds
    phrases=plan.get('captions',{}).get('phrases',[])
    if not phrases:return {'status':'not_applicable','contrast_ratio':None,'samples':[]}
    selected=sorted({round(i*(len(phrases)-1)/max(1,min(6,len(phrases))-1)) for i in range(min(6,len(phrases)))})
    requests=[]
    for i in selected:
        p=phrases[i];d=p['end']-p['start']
        for offset in sorted({min(.04,d*.15),min(.2,d*.55)}):requests.append((p,max(0,min(plan['duration']-1/cfg.output_fps,p['start']+offset))))
    def luminance(rgb):
        a=np.array(rgb,dtype=float)/255.;linear=np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
        return float(linear @ np.array([.2126,.7152,.0722]))
    rows=[]
    for p,t in requests[:12]:
        result=subprocess.run(['ffmpeg','-nostdin','-v','error','-ss',str(t),'-i',str(video),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True)
        if result.returncode or len(result.stdout)!=plan['width']*plan['height']*3:
            rows.append({'time':t,'status':'unmeasured','contrast_ratio':None,'reason':'Frame raster tidak dapat diukur'});continue
        pixels=np.frombuffer(result.stdout,dtype=np.uint8).reshape(plan['height'],plan['width'],3)
        for word in p['words']:
            k=sample(word,t-p['start'])
            if k['opacity']<.98:continue
            x,y,w,h=bounds(word,k);x0,y0=max(0,math.floor(x)),max(0,math.floor(y));x1,y1=min(plan['width'],math.ceil(x+w)),min(plan['height'],math.ceil(y+h))
            roi=pixels[y0:y1,x0:x1].reshape(-1,3).astype(float)
            paint=word['paint'];color=np.array(ImageColor.getrgb(k.get('color',word['color'])),dtype=float)
            outline=np.array(ImageColor.getrgb(paint['stroke_color']),dtype=float)
            foreground=roi[np.max(abs(roi-color),axis=1)<=35]
            border=roi[np.max(abs(roi-outline),axis=1)<=35] if paint['stroke']>0 else np.empty((0,3))
            ratio=None;state='unmeasured'
            if len(foreground)>=4 and len(border)>=4:
                a,b=luminance(np.median(foreground,axis=0)),luminance(np.median(border,axis=0));ratio=(max(a,b)+.05)/(min(a,b)+.05);state='measured'
            rows.append({'time':round(t,6),'phrase_id':p['phrase_id'],'token':word['text'],'status':state,
                'contrast_ratio':round(ratio,3) if ratio is not None else None,'foreground_matching_pixels':len(foreground),'outline_matching_pixels':len(border),
                'scope':'matching encoded foreground/outline colors in predicted ink ROI; not every glyph boundary',
                'reason':None if ratio is not None else 'Paint tidak cukup terpisah/terukur; perlu review latar bergerak'})
    measured=[r['contrast_ratio'] for r in rows if r['contrast_ratio'] is not None]
    review=not measured or any(r['status']=='unmeasured' for r in rows) or min(measured,default=0)<4.5
    return {'status':'needs_review' if review else 'sampled_paint_pass','contrast_ratio':min(measured) if measured else None,
        'minimum_ratio':4.5,'samples':rows,'decoded_frames':min(12,len(requests)),'scope':'sampled actual MP4 paint colors; plan checks every motion keyframe',
        'limits':'Source-wide background contrast, complex script shaping, meaning and aesthetics still require human corpus review','G5':'pending_real_corpus'}

