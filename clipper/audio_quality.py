"""Bounded waveform samples and measured audio delivery checks."""
import array
import json
import math
import re
import subprocess


def waveform(source,duration,bins=600):
    bins=max(40,min(1200,int(bins)));rate=8000;step=max(1,math.ceil(duration*rate/bins));values=[]
    proc=subprocess.Popen(['ffmpeg','-nostdin','-v','error','-i',str(source),'-vn','-ac','1','-ar',str(rate),'-f','f32le','-'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        while True:
            block=proc.stdout.read(step*4)
            if not block:break
            samples=array.array('f');samples.frombytes(block[:len(block)//4*4]);values.append(round(max((abs(x) for x in samples),default=0),4))
        if proc.wait()!=0:raise ValueError('Gelombang audio belum dapat dibaca')
    finally:
        proc.stdout.close()
        if proc.poll() is None:proc.kill();proc.wait()
    return {'duration':duration,'step_seconds':step/rate,'peaks':values,'timebase':'source_seconds','sample_rate':rate}


def inspect(path,cfg):
    result=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-i',str(path),'-vn','-af',
        f'loudnorm=I={cfg.audio_target_lufs}:TP={cfg.audio_peak_db}:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    matches=re.findall(r'\{\s*"input_i".*?\}',result.stderr,re.S)
    if result.returncode or not matches:return {'status':'unavailable','issues':['Pengukuran loudness belum tersedia']}
    raw=json.loads(matches[-1]);lufs=float(raw['input_i']);peak=float(raw['input_tp']);issues=[]
    if not math.isfinite(lufs):issues.append('Audio hening; periksa track yang dipilih')
    elif abs(lufs-cfg.audio_target_lufs)>3:issues.append('Loudness di luar toleransi ±3 LU dari target')
    if peak>cfg.audio_peak_db+.5:issues.append('True peak di atas batas target')
    return {'status':'needs_review' if issues else 'passed','integrated_lufs':lufs if math.isfinite(lufs) else None,
        'true_peak_db':peak if math.isfinite(peak) else None,'target_lufs':cfg.audio_target_lufs,'target_peak_db':cfg.audio_peak_db,
        'issues':issues,'join_fade_ms':cfg.join_fade_ms,'music_ducking':bool(cfg.music_path),'measurement':'FFmpeg loudnorm; not a listening test'}
