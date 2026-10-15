"""M6 local audio execution: separate evidence, additive stems and final master."""
import copy
import json
import math
import shutil
import subprocess
import zipfile
from dataclasses import replace
from pathlib import Path
from .audio6_contract import VERSION,RATE,MAX_SECONDS,effective
from .dependency_cache import content_id
from .storage import read_json,write_json

def run_float(args,target,log=None):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);pending=target.with_name(target.stem+'.partial.wav')
    try:
        p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-v','error','-y',*map(str,args),'-ar',str(RATE),'-ac','2','-c:a','pcm_f32le',str(pending)],capture_output=True,timeout=600)
        if p.returncode:
            error=p.stderr.decode('utf-8','replace')[-1800:]
            if log:Path(log).write_text(error)
            raise ValueError('Audio M6 gagal: '+error)
        pending.replace(target)
    finally:pending.unlink(missing_ok=True)
    return str(target.resolve())

def _filter(source,target,filters,duration):
    return run_float(['-i',source,'-vn','-af',','.join(filters or ['anull']),'-t',duration],target)

def _atempo(rate):
    from .editor_media import _atempo
    return _atempo(rate)

def source_stem(source,plan,cfg,folder):
    from .contracts import fingerprint
    from .render import voice_stem
    from .audio6_contract import asset_signature
    s=effective(cfg);folder=Path(folder)/'audio6';folder.mkdir(parents=True,exist_ok=True)
    signature=fingerprint([VERSION,content_id(source,fresh=True),plan['spans'],plan.get('editor',{}).get('clock'),s,asset_signature(cfg.audio6,fresh=True)])
    cache=read_json(folder/'source-receipt.json',{})
    if cache.get('signature')==signature and all(Path(p).is_file() and content_id(p,fresh=True)==digest for p,digest in cache.get('members',{}).items()) and cache.get('members'):
        plan['audio6_source']=cache['source'];return cache['source']['processed']
    # The legacy executor is used only to cut the approved source spans. M6
    # normalization belongs to the final mix, not this reusable source stem.
    raw=voice_stem(source,plan,replace(cfg,audio6=None,audio_normalize=False,join_fade_ms=0),folder)
    before=run_float(['-i',raw,'-vn','-t',plan['duration']],folder/'source-before.wav')
    source_info={'before':before,'source_content_id':content_id(source,fresh=True),'processing':[],'source_immutable':True}
    current=before
    if s['separation']=='demucs':
        from .audio6_models import separate
        separation=separate(before,folder/'separation',s);source_info['separation']=separation;current=separation['speech']
    filters=[]
    if s['source_gain_db']:filters.append(f"volume={s['source_gain_db']}dB")
    if s['denoise']=='fft':filters.append(f"afftdn=nr={s['noise_reduction_db']}:nf=-35:tn=1")
    elif s['denoise']=='nlmeans':filters.append(f"anlmdn=s={min(.5,.005*s['noise_reduction_db']):.5f}:p=0.002:r=0.006")
    if s['hum_hz']:
        filters.extend(f"bandreject=f={s['hum_hz']*i}:t=q:w=30" for i in range(1,5))
    if s['enhancement']:filters.extend(['highpass=f=65','equalizer=f=2800:t=q:w=1:g=2','deesser=i=0.15:m=0.3:f=0.5'])
    for band in s['eq_bands']:filters.append(f"equalizer=f={band['hz']}:t=q:w={band['q']}:g={band['gain_db']}")
    if s['compressor']:filters.append(f"acompressor=threshold={10**(s['compressor_threshold_db']/20):.8f}:ratio={s['compressor_ratio']}:attack={s['compressor_attack_ms']}:release={s['compressor_release_ms']}:makeup=1")
    if s['pitch_semitones']:filters.append(f"rubberband=pitch={2**(s['pitch_semitones']/12):.9f}:tempo=1")
    current=_filter(current,folder/'source-filtered.wav',filters,plan['duration'])
    source_info['processing']=filters
    if s['dereverb']:
        from .audio6_dsp import decode,wpe,write
        current=write(folder/'source-dereverb.wav',wpe(decode(current,seconds=plan['duration']),s['dereverb_strength']))
        source_info['dereverb']={'backend':'local delayed linear prediction WPE','strength':s['dereverb_strength'],'neural_model':None,'listening_required':True}
    # Microfades touch only a measured gap beside a cut, never a word body.
    joins=[];fade_filters=[];words=plan.get('words',[]);smooth=s['smooth_ms']/1000
    for span in plan['spans']:
        a,b=span['start'],span['end'];inside=[w for w in words if w['end']>a and w['start']<b]
        left=min(smooth,max(0.,min((w['start'] for w in inside),default=b)-a))
        right=min(smooth,max(0.,b-max((w['end'] for w in inside),default=a)))
        if a>0 and left>0:fade_filters.append(f'afade=t=in:st={a:.9f}:d={left:.9f}')
        if b<plan['duration'] and right>0:fade_filters.append(f'afade=t=out:st={b-right:.9f}:d={right:.9f}')
        joins.append({'output_interval':[a,b],'in_seconds':left if a>0 else 0.,'out_seconds':right if b<plan['duration'] else 0.,'policy':'fade only gap; no overlap, word duplication or duration change'})
    # afade has no finite enable range: compose each fade as a bounded volume
    # expression so subsequent spans cannot remain accidentally silent.
    if fade_filters:
        from .audio6_dsp import decode,write
        import numpy as np
        samples=decode(current,seconds=plan['duration'])
        for row in joins:
            a,b=row['output_interval'];fi,fo=row['in_seconds'],row['out_seconds']
            if fi:
                left=max(0,round(a*RATE));right=min(len(samples),round((a+fi)*RATE));samples[left:right]*=np.linspace(0,1,right-left,dtype=np.float32)[:,None]
            if fo:
                left=max(0,round((b-fo)*RATE));right=min(len(samples),round(b*RATE));samples[left:right]*=np.linspace(1,0,right-left,dtype=np.float32)[:,None]
        current=write(folder/'source-smooth.wav',samples)
    source_info.update(processed=current,processed_content_id=content_id(current,fresh=True),join_policy=joins,
        normalization_applied=False,sample_rate=RATE)
    members={p:content_id(p,fresh=True) for p in (before,current)}
    if source_info.get('separation'):members[source_info['separation']['music']]=content_id(source_info['separation']['music'],fresh=True)
    write_json(folder/'source-receipt.json',{'signature':signature,'source':source_info,'members':members})
    plan['audio6_source']=source_info;return current

