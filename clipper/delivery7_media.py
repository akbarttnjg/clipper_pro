"""Explicit local M7 derivatives. No source downloads or unrecorded encoder fallback."""
import json,shutil,subprocess
from dataclasses import replace
from pathlib import Path
from .dependency_cache import content_id
from .delivery7_contract import PROFILES
from .storage import write_json


def run(command,duration=0):
    proc=subprocess.run(command,capture_output=True,text=True,timeout=max(120,float(duration)*12))
    if proc.returncode:raise ValueError('Media M7 gagal: '+proc.stderr[-2000:])
    return proc


def probe(path):
    return json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]).stdout)


def qc(path,plan,cfg):
    from .qc import inspect
    receipt=inspect(path,replace(cfg,target_w=plan['width'],target_h=plan['height'],output_fps=plan['fps']),plan['duration'])
    data=probe(path);video=next(s for s in data['streams'] if s['codec_type']=='video');audio=next(s for s in data['streams'] if s['codec_type']=='audio')
    if video['codec_name']!='h264' or audio['codec_name']!='aac':raise ValueError('Final M7 harus H.264/AAC dalam MP4')
    expected_frames=plan.get('duration_frames',plan.get('frames',round(plan['duration']*plan['fps'])))
    if str(video.get('nb_frames',''))!=str(expected_frames):raise ValueError('Jumlah frame MP4 M7 berbeda dari timeline')
    receipt['frames']=int(video['nb_frames'])
    receipt['streams']={'video':{k:video.get(k) for k in ('codec_name','profile','pix_fmt','avg_frame_rate','width','height','bit_rate')},
                        'audio':{k:audio.get(k) for k in ('codec_name','sample_rate','channels','bit_rate')}}
    return receipt


def final(source,target,plan,cfg,profile):
    source=Path(source);target=Path(target);p=PROFILES[profile]
    if profile=='reference':shutil.copy2(source,target);command=None
    else:
        command=['ffmpeg','-nostdin','-v','error','-y','-i',str(source),'-map','0:v:0','-map','0:a:0',
            '-c:v','libx264','-preset',p['preset'],'-crf',str(p['crf']),'-pix_fmt','yuv420p','-threads','2',
            '-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(target)]
        run(command,plan['duration'])
    receipt=qc(target,plan,cfg);receipt.update(profile=profile,requested_profile=p,
        encoding_policy='byte_identical_reviewed_final' if command is None else 'explicit_CPU_delivery_transcode',
        actual_encoder=plan.get('runtime_receipt',{}).get('actual_encoder',plan.get('encoder')) if command is None else 'libx264',
        source_content_id=content_id(source,fresh=True),output_content_id=content_id(target,fresh=True))
    if command:receipt['encoder_arguments']=['-c:v','libx264','-preset',p['preset'],'-crf',str(p['crf']),'-c:a','aac','-b:a','192k']
    write_json(target.with_suffix('.profile.json'),receipt);return receipt


def audio_qc(path,duration):
    data=probe(path);a=next((s for s in data['streams'] if s['codec_type']=='audio'),None)
    if not a or abs(float(data['format']['duration'])-duration)>.02 or int(a['sample_rate'])!=48000:raise ValueError('Stem tidak mencakup timeline 48 kHz')
    run(['ffmpeg','-nostdin','-v','error','-xerror','-err_detect','explode','-threads','1','-i',str(path),'-map','0:a:0','-f','null','-'],duration)
    return {'passed':True,'full_decode':'passed','duration':float(data['format']['duration']),'codec':a['codec_name'],'channels':a['channels'],'sample_rate':48000}


def clean(plan,cfg,target):
    from .render import video
    p={**plan,'caption_renderer':{},'_m7_caption_free':True}
    c=replace(cfg,target_w=plan['width'],target_h=plan['height'],output_fps=plan['fps'],**plan.get('render_config',{}))
    video(plan['source']['path'],p,c,None,target,plan['audio']['mix'],mode='final')
    report=qc(target,plan,c);report['scope']='caption_free; broll, M4 composition and M5 finishing remain baked'
    report['actual_encoder']=p.get('encoder');return report


def alpha(plan,cfg,ass,target):
    """Caption-only alpha, paired with caption-free clean picture. qtrle/ARGB MOV."""
    from .ffmpeg_util import ass_filter
    overlay=plan.get('caption_renderer',{})
    duration=plan['duration'];base=['ffmpeg','-nostdin','-v','error','-y']
    if overlay.get('engine') in ('remotion','raster') and overlay.get('path'):
        command=base+(['-c:v','libvpx-vp9'] if overlay['engine']=='remotion' else [])+['-i',overlay['path'],
            '-t',str(duration),'-vf','format=argb','-an','-c:v','qtrle','-threads','1',str(target)]
    else:
        filtergraph=ass_filter(ass,cfg)+':alpha=1,format=argb'
        command=base+['-f','lavfi','-i',f'color=c=black@0.0:s={plan["width"]}x{plan["height"]}:r={plan["fps"]}:d={duration},format=rgba',
            '-vf',filtergraph,'-an','-c:v','qtrle','-pix_fmt','argb','-threads','1',str(target)]
    run(command,duration);data=probe(target);v=next(s for s in data['streams'] if s['codec_type']=='video')
    if v['codec_name']!='qtrle' or v.get('pix_fmt')!='argb' or [v['width'],v['height']]!=[plan['width'],plan['height']] or abs(float(data['format']['duration'])-duration)>.06:raise ValueError('Codec/durasi/dimensi alpha tidak valid')
    run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(target),'-map','0:v:0','-f','null','-'],duration)
    # Actual decoded alpha must retain a transparent background.
    cues=plan.get('captions',{}).get('phrases',[]);at=(cues[0]['start']+cues[0]['end'])/2 if cues else 0
    pixels=subprocess.run(['ffmpeg','-nostdin','-v','error','-ss',str(at),'-i',str(target),'-frames:v','1','-vf','alphaextract','-f','rawvideo','-pix_fmt','gray','-'],capture_output=True,timeout=60,check=True).stdout
    if not pixels or min(pixels)!=0:raise ValueError('Overlay tidak mempunyai latar transparan')
    if cues and max(pixels)==0:raise ValueError('Overlay caption seluruhnya transparan')
    return {'passed':True,'codec':'qtrle','pix_fmt':'argb','full_decode':'passed','scope':'caption_only_alpha; finishing and B-roll are in clean picture','sample_alpha_range':[min(pixels),max(pixels)]}


