"""Explicit CPU/FFmpeg/OCR smoke test with SYNTHETIC media, not an ASR benchmark.

python -m clipper.tests.parallel_a.media_smoke --output /absolute/qa-directory
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from dataclasses import replace
from PIL import Image,ImageDraw
from clipper.analysis_options import AnalysisConfig
from clipper import typography,evidence,editplan,composition,placement,captions_pro,render,ffmpeg_util
from clipper import caption_checks,asset_review,analysis_adapter,source_assets


def run(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    cfg=AnalysisConfig(work_dir=str(output/'work'),out_dir=str(output),use_nvenc=False,trim_silence=False,
        audio_normalize=False,ocr_max_frames=3,ocr_interval_s=5,visual_cues=True,caption_style='magazine',punch_zoom=False,
        material_rect='3,7,65,64',speaker_rect='75,12,22,66',broll_mode='off')
    image=Image.new('RGB',(1280,720),'#172337');d=ImageDraw.Draw(image)
    d.rounded_rectangle((36,50,870,514),radius=12,fill='#eef2f7')
    f=lambda size:typography.font(cfg.fonts_dir,size,'dm_sans')
    d.text((74,80),'XAUUSD / TIMEFRAME',font=f(43),fill='#14243b')
    d.text((74,155),'DROP BASE DROP',font=f(38),fill='#24394d')
    d.line([(85,245),(310,380),(545,380),(792,468)],fill='#ad412d',width=10)
    d.text((76,555),'SYNTHETIC TEST / NO REAL MARKET DATA',font=f(23),fill='#cad3e2')
    d.rounded_rectangle((960,86,1245,560),radius=24,fill='#365370')
    d.ellipse((1020,120,1184,295),fill='#d1b69c');d.rounded_rectangle((990,300,1220,550),radius=30,fill='#a5b6c9')
    frame=output/'synthetic-source.png';image.save(frame)
    media=output/'synthetic-source.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-loop','1','-i',str(frame),'-f','lavfi','-i',
        'sine=frequency=440:sample_rate=48000:duration=14','-t','14','-vf','format=yuv420p','-r','30',
        '-c:v','libx264','-preset','veryfast','-threads','2','-c:a','aac','-shortest',str(media)],check=True)
    source_id='sha256:'+hashlib.sha256(media.read_bytes()).hexdigest()
    ev=evidence.scan(media,cfg,14,input_fingerprint=source_id)
    assert ev['sample_count']==3
    assert ev['ocr_status']=='ready' and any('XAUUSD' in r['text'] for fr in ev['frames'] for r in fr['texts'])
    script='Pahami konteks timeframe sebelum memilih arah trading XAUUSD Kelola risiko dengan stop loss dan jangan mengabaikan kondisi pasar'
    words=[dict(word_id=i,word=w,start=.4+i*.53,end=.4+i*.53+.49) for i,w in enumerate(script.split())]
    clip=dict(start=0,end=14,title='Synthetic typography verification',keywords=['stop loss','risiko'])
    results=[]
    for width,height in ((540,960),(960,540)):
        local=replace(cfg,target_w=width,target_h=height)
        plan=editplan.build(words,clip,local)
        context=analysis_adapter.envelope('MediaContext',source_id,'fixture-context',display_size=[1280,720],
            encoded_size=[1280,720],sample_aspect_ratio=[1,1],rotation_applied=False,source_time_origin=0,
            audio_stream_id='audio:0',duration=14,working_path=str(media),coordinate_space='canonical_source_pixels',geometry_status='ready')
        scenes,plan=analysis_adapter.analyze_scenes(context,plan,local,input_fingerprint=f'fixture:{width}x{height}')
        assert scenes['state']=='ready'
        folder=output/f'{width}x{height}';folder.mkdir(exist_ok=True)
        plan['display_words']=plan['words']
        ass=captions_pro.write_ass(plan['words'],folder/'captions.ass',local,keywords=clip['keywords'],anchors=placement.caption_anchors(plan,local))
        cp=json.loads(Path(ass).with_suffix('.caption-plan.json').read_text())
        checks=caption_checks.inspect_caption_plan(cp,local,expected_words=plan['words'])
        mix=render.audio_stems(media,plan,local,folder)
        target=folder/'render.mp4';render.video(media,plan,local,ass,target,mix)
        probe=ffmpeg_util.probe(target);assert (probe['width'],probe['height'])==(width,height)
        assert abs(probe['duration']-plan['duration'])<.15
        subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-ss','4.0','-i',str(target),'-frames:v','1',str(folder/'frame.png')],check=True)
        results.append({'ratio':f'{width}x{height}','qc':checks,'file':str(target),'source_kind':'synthetic','duration':probe['duration']})
    diagram=source_assets.diagram('drop base drop','contoh drop base drop',cfg)
    assert diagram and Path(diagram['editable_path']).is_file()
    asset=source_assets.from_source('XAUUSD timeframe','Pahami XAUUSD timeframe',cfg)
    assert asset and asset['provider']=='source'
    assert asset_review.poster(asset,cfg).is_file()
    recipe={'scenes':[dict(id='fixture-proposal',source_start=5,source_end=8,reason='Materi sumber sesuai',query='XAUUSD timeframe',asset={**asset,'duration':3})],'notes':[]}
    exchange=analysis_adapter.asset_proposal_set(recipe,source_id=source_id,input_fingerprint='fixture-proposal',cfg=cfg)
    assert exchange['payload']['proposals'][0]['usage_status']=='not_scheduled'
    assert exchange['payload']['proposals'][0]['content_fingerprint'].startswith('sha256:')
    report={'environment':'Linux CPU / FFmpeg','synthetic':True,'ocr_engine':'rapidocr-onnxruntime 1.4.4',
            'ocr_frames':ev['sample_count'],'renders':results,'asset_proposals':exchange,
            'not_tested':['Whisper accuracy','Ollama real semantic/vision output','Windows NVENC','CapCut/DaVinci native import']}
    (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print(json.dumps({'report':str(output/'report.json'),'ocr_frames':ev['sample_count'],'renders':len(results)},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
