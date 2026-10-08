"""Reproducible video/export QA using a recovered plate and observed face box.

This replay tests composition, caption rendering, audio and package generation.
It deliberately does not claim to test ASR or a live detector. Inputs are the
user's previously rendered source-only plate and original frozen edit plan.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
import types
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--original-plan',required=True)
    p.add_argument('--output',required=True);p.add_argument('--offset',type=float,default=20);p.add_argument('--seconds',type=float,default=14)
    args=p.parse_args();sys.path.insert(0,str(ROOT))
    try:import cv2
    except ImportError:
        cv2=types.ModuleType('cv2');cv2.VideoCapture=lambda *_:types.SimpleNamespace(release=lambda:None)
        sys.modules['cv2']=cv2
    from dataclasses import replace
    from clipper.config import Config
    from clipper import pipeline,visual4,projects
    from clipper.storage import read_json,write_json
    from clipper.dependency_cache import content_id
    original=read_json(args.original_plan);folder=Path(args.output).resolve();folder.mkdir(parents=True,exist_ok=True)
    words=[]
    for w in original['words']:
        if args.offset<=w['start'] and w['end']<=args.offset+args.seconds:
            row=copy.deepcopy(w);row.update(start=w['start']-args.offset,end=w['end']-args.offset)
            row.pop('source_start',None);row.pop('source_end',None);words.append(row)
    face=[772.,240.,318.,416.]
    rows=[{'t':i*.5,'faces':[face],'tracks':[{'track_id':'face-0001','box':face,'confidence':.93,'time':i*.5}],
        'hist':None,'area':[0,0,1920,1080],'panel':None,'texts':[],'ocr':[]} for i in range(int(args.seconds*2)+1)]
    cfg=Config(work_dir=str(folder/'work'),out_dir=str(folder/'clips'),job_id='complete-replay',
        use_nvenc=False,source_kind='speaker',style_preset='adaptif',font_main='dm_sans',font_accent='dm_serif_italic',
        trim_silence=False,caption_backdrop=True,caption_template_policy='auto',visual_runtime_root=str(folder/'runtime'),
        illustration_mode='off',broll_mode='off',caption_renderer='ass')
    clip={'start':0.,'end':args.seconds,'title':'Uji tampilan dari plate sebelumnya','keywords':['plan','ego'],'revision':0}
    results=[];report={'scope':'Recovered old source-only plate, saved transcript and controlled prior face observations. No fresh ASR/detector/native-editor verification.','renders':[]}
    for vid,w,h in [('portrait',1080,1920),('landscape',1920,1080)]:
        at=time.monotonic()
        with patch.object(visual4,'collect',return_value=(rows,{'status':'controlled_prior_observations'})):
            result=pipeline.render_clip(args.source,words,clip,'replay-'+vid,replace(cfg,target_w=w,target_h=h,variant_id=vid))
        final=Path(cfg.out_dir)/result['file'];result.update(absolute_file=str(final),variant_id=vid,clip_id='replay-one',
            output_content_id=content_id(final,fresh=True),plan_content_id=content_id(result['plan_path'],fresh=True),title=clip['title']+' ['+vid+']')
        results.append(result);plan=read_json(result['plan_path'])
        poster=folder/(vid+'.jpg');subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-ss','3','-i',str(final),'-frames:v','1',str(poster)],capture_output=True,check=True)
        report['renders'].append({'variant':vid,'seconds':round(time.monotonic()-at,3),'qc':result.get('qc'),
            'caption_checks':plan.get('caption_checks'),'audio_quality':plan.get('audio_quality'),
            'placement':[{'mode':s['mode'],'image_height':s.get('image_height'),'zoom_at':s.get('zoom_at')} for s in plan['shots']],
            'voice_cache':plan.get('voice_cache'),'style_issues':plan.get('style_report',{}).get('issues'),
            'final':str(final),'poster':str(poster)})
        print('Render selesai: '+vid,flush=True)
    write_json(folder/'results.json',results)
    report['package']=projects.export_bundle(results,cfg,mode='hybrid')
    write_json(folder/'replay-report.json',report)
    print(json.dumps({'renders':len(results),'package':report['package']['structural_status']},ensure_ascii=False))


if __name__=='__main__':main()
