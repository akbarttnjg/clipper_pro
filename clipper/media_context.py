"""M2 probe and canonical source clocks for video and audio, without CV imports."""
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from .contracts import envelope, fingerprint
from .dependency_cache import content_id
from .storage import read_json, write_json


def rational(value, default='30/1'):
    try:
        f = Fraction(str(value))
        if f <= 0: raise ValueError()
    except (ValueError, ZeroDivisionError): f = Fraction(default)
    return {'numerator': f.numerator, 'denominator': f.denominator}


def inspect(path):
    p = Path(path).resolve()
    data = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(p)],
        check=True, capture_output=True, text=True, timeout=45).stdout)
    streams = data.get('streams', [])
    video = next((s for s in streams if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
    audio = [{'index': s['index'], 'language': s.get('tags', {}).get('language', 'und'),
        'title': s.get('tags', {}).get('title', 'Audio '+str(i+1)), 'channels': s.get('channels'),
        'sample_rate': s.get('sample_rate'), 'codec': s.get('codec_name'), 'time_base': s.get('time_base'),
        'start_time': float(s.get('start_time', 0))}
        for i,s in enumerate(s for s in streams if s['codec_type'] == 'audio')]
    if not video and not audio: raise ValueError('Berkas tidak mempunyai video atau audio')
    duration = float((video or {}).get('duration') or data.get('format', {}).get('duration') or 0)
    if not math.isfinite(duration) or duration <= 0: raise ValueError('Durasi media tidak valid')
    info = {'path': str(p), 'kind': 'video' if video else 'audio', 'duration': duration, 'audio_tracks': audio,
        'format_start_time': float(data.get('format', {}).get('start_time', 0)),
        'subtitle_tracks': [{'index': s['index'], 'codec': s.get('codec_name'), 'language': s.get('tags', {}).get('language', 'und')}
            for s in streams if s['codec_type'] == 'subtitle']}
    if not video:
        return {**info, 'encoded_size': [0,0], 'display_size': [0,0], 'rotation': 0,
            'sample_aspect_ratio': rational('1/1'), 'fps': rational('30/1'), 'r_frame_rate': rational('30/1'),
            'video_stream_index': None, 'video_start_time': 0., 'color_transfer': 'not_applicable',
            'color_space': 'not_applicable', 'color_primaries': 'not_applicable', 'pixel_format': None,
            'vfr': {'detected': False, 'status': 'not_applicable'}}
    rotation = float(video.get('tags', {}).get('rotate', 0))
    for side in video.get('side_data_list', []):
        if 'rotation' in side: rotation = float(side['rotation'])
    rotation = round(rotation) % 360
    if rotation not in (0,90,180,270): raise ValueError('Rotasi sumber harus 0, 90, 180, atau 270 derajat')
    sar = rational(video.get('sample_aspect_ratio', '1:1').replace(':','/'), '1/1')
    width = max(2, round(int(video['width'])*sar['numerator']/sar['denominator']/2)*2)
    height = max(2, round(int(video['height'])/2)*2)
    if rotation in (90,270): width,height = height,width
    fps = rational(video.get('avg_frame_rate', '30/1')); r = rational(video.get('r_frame_rate', '30/1'))
    frames = json.loads(subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-read_intervals','%+#180',
        '-show_entries','frame=best_effort_timestamp_time','-of','json',str(p)],capture_output=True,text=True,check=True,timeout=45).stdout)
    times = [float(f['best_effort_timestamp_time']) for f in frames.get('frames',[]) if 'best_effort_timestamp_time' in f]
    gaps = [b-a for a,b in zip(times,times[1:]) if b>a]; sampled = len(gaps)>2 and max(gaps)-min(gaps)>.002
    return {**info, 'encoded_size': [int(video['width']),int(video['height'])], 'display_size': [width,height],
        'rotation': rotation, 'sample_aspect_ratio': sar, 'fps': fps, 'r_frame_rate': r,
        'video_stream_index': video['index'], 'video_time_base': video.get('time_base'),
        'video_start_time': float(video.get('start_time',0)),
        'vfr': {'detected': sampled or fps != r, 'status': 'sampled_first_180_frames', 'intervals_sampled': len(gaps),
            'min_interval': min(gaps) if gaps else None, 'max_interval': max(gaps) if gaps else None},
        'color_transfer': video.get('color_transfer','unknown'), 'color_space': video.get('color_space','unknown'),
        'color_primaries': video.get('color_primaries','unknown'), 'pixel_format': video.get('pix_fmt','unknown')}


