"""M4 geometry is executed by the actual core FFmpeg renderer, before captions."""
import copy
from pathlib import Path
from . import camera4_contract as c,camera4_plan as planning
from .dependency_cache import content_id
from .contracts import fingerprint


def interpolate(path,t,default):
    if not path:return list(default)
    if t<=path[0]['time']:return list(path[0]['box'])
    for a,b in zip(path,path[1:]):
        if t<=b['time']:
            u=(t-a['time'])/(b['time']-a['time']);return [x+(y-x)*u for x,y in zip(a['box'],b['box'])]
    return list(path[-1]['box'])


def apply(plan,clip,cfg,info):
    report=clip['_m4_camera'];settings=report['settings'];clock=clip.get('_editor_clock');fps=plan['fps'];W,H=plan['width'],plan['height'];shots=[]
    # Canonical decisions use source seconds. Resolve them on every output
    # frame so reorder/rate/reverse/freeze follow the same M1 clock.
    for span in plan['spans']:
        count=span['duration_frames'];previous=None
        for frame in range(count):
            media_time=span['source_start']+frame/fps
            if clock:
                from .editor_contract import output_to_source
                mapping=output_to_source(clock,media_time)
                if not mapping:raise ValueError('Clock kamera tidak mencakup frame render')
                original=mapping['source_time'];camera=mapping['camera_id']
            else:original=media_time;camera='primary'
            segment=next((s for s in report['segments'] if s['start']-1e-6<=original<s['end']+1e-6),None)
            if segment is None:raise ValueError('Komposisi M4 tidak mencakup sumber aktif; analisis ulang kamera')
            if camera!='primary':raise ValueError('Kamera alternatif memerlukan komposisi M4 sendiri; matikan M4 atau gunakan kamera utama')
            built=planning.layers(segment,W,H,settings);layers=built['layers']
            for layer in layers:
                path=layer.pop('path');layer['source_crop']=interpolate(path,original,layer['source_crop'])
            matte=report.get('matte');mask=None
            if matte and matte['start']<=original<matte['end'] and not any(p['kind'] in ('material','hud','ocr') for p in segment['protected_source']):
                if content_id(matte['path'])!=matte['content_id']:raise ValueError('Carrier mask berubah; hasil sebelumnya dipertahankan')
                mask={**matte,'time':original-matte['start']}
            attachment=None
            if report.get('attachment') and report.get('tracking'):
                rows=report['tracking']['measurements']
                if rows and rows[0]['time']<=original<=rows[-1]['time']:
                    near=min(rows,key=lambda r:abs(r['time']-original))
                    if abs(near['time']-original)<=.125:
                        attachment={**report['attachment'],'corners':near['corners']}
            key=fingerprint([segment['shot_id'],segment['layout'],layers,mask and [mask['content_id'],round(mask['time'],6)]])
            if attachment:key=fingerprint([key,attachment])
            # Static no-pan sections are merged. Moving sections use frame-exact
            # source geometry rather than output expressions drifting after edits.
            if previous and previous['_key']==key:
                previous['duration_frames']+=1;previous['end']+=1/fps;previous['source_end']+=1/fps
            else:
                item={'start':span['start_frame']/fps+frame/fps,'end':span['start_frame']/fps+(frame+1)/fps,
                    'source_start':media_time,'source_end':media_time+1/fps,'duration_frames':1,'rect':[0,0,info['width'],info['height']],
                    'mode':'fit','face_rect':None,'zoom_at':None,'has_material':bool(segment['material']),
                    'protected_source':[],'protected_output':built['protected_output'],'caption_panel':built['caption_panel'],'position':'bottom',
                    'm4':{'shot_id':segment['shot_id'],'layers':layers,'background':settings['background'],'mask':mask,'safe_rect':built['safe_rect'],
                        'fallbacks':segment['fallbacks'],'motion':settings['motion'],'source_time':original,'attachment':attachment},'_key':key}
                shots.append(item);previous=item
    # Static stays compact. Moving/masked layouts use a streamed baked layer;
    # the filter graph never grows by one branch for every frame.
    for shot in shots:shot.pop('_key',None)
    plan['shots']=shots;plan['m4']={'version':c.VERSION,'analysis_id':report['analysis_id'],'source_size':report['source_size'],
        'approved_revision':report.get('approved_revision'),'motion':settings['motion'],'no_pan':settings['motion']=='static',
        'source_clock':clock['digest'] if clock else None,'mask_rendered_frames':sum(s['duration_frames'] for s in shots if s['m4']['mask']),
        'quality_gate':'G4_pending_real_corpus'}
    plan['visual_summary']={'version':c.VERSION,'sample_count':report['coverage']['sample_count'],'source_reviewed':True}
    return plan


