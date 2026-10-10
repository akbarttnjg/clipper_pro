"""62s real FFmpeg regression with synthetic source and declared source boxes.

No raw user footage, ASR, live detector, neural inference or native-editor
acceptance is claimed. Exercises production placement, typography, ASS, video
renderer, stream QC and full decode in both Full HD ratios.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run(command):
    p=subprocess.run(list(map(str,command)),capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stderr[-2400:])
    return p


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    from PIL import Image,ImageDraw
    from clipper.config import Config
    from clipper import typography,placement,framing,captions_pro,render,qc,projects
    from clipper.storage import write_json
    from clipper.dependency_cache import content_id
    folder=Path(args.output).resolve();folder.mkdir(parents=True,exist_ok=True)
    source=folder/'synthetic-source.mp4';mix=folder/'silent-fixture.wav'
    picture=Image.new('RGB',(1920,1080),'#273540');draw=ImageDraw.Draw(picture)
    draw.rectangle((0,0,570,1080),fill='#43555e');draw.rectangle((1400,0,1920,1080),fill='#35464c')
    draw.rounded_rectangle((690,360,1240,1140),radius=170,fill='#55726e')
    draw.ellipse((790,105,1110,450),fill='#ba9b80');draw.ellipse((850,260,862,272),fill='#293136');draw.ellipse((1025,260,1037,272),fill='#293136')
    draw.rounded_rectangle((1090,930,1230,1080),radius=20,fill='#20242a')
    image=folder/'synthetic-source.png';picture.save(image)
    if not source.is_file():run(['ffmpeg','-nostdin','-v','error','-y','-loop','1','-i',image,'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','62','-r','30','-c:v','libx264','-preset','ultrafast','-crf','24','-pix_fmt','yuv420p','-threads','4','-c:a','aac',source])
    if not mix.is_file():run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','62','-c:a','pcm_s16le',mix])
    lines=[(0.,'Ketika emosinya makin memuncak.'),(3.,'Itu yang bahaya.'),(6.,'Tetap memahami konteks sumber.'),
           (9.,'Kita trading tanpa rencana.'),(12.,'Jangan hilangkan kata penting.'),(15.,'Modal Rp 5 juta tetap dijaga.'),
           (18.,'Hari ini kita belajar.'),(21.,'Risiko bukan alasan berhenti.'),(24.,'Setiap keputusan punya konsekuensi.'),
           (27.,'Perhatikan waktu dan biaya.'),(30.,'Pahami penjelasan dengan utuh.'),(33.,'Jangan mengubah makna ucapan.'),
           (36.,'Tetap tenang saat belajar.'),(39.,'Hasil membutuhkan proses.'),(42.,'Lihat bukti dan alasannya.'),
           (45.,'Gara -gara kesentil.'),(50.,'jadi hilang dan itu'),(53.,'akan terus -terusan kalian alamin'),(58.,'Tetap dengarkan kalimat utuh.')]
    ws=[]
    for start,text in lines:
        for i,t in enumerate(text.split()):
            ws.append(dict(word_id=len(ws),word=t,start=start+i*.36,end=start+(i+1)*.36,
                           sentence_end=i==len(text.split())-1))
    report={'version':'4.0.10','seconds':62,'scope':__doc__.strip(),'source_content_id':content_id(source),'renders':[]}
    for variant,W,H in [('portrait',1080,1920),('landscape',1920,1080)]:
        started=time.monotonic();cfg=Config(style_preset='ekspresif',target_w=W,target_h=H,use_nvenc=False,punch_zoom=False)
        rect=framing.crop_rect([0,0,1920,1080],[790,105,320,345],W/H)
        shots=[]
        for a,b in ((0,11),(11,20),(20,49),(49,55),(55,62)):
            shots.append(dict(mode='fill',rect=rect.copy(),active_area=[0,0,1920,1080],face=[790,105,320,345],
                start=a,end=b,source_start=a,source_end=b,start_frame=a*30,duration_frames=(b-a)*30,
                position='bottom',zoom_at=None,protected_source=[{'kind':'face','box':[790,105,320,345]},
                                                               {'kind':'accessory','box':[1090,930,140,150]}]))
        plan=dict(width=W,height=H,fps=30,duration=62,words=copy.deepcopy(ws),display_words=copy.deepcopy(ws),shots=shots,
                  spans=[dict(start=0,end=62,source_start=0,source_end=62)],warnings=[],broll=[])
        placement.apply(plan,cfg);anchors=placement.caption_anchors(plan,cfg)
        captions=typography.make_plan(ws,cfg,anchors=anchors)
        plan['captions']=captions;plan['caption_checks']=qc.inspect_caption_plan(captions,cfg,expected_words=ws)
        assert not any(s.get('image_height') for s in plan['shots']),'Unexpected image shrink on plain clothing fixture'
        ass=captions_pro.write_plan(captions,folder/(variant+'.ass'),cfg)
        projects.write_srt(plan,folder/(variant+'.srt'))
        target=folder/(variant+'-62s.mp4');render.video(source,plan,cfg,ass,target,mix)
        checked=qc.inspect(target,cfg,62)
        run(['ffmpeg','-nostdin','-v','error','-i',target,'-f','null','-'])
        for at in (12.8,50.5,53.6):run(['ffmpeg','-nostdin','-v','error','-y','-ss',at,'-i',target,'-frames:v','1',folder/(variant+'-'+str(at)+'.png')])
        write_json(folder/(variant+'-plan.json'),plan)
        report['renders'].append(dict(variant=variant,file=target.name,wall_seconds=round(time.monotonic()-started,3),qc=checked,
            full_decode='passed',caption_checks=plan['caption_checks'],placement=plan['placement_summary'],
            min_lower_px=min(p['min_visible_lower_px'] for p in captions['readability']['phrases']),
            readability=captions['readability'],output_content_id=content_id(target)))
        write_json(folder/'proof-report.json',report);print(variant+' finished',flush=True)
    print(json.dumps({r['variant']:{'seconds':r['wall_seconds'],'min_lower_px':r['min_lower_px'],'decode':r['full_decode']} for r in report['renders']},indent=2))


if __name__=='__main__':main()
