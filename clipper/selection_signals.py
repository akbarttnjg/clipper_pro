"""Measured audio/frame signals and reviewed markers, never invented emotions."""
import array
import hashlib
import math
from pathlib import Path
import statistics
import subprocess
import sys
from .contracts import fingerprint
from .storage import read_json,write_json
from .selection_contract import tokens,contains_phrase,VERSION


def voice_markers(words,phrases,source_id):
    units=[]
    for word in words:
        for text in tokens(word['word']):units.append((text,word))
    result=[]
    for phrase in phrases:
        wanted=tokens(phrase)
        if not wanted:continue
        for i in range(len(units)-len(wanted)+1):
            group=units[i:i+len(wanted)]
            if [u[0] for u in group]!=wanted:continue
            a,b=group[0][1]['start'],group[-1][1]['end']
            if b-a>max(10,len(wanted)*3):continue
            ids=list(dict.fromkeys(w['word_id'] for _,w in group))
            result.append({'event_id':'voice-'+fingerprint([source_id,phrase,ids])[:24],
                'kind':'voice_marker','time':a,'end':b,'quote':phrase,'word_ids':ids,
                'source_id':source_id,'provenance':'accepted_transcript_marker_match','confidence':None,
                'resolution':'source_units; no_invented_subcue_timing'})
    return list({r['event_id']:r for r in result}.values())


def audio_events(media,audio_index,start,end,progress=lambda p,m:None):
    """Stream 2 kHz selected audio; bounded memory and explicit failure/cancel."""
    command=['ffmpeg','-nostdin','-v','error','-ss',str(start),'-i',str(media),'-t',str(end-start),
        '-map','0:'+str(audio_index),'-vn','-ac','1','-ar','2000','-f','s16le','pipe:1']
    levels=[]
    with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process:
        try:
            while True:
                block=process.stdout.read(4000)
                if not block:break
                values=array.array('h',block[:len(block)//2*2])
                if sys.byteorder!='little':values.byteswap()
                levels.append(math.sqrt(sum(v*v for v in values)/max(1,len(values)))/32768.)
                if len(levels)%120==0:progress(24,'Mengukur petunjuk suara pada track terpilih')
            error=process.stderr.read(2000);process.wait()
            if process.returncode:raise ValueError('Track suara gagal diukur: '+error.decode('utf-8','replace')[-500:])
        except BaseException:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            raise
    typical=statistics.median([v for v in levels if v>.0001]) if any(v>.0001 for v in levels) else 0.
    events=[]
    for i,value in enumerate(levels):
        prior=levels[i-1] if i else value
        if typical and value>max(.01,typical*1.65) and value>prior*1.4:
            events.append({'kind':'audio_energy_event','time':start+i,'end':min(end,start+i+1),
                'rms':round(value,6),'relative_to_median':round(value/typical,3),'emotion':None,
                'confidence':None,'provenance':'ffmpeg_selected_stream_pcm_rms'})
    return events[:240],{'audio_stream_index':audio_index,'start':start,'end':end,'measured_seconds':len(levels),
        'samples_per_second':2000,'typical_rms':typical,'emotion_inference':'not_performed','memory':'one_second_buffer'}


def sample_frames(media,times,folder,source_id,progress=lambda p,m:None):
    from PIL import Image,ImageChops,ImageStat
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);rows=[];events=[];previous=None
    for i,time in enumerate(times):
        progress(25+int(10*i/max(1,len(times))),'Menyimpan frame bukti '+str(i+1)+'/'+str(len(times)))
        path=folder/('frame-'+fingerprint([source_id,time])[:24]+'.png')
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-ss',str(time),'-i',str(media),
            '-frames:v','1','-vf','scale=480:-2','-threads','1',str(path)],check=True,capture_output=True,timeout=30)
        if not path.is_file():raise ValueError('Frame bukti gagal dibaca pada waktu '+str(time))
        with Image.open(path) as image:
            image.load();small=image.convert('RGB').resize((32,18));width,height=image.size
            delta=sum(ImageStat.Stat(ImageChops.difference(small,previous)).mean)/(3*255) if previous else None
        row={'time':time,'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'width':width,'height':height,'source_id':source_id,'pixel_change':delta,'objects':[],
            'model':None,'provenance':'ffmpeg_decoded_source_frame'}
        rows.append(row)
        if delta is not None and delta>.18:events.append({'kind':'sampled_visual_change','time':time,'frame_path':row['path'],
            'frame_sha256':row['sha256'],'pixel_change':delta,'confidence':None,'model':None,
            'provenance':'Pillow_mean_absolute_sampled_pixel_difference'})
        previous=small
    return rows,events