def shot_graph(shot,index,seek,plan,extra_inputs):
    """Returns one composited shot label. No shell expressions or fake media."""
    W,H,fps=plan['width'],plan['height'],plan['fps'];meta=shot['m4'];duration=shot['duration_frames']/fps;graph=[]
    if meta['background']=='blur':
        graph.append(f"[0:v]trim=start={shot['source_start']-seek:.8f}:end={shot['source_end']-seek:.8f},setpts=PTS-STARTPTS,fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=16:2[bg{index}]")
    else:graph.append(f'color=c=0x11151b:s={W}x{H}:r={fps}:d={duration:.8f}[bg{index}]')
    previous=f'bg{index}'
    for j,layer in enumerate(meta['layers']):
        x,y,w,h=layer['source_crop'];x,y=int(x)//2*2,int(y)//2*2;w,h=int(w)//2*2,int(h)//2*2
        vx,vy,vw,vh=layer['viewport'];label=f'm4_{index}_{j}'
        prefix=f"[0:v]trim=start={shot['source_start']-seek:.8f}:end={shot['source_end']-seek:.8f},setpts=PTS-STARTPTS,fps={fps}"
        mask=meta.get('mask') if j==0 else None
        if mask:
            number=2+len(extra_inputs)//2;extra_inputs.extend(['-i',mask['path']]);mt=mask['time']
            graph.append(prefix+f'[fg{index}_{j}]')
            graph.append(f'[{number}:v]trim=start={mt:.8f}:duration={duration:.8f},setpts=PTS-STARTPTS,fps={fps},format=gray[a{index}_{j}]')
            graph.append(f'[fg{index}_{j}][a{index}_{j}]alphamerge,crop={w}:{h}:{x}:{y},scale={vw}:{vh}:force_original_aspect_ratio=decrease,format=rgba,pad={vw}:{vh}:(ow-iw)/2:(oh-ih)/2:color=0x00000000[{label}]')
        else:graph.append(prefix+f',crop={w}:{h}:{x}:{y},scale={vw}:{vh}:force_original_aspect_ratio=decrease,pad={vw}:{vh}:(ow-iw)/2:(oh-ih)/2:color=0x11151b[{label}]')
        out=f'm4mix{index}_{j}';graph.append(f'[{previous}][{label}]overlay={vx}:{vy}:shortest=1[{out}]');previous=out
    graph.append(f'[{previous}]setsar=1,format=yuv420p,trim=end_frame={shot["duration_frames"]},setpts=N/({fps}*TB)[v{index}]')
    return graph


