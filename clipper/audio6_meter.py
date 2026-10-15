"""Measurements refer to the actual supplied PCM/encoded file, not a target."""
import json
import math
import re
import subprocess
import numpy as np

def loudness(path,settings):
    graph=f"loudnorm=I={settings['target_lufs']}:TP={settings['peak_db']}:LRA=11:print_format=json"
    p=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-i',str(path),'-vn','-af',graph,'-f','null','-'],capture_output=True,text=True,timeout=300)
    matches=re.findall(r'\{\s*"input_i".*?\}',p.stderr,re.S)
    if p.returncode or not matches:raise ValueError('Pengukuran loudness M6 gagal: '+p.stderr[-800:])
    return json.loads(matches[-1])

def finite(value):
    try:r=float(value)
    except (ValueError,TypeError):return None
    return r if math.isfinite(r) else None

def measure(path,settings,*,expected_duration=None,fps=30):
    raw=loudness(path,settings)
    p=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=30)
    info=json.loads(p.stdout);a=next((x for x in info['streams'] if x['codec_type']=='audio'),None)
    if not a:raise ValueError('Output M6 tidak mempunyai track audio')
    rate=int(a['sample_rate']);channels=int(a['channels']);count=0;peak=0.;power=0.;clipped=0
    proc=subprocess.Popen(['ffmpeg','-nostdin','-v','error','-i',str(path),'-vn','-f','f32le','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        while data:=proc.stdout.read(256*1024):
            x=np.frombuffer(data[:len(data)//4*4],dtype='<f4')
            if not np.isfinite(x).all():raise ValueError('Output audio berisi sample tidak finite')
            peak=max(peak,float(np.max(abs(x),initial=0)));power+=float(np.sum(x.astype(np.float64)**2));count+=len(x);clipped+=int(np.sum(abs(x)>=1.))
        error=proc.stderr.read();rc=proc.wait(timeout=60)
        if rc:raise ValueError('Decode audio QC gagal: '+error.decode('utf-8','replace')[-500:])
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        proc.stdout.close();proc.stderr.close()
    lufs=finite(raw['input_i']);true_peak=finite(raw['input_tp']);issues=[]
    silent=peak<1e-9
    if silent:issues.append('Audio hening; periksa mute, source dan track yang dipilih')
    elif lufs is None:issues.append('Durasi/energi belum cukup untuk integrated LUFS; bukan nilai nol')
    if settings['normalize'] and lufs is not None and abs(lufs-settings['target_lufs'])>1.:issues.append('Loudness final di luar toleransi ±1 LU dari target aktif')
    if settings['limiter'] and true_peak is not None and true_peak>settings['peak_db']+.35:issues.append('True peak final melewati batas +0,35 dB')
    if clipped:issues.append('Ada sample PCM pada/di atas full scale')
    duration=float(a.get('duration') or info['format'].get('duration') or count/channels/rate)
    audio_start=float(a.get('start_time',0));video=next((x for x in info['streams'] if x['codec_type']=='video'),None)
    sync={'expected_seconds':expected_duration,'actual_seconds':duration,'sample_count':count//channels,
          'audio_start_seconds':audio_start,'video_start_seconds':float(video.get('start_time',0)) if video else None,
          'tolerance_seconds':1/fps+1024/rate,'status':'not_requested'}
    if expected_duration is not None:
        sync['duration_delta_seconds']=duration-expected_duration
        sync['start_delta_seconds']=audio_start-(sync['video_start_seconds'] or 0.)
        sync['status']='passed' if max(abs(sync['duration_delta_seconds']),abs(sync['start_delta_seconds']))<=sync['tolerance_seconds'] else 'needs_review'
        if sync['status']!='passed':issues.append('Clock audio/hasil tidak cocok dengan snapshot video')
    return {'version':'4.0.17-m6','status':'needs_review' if issues else 'passed','integrated_lufs':lufs,'true_peak_db':true_peak,
        'sample_peak_db':20*math.log10(peak) if peak>0 else None,'rms_db':10*math.log10(power/count) if power>0 and count else None,
        'clipped_samples':clipped,'sample_rate':rate,'channels':channels,'codec':a.get('codec_name'),'silent':silent,
        'normalization_active':settings['normalize'],'target_lufs':settings['target_lufs'] if settings['normalize'] else None,
        'stored_target_lufs':settings['target_lufs'],'target_peak_db':settings['peak_db'] if settings['limiter'] else None,
        'sync':sync,'issues':issues,'measurement':'actual FFmpeg loudnorm input measurements and decoded PCM; not a listening test',
        'gate_g6':'pending_real_speech_listening'}
