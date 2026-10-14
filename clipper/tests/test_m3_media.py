"""Actual M3 acceptance -> source clock -> FFmpeg finals in both ratios.

Synthetic colors/tones and authored cue timing test execution, not ASR, CV,
typography aesthetics, a neural provider or G3 story-selection quality.
"""
import copy
import json
import subprocess
from dataclasses import replace
from pathlib import Path
import numpy as np
import pytest
from .. import selection_engine,selection_service,editor_media,render,ffmpeg_util
from ..dependency_cache import content_id
from ..studio_service import StudioService,identifier
from ._m3_fixture import reference,options,config


def run(command):
    return subprocess.run(['ffmpeg','-nostdin','-v','error',*map(str,command)],check=True,capture_output=True)


def test_actual_multispan_two_ratio_final_clock_audio_color_captions_and_cache(tmp_path):
    source=tmp_path/'synthetic-colors-tones.mp4'
    run(['-y','-f','lavfi','-i','color=c=red:s=320x180:r=30:d=2',
        '-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=2',
        '-f','lavfi','-i','color=c=green:s=320x180:r=30:d=2',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2',
        '-f','lavfi','-i','sine=frequency=660:sample_rate=48000:duration=2',
        '-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=2',
        '-filter_complex','[0:v][1:v][2:v]concat=n=3:v=1:a=0[v];[3:a][4:a][5:a]concat=n=3:v=0:a=1[a]',
        '-map','[v]','-map','[a]','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',source])
    before=content_id(source,fresh=True);cfg=config(tmp_path/'work',audio_normalize=False,join_fade_ms=0,trim_silence=False)
    service=StudioService(tmp_path,cfg,autostart=False)
    try:
        doc=service.create(source);pid=doc['project_id']
        data=reference(['Catat pemasukan usaha.','Pisahkan uang pribadi.','Jadi simpan bukti transaksi.'],step=2.)
        take=service.store.save_transcript(pid,data,'explicit-authored-media-clock')
        service.store.mutate(pid,0,identifier('media-seed'),{},lambda d:d.update(transcript_id=take,transcript_revision=1))
        doc=service.store.get(pid);report=selection_engine.analyze(data,options(min_seconds=1,max_seconds=6),cfg,source_id=before,take=take)
        report['source_signature']=selection_service.signature(service,doc)
        service.store.mutate(pid,doc['revision'],identifier('media-report'),{},lambda d:d.update(selection3=report))
        def change(op):
            current=service.store.get(pid)
            service.changes({'project_id':pid,'expected_revision':current['revision'],'operation_id':identifier('media-op'),'operations':[op]})
        change({'op':'m3_story','analysis_id':report['analysis_id'],'title':'Synthetic ordered clock',
            'source_spans':[{'start':4.2,'end':5.8},{'start':.2,'end':1.8}]})
        doc=service.store.get(pid);candidate=next(c for c in doc['selection3']['candidates'] if c['candidate_id']==doc['last_m3_story_candidate'])
        assert not candidate['completeness']['hard_blockers']
        change({'op':'m3_decide','analysis_id':report['analysis_id'],'candidate_id':candidate['candidate_id'],
            'status':'accepted','reason':'Authored execution fixture; source order checked','reviewed':selection_service.required_review(candidate)})
        doc=service.store.get(pid);cid=next(iter(doc['clips']));clip={k:v for k,v in doc['clips'][cid].items() if k!='variants'}
        original=copy.deepcopy(service.transcript(doc)['words']);receipts=[]
        for vid,width,height in [('portrait',360,640),('landscape',640,360)]:
            local=replace(service.config(doc,cid,vid),target_w=width,target_h=height,audio_normalize=False,join_fade_ms=0,use_nvenc=False)
            proxy,mapped,edited,local,receipt=editor_media.prepare(service,doc,cid,vid,str(source),original,clip,local)
            assert [w['origin_word_id'] for w in mapped]==[2,0]
            assert [(w['start'],w['end']) for w in mapped]==pytest.approx([(0.,1.6),(1.6,3.2)])
            assert receipt['clock']['duration']==pytest.approx(3.2)
            folder=tmp_path/vid;folder.mkdir();ass=folder/'authored-clock.ass'
            ass.write_text('[Script Info]\nScriptType: v4.00+\nPlayResX: '+str(width)+'\nPlayResY: '+str(height)+
                '\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
                'Style: Default,DejaVu Sans,18,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,12,12,18,1\n'
                '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
                'Dialogue: 0,0:00:00.00,0:00:01.60,Default,,0,0,0,,Jadi simpan bukti transaksi.\n'
                'Dialogue: 0,0:00:01.60,0:00:03.20,Default,,0,0,0,,Catat pemasukan usaha.\n',encoding='utf-8')
            # Fixed geometry is explicit. No unavailable CV detector is substituted.
            plan={'width':width,'height':height,'fps':30,'duration':3.2,'warnings':[],
                'spans':[{'source_start':0.,'source_end':3.2,'duration_frames':96,'kind':'body'}],
                'shots':[{'source_start':0.,'source_end':3.2,'duration_frames':96,'rect':[0,0,320,180],'mode':'fill','zoom_at':None}]}
            mix=render.audio_stems(proxy,plan,local,folder);final=folder/'final.mp4'
            render.video(proxy,plan,local,ass,final,mix)
            actual=ffmpeg_util.probe(final);assert (actual['width'],actual['height'])==(width,height)
            assert actual['has_audio'] and abs(actual['duration']-3.2)<=2/30
            run(['-i',final,'-f','null','-'])
            colors=[];tones=[]
            for position,expected_channel,frequency in [(.5,1,880),(2.1,0,440)]:
                frame=run(['-ss',position,'-i',final,'-frames:v','1','-vf','scale=2:2','-f','rawvideo','-pix_fmt','rgb24','-']).stdout
                rgb=np.frombuffer(frame,dtype=np.uint8).reshape(-1,3).mean(axis=0);assert int(np.argmax(rgb))==expected_channel;colors.append(rgb.tolist())
                pcm=run(['-ss',position,'-t','0.25','-i',final,'-vn','-ac','1','-ar','8000','-f','f32le','-']).stdout
                values=np.frombuffer(pcm,dtype='<f4');peak=float(np.fft.rfftfreq(len(values),1/8000)[np.argmax(abs(np.fft.rfft(values)))])
                assert abs(peak-frequency)<12;tones.append(peak)
            again=editor_media.prepare(service,doc,cid,vid,str(source),original,clip,local)
            assert again[-1]['reused'] and again[-1]['clock']['digest']==receipt['clock']['digest']
            receipts.append({'ratio':vid,'dimensions':[width,height],'duration':actual['duration'],'full_decode':'passed',
                'source_word_order':[w['origin_word_id'] for w in mapped],'source_clock':receipt['clock'],'colors':colors,'tone_hz':tones,
                'output_sha256':content_id(final),'proxy_reused':again[-1]['reused']})
        assert content_id(source,fresh=True)==before and service.transcript(doc)['words']==original
        assert receipts[0]['source_clock']['digest']==receipts[1]['source_clock']['digest']
        import os,shutil
        destination=os.environ.get('CLIPPER_M3_MEDIA_EVIDENCE')
        if destination:
            out=Path(destination);out.mkdir(parents=True,exist_ok=True)
            for vid in ('portrait','landscape'):shutil.copyfile(tmp_path/vid/'final.mp4',out/(vid+'-synthetic.mp4'))
            (out/'report.json').write_text(json.dumps({'environment':'Linux CPU, actual FFmpeg/libass','source':'synthetic colors/tones; authored cue times',
                'quality_g3':'not_measured','geometry':'fixed; no CV inference','receipts':receipts},indent=2))
    finally:service.queue.close()
