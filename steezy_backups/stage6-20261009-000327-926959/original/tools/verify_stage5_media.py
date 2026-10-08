"""Real FFmpeg/ASS/audio acceptance on synthetic material, no model mocks."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
# This workspace has pip's real vendored requests; application files are unchanged.
from pip._vendor import requests
sys.modules['requests']=requests
import copy,hashlib,json,subprocess
from dataclasses import replace
from PIL import Image,ImageDraw
from clipper.config import Config
from clipper.typography import make_plan,font
from clipper.captions_pro import write_plan
from clipper import render,ffmpeg_util,audio_quality,explanation5

OUT=ROOT/'work/stage5-verification/media';OUT.mkdir(parents=True,exist_ok=True)
def run(command):
 r=subprocess.run([str(s) for s in command],capture_output=True,timeout=90)
 if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')[-1400:])
 return r.stdout
cfg=Config(use_nvenc=False,work_dir=str(OUT/'work'),out_dir=str(OUT))
poster=OUT/'synthetic-source.png';im=Image.new('RGB',(1280,720),'#11151b');d=ImageDraw.Draw(im)
d.rounded_rectangle((70,64,1210,512),radius=22,fill='#213043')
d.text((115,105),'DEMO TAHAP 5',font=font(cfg.fonts_dir,46,cfg.font_main),fill='#F6CF69')
d.text((115,185),'Materi sumber sintetis',font=font(cfg.fonts_dir,32,cfg.font_main),fill='#FFFFFF')
d.text((115,250),'Kutipan dan waktu kata adalah fixture pengujian.',font=font(cfg.fonts_dir,26,cfg.font_main),fill='#B4C6DC')
d.text((115,300),'Audio berupa nada uji, bukan ucapan manusia.',font=font(cfg.fonts_dir,26,cfg.font_main),fill='#B4C6DC')
d.line([(120,439),(310,360),(490,397),(680,320),(880,378),(1155,334)],fill='#81C3BD',width=6)
im.save(poster)
source=OUT/'synthetic-source.mp4'
run(['ffmpeg','-nostdin','-v','error','-y','-loop','1','-i',poster,'-f','lavfi','-i','sine=frequency=260:sample_rate=48000:duration=12',
 '-af',r"volume=if(between(t\,2\,3)+between(t\,6\,7)\,0.02\,0.20):eval=frame",'-t','12','-r','30','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',source])
music=OUT/'music.wav';sfx=OUT/'sfx.wav'
run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','sine=frequency=90:sample_rate=48000:duration=12',music])
run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','sine=frequency=800:sample_rate=48000:duration=0.25',sfx])
sentences=['Risiko bukan alasan untuk berhenti belajar.','Modal Rp 5 juta tetap perlu dijaga.','Jangan abaikan konteks ketika mengambil keputusan.','Disiplin menjaga proses agar tetap konsisten.']
words=[];identity=0
for k,sentence in enumerate(sentences):
 tokens=sentence.split();step=2.70/len(tokens)
 for i,text in enumerate(tokens):
  words.append({'word':text,'word_id':identity,'start':k*3+i*step,'end':k*3+(i+1)*step});identity+=1
results=[];thumbnails=[]
for W,H,ratio in [(1280,720,'16x9'),(720,1280,'9x16')]:
 for preset in ('rapi','ekspresif','adaptif'):
  local=replace(cfg,target_w=W,target_h=H,style_preset=preset,source_kind='board' if preset=='adaptif' else 'auto',
                music_path=str(music),sfx_path=str(sfx),sfx_max=2,sfx_gap_s=8.)
  folder=OUT/(preset+'-'+ratio);folder.mkdir(exist_ok=True)
  plan={'width':W,'height':H,'fps':30,'duration':12.,'warnings':[],
    'spans':[{'start':0.,'end':12.,'source_start':0.,'source_end':12.,'kind':'story'}],
    'shots':[{'start':0.,'end':12.,'source_start':0.,'source_end':12.,'rect':[0,0,1280,720],
              'mode':'fit','image_height':int(H*.77)//2*2,'zoom_at':None,'duration_frames':360}],
    'captions':make_plan(words,local,keywords=['berhenti belajar','Modal','konteks'],anchors=[{'start':0,'end':12,'position':'bottom',
        'panel':[W*.08,H*.815,W*.78,H*.16],'protected':[],'has_material':preset=='adaptif'}])}
  ass=folder/'captions.ass';write_plan(plan['captions'],ass,local)
  from clipper.caption_checks import inspect_caption_plan
  inspect_caption_plan(plan['captions'],local,expected_words=words)
  mix=render.audio_stems(source,plan,local,folder)
  target=folder/'demo.mp4';render.video(source,plan,local,str(ass),target,mix)
  info=ffmpeg_util.probe(str(target));assert (info['width'],info['height'])==(W,H);assert abs(info['duration']-12)<.1 and info['has_audio']
  check=audio_quality.inspect(str(target),local)
  assert len(plan['audio']['sfx_events'])<=2
  assert all(b-a>=8 for a,b in zip(plan['audio']['sfx_events'],plan['audio']['sfx_events'][1:]))
  frame=folder/'frame.png';run(['ffmpeg','-nostdin','-v','error','-y','-ss','4.35','-i',target,'-frames:v','1',frame])
  thumbnails.append((preset+' '+ratio,frame))
  results.append({'preset':preset,'ratio':ratio,'file':str(target),'metadata':info,'audio_quality':check,
    'readability':plan['captions']['readability']['status'],'sfx_events':plan['audio']['sfx_events'],
    'caption_plan_sha256':hashlib.sha256(json.dumps(plan['captions'],sort_keys=True).encode()).hexdigest()})
  (folder/'edit-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
  print(preset,ratio,'video passed',check['status'],flush=True)
# Regenerating one final render must preserve decoded sample pixels.
repeat=OUT/'rapi-9x16/repeat.mp4'
local=replace(cfg,target_w=720,target_h=1280,style_preset='rapi',music_path=str(music),sfx_path=str(sfx),sfx_max=2,sfx_gap_s=8.)
plan=json.loads((OUT/'rapi-9x16/edit-plan.json').read_text());render.video(source,plan,local,str(OUT/'rapi-9x16/captions.ass'),repeat,plan['audio']['mix'])
frame_hashes=[]
for t in (.35,1.65,4.35,7.35,10.35):
 hashes=[hashlib.sha256(run(['ffmpeg','-nostdin','-v','error','-ss',str(t),'-i',p,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])).hexdigest() for p in (OUT/'rapi-9x16/demo.mp4',repeat)]
 assert hashes[0]==hashes[1];frame_hashes.append({'time':t,'sha256':hashes[0]})
asset=explanation5.make_asset('Jangan abaikan konteks ketika mengambil keputusan.',[10,11,12,13,14],cfg)
assert ffmpeg_util.probe(asset['path'])['duration']==3
assert asset['origin']['quote']=='Jangan abaikan konteks ketika mengambil keputusan.'
assert Path(asset['editable_path'],'src/scene.tsx').is_file()
sheet=Image.new('RGB',(1500,1040),'#0d1117');draw=ImageDraw.Draw(sheet)
for i,(label,path) in enumerate(thumbnails):
 x=(i%3)*500;y=(i//3)*520;pic=Image.open(path);pic.thumbnail((470,455));sheet.paste(pic,(x+(500-pic.width)//2,y+55));draw.text((x+20,y+15),label,font=font(cfg.fonts_dir,26,cfg.font_main),fill='white')
sheet.save(OUT/'Perbandingan_Gaya_Tahap_5.png')
report={'scope':'real FFmpeg CPU with synthetic source and tones; direct render modules, not full ASR pipeline',
 'renders':results,'repeat_decoded_frame_hashes':frame_hashes,'explanation':asset,
 'pending':['real browser Remotion/Motion Canvas execution','SigLIP2 real model inference','Windows/RTX3050','native editor imports','real speech intelligibility review']}
(OUT.parent/'media_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('All six MP4s, repeat frame identity, explanation quote and editable project passed.',flush=True)