def prepare(path, cfg, progress=lambda p,m:None):
    source=Path(path).resolve(); info=inspect(source); source_id=content_id(source,fresh=True)
    tracks=info['audio_tracks']
    if not tracks: raise ValueError('Sumber tidak mempunyai track suara')
    requested=getattr(cfg,'audio_stream_index',-1)
    track=tracks[0] if requested<0 else next((t for t in tracks if t['index']==requested),None)
    if track is None: raise ValueError('Track audio yang dipilih tidak ada pada sumber ini')
    audio_only=info['kind']=='audio'; sar=info['sample_aspect_ratio']; hdr=info['color_transfer'] in ('smpte2084','arib-std-b67')
    normalize=audio_only or bool(info['rotation'] or sar!=rational('1/1') or hdr or info['vfr']['detected']
        or track!=tracks[0] or abs(info['video_start_time'])>.001 or abs(track['start_time']-info['video_start_time'])>.001)
    key=fingerprint([source_id,track['index'],{k:v for k,v in info.items() if k!='path'},cfg.output_fps,'canonical-m2'])
    folder=Path(cfg.work_dir)/'cache'/'canonical'/key;folder.mkdir(parents=True,exist_ok=True)
    output=folder/('source.wav' if audio_only else 'source.mp4') if normalize else source
    manifest=folder/'context.json'; cached=read_json(manifest)
    if cached and output.is_file() and cached['payload'].get('working_content_id')==content_id(output,fresh=True):
        cached['payload'].update(path=str(source),source_path=str(source),working_path=str(output));return cached
    progress(2,'Memeriksa waktu, warna, orientasi dan track suara sumber')
    if normalize:
        pending=folder/('source.partial.wav' if audio_only else 'source.partial.mp4')
        offset=info['video_start_time']-info['format_start_time'] if not audio_only else 0
        command=['ffmpeg','-nostdin','-hide_banner','-v','error','-y','-i',str(source)]
        af=f'asetpts=PTS-({offset:.9f})/TB,aresample=async=1:first_pts=0'
        if audio_only:
            command+=['-map',f"0:{track['index']}",'-vn','-af',af,'-t',str(info['duration']),'-c:a','pcm_s16le','-ar','48000',str(pending)]
        else:
            w,h=info['display_size'];filters=[]
            if hdr:
                available=subprocess.run(['ffmpeg','-hide_banner','-filters'],capture_output=True,text=True,check=True).stdout
                if 'zscale' not in available or 'tonemap' not in available: raise ValueError('HDR memerlukan FFmpeg dengan zscale dan tonemap')
                filters+=['zscale=t=linear:npl=100','format=gbrpf32le','zscale=p=bt709','tonemap=tonemap=hable:desat=0','zscale=t=bt709:m=bt709:r=tv']
            filters += [f'scale={w}:{h}','setsar=1',f'fps={cfg.output_fps}','setpts=PTS-STARTPTS','format=yuv420p']
            command+=['-map',f"0:{info['video_stream_index']}",'-map',f"0:{track['index']}",'-vf',','.join(filters),'-af',af,
                '-metadata:s:v:0','rotate=0','-t',str(info['duration']),'-c:v','libx264','-preset','fast','-crf','18','-threads','4',
                '-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(pending)]
        try:
            subprocess.run(command,capture_output=True,check=True,timeout=7200)
            decoded=inspect(pending)
            if abs(decoded['duration']-info['duration'])>max(.12,2/cfg.output_fps): raise ValueError('Durasi kanonis tidak sesuai sumber')
            pending.replace(output)
        finally: pending.unlink(missing_ok=True)
    if not audio_only:
        w,h=info['display_size']
        raw=subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(output),'-frames:v','1','-vf',f'scale={w}:{h}',
            '-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True,timeout=45).stdout
        if len(raw)!=w*h*3: raise ValueError('Decoder gagal membaca geometri sumber')
    payload={**info,'source_path':str(source),'working_path':str(output),'source_time_origin':0,
        'source_content_id':source_id,'working_content_id':content_id(output,fresh=True),
        'audio_stream_id':source_id+':audio:'+str(track['index']),'selected_audio_index':track['index'],
        'coordinate_space':'source_seconds' if audio_only else 'canonical_source_pixels','geometry_status':'not_applicable' if audio_only else 'ready',
        'canonical_sample_aspect_ratio':rational('1/1'),'rotation_applied':normalize and bool(info['rotation']),
        'normalized':normalize,'color_conversion':'HDR_to_SDR_bt709' if hdr else ('not_applicable' if audio_only else 'source_SDR'),
        'normalization_notes':['Waktu mulai nol dan audio terpilih; sumber asli tidak ditimpa.'] if normalize else [],
        'fps':{'numerator':cfg.output_fps,'denominator':1} if normalize else info['fps']}
    result=envelope('MediaContext',source_id,payload,key,producer='M2.1');write_json(manifest,result);return result


def proxy(path,cfg,progress=lambda p,m:None):
    context=prepare(path,cfg,progress);p=context['payload']
    if p['kind']=='audio': return {'status':'not_applicable','reason':'Sumber audio memakai waveform; tidak dibuat video palsu'}
    folder=Path(p['working_path']).parent if p['normalized'] else Path(cfg.work_dir)/'cache'/'proxy'/context['input_fingerprint']
    folder.mkdir(parents=True,exist_ok=True); output=folder/'edit-proxy.mp4';receipt=folder/'proxy.json';cached=read_json(receipt,{})
    if not output.is_file() or cached.get('content_id')!=content_id(output,fresh=True):
        progress(15,'Membuat proxy ringan untuk editor')
        pending=folder/'proxy.partial.mp4'
        try:
            subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-i',p['working_path'],'-vf',"scale='min(960,iw)':-2",'-c:v','libx264',
                '-preset','fast','-crf','25','-threads','4','-c:a','aac','-b:a','96k','-movflags','+faststart',str(pending)],check=True,capture_output=True,timeout=7200)
            info=inspect(pending)
            if abs(info['duration']-p['duration'])>max(.12,2/cfg.output_fps):raise ValueError('Clock proxy berbeda dari sumber')
            pending.replace(output)
        finally:pending.unlink(missing_ok=True)
    result={'status':'ready','path':str(output),'content_id':content_id(output,fresh=True),'source_id':context['source_id'],
        'working_content_id':p['working_content_id'],'duration':p['duration'],'timebase':'source_seconds','mapping':'identity',
        'selected_audio_index':p['selected_audio_index'],'final_render_uses':'canonical_source'};write_json(receipt,result);return result
