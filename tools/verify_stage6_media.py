"""Five synthetic scene fixtures, both ratios, against a frozen Stage 5 checkout.

Requires core application dependencies and FFmpeg. No ASR/model/editor is invoked.
The generated tones and schematic subjects do not test human speech or detection.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run(args):
    p=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=180)
    if p.returncode:raise RuntimeError(p.stderr[-1600:])
    return p.stdout


def render_case(settings):
    sys.path.insert(0,settings['code_root'])
    from clipper.config import Config
    from clipper.typography import make_plan
    from clipper.captions_pro import write_plan
    from clipper.caption_checks import inspect_caption_plan
    from clipper import render,ffmpeg_util
    from clipper.storage import write_json
    folder=Path(settings['folder']);folder.mkdir(parents=True,exist_ok=True)
    w,h=settings['size'];cfg=Config(use_nvenc=False,target_w=w,target_h=h,style_preset='adaptif' if settings['category'] in ('chart','board') else 'rapi',
        work_dir=str(folder/'work'),out_dir=str(folder),sfx_mode='off',punch_zoom=False)
    source=Path(settings['source']);words=[{'word':text,'word_id':i,'start':i*.45,'end':(i+1)*.45}
        for i,text in enumerate('Jangan abaikan konteks angka dan materi sumber.'.split())]
    anchor={'start':0.,'end':4.,'panel':[w*.06,h*.79,w*.88,h*.18],'protected':[],
        'has_material':settings['category'] in ('chart','board','graphics'),'position':'bottom'}
    captions=make_plan(words,cfg,keywords=['konteks'],anchors=[anchor]);inspect_caption_plan(captions,cfg,expected_words=words)
    plan={'revision':1,'width':w,'height':h,'fps':30,'duration':4.,'duration_frames':120,
        'source':{'path':str(source),**ffmpeg_util.probe(str(source))},'words':words,'warnings':[],
        'spans':[{'start':0.,'end':4.,'source_start':0.,'source_end':4.,'kind':'story','start_frame':0,'duration_frames':120}],
        'shots':[{'start':0.,'end':4.,'source_start':0.,'source_end':4.,'rect':[0,0,640,360],
            'mode':'fit','image_height':int(h*.74)//2*2,'zoom_at':None,'zoom_amount':0.,'start_frame':0,'duration_frames':120}],
        'style':{'caption_style':cfg.caption_style,'accent':cfg.accent_hex,'base':cfg.base_hex},
        'captions':captions,'broll':[],'render_config':{}}
    ass=folder/'captions.ass';write_plan(captions,ass,cfg);plan['subtitle_path']=str(ass)
    mix=render.audio_stems(source,plan,cfg,folder);target=folder/'final.mp4';render.video(source,plan,cfg,str(ass),target,mix)
    write_json(folder/'edit-plan.json',plan)
    info=ffmpeg_util.probe(str(target));assert [info['width'],info['height']]==[w,h] and abs(info['duration']-4)<.1 and info['has_audio']
    result={'absolute_file':str(target),'plan_path':str(folder/'edit-plan.json'),'revision':1,'title':settings['category'],
        'width':w,'height':h,'length':4.,'output_content_id':'sha256:'+hashlib.sha256(target.read_bytes()).hexdigest()}
    result['plan_content_id']='sha256:'+hashlib.sha256((folder/'edit-plan.json').read_bytes()).hexdigest()
    write_json(folder/'result.json',result)


def fixtures(output,baseline_root):
    sys.path.insert(0,str(ROOT))
    from PIL import Image,ImageDraw,ImageFont
    from clipper.evaluation6 import CATEGORIES,compare
    from clipper.metrics6 import ResourceMeter
    from clipper.config import Config
    from clipper.projects import export_bundle
    from clipper.storage import read_json,write_json
    from clipper.dependency_cache import content_id
    output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('Pilih folder evaluasi baru; hasil sebelumnya tidak ditimpa.')
    output.mkdir(parents=True,exist_ok=True);(output/'sources').mkdir();baseline_root=Path(baseline_root).resolve()
    if baseline_root==ROOT or not (baseline_root/'clipper/render.py').is_file():raise ValueError('Pilih salinan kode Tahap 5 yang terpisah sebagai baseline.')
    font=ImageFont.truetype(str(ROOT/'clipper/fonts/DMSans-SemiBold.ttf'),21)
    rows=[];resources=[]
    for category in CATEGORIES:
        poster=Image.new('RGB',(640,360),'#142332');d=ImageDraw.Draw(poster)
        d.text((20,16),'FIXTURE SINTETIS / '+category,font=font,fill='#F6CF69')
        if category in ('talking_head','multispeaker'):
            for x in ([300] if category=='talking_head' else [180,440]):
                d.ellipse((x-43,82,x+43,168),fill='#dcad80');d.rounded_rectangle((x-75,175,x+75,310),radius=30,fill='#5a819d')
        elif category=='chart':
            d.line((65,280,585,280),fill='white',width=2)
            for i,height in enumerate((85,150,105,175,130)):d.rectangle((90+i*95,280-height,140+i*95,280),fill='#70bdaf')
            d.text((65,55),'Chart contoh / bukan data faktual',font=font,fill='white')
        elif category=='board':
            d.rectangle((40,65,600,305),fill='#30554e');d.text((65,95),'0,01  /  Rp 5 juta',font=font,fill='white')
            d.text((65,145),'Negasi tetap punya konteks',font=font,fill='white');d.line((65,200,480,200),fill='#e7dd9e',width=3)
        else:
            for i,color in enumerate(('#4b7594','#688e81','#ac8d5b')):d.rounded_rectangle((30+i*203,80,210+i*203,255),radius=15,fill=color)
            d.text((30,285),'Grafis contoh / label tetap di sumber',font=font,fill='white')
        poster_path=output/'sources'/(category+'.png');poster.save(poster_path);source=output/'sources'/(category+'-source.mp4')
        run(['ffmpeg','-nostdin','-v','error','-y','-loop','1','-i',poster_path,'-f','lavfi','-i','sine=frequency=300:duration=4',
            '-t','4','-r','30','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac',source])
        source_hash=content_id(source,fresh=True)
        for size,ratio in [([640,360],'16x9'),([360,640],'9x16')]:
            results=[]
            for label,code in [('baseline',baseline_root),('candidate',ROOT)]:
                folder=output/category/ratio/label;cfg_path=output/(category+'-'+ratio+'-'+label+'.json')
                write_json(cfg_path,{'source':str(source),'folder':str(folder),'code_root':str(code),'size':size,'category':category})
                p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--render-one',str(cfg_path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                meter=ResourceMeter(p.pid)
                while p.poll() is None:
                    meter.sample()
                    try:stdout,stderr=p.communicate(timeout=.2)
                    except subprocess.TimeoutExpired:continue
                stdout,stderr=p.communicate()
                if p.returncode:raise RuntimeError(stderr[-1800:])
                if content_id(source,fresh=True)!=source_hash:raise RuntimeError('Fixture sumber berubah saat render '+category+' '+ratio+' '+label)
                result=read_json(folder/'result.json');results.append(result)
                resources.append({'category':category,'ratio':ratio,'engine':label,**meter.report()})
            value=compare(results[0]['absolute_file'],results[1]['absolute_file'],category=category,
                context={'source_content_id':content_id(source),'source_spans':[[0.,4.]],'ratio':ratio},label='Stage 5 → Stage 6 synthetic regression')
            assert value['ssim']==1.,'Stage 6 changed decoded pixels for '+category+' '+ratio
            rows.append(value);print(category,ratio,'identical decoded pixels',flush=True)
    # Validate the new exports on real generated media. CapCut absence stays a failure.
    selected=read_json(output/'talking_head/16x9/candidate/result.json');cfg=Config(use_nvenc=False,work_dir=str(output/'export-work'),out_dir=str(output/'exports'),target_w=640,target_h=360)
    preserved=export_bundle([selected],cfg,mode='preserved')
    import zipfile
    with zipfile.ZipFile(preserved['zip']) as z:
        assert 'sha256:'+hashlib.sha256(z.read('Media/01-final.mp4')).hexdigest()==selected['output_content_id']
    hybrid=export_bundle([selected],cfg,mode='hybrid')
    # Use a supported full-canvas shot for the native adapter, with the same source range.
    from clipper import render
    plan=read_json(selected['plan_path']);plan['shots'][0]['image_height']=360
    native_root=output/'native-compatible';native_root.mkdir();native_file=native_root/'final.mp4'
    render.video(plan['source']['path'],plan,cfg,plan['subtitle_path'],native_file,plan['audio']['mix'])
    plan_path=native_root/'edit-plan.json';write_json(plan_path,plan)
    native_result={**selected,'plan_path':str(plan_path),'absolute_file':str(native_file),
        'output_content_id':content_id(native_file),'plan_content_id':content_id(plan_path)}
    native=export_bundle([native_result],cfg,mode='native')
    native_plan=read_json(Path(native['folder'])/'edit-plan-01.json');assert native_plan['shots'][0]['rect']==[0,0,640,360]
    assert content_id(native_plan['source']['path'])==content_id(output/'sources/talking_head-source.mp4')
    assert hybrid['editors']['resolve']['structural_status']=='passed',hybrid
    assert native['editors']['resolve']['structural_status']=='passed',native
    report={'scope':'synthetic, manually composed shots, fixture words and test tones; no ASR/detection/native editor',
        'baseline_root':str(baseline_root),'candidate_root':str(ROOT),'categories':list(CATEGORIES),'ratios':['16:9','9:16'],
        'comparisons':rows,'resources':resources,'exports':{'preserved':preserved,'hybrid':hybrid,'native':native},
        'pending':['real five-category source collection and human review','Windows/RTX3050 measurements','CapCut runtime generation and both native editor import tests']}
    write_json(output/'acceptance.json',report);print('All 10 before/after pairs and three export paths verified.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--render-one');parser.add_argument('--baseline-root');parser.add_argument('--output',default=str(ROOT/'work/stage6-evaluation'))
    args=parser.parse_args()
    if args.render_one:render_case(json.loads(Path(args.render_one).read_text()))
    elif args.baseline_root:fixtures(args.output,args.baseline_root)
    else:parser.error('--baseline-root diperlukan untuk perbandingan dua versi')
