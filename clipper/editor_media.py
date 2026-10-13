"""Measured M1 source edits on one shared clock; advanced effects are baked.

The original source and transcript remain intact. Both ratios use the same
frame-grid edit proxy. Native exports identify these source edits as baked.
"""
import copy
import math
import re
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path

from . import editor_contract as ec, ffmpeg_util
from .contracts import fingerprint
from .dependency_cache import content_id
from .storage import read_json, write_json


def _run(command, *, timeout=180):
    process=subprocess.run([str(x) for x in command],capture_output=True,timeout=timeout)
    if process.returncode:
        raise ValueError('Tahap edit media FFmpeg gagal: '+process.stderr.decode('utf-8','replace')[-1400:])
    return process.stdout


def source_path(doc):
    working=doc['source'].get('media_context',{}).get('payload',{}).get('working_path')
    return working if working and Path(working).is_file() else doc['source']['path']


def camera_record(service,doc,operation):
    path=Path(operation.get('path','')).expanduser().resolve()
    if not path.is_file():
        raise ValueError('Video kamera tidak ditemukan')
    info=ffmpeg_util.probe(path)
    offset=operation.get('offset_seconds',0.)
    if isinstance(offset,bool) or not math.isfinite(float(offset)) or abs(float(offset))>3600:
        raise ValueError('Offset kamera harus detik hingga ±3600')
    evidence=operation.get('sync_evidence')
    identity=content_id(path,fresh=True)
    if evidence:
        if evidence.get('primary_content_id')!=content_id(source_path(doc),fresh=True) or evidence.get('camera_content_id')!=identity:
            raise ValueError('Bukti sinkronisasi berasal dari sumber/kamera berbeda')
        # Only a server measurement is evidence; decoding precedes the project write lock.
        with service.store.connect() as db:
            saved=db.execute('SELECT data FROM editor_sync_evidence WHERE id=? AND project_id=?',
                (evidence.get('id'),doc['project_id'])).fetchone()
        if saved is None:raise ValueError('Bukti sync server tidak ditemukan; ukur kembali')
        import json
        measured=json.loads(saved['data'])
        if measured['primary_content_id']!=content_id(source_path(doc),fresh=True) or measured['camera_content_id']!=identity:
            raise ValueError('Masukan bukti sync berubah; ukur kembali')
        if measured['status']!='ready':
            raise ValueError('Sinkronisasi otomatis perlu review: '+measured['message'])
        offset=measured['offset_seconds']
        sync={'method':'measured_pcm_correlation',**measured}
    else:
        if operation.get('confirm_manual_offset') is not True:
            raise ValueError('Offset manual perlu dikonfirmasi setelah memeriksa awal, tengah, dan akhir')
        sync={'method':'manual_review','status':'user_confirmed','measured':False,
            'note':'Offset diberikan operator; drift tidak dinilai otomatis.'}
    return {'id':'camera-'+identity[:20],'name':str(operation.get('name',path.stem))[:100],
        'path':str(path),'content_id':identity,'offset_seconds':float(offset),
        'duration':info['duration'],'width':info['width'],'height':info['height'],'sync':sync}


def _pcm(path,start,duration):
    import numpy as np
    raw=_run(['ffmpeg','-v','error','-nostdin','-ss',f'{start:.6f}','-i',path,'-t',f'{duration:.6f}',
        '-map','0:a:0','-ac','1','-ar','4000','-f','f32le','pipe:1'],timeout=45)
    return np.frombuffer(raw,dtype='<f4').astype(float)


def _correlate(reference,search,sample_rate=4000):
    import numpy as np
    if len(search)<len(reference) or len(reference)<sample_rate:
        return None
    # Remove DC and use first differences so background DC is not a sync cue.
    a=np.diff(reference);b=np.diff(search)
    energy=float(np.dot(a,a))
    if energy<1e-5 or float(np.mean(reference*reference))<1e-7:
        return None
    n=1<<(len(a)+len(b)-2).bit_length()
    conv=np.fft.irfft(np.fft.rfft(b,n)*np.fft.rfft(a[::-1],n),n)
    dot=conv[len(a)-1:len(b)]
    summed=np.r_[0.,np.cumsum(b*b)]
    norms=np.sqrt(np.maximum(1e-12,energy*(summed[len(a):]-summed[:-len(a)])))
    scores=dot/norms
    best=int(np.argmax(scores))
    exclusion=round(.3*sample_rate)
    rest=np.r_[scores[:max(0,best-exclusion)],scores[min(len(scores),best+exclusion):]]
    second=float(np.max(rest)) if len(rest) else 0.
    return {'offset_samples':best,'score':float(scores[best]),'runner_up':second}