def collect(media,source_id,requested,words,cfg,*,kind='video',source_markers=(),progress=lambda p,m:None):
    events=voice_markers(words,requested['voice_markers'],source_id)
    if not requested['signals']:
        return {'status':'disabled','source_id':source_id,'events':events,'frames':[],'receipt':{'emotion_inference':'not_performed'}}
    from .media_context import inspect
    from .dependency_cache import content_id
    info=inspect(media);audio=info.get('audio_tracks',[])
    if not audio:raise ValueError('Track suara untuk sinyal M3 tidak ditemukan')
    # `media` is M2's canonical source with the selected original audio track.
    marker_times=sorted({e['time'] for e in [*events,*source_markers] if requested['start']<=e['time']<requested['end']})
    key=fingerprint([VERSION,source_id,content_id(media),requested['start'],requested['end'],requested['frame_budget'],kind,marker_times])
    folder=Path(cfg.work_dir)/'m3-signals'/key;folder.mkdir(parents=True,exist_ok=True);cache=folder/'measured.json'
    measured=read_json(cache)
    if measured and all(Path(r['path']).is_file() and hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256'] for r in measured.get('frames',[])):
        measured={**measured,'cache_reused':True}
    else:
        cue,audio_receipt=audio_events(media,audio[0]['index'],requested['start'],requested['end'],progress)
        frame_rows=[];visual=[];budget=requested['frame_budget']
        if kind!='audio' and budget:
            length=requested['end']-requested['start'];uniform=max(1,budget//2)
            times=[requested['start']+min(max(0,length-.01),(i+.5)*length/uniform) for i in range(uniform)]
            points=marker_times+[e['time'] for e in sorted(cue,key=lambda r:-r.get('relative_to_median',0))]
            times=sorted(set([*points[:budget-uniform],*times]))[:budget]
            frame_rows,visual=sample_frames(media,times,folder,source_id,progress)
        measured={'status':'ready','source_id':source_id,'events':cue+visual,'frames':frame_rows,
            'receipt':{'audio':audio_receipt,'visual_sampling':'not_applicable_audio' if kind=='audio' else 'uniform_and_marker_bounded','frame_budget':budget,
                'model':None,'objects':'not_inferred','emotion_inference':'not_performed'},'cache_reused':False}
        write_json(cache,measured)
    events.extend(measured['events']);frames=measured['frames'];receipt={**measured['receipt']}
    if requested['visual_model']!='off' or requested['profile']=='gaming' and requested['hud_terms']:
        from .visual4 import backend
        for row in frames[:8]:
            if requested['visual_model']!='off':
                result=backend(requested['visual_model'],{'operation':'m3_visual_story','source':str(media),'source_content_id':source_id,'time':row['time']},cfg,folder)
                row={**row,'model_result':result};receipt.setdefault('model_results',[]).append(row)
                if result.get('status')=='ready':events.append({'kind':'visual_model_proposal','time':row['time'],'frame_path':row['path'],
                    'frame_sha256':row['sha256'],'model':result.get('provenance'),'assessment':result,'confidence':None,'requires_review':True})
            if requested['profile']=='gaming' and requested['hud_terms']:
                result=backend('rapidocr',{'source':str(media),'source_content_id':source_id,'times':[row['time']]},cfg,folder)
                for frame in result.get('frames',[]) if result.get('status')=='ready' else []:
                    for text in frame.get('texts',[]):
                        for term in requested['hud_terms']:
                            if contains_phrase(text.get('text',''),term):
                                events.append({'kind':'gaming_hud_marker','time':row['time'],'quote':text['text'],'game_name':requested['game_name'],
                                    'frame_path':row['path'],'frame_sha256':row['sha256'],'box':text.get('box'),
                                    'confidence':text.get('confidence'),'model':result.get('provenance'),
                                    'provenance':'reviewable_local_ocr_match','game_corpus_status':'not_validated_for_real_game'})
                receipt['gaming']={'game_name':requested['game_name'],'hud_terms':requested['hud_terms'],
                    'profile':'custom_reviewed_hud','real_game_corpus':'not_tested','ocr_status':result.get('status')}
    return {**measured,'events':events,'receipt':receipt,'visual_model_ablation':'not_measured',
        'emotion_classification':'not_performed','sampling_limit':'events outside sample times may be missed'}
