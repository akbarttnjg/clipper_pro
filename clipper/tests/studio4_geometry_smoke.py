"""Actual ffprobe/FFmpeg/OpenCV media interpretation gate (opt-in)."""
import argparse,json,subprocess
from dataclasses import replace
from pathlib import Path
from clipper.config import Config
from clipper import media_context
from clipper.storage import write_json


def ff(*args):subprocess.run(['ffmpeg','-nostdin','-hide_banner','-v','error','-y',*map(str,args)],check=True)


def run(output):
    root=Path(output).resolve();root.mkdir(parents=True,exist_ok=True);cfg=Config(work_dir=str(root/'work'),use_nvenc=False)
    plain=root/'plain.mp4'
    ff('-f','lavfi','-i','testsrc2=s=160x90:r=30:d=3','-f','lavfi','-i','sine=f=440:r=48000:d=3','-c:v','libx264','-threads','2','-c:a','aac','-shortest',plain)
    rotated=root/'rotated.mp4';ff('-display_rotation','90','-i',plain,'-c','copy',rotated)
    sar=root/'sar.mp4';ff('-i',plain,'-vf','setsar=2/1','-c:v','libx264','-threads','2','-c:a','copy',sar)
    multi=root/'two-audio.mp4';ff('-i',plain,'-f','lavfi','-i','sine=f=880:r=48000:d=3','-map','0:v','-map','0:a','-map','1:a','-c:v','copy','-c:a','aac','-shortest',multi)
    offset=root/'offset.mp4';ff('-i',plain,'-itsoffset','0.5','-i',plain,'-map','0:v','-map','1:a','-c','copy',offset)
    vfr=root/'vfr.mp4';ff('-i',plain,'-vf',"select='if(lt(t,1),1,not(mod(n,2)))'",'-fps_mode','vfr','-c:v','libx264','-threads','2','-c:a','copy',vfr)
    reports=[]
    for path,local,expected in [(rotated,cfg,[90,160]),(sar,cfg,[320,90]),(multi,replace(cfg,audio_stream_index=2),[160,90]),(offset,cfg,[160,90]),(vfr,cfg,[160,90])]:
        context=media_context.prepare(path,local);out=media_context.inspect(context['payload']['working_path'])
        assert out['display_size']==expected,(path,out)
        assert out['rotation']==0 and out['sample_aspect_ratio']=={'numerator':1,'denominator':1}
        assert abs(out['video_start_time'])<.001 and len(out['audio_tracks'])==1
        reports.append({'fixture':path.name,'source':media_context.inspect(path),'canonical':out,'context':context})
        print(path.name,'OK',flush=True)
    # The chosen stream really contains 880 Hz, not the original 440 Hz.
    import numpy as np
    chosen=reports[2]['context']['payload']['working_path']
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',chosen,'-vn','-ac','1','-ar','8000','-f','f32le','-'])
    samples=np.frombuffer(raw,dtype='<f4')[4000:12000];peak=np.argmax(abs(np.fft.rfft(samples)))*8000/len(samples)
    assert abs(peak-880)<5,peak
    # The delayed source audio remains silent at video time 0, instead of shifting speech earlier.
    delayed=reports[3]['context']['payload']['working_path'];raw=subprocess.check_output(['ffmpeg','-v','error','-i',delayed,'-vn','-ac','1','-ar','8000','-f','f32le','-'])
    samples=np.frombuffer(raw,dtype='<f4');early=np.sqrt(np.mean(samples[:2400]**2));later=np.sqrt(np.mean(samples[6400:8800]**2))
    assert early<.001 and later>.02,(early,later)
    result={'passed':True,'fixtures':reports,'selected_audio_frequency_hz':float(peak),'delayed_audio_rms':[float(early),float(later)]}
    write_json(root/'report.json',result);print('Geometry and audio timebase passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);run(p.parse_args().output)