def bake(source,plan,cfg,folder,on_progress=None):
    """Stream source RGB through approved geometry, with bounded frame memory."""
    import subprocess,uuid
    from PIL import Image,ImageOps,ImageFilter
    from .storage import read_json,write_json
    from .ffmpeg_util import probe
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);W,H,fps=plan['width'],plan['height'],plan['fps'];info=probe(source);sw,sh=info['width'],info['height']
    key=fingerprint([c.VERSION,content_id(source,fresh=True),plan['shots'],W,H,fps]);path=folder/(key[:32]+'.mp4');meta=path.with_suffix('.json');cached=read_json(meta)
    if cached and path.is_file() and content_id(path,fresh=True)==cached.get('content_id'):return str(path),{**cached,'cache_reused':True}
    masks={}
    for shot in plan['shots']:
        mask=shot['m4'].get('mask')
        if mask:
            for row in mask['model_samples']:
                if content_id(row['path'],fresh=True)!=row['content_id']:raise ValueError('Sampel mask berubah sebelum render')
            masks[mask['content_id']]=mask
    pending=folder/(uuid.uuid4().hex+'.pending.mp4');count=round(plan['duration']*fps)
    encoder=subprocess.Popen(['ffmpeg','-nostdin','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',str(W)+'x'+str(H),'-r',str(fps),'-i','-',
        '-an','-c:v','libx264','-preset','veryfast','-crf','18','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(pending)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    rendered=0;mask_frames=0;decoder=None
    try:
        for span in plan['spans']:
            frames=span['duration_frames'];decoder=subprocess.Popen(['ffmpeg','-nostdin','-v','error','-ss',str(span['source_start']),'-i',str(source),
                '-an','-vf',f'fps={fps},tpad=stop_mode=clone:stop_duration=0.1,trim=end_frame={frames}',
                '-frames:v',str(frames),'-f','rawvideo','-pix_fmt','rgb24','-threads','1','-'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            for frame in range(frames):
                raw=bytearray()
                while len(raw)<sw*sh*3:
                    part=decoder.stdout.read(sw*sh*3-len(raw))
                    if not part:raise ValueError('Decode source layer M4 tidak lengkap')
                    raw.extend(part)
                original=Image.frombytes('RGB',(sw,sh),bytes(raw));output_time=(span['start_frame']+frame)/fps
                shot=next(s for s in plan['shots'] if s['start']-1e-7<=output_time<s['end']-1e-7)
                data=shot['m4'];canvas=ImageOps.fit(original,(W,H)).filter(ImageFilter.GaussianBlur(12)) if data['background']=='blur' else Image.new('RGB',(W,H),'#11151b')
                if data.get('attachment'):
                    item=data['attachment']
                    if content_id(item['path'])!=item['content_id']:raise ValueError('Attachment berubah ketika render')
                    with Image.open(item['path']) as asset:attached=warp_attachment(asset.convert('RGBA'),item['corners'],(sw,sh),item['opacity'])
                    original=Image.alpha_composite(original.convert('RGBA'),attached).convert('RGB')
                for index,layer in enumerate(data['layers']):
                    x,y,w,h=layer['source_crop'];vx,vy,vw,vh=layer['viewport'];region=(int(x),int(y),int(x+w),int(y+h));tile=original.crop(region)
                    scale=min(vw/tile.width,vh/tile.height);size=(max(1,round(tile.width*scale)),max(1,round(tile.height*scale)));image=tile.resize(size,Image.Resampling.LANCZOS)
                    alpha=None;mask=data.get('mask') if index==0 else None
                    if mask:
                        # Sample-held matte follows the exact canonical source
                        # time, including reverse, freeze and repeated spans.
                        at=mask['time']
                        row=mask['model_samples'][min(len(mask['model_samples'])-1,max(0,int(at*mask['model_sample_fps'])))]
                        with Image.open(row['path']) as m:alpha=m.convert('L').crop(region).resize(size,Image.Resampling.NEAREST)
                        mask_frames+=1
                    canvas.paste(image,(vx+(vw-size[0])//2,vy+(vh-size[1])//2),alpha)
                encoder.stdin.write(canvas.tobytes());rendered+=1
                if on_progress and rendered%max(1,round(fps))==0:on_progress(20+int(60*rendered/max(1,count)),'Menerapkan kamera dan matte kontinu')
            decoder.stdout.close()
            if decoder.wait(timeout=30)!=0:raise ValueError('Decode kamera M4 gagal')
            decoder=None
        encoder.stdin.close();error=encoder.stderr.read();status=encoder.wait(timeout=120)
        if status or rendered!=count:raise ValueError('Encode source layer M4 gagal: '+error.decode('utf-8','replace')[-500:])
        actual=probe(pending)
        if abs(actual['duration']-plan['duration'])>2/fps:raise ValueError('Source layer M4 tidak sesuai clock final')
        pending.replace(path);receipt={'version':c.VERSION,'path':str(path),'content_id':content_id(path,fresh=True),'frames':rendered,'mask_frames':mask_frames,
            'duration':actual['duration'],'dimensions':[W,H],'geometry_digest':key,'bounded_memory':'one source and output frame; CPU','cache_reused':False}
        write_json(meta,receipt);return str(path),receipt
    finally:
        for process in (decoder,encoder):
            if process and process.poll() is None:process.terminate();process.wait(timeout=10)
        pending.unlink(missing_ok=True)


def warp_attachment(image,corners,size,opacity):
    """Inverse homography in canonical source pixels, executed by Pillow."""
    import numpy as np
    from PIL import Image
    source=[(0,0),(image.width,0),(image.width,image.height),(0,image.height)];matrix=[];values=[]
    for (x,y),(u,v) in zip(corners,source):
        matrix.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]);values.extend([u,v])
    coefficients=np.linalg.solve(np.asarray(matrix,float),np.asarray(values,float))
    if not np.isfinite(coefficients).all():raise ValueError('Homography attachment tidak terukur')
    warped=image.transform(size,Image.Transform.PERSPECTIVE,coefficients.tolist(),Image.Resampling.BICUBIC)
    if opacity<1:warped.putalpha(warped.getchannel('A').point(lambda v:round(v*opacity)))
    return warped