def merged(rows,target,cfg):
    from .delivery7_exchange import fps_rate
    if any((r['width'],r['height'],r['fps'])!=(rows[0]['width'],rows[0]['height'],rows[0]['fps']) for r in rows):raise ValueError('Resolusi/fps gabungan harus sama')
    # Concat-demuxer AAC priming shifts video PTS and can add a frame even
    # for one file. Reset each reviewed cut on a frame/sample clock instead.
    inputs=[];graph=[];total=sum(r['frames'] for r in rows);fps=rows[0]['fps']
    for i,row in enumerate(rows):
        inputs+=['-threads','1','-i',str(row['local_path'])]
        seconds=float(row['frames']/fps_rate(fps))
        graph.append(f"[{i}:v]trim=end_frame={row['frames']},setpts=PTS-STARTPTS[v{i}]")
        graph.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={seconds:.9f},atrim=duration={seconds:.9f},asetpts=N/SR/TB[a{i}]")
    graph.append(''.join(f'[v{i}][a{i}]' for i in range(len(rows)))+f'concat=n={len(rows)}:v=1:a=1[outv][outa]')
    script=target.with_suffix('.concat-filter.txt');script.write_text(';\n'.join(graph),encoding='utf-8')
    duration=float(total/fps_rate(fps))
    from .ffmpeg_util import filter_file_args
    run(['ffmpeg','-nostdin','-v','error','-y',*inputs,'-filter_complex_threads','1',*filter_file_args(script),
         '-map','[outv]','-map','[outa]','-r',str(fps),'-frames:v',str(total),'-t',str(duration),
         '-c:v','libx264','-preset','fast','-crf','18','-threads','2','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(target)],duration)
    script.unlink()
    report=qc(target,{**rows[0],'duration':duration,'duration_frames':total},cfg)
    return {**report,'scope':'baked concatenation; one clip per selected story; no transitions inserted','actual_encoder':'libx264','crf':18,'duration':duration}
