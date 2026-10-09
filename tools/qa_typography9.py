"""Render regression replay with real optional segmentation and font metrics.

The input is a recovered source-only plate with saved transcript. Frozen face
observations are replay evidence, not a fresh detector/ASR benchmark.
"""
import argparse
import copy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--plan',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--runtime',default='');args=parser.parse_args()
    sys.path.insert(0,str(ROOT))
    import cv2
    from clipper import pipeline,visual4,ffmpeg_util,projects
    from clipper.config import Config
    from clipper.text_area import grid
    from clipper.dependency_cache import content_id
    from clipper.storage import read_json,write_json
    saved=read_json(args.plan);info=ffmpeg_util.probe(args.source)
    # The recovered container advertises 14s but has only 410 video frames.
    # Test the intact 13.5s region instead of padding a truncated source.
    duration=min(13.5,info['duration'])
    words=copy.deepcopy([w for w in saved['words'] if w['end']<=duration])
    for w in words:w.pop('source_start',None);w.pop('source_end',None)
    folder=Path(args.output).resolve();folder.mkdir(parents=True,exist_ok=True)
    rows=[];cap=cv2.VideoCapture(args.source);face=[772.,240.,318.,416.]
    try:
        for i in range(int(duration*2)):
            t=i*.5;cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read()
            if not ok:raise ValueError('Plate QA tidak terbaca.')
            sample=grid(cv2.resize(frame,(640,360)));sample['source_size']=[info['width'],info['height']]
            rows.append({'t':t,'faces':[face],'tracks':[{'track_id':'replay-face','box':face,'confidence':.93,'time':t}],
                'hist':None,'area':[0,0,info['width'],info['height']],'panel':None,'texts':[],'ocr':[],'area_grid':sample})
    finally:cap.release()
    cfg=Config(work_dir=str(folder/'work'),out_dir=str(folder/'clips'),job_id='typography9-proof',use_nvenc=False,
        source_kind='speaker',style_preset='adaptif',trim_silence=False,caption_backdrop=True,caption_template_policy='auto',
        visual_runtime_root=args.runtime or str(folder/'runtime'),illustration_mode='off',broll_mode='off',caption_renderer='ass',punch_zoom=False)
    clip={'start':0.,'end':duration,'title':'Replay sumber lama 4.0.9','keywords':saved.get('keywords',[]),'revision':0}
    report={'version':'4.0.9','source_content_id':content_id(args.source),'source_seconds':duration,'container_seconds':info['duration'],
        'scope':'Recovered old source-only plate, saved transcript and frozen prior face observations. Real FFmpeg/MediaPipe CPU inference when configured. No fresh ASR, YuNet, latest video, Windows-native editor or user-device benchmark.',
        'renders':[]};results=[]
    for variant,W,H in [('portrait',1080,1920),('landscape',1920,1080)]:
        at=time.monotonic()
        with patch.object(visual4,'collect',return_value=(copy.deepcopy(rows),{'status':'replayed_face_observations'})):
            result=pipeline.render_clip(args.source,words,clip,'typography9-'+variant,replace(cfg,target_w=W,target_h=H,variant_id=variant))
        final=Path(cfg.out_dir)/result['file']
        result.update(clip_id='replay-source',variant_id=variant,absolute_file=str(final.resolve()),
                      output_content_id=content_id(final),plan_content_id=content_id(result['plan_path']))
        results.append(result)
        plan=read_json(result['plan_path']);caption_plan=plan['captions'] if 'captions' in plan else None
        if caption_plan is None:caption_plan=read_json(Path(result['ass_file']).with_suffix('.caption-plan.json')) if result.get('ass_file') else None
        poster=folder/(variant+'.jpg');subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-ss','3.1','-i',result['absolute_file'],'-frames:v','1',str(poster)],check=True,capture_output=True)
        report['renders'].append({'variant':variant,'seconds':round(time.monotonic()-at,3),'file':result['absolute_file'],
             'segmentation':plan.get('segmentation'),'placement':plan.get('placement_summary'),'qc':result.get('qc'),
             'caption_qc':result.get('caption_qc'),'style_report':result.get('style_report')})
        write_json(folder/(variant+'-result.json'),result)
        write_json(folder/(variant+'-plan.json'),plan)
    report['package']=projects.export_bundle(results,cfg)
    write_json(folder/'proof-report.json',report)
    print(json.dumps({'renders':[{'variant':r['variant'],'seconds':r['seconds'],'segmentation_status':(r.get('segmentation') or {}).get('status')} for r in report['renders']],
                      'editor_structures':report['package'].get('editors'),'report':str(folder/'proof-report.json')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