def sync_evidence(service,doc,path):
    primary=source_path(doc);path=str(Path(path).expanduser().resolve())
    a,b=ffmpeg_util.probe(primary),ffmpeg_util.probe(path)
    if not a['has_audio'] or not b['has_audio']:
        raise ValueError('Sinkronisasi otomatis memerlukan audio pada kedua kamera')
    duration=min(a['duration'],b['duration'])
    if duration<8:
        raise ValueError('Periksa offset manual untuk sumber kamera kurang dari 8 detik')
    windows=[]
    size=min(4.,duration/5)
    for t in (0.,max(0.,duration/2-size/2),max(0.,duration-size)):
        left=max(0.,t-8.)
        length=min(b['duration']-left,size+16.)
        correlation=_correlate(_pcm(primary,t,size),_pcm(path,left,length))
        windows.append({'primary_start':t,**(correlation or {'score':0.,'runner_up':0.,'offset_samples':None}),
            'offset_seconds':left+correlation['offset_samples']/4000-t if correlation else None})
    offsets=[r['offset_seconds'] for r in windows if r['offset_seconds'] is not None]
    valid=len(offsets)==3 and all(r['score']>=.55 and r['score']-r['runner_up']>=.08 for r in windows)
    drift=max(offsets)-min(offsets) if offsets else None
    fps=service.config(doc).output_fps
    ready=valid and drift<=1/fps
    result={'schema_version':1,'status':'ready' if ready else 'review','offset_seconds':sorted(offsets)[len(offsets)//2] if offsets else None,
        'drift_seconds':drift,'tolerance_seconds':1/fps,'windows':windows,'sample_rate':4000,
        'primary_content_id':content_id(primary,fresh=True),'camera_content_id':content_id(path,fresh=True),
        'message':'Offset dan drift lolos pada awal/tengah/akhir.' if ready else 'Sinyal lemah, ambigu, atau drift melebihi satu frame. Periksa offset manual.'}
    result['id']='sync-'+fingerprint([doc['project_id'],result])[:32]
    from .project_store import dumps
    import time
    with service.store.connect() as db:
        db.execute('INSERT OR IGNORE INTO editor_sync_evidence VALUES(?,?,?,?)',(result['id'],doc['project_id'],dumps(result),time.time()))
    return result


def filmstrip(service,doc,cid,vid,count):
    if type(count) is not int or not 2<=count<=24:
        raise ValueError('Filmstrip harus memuat 2–24 frame')
    variant=service.variant(doc,cid,vid)
    clock=ec.build_clock(ec.segments_for(doc['clips'][cid],variant),service.config(doc,cid,vid).output_fps)
    base=source_path(doc);digest=fingerprint([clock['digest'],content_id(base),doc.get('editor_cameras'),count])
    folder=service.work/doc['project_id']/'editor-filmstrip'/digest[:24]
    folder.mkdir(parents=True,exist_ok=True)
    frames=[]
    for i in range(count):
        output_time=i/count*clock['duration']
        mapping=ec.output_to_source(clock,output_time)
        camera=doc.get('editor_cameras',{}).get(mapping['camera_id'])
        path=camera['path'] if camera else base
        timestamp=mapping['source_time']+(camera['offset_seconds'] if camera else 0.)
        if timestamp<0 or camera and timestamp>=camera['duration']:
            raise ValueError('Kamera tidak mencakup waktu sumber filmstrip; periksa offset')
        target=folder/(str(i)+'.jpg')
        if not target.is_file():
            _run(['ffmpeg','-v','error','-nostdin','-y','-ss',f'{timestamp:.6f}','-i',path,'-frames:v','1','-vf','scale=240:-2','-q:v','3',target],timeout=30)
        if not target.is_file():
            raise ValueError('Decoder tidak menghasilkan frame filmstrip. Periksa sumber/codec.')
        frames.append({'output_time':output_time,**mapping,'url':service.register_file(doc['project_id'],target)})
    return {'revision':doc['revision'],'clock_digest':clock['digest'],'frames':frames}


def _atempo(rate):
    filters=[]
    while rate>2:
        filters.append('atempo=2');rate/=2
    while rate<.5:
        filters.append('atempo=0.5');rate*=2
    return ','.join([*filters,f'atempo={rate:.9f}'])


def _chunks(clock):
    """Bound reverse filter RAM without changing the canonical temporal mapping."""
    for row in clock['slices']:
        source_duration=ec.seconds(row['source_end_tick']-row['source_start_tick'])
        n=max(1,math.ceil(source_duration/4.)) if row['reverse'] else 1
        edges=[round(row['source_start_tick']+(row['source_end_tick']-row['source_start_tick'])*i/n) for i in range(n+1)]
        frame_edges=[round(row['duration_frames']*i/n) for i in range(n+1)]
        indices=range(n-1,-1,-1) if row['reverse'] else range(n)
        for i in indices:
            frames=frame_edges[i+1]-frame_edges[i]
            if frames:
                yield {**row,'source_start_tick':edges[i],'source_end_tick':edges[i+1],'duration_frames':frames}


def _remap_recipe(recipe,clock):
    result={**copy.deepcopy(recipe),'scenes':[]}
    for scene in recipe.get('scenes',[]):
        if not scene.get('enabled',True):continue
        a,b=ec.tick(scene['source_start']),ec.tick(scene['source_end'])
        for row in clock['slices']:
            left,right=max(a,row['source_start_tick']),min(b,row['source_end_tick'])
            if right<=left or row['kind']=='freeze':
                continue
            if row['reverse'] or abs(row['render_speed']-1)>1e-9:
                raise ValueError('Ilustrasi video pada reverse/ramp belum mempunyai clock aset yang aman. Nonaktifkan ilustrasi itu atau render tanpa edit waktu tersebut.')
            start=row['output_start_frame']/clock['fps']+(left-row['source_start_tick'])/1e6
            result['scenes'].append({**copy.deepcopy(scene),'id':scene['id']+'@'+row['logical_segment_id'],
                'source_start':start,'source_end':start+(right-left)/1e6,'asset_start':scene.get('asset_start',0)+(left-a)/1e6})
    return result


def prepare(service,doc,cid,vid,source,words,clip,cfg,progress=lambda *_:None):
    variant=service.variant(doc,cid,vid);editor=variant.get('editor',{})
    if not editor:
        return source,words,clip,cfg,None
    clock=ec.build_clock(ec.segments_for(doc['clips'][cid],variant),cfg.output_fps)
    tracks=ec.track_state(editor)
    if not editor.get('segments') and not any(editor.get('curves',{}).values()) and not editor.get('hidden_caption_word_ids') and all(r['enabled'] for r in tracks.values()):
        return source,words,clip,cfg,None
    cameras=doc.get('editor_cameras',{})
    for row in clock['slices']:
        if row['camera_id']=='primary':
            continue
        camera=cameras.get(row['camera_id'])
        if not camera or content_id(camera['path'],fresh=True)!=camera['content_id']:
            raise ValueError('Berkas kamera hilang/berubah; registrasikan ulang dan periksa sinkronisasi')
        a,b=ec.seconds(row['source_start_tick']),ec.seconds(row['source_end_tick'])
        if a+camera['offset_seconds']<0 or b+camera['offset_seconds']>camera['duration']+.01:
            raise ValueError('Kamera tidak mencakup potongan sumber; periksa offset dan batas')
    recipe=_remap_recipe(clip.get('_broll_recipe',{}) if tracks['illustration']['enabled'] and cfg.broll_mode!='off' else {'scenes':[]},clock)
    values={'broll_mode':cfg.broll_mode if tracks['illustration']['enabled'] else 'off',
        'illustration_mode':cfg.illustration_mode if tracks['illustration']['enabled'] else 'off',
        'music_path':cfg.music_path if tracks['music']['enabled'] else '',
        'sfx_path':cfg.sfx_path if tracks['sfx']['enabled'] else '',
        'sfx_mode':cfg.sfx_mode if tracks['sfx']['enabled'] else 'off',
        'cold_open':False,'title_card':False,'trim_silence':False,'punch_zoom':False,'align_selected_clips':False}
    cfg=replace(cfg,**values)
    info=ffmpeg_util.probe(source)
    width,height=info['width']//2*2,info['height']//2*2
    identities={k:r['content_id'] for k,r in cameras.items() if any(s['camera_id']==k for s in clock['slices'])}
    key=fingerprint([ec.VERSION,content_id(source),clock['digest'],identities,editor.get('curves'),
        {k:v['enabled'] for k,v in tracks.items()},width,height])
    folder=service.work/doc['project_id']/'editor-proxies'/key[:32]
    cached=read_json(folder/'receipt.json',{})
    proxy=folder/'edited.mp4'
    reused=proxy.is_file() and cached.get('content_id')==content_id(proxy,fresh=True)
    if not reused:
        folder.mkdir(parents=True,exist_ok=True)
        attempt=folder/('attempt-'+uuid.uuid4().hex);attempt.mkdir()
        files=[]
        chunks=list(_chunks(clock))
        for i,row in enumerate(chunks):
            progress(3+round(i/max(1,len(chunks))*12),'Menerapkan clock potongan, audio, dan kamera')
            camera=cameras.get(row['camera_id']);path=camera['path'] if camera else source
            start,end=ec.seconds(row['source_start_tick']),ec.seconds(row['source_end_tick'])
            camera_offset=camera['offset_seconds'] if camera else 0.
            duration=row['duration_frames']/clock['fps']
            filt=[]
            if tracks['video']['enabled']:
                v=f'[0:v]trim=start={start+camera_offset:.9f}:end={end+camera_offset:.9f},setpts=PTS-STARTPTS'
                if row['kind']=='freeze':
                    v+=f',trim=end_frame=1,tpad=stop_mode=clone:stop_duration={duration:.9f}'
                else:
                    if row['reverse']:
                        v+=',reverse'
                    v+=f',setpts=PTS/{row["render_speed"]:.9f}'
                v+=f',scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={cfg.output_fps},tpad=stop_mode=clone:stop_duration=1,trim=end_frame={row["duration_frames"]},setpts=N/({cfg.output_fps}*TB)[v]'
            else:
                v=f'color=c=black:s={width}x{height}:r={cfg.output_fps}:d={duration:.9f},trim=end_frame={row["duration_frames"]}[v]'
            filt.append(v)
            if tracks['voice']['enabled'] and row['kind']!='freeze':
                audio=f'[1:a]atrim=start={start:.9f}:end={end:.9f},asetpts=PTS-STARTPTS'
                if row['reverse']:
                    audio+=',areverse'
                audio+=','+_atempo(row['render_speed'])+f',aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={duration:.9f},asetpts=PTS-STARTPTS[a]'
            else:
                audio=f'anullsrc=r=48000:cl=stereo,atrim=duration={duration:.9f},asetpts=PTS-STARTPTS[a]'
            filt.append(audio)
            script=attempt/(str(i)+'.filter.txt');script.write_text(';\n'.join(filt),encoding='utf-8')
            part=attempt/(str(i)+'.nut')
            command=['ffmpeg','-v','error','-nostdin','-y','-threads','2','-i',path,'-i',source,
                *ffmpeg_util.filter_file_args(str(script)),'-filter_complex_threads','1','-map','[v]','-map','[a]',
                '-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-c:a','pcm_s16le','-ar','48000','-ac','2','-t',f'{duration:.9f}',part]
            _run(command,timeout=max(180,min(1800,(end-start)*15)))
            files.append((part,duration))
        # File names are internal UUID/numeric paths. Quote apostrophes for concat syntax.
        listing=attempt/'concat.txt'
        listing.write_text('ffconcat version 1.0\n'+''.join("file '"+str(p.resolve()).replace("'","'\\''")+f"'\nduration {duration:.9f}\n" for p,duration in files),encoding='utf-8')
        combined=attempt/'joined.mp4'
        _run(['ffmpeg','-v','error','-nostdin','-y','-f','concat','-safe','0','-i',listing,'-c:v','copy','-c:a','aac','-t',f'{clock["duration"]:.9f}','-movflags','+faststart',combined],timeout=180)
        curves=editor.get('curves',{})
        if any(curves.values()):
            scale=ec.ffmpeg_curve(curves.get('scale'),1.)
            x=ec.ffmpeg_curve(curves.get('x'),0.);y=ec.ffmpeg_curve(curves.get('y'),0.)
            opacity=ec.ffmpeg_curve(curves.get('opacity'),1.)
            # scale/x/y are source-image transforms, independent of the ratio composition.
            opacity=re.sub(r'\bt\b','T',opacity)
            text=f"[0:v]scale=w='ceil({width}*({scale})/2)*2':h='ceil({height}*({scale})/2)*2':eval=frame[scaled];color=c=black:s={width}x{height}:r={cfg.output_fps}:d={clock['duration']:.9f}[bg];[bg][scaled]overlay=x='(W-w)/2+({x})*W/2':y='(H-h)/2+({y})*H/2':eval=frame:shortest=1[image];color=c=black:s={width}x{height}:r={cfg.output_fps}:d={clock['duration']:.9f}[dark];[image][dark]blend=all_expr='A*({opacity})+B*(1-({opacity}))':shortest=1[v]"
            script=attempt/'curves.filter.txt';script.write_text(text,encoding='utf-8')
            transformed=attempt/'curved.mp4'
            _run(['ffmpeg','-v','error','-nostdin','-y','-i',combined,*ffmpeg_util.filter_file_args(str(script)),
                '-filter_complex_threads','1','-map','[v]','-map','0:a','-c:v','libx264','-preset','veryfast','-crf','18',
                '-pix_fmt','yuv420p','-c:a','copy','-frames:v',str(clock['duration_frames']),'-movflags','+faststart',transformed],timeout=1800)
            combined=transformed
        measured=ffmpeg_util.probe(combined)
        if abs(measured['duration']-clock['duration'])>max(.06,2/cfg.output_fps):
            raise ValueError('Durasi proxy tidak cocok dengan clock; hasil final sebelumnya dipertahankan')
        combined.replace(proxy)
        write_json(folder/'receipt.json',{'schema_version':1,'content_id':content_id(proxy,fresh=True),'clock':clock,'tracks':tracks,'curves':curves,
            'source_content_id':content_id(source),'camera_content_ids':identities,'advanced_source_layer':'baked',
            'audio_policy':'speech follows rate/reverse; freeze is silence','duration_measured':measured['duration']})
        import shutil
        shutil.rmtree(attempt)
    mapped=ec.remap_words(words,clock,editor.get('hidden_caption_word_ids',[]))
    display=[w for w in mapped if not w['caption_hidden']] if tracks['captions']['enabled'] else []
    proxy_clip={**clip,'start':0.,'end':clock['duration'],'manual_keep_spans':[[0.,clock['duration']]],
        '_broll_recipe':recipe,'_editor_clock':clock,'_editor_tracks':tracks,'_editor_original_bounds':[clip['start'],clip['end']],
        '_editor_source':str(source),'_editor_proxy_content_id':content_id(proxy),
        '_editor_hidden_caption_word_ids':editor.get('hidden_caption_word_ids',[])}
    controls=copy.deepcopy(cfg.visual_overrides or {})
    if controls.get('pins'):
        pins=[]
        for pin in controls['pins']:
            # Pins use source seconds. Repeated/reordered spans produce explicit instances.
            for row in clock['slices']:
                a,b=ec.seconds(row['source_start_tick']),ec.seconds(row['source_end_tick'])
                x,y=max(a,pin['start']),min(b,pin['end'])
                if y<=x or row['kind']=='freeze':continue
                offset=row['output_start_frame']/clock['fps'];length=row['duration_frames']/clock['fps']
                left,right=(offset+(b-y)/(b-a)*length,offset+(b-x)/(b-a)*length) if row['reverse'] else (offset+(x-a)/(b-a)*length,offset+(y-a)/(b-a)*length)
                pins.append({**pin,'start':left,'end':right})
        controls['pins']=pins
    cfg=replace(cfg,visual_overrides=controls,source_content_id=content_id(proxy))
    return str(proxy),display,proxy_clip,cfg,{'clock':clock,'proxy_path':str(proxy),'content_id':content_id(proxy),'reused':reused,'source_layer':'baked'}
