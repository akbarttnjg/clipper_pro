"""Interpret video metadata once, then give every analysis/render stage one geometry."""
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from .contracts import envelope,fingerprint
from .dependency_cache import content_id
from .storage import read_json,write_json


def rational(value,default='30/1'):
    try:
        f=Fraction(str(value))
        if f<=0:raise ValueError()
    except (ValueError,ZeroDivisionError):f=Fraction(default)
    return {'numerator':f.numerator,'denominator':f.denominator}


def inspect(path):
    p=Path(path).resolve()
    data=json.loads(subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)],
        check=True,capture_output=True,text=True).stdout)
    video=next((s for s in data['streams'] if s['codec_type']=='video'),None)
    if video is None:raise ValueError('Berkas tidak mempunyai gambar video')
    duration=float(video.get('duration') or data['format'].get('duration') or 0)
    if not math.isfinite(duration) or duration<=0:raise ValueError('Durasi media tidak valid')
    rotation=float(video.get('tags',{}).get('rotate',0))
    for side in video.get('side_data_list',[]):
        if 'rotation' in side:rotation=float(side['rotation'])
    rotation=round(rotation)%360
    if rotation not in (0,90,180,270):raise ValueError('Rotasi sumber harus 0, 90, 180, atau 270 derajat')
    sar=rational(video.get('sample_aspect_ratio','1:1').replace(':','/'),'1/1')
    width=max(2,round(int(video['width'])*sar['numerator']/sar['denominator']/2)*2)
    height=max(2,round(int(video['height'])/2)*2)
    if rotation in (90,270):width,height=height,width
    audio=[{'index':s['index'],'language':s.get('tags',{}).get('language','und'),
            'title':s.get('tags',{}).get('title','Audio '+str(i+1)),'channels':s.get('channels'),
            'sample_rate':s.get('sample_rate'),'start_time':float(s.get('start_time',0))}
           for i,s in enumerate(s for s in data['streams'] if s['codec_type']=='audio')]
    return {'path':str(p),'encoded_size':[int(video['width']),int(video['height'])],'display_size':[width,height],
        'rotation':rotation,'sample_aspect_ratio':sar,'fps':rational(video.get('avg_frame_rate','30/1')),
        'r_frame_rate':rational(video.get('r_frame_rate','30/1')),'duration':duration,'audio_tracks':audio,
        'video_stream_index':video['index'],'video_start_time':float(video.get('start_time',0)),
        'format_start_time':float(data['format'].get('start_time',0)),
        'color_transfer':video.get('color_transfer','unknown'),'color_space':video.get('color_space','unknown'),
        'color_primaries':video.get('color_primaries','unknown'),'pixel_format':video.get('pix_fmt','unknown')}


def prepare(path,cfg,progress=lambda p,m:None):
    source=Path(path).resolve();info=inspect(source);source_id=content_id(source,fresh=True)
    tracks=info['audio_tracks']
    if not tracks:raise ValueError('Sumber tidak mempunyai track suara')
    requested=getattr(cfg,'audio_stream_index',-1)
    track=tracks[0] if requested<0 else next((t for t in tracks if t['index']==requested),None)
    if track is None:raise ValueError('Track audio yang dipilih tidak ada pada sumber ini')
    sar=info['sample_aspect_ratio'];hdr=info['color_transfer'] in ('smpte2084','arib-std-b67')
    variable=info['fps']!=info['r_frame_rate']
    # A single normalization path also resolves time origins and audio track selection.
    normalize=bool(info['rotation'] or sar!={'numerator':1,'denominator':1} or hdr or variable
        or track!=tracks[0] or abs(info['video_start_time'])>.001 or abs(track['start_time']-info['video_start_time'])>.001)
    key=fingerprint([source_id,track['index'],{k:v for k,v in info.items() if k!='path'},cfg.output_fps,'canonical-4'])
    folder=Path(cfg.work_dir)/'cache'/'canonical'/key;folder.mkdir(parents=True,exist_ok=True)
    output=folder/'source.mp4' if normalize else source
    manifest=folder/'context.json';cached=read_json(manifest)
    if cached and output.is_file() and cached['payload'].get('working_content_id')==content_id(output):
        cached['payload'].update(path=str(source),source_path=str(source),working_path=str(output));return cached
    progress(2,'Memeriksa orientasi gambar, waktu, warna, dan track suara')
    if normalize:
        w,h=info['display_size'];filters=[]
        if hdr:
            available=subprocess.run(['ffmpeg','-hide_banner','-filters'],capture_output=True,text=True,check=True).stdout
            if 'zscale' not in available or 'tonemap' not in available:raise ValueError('Sumber HDR memerlukan FFmpeg dengan zscale dan tonemap')
            filters+=['zscale=t=linear:npl=100','format=gbrpf32le','zscale=p=bt709','tonemap=tonemap=hable:desat=0','zscale=t=bt709:m=bt709:r=tv']
        filters += [f'scale={w}:{h}','setsar=1',f'fps={cfg.output_fps}','setpts=PTS-STARTPTS','format=yuv420p']
        offset=info['video_start_time']-info['format_start_time']
        pending=folder/'source.partial.mp4'
        command=['ffmpeg','-nostdin','-hide_banner','-v','error','-y','-i',str(source),'-map','0:v:0',
            '-map',f"0:{track['index']}",'-vf',','.join(filters),'-af',f'asetpts=PTS-({offset:.9f})/TB,aresample=async=1:first_pts=0',
            '-metadata:s:v:0','rotate=0','-t',str(info['duration']),'-c:v','libx264','-preset','fast','-crf','18',
            '-threads','4','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(pending)]
        try:
            subprocess.run(command,capture_output=True,check=True);pending.replace(output)
        finally:pending.unlink(missing_ok=True)
    import cv2
    cap=cv2.VideoCapture(str(output))
    try:ok,frame=cap.read()
    finally:cap.release()
    if not ok or list(reversed(frame.shape[:2]))!=info['display_size']:
        raise ValueError('Geometri frame decoder belum cocok dengan metadata. Analisis dihentikan agar crop tidak salah.')
    payload={**info,'source_path':str(source),'working_path':str(output),'source_time_origin':0,
        'source_content_id':source_id,'working_content_id':content_id(output),'audio_stream_id':source_id+':audio:'+str(track['index']),
        'selected_audio_index':track['index'],'coordinate_space':'canonical_source_pixels','geometry_status':'ready',
        'canonical_sample_aspect_ratio':{'numerator':1,'denominator':1},'rotation_applied':normalize and bool(info['rotation']),'normalized':normalize,'color_conversion':'HDR_to_SDR_bt709' if hdr else 'source_SDR',
        'normalization_notes':['Gambar kanonis, piksel persegi, waktu mulai nol dan audio terpilih.'] if normalize else [],
        'fps':{'numerator':cfg.output_fps,'denominator':1} if normalize else info['fps']}
    result=envelope('MediaContext',source_id,payload,key,producer='B-4')
    write_json(manifest,result);return result