def _track(row,plan,folder):
    from .audio6_dsp import decode,write,loop,fixed,fade
    import numpy as np
    info=row['asset'];duration=info['metadata']['duration'];start=row['asset_start'];count=round(row['asset_seconds']*RATE)
    if row['loop']:
        origin=row.get('original_asset_start',0.);available=duration-origin
        if available<=.02:raise ValueError('Awal musik berada di luar aset')
        samples=decode(info['path'],start=origin,seconds=min(available,MAX_SECONDS))
        period=max(1,len(samples)-min(round(row['loop_crossfade']*RATE),len(samples)//4))
        offset=round(max(0.,start-origin)*RATE)%period
        samples=loop(samples,count+offset,row['loop_crossfade'])[offset:offset+count]
    else:
        available=duration-start
        if available<=0:raise ValueError('Awal track '+row['id']+' di luar aset')
        samples=decode(info['path'],start=start,seconds=min(available,row['asset_seconds'],MAX_SECONDS))
        samples=fixed(samples,count)
    if row['reverse']:samples=samples[::-1].copy()
    raw=write(folder/(row['event_id']+'-raw.wav'),samples)
    if abs(row['rate']-1)>1e-8:
        raw=_filter(raw,folder/(row['event_id']+'-speed.wav'),[_atempo(row['rate']),'apad',f"atrim=duration={row['end']-row['start']:.9f}"],row['end']-row['start'])
        samples=decode(raw,seconds=row['end']-row['start'])
    samples=fixed(samples,row['end_sample']-row['start_sample'])
    samples=fade(samples,min(row['fade_in'],len(samples)/RATE/2),min(row['fade_out'],len(samples)/RATE/2))*10**(row['gain_db']/20)
    event=write(folder/(row['event_id']+'.wav'),samples)
    # adelay with the S suffix is sample based, not millisecond rounding.
    return run_float(['-i',event,'-af',f"adelay={row['start_sample']}S:all=1,apad,atrim=end_sample={round(plan['duration']*RATE)}"],folder/(row['event_id']+'-aligned.wav'))

def _sum(paths,target,duration):
    args=[]
    for p in paths:args+=['-i',p]
    graph=''.join(f'[{i}:a]' for i in range(len(paths)))+f'amix=inputs={len(paths)}:normalize=0:duration=longest,apad,atrim=duration={duration:.9f}[out]'
    return run_float([*args,'-filter_complex_threads','1','-filter_complex',graph,'-map','[out]'],target)

def mute_windows(source,target,windows,duration):
    from .audio6_dsp import decode,write
    samples=decode(source,seconds=duration)
    for a,b in windows:samples[max(0,round(a*RATE)):min(len(samples),round(b*RATE))]=0
    return write(target,samples)

def premix(source,plan,cfg,folder):
    from .audio6_plan import build
    from .audio6_dsp import decode,write,duck_envelope
    import numpy as np
    folder=Path(folder)/'audio6';folder.mkdir(parents=True,exist_ok=True)
    p=build(plan,cfg);plan['audio6']=p;s=p['settings'];duration=plan['duration'];count=p['duration_samples']
    voice=source_stem(source,plan,cfg,folder.parent);track_state=cfg.audio6.get('track_state',{})
    if not track_state.get('voice',True):voice=run_float(['-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',duration],folder/'source-muted.wav')
    stems={'voice':voice};music=[];sfx=[];voices=[];asset_refs=[]
    for i,row in enumerate(p['events']):
        row['event_id']=f'event-{i:03d}-{row["id"]}';row['original_asset_start']=next(t['asset_start'] for t in cfg.audio6['tracks'] if t['id']==row['id'])
        path=_track(row,plan,folder);row['rendered_path']=path
        asset_refs.append(row['asset'])
        if row['owner']=='music':music.append(path)
        elif row['owner']=='sfx':sfx.append(path)
        else:stems[row['role']+'-'+row['id']+'-'+str(i)]=path;voices.append(row)
    if voices and any(r['replace_source'] for r in voices):
        stems['voice']=mute_windows(stems['voice'],folder/'source-dubbing-replaced.wav',[(r['start'],r['end']) for r in voices if r['replace_source']],duration)
    background=plan['audio6_source'].get('separation',{}).get('music')
    if background and track_state.get('music',True):music.append(_filter(background,folder/'separated-music-gain.wav',[f"volume={s['separation_background_db']}dB"],duration))
    # Existing local background paths are retained on opt-in. Their original
    # provenance remains explicitly legacy/unrecorded, never relabelled licensed.
    if cfg.music_path and track_state.get('music',True):
        from .ffmpeg_util import probe
        row=dict(id='legacy-music',event_id='legacy-music',asset={'path':cfg.music_path,'metadata':{'duration':probe(cfg.music_path)['duration']}},asset_start=0.,original_asset_start=0.,asset_seconds=duration,start=0.,end=duration,start_sample=0,end_sample=count,loop=True,loop_crossfade=.04,reverse=False,rate=1.,fade_in=.7,fade_out=min(1.2,duration/3),gain_db=cfg.music_db)
        music.append(_track(row,plan,folder));p['notes'].append({'legacy_music':cfg.music_path,'permission':'legacy_unrecorded; user must verify rights'})
    if cfg.sfx_path and cfg.sfx_mode!='off' and s['sfx_enabled'] and track_state.get('sfx',True):
        from .ffmpeg_util import probe
        candidates=sorted({ph['start'] for ph in plan.get('captions',{}).get('phrases',[]) if any(w.get('emphasis') for w in ph.get('words',[]))});previous=-1e9
        for at in candidates:
            if len(sfx)>=cfg.sfx_max:break
            if at-previous<cfg.sfx_gap_s or at+.65>duration or any(at<w['end'] and at+.65>w['start'] for w in plan.get('display_words',[]) if re_critical(w['word'])):continue
            n=min(.65,probe(cfg.sfx_path)['duration']);row=dict(id='legacy-sfx',event_id=f'legacy-sfx-{len(sfx)}',asset={'path':cfg.sfx_path,'metadata':{'duration':probe(cfg.sfx_path)['duration']}},asset_start=0.,asset_seconds=n,start=at,end=at+n,start_sample=round(at*RATE),end_sample=round((at+n)*RATE),loop=False,reverse=False,rate=1.,fade_in=.01,fade_out=.15,gain_db=cfg.sfx_db)
            sfx.append(_track(row,plan,folder));p['events'].append({'id':row['event_id'],'role':'sfx','start':at,'end':at+n,'origin':'legacy cue; critical-word overlap excluded'});previous=at
    if music:
        combined=_sum(music,folder/'music-before-duck.wav',duration)
        if s['ducking']:
            samples=decode(combined,seconds=duration);envelope=duck_envelope(len(samples),p['speech_intervals'],s['duck_db'],s['duck_attack_ms'],s['duck_release_ms'])
            samples*=envelope[:,None];combined=write(folder/'music-ducked.wav',samples)
            p['ducking']={'active':True,'gain_db':s['duck_db'],'attack_ms':s['duck_attack_ms'],'release_ms':s['duck_release_ms'],'speech_intervals':p['speech_intervals'],'basis':'effective transcript and scheduled voice tracks; no loudness threshold misses quiet words'}
        else:p['ducking']={'active':False,'speech_intervals':[]}
        stems['music']=combined
    if sfx:stems['effects']=_sum(sfx,folder/'effects.wav',duration)
    windows=plan.get('captions',{}).get('censor_intervals',[])
    if windows:
        stems={role:mute_windows(path,folder/(role+'-censored.wav'),windows,duration) for role,path in stems.items()}
        bleep=np.zeros((count,2),np.float32)
        for a,b in windows:
            left=max(0,round(a*RATE));right=min(count,round(b*RATE));wave=.01*np.sin(2*np.pi*1000*np.arange(left,right)/RATE);bleep[left:right]=wave[:,None]
        stems['censor']=write(folder/'approved-bleep.wav',bleep);p['censor_applied']=True
    mix=_sum(list(stems.values()),folder/'premix.wav',duration)
    p.update(source=plan['audio6_source'],asset_refs=asset_refs,sfx_events=[{k:r.get(k) for k in ('id','start','end','asset_id','reviewed')} for r in p['events'] if r.get('role')=='sfx'])
    plan['audio']={'stems':stems,'mix':mix,'sfx_events':[r['start'] for r in p['sfx_events']],'music_original':cfg.music_path,'music_db':cfg.music_db,'sfx_original':cfg.sfx_path}
    if windows:plan['audio']['censor']={'mode':'bleep_mask','intervals':windows,'dictionary_approved':True}
    return mix

def re_critical(value):
    import re
    from .transcript_correction import PROTECTED
    return bool(re.search(r'\d',value) or set(re.findall(r'\w+',value.casefold()))&set(PROTECTED))

def finalize(plan,cfg,mix,folder):
    from .audio6_meter import loudness,finite,measure
    s=effective(cfg);folder=Path(folder)/'audio6';folder.mkdir(parents=True,exist_ok=True);duration=plan['duration']
    ceiling=max(-9.,s['peak_db']-.6)
    raw=loudness(mix,{**s,'peak_db':ceiling});current=mix;normalization={'active':s['normalize'],'stored_target_lufs':s['target_lufs'],'target_lufs':s['target_lufs'] if s['normalize'] else None,
        'input_integrated_lufs':finite(raw['input_i']),'input_true_peak_db':finite(raw['input_tp']),'stage':'after all music/SFX/voice/censor inputs'}
    if s['normalize'] and all(finite(raw[k]) is not None for k in ('input_i','input_tp','input_lra','input_thresh','target_offset')):
        graph=f"loudnorm=I={s['target_lufs']}:TP={ceiling}:LRA=11:measured_I={raw['input_i']}:measured_TP={raw['input_tp']}:measured_LRA={raw['input_lra']}:measured_thresh={raw['input_thresh']}:offset={raw['target_offset']}:linear=true,aresample=48000"
        current=_filter(mix,folder/'normalized-master.wav',[graph],duration);normalization['status']='applied_two_pass'
    else:normalization['status']='off' if not s['normalize'] else 'unmeasurable_input_no_fake_target'
    if s['limiter']:
        ceiling=10**((s['peak_db']-.6)/20)
        current=_filter(current,folder/'limited-master.wav',['aresample=192000',f'alimiter=limit={ceiling:.9f}:level=0:latency=1','aresample=48000'],duration)
    master=run_float(['-i',current,'-af',f'apad,atrim=end_sample={round(duration*RATE)}'],folder/'master.wav')
    plan['audio']['mix']=master;plan['audio6'].update(normalization=normalization,limiter={'active':s['limiter'],'ceiling_db':s['peak_db'],'encoding_headroom_db':.6,'oversample_rate':192000 if s['limiter'] else None},master=master)
    plan['audio6']['meter_pcm']=measure(master,s,expected_duration=duration,fps=plan['fps'])
    plan['audio6']['premix_meter']={k:finite(raw[k]) for k in ('input_i','input_tp','input_lra')}
    if s['export_stems']:
        archive=folder/'audio-stems.zip';manifest={'version':VERSION,'snapshot_digest':plan['audio6']['snapshot_digest'],'sample_rate':RATE,'duration_samples':round(duration*RATE),
            'timebase':'same output clock as final video','revision_context':plan['audio6']['revision_context'],
            'source_content_id':plan['audio6']['source']['source_content_id'],'stems':[],'normalization':normalization,'limiter':plan['audio6']['limiter'],
            'reconstruction':'Stem tracks sum to the pre-master mix. Master normalization/limiter is nonlinear; use master.wav for final sound.',
            'gate_g6':'pending_real_speech_listening'}
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for role,path in plan['audio']['stems'].items():
                z.write(path,'stems/'+role+'.wav');manifest['stems'].append({'role':role,'file':'stems/'+role+'.wav','content_id':content_id(path,fresh=True)})
            z.write(master,'master.wav');z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        plan['audio6']['stem_archive']=str(archive.resolve())
    return master
