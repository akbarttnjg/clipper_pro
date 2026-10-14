"""Actual FFmpeg/camera/matte output. Authored geometry is not neural/G4 evidence."""
import copy,json,os,subprocess
from pathlib import Path
from dataclasses import replace
import numpy as np
from PIL import Image,ImageDraw
import pytest
from .. import camera4_contract as c,camera4_plan as planning,camera4_render as camera,render,ffmpeg_util,editor_contract as ec,editor_media
from ..camera4_tracking import matte
from ..dependency_cache import content_id
from ..config import Config
from ._m4_fixture import video,make_studio,controls,change


def run(args):return subprocess.run(['ffmpeg','-nostdin','-v','error',*map(str,args)],check=True,capture_output=True)
def frame(path,t,width,height):
    data=run(['-ss',t,'-i',path,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']).stdout
    return np.frombuffer(data,dtype=np.uint8).reshape(height,width,3)
def plan_for(duration,width,height):
    return {'width':width,'height':height,'fps':30,'duration':duration,'warnings':[],
        'spans':[{'source_start':0.,'source_end':duration,'duration_frames':round(duration*30),'start_frame':0,'end_frame':round(duration*30),'kind':'body'}]}
def report_for(settings,duration=4.):
    segment={'shot_id':'authored-shot','start':0.,'end':duration,'source_size':[320,180],'layout':settings['layout'] if settings['layout']!='auto' else 'fit',
        'subjects':[],'material':None,'speaker':{'selected':None},'protected_source':[],'fallbacks':[],
        'background':settings['background'],'motion':settings['motion'],'keyframes':settings['keyframes'],'safe_margins':settings['safe_margins']}
    return {'analysis_id':'explicit-authored-geometry','settings':settings,'source_size':[320,180],'segments':[segment],'coverage':{'sample_count':0},'approved_revision':1}

@pytest.mark.parametrize('size',[(180,320),(320,180),(240,240),(240,300),(360,240)])
def test_actual_static_no_pan_full_decode_source_color_order_and_all_ratios(tmp_path,size):
    source=video(tmp_path/'source.mp4');before=content_id(source,fresh=True);W,H=size;cfg=Config(work_dir=str(tmp_path/'work'),use_nvenc=False,target_w=W,target_h=H,audio_normalize=False,join_fade_ms=0)
    settings=c.controls(controls(profile='education'),4.);plan=plan_for(4.,W,H);camera.apply(plan,{'_m4_camera':report_for(settings)},cfg,ffmpeg_util.probe(source))
    assert len(plan['shots'])==1 and plan['m4']['no_pan'];mix=render.audio_stems(source,plan,cfg,tmp_path/'audio');target=tmp_path/'final.mp4';render.video(source,plan,cfg,None,target,mix)
    actual=ffmpeg_util.probe(target);assert [actual['width'],actual['height']]==list(size);assert abs(actual['duration']-4)<.07;assert actual['has_audio'];run(['-i',target,'-f','null','-'])
    viewport=plan['shots'][0]['m4']['layers'][0]['viewport'];y=min(H-1,viewport[3]//2);x=W//2
    assert int(np.argmax(frame(target,.5,W,H)[y,x]))==0;assert int(np.argmax(frame(target,2.5,W,H)[y,x]))==2
    assert content_id(source,fresh=True)==before
    output=os.environ.get('CLIPPER_M4_MEDIA_EVIDENCE')
    if output:
        import shutil
        folder=Path(output);folder.mkdir(parents=True,exist_ok=True);shutil.copyfile(target,folder/(str(W)+'x'+str(H)+'-synthetic.mp4'))
        (folder/(str(W)+'x'+str(H)+'-report.json')).write_text(json.dumps({'source':'synthetic color/tone; authored fixed geometry','dimensions':size,'duration':actual['duration'],'no_pan':True,'full_decode':'passed','source_unchanged':True,'G4':'not_measured'},indent=2))


def test_manual_motion_bakes_frame_exact_geometry_with_bounded_memory(tmp_path):
    image=Image.new('RGB',(320,180),'red');ImageDraw.Draw(image).rectangle((160,0,319,179),fill='blue');png=tmp_path/'source.png';image.save(png);source=tmp_path/'source.mp4'
    run(['-y','-loop','1','-i',png,'-f','lavfi','-i','sine=frequency=440:duration=2','-t','2','-r','30','-c:v','libx264','-threads','2','-c:a','aac','-pix_fmt','yuv420p',source])
    settings=c.controls(controls(motion='manual',keyframes=[{'time':0,'box':[0,0,40,100]},{'time':2,'box':[60,0,40,100]}]),2.)
    cfg=Config(work_dir=str(tmp_path/'work'),use_nvenc=False,target_w=180,target_h=320,audio_normalize=False,join_fade_ms=0);plan=plan_for(2.,180,320);camera.apply(plan,{'_m4_camera':report_for(settings,2.)},cfg,ffmpeg_util.probe(source));assert len(plan['shots'])>30
    mix=render.audio_stems(source,plan,cfg,tmp_path/'audio');target=tmp_path/'motion.mp4';render.video(source,plan,cfg,None,target,mix)
    y=plan['shots'][0]['m4']['layers'][0]['viewport'][3]//2
    assert np.argmax(frame(target,.1,180,320)[y,90])==0;assert np.argmax(frame(target,1.8,180,320)[y,90])==2
    receipt=plan['m4']['composition_receipt'];assert receipt['frames']==60 and receipt['bounded_memory'].startswith('one source');run(['-i',target,'-f','null','-']);save_evidence('manual-motion-synthetic',target,receipt)


def mask_result(tmp_path,source,duration=2.):
    rows=[]
    for i in range(round(duration*2)):
        image=Image.new('L',(320,180));draw=ImageDraw.Draw(image);left=0 if i<2 else 160;draw.rectangle((left,0,left+159,179),fill=255);path=tmp_path/(str(i)+'-mask.png');image.save(path);rows.append({'time':i/2,'path':str(path)})
    return {'status':'ready','scope':'selected_range_sampled','source_content_id':content_id(source,fresh=True),'start':0.,'end':duration,'width':320,'height':180,'fps':2.,'frames':rows,'provenance':{'provider':'explicit_authored_mask_protocol_double'}}

def test_actual_continuous_matte_is_rendered_and_preserved_on_freeze_clock(tmp_path):
    source=video(tmp_path/'source.mp4');request={'start':0.,'end':2.,'time':0.,'box':[0,0,50,100]};carrier=matte(mask_result(tmp_path,source),source,request,[320,180],tmp_path/'matte');assert carrier['frames']==60
    settings=c.controls(controls(mask=request),4.);report=report_for(settings);report['matte']=carrier
    cfg=Config(work_dir=str(tmp_path/'work'),use_nvenc=False,target_w=320,target_h=180,audio_normalize=False,join_fade_ms=0);plan=plan_for(2.,320,180)
    clock=ec.build_clock(ec.validate_segments([{'id':'freeze','start':.2,'end':.3,'kind':'freeze','freeze_duration':2.}],{'start':0,'end':4}),30)
    # Source frame is constant red during this freeze; matte must remain left,
    # never advance into the right-hand mask at source second 1.
    camera.apply(plan,{'_m4_camera':report,'_editor_clock':clock},cfg,ffmpeg_util.probe(source));assert len(plan['shots'])==1
    mix=render.audio_stems(source,plan,cfg,tmp_path/'audio');target=tmp_path/'matte.mp4';render.video(source,plan,cfg,None,target,mix);assert plan['m4']['composition_receipt']['mask_frames']==60
    first=frame(target,.2,320,180);last=frame(target,1.7,320,180);y=plan['shots'][0]['m4']['layers'][0]['viewport'][3]//2
    assert np.argmax(first[y,120])==0 and np.argmax(last[y,120])==0;assert max(last[y,200])<40;run(['-i',target,'-f','null','-']);save_evidence('continuous-matte-freeze-synthetic',target,plan['m4']['composition_receipt'])

@pytest.mark.parametrize('mutation',['missing_frame','wrong_time','wrong_source','wrong_geometry','reference_only'])
def test_mask_gaps_and_foreign_source_rejected_before_carrier_write(tmp_path,mutation):
    source=video(tmp_path/'source.mp4');result=mask_result(tmp_path,source);request={'start':0.,'end':2.,'time':0.,'box':[0,0,50,100]}
    if mutation=='missing_frame':result['frames'].pop()
    elif mutation=='wrong_time':result['frames'][1]['time']=.75
    elif mutation=='wrong_source':result['source_content_id']='not source'
    elif mutation=='wrong_geometry':result['width']=640
    else:result['scope']='reference_frame_only'
    with pytest.raises(ValueError):matte(result,source,request,[320,180],tmp_path/'matte')
    assert not (tmp_path/'matte/continuous-matte.nut').exists()


def test_planar_attachment_warp_has_actual_pixels_and_transparency():
    image=Image.new('RGBA',(16,16),(255,0,0,255));result=camera.warp_attachment(image,[[10,10],[40,12],[38,42],[8,40]],(60,60),.5);array=np.asarray(result)
    assert 100<=array[25,25,3]<=150 and array[0,0,3]==0 and array[25,25,0]>200


def test_actual_core_pipeline_caption_sidecars_and_atomic_artifact_set(tmp_path):
    """Real core pipeline, FFmpeg/libass and ArtifactSet. Geometry is authored."""
    from .. import pipeline
    from ..artifact_store import verify
    source=video(tmp_path/'source.mp4');settings=c.controls(controls(),4.);report=report_for(settings)
    cfg=Config(work_dir=str(tmp_path/'work'),out_dir=str(tmp_path/'clips'),use_nvenc=False,target_w=180,target_h=320,visual_enabled=False,segmentation_enabled=False,align_selected_clips=False,audio_normalize=False,trim_silence=False,punch_zoom=False,broll_mode='off',illustration_mode='off')
    words=[{'word_id':i,'word':w,'start':.2+i*.3,'end':.45+i*.3,'probability':None} for i,w in enumerate('Catat biaya usaha dan simpan bukti transaksi'.split())]
    clip={'start':0.,'end':4.,'title':'Synthetic core M4 execution','keywords':[],'_m4_camera':report}
    result=pipeline.render_clip(str(source),words,clip,'m4-synthetic-core',cfg)
    assert Path(result['absolute_file']).is_file() and verify(result)
    saved=json.loads(Path(result['plan_path']).read_text());assert saved['m4']['analysis_id']==report['analysis_id'];assert saved['m4']['no_pan']
    assert Path(result['ass_path']).is_file() if 'ass_path' in result else result.get('ass_url')
    run(['-i',result['absolute_file'],'-f','null','-'])
    output=os.environ.get('CLIPPER_M4_MEDIA_EVIDENCE')
    if output:
        import shutil
        folder=Path(output);folder.mkdir(parents=True,exist_ok=True);shutil.copyfile(result['absolute_file'],folder/'core-captioned-synthetic.mp4');(folder/'core-pipeline-report.json').write_text(json.dumps({'source':'synthetic; authored geometry/timing','artifact_set_integrity':'passed','full_decode':'passed','caption_renderer':'actual core libass','G4':'not_measured'},indent=2))


def test_actual_M1_reorder_proxy_keeps_M4_camera_audio_and_both_ratio_clocks(tmp_path):
    from ..studio_worker import execute
    from .. import camera4_service
    service=make_studio(tmp_path)
    try:
        pid,cid=service.test_pid,service.test_cid;original=copy.deepcopy(service.transcript(service.store.get(pid))['words']);clocks=[]
        for vid,W,H in [('portrait',180,320),('landscape',320,180)]:
            change(service,{'op':'editor_segments','segments':[{'id':'second-first','start':2.,'end':4.},{'id':'first-last','start':0.,'end':2.}]},vid)
            change(service,{'op':'m4_controls','values':controls()},vid);execute(service,service.enqueue(pid,'camera_m4',cid,vid));doc=service.store.get(pid);report=service.variant(doc,cid,vid)['camera4_report']
            change(service,{'op':'m4_decide','analysis_id':report['analysis_id'],'accepted':True,'reason':'Authored clock/source verification','reviewed':['speaker_identity','material_hud','motion_no_pan','safe_area','source_order']},vid)
            doc=service.store.get(pid);clip={k:v for k,v in doc['clips'][cid].items() if k!='variants'};clip['_m4_camera']=camera4_service.renderable(service,doc,cid,vid);cfg=replace(service.config(doc,cid,vid),target_w=W,target_h=H,join_fade_ms=0)
            source,mapped,edited,local,receipt=editor_media.prepare(service,doc,cid,vid,doc['source']['path'],original,clip,cfg);clocks.append(receipt['clock']['digest']);assert [w['origin_word_id'] for w in mapped]==[1,0]
            plan=plan_for(4.,W,H);camera.apply(plan,edited,local,ffmpeg_util.probe(source));folder=tmp_path/vid;folder.mkdir();mix=render.audio_stems(source,plan,local,folder);target=folder/'reordered-camera.mp4';render.video(source,plan,local,None,target,mix)
            y=plan['shots'][0]['m4']['layers'][0]['viewport'][3]//2;x=W//2
            assert np.argmax(frame(target,.5,W,H)[y,x])==2 and np.argmax(frame(target,2.5,W,H)[y,x])==0
            for t,expected in [(.5,880),(2.5,660)]:
                raw=run(['-ss',t,'-t','0.25','-i',target,'-vn','-ac','1','-ar','8000','-f','f32le','-']).stdout;pcm=np.frombuffer(raw,dtype='<f4');hz=np.fft.rfftfreq(len(pcm),1/8000)[np.argmax(abs(np.fft.rfft(pcm)))];assert abs(hz-expected)<12
            run(['-i',target,'-f','null','-'])
        assert clocks[0]==clocks[1];assert service.transcript(service.store.get(pid))['words']==original
    finally:service.queue.close()


def save_evidence(name,path,receipt):
    output=os.environ.get("CLIPPER_M4_MEDIA_EVIDENCE")
    if output:
        import shutil
        folder=Path(output);folder.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,folder/(name+".mp4"));(folder/(name+".json")).write_text(json.dumps({"fixture":"synthetic/authored; no neural quality claim","receipt":receipt,"G4":"not_measured"},indent=2))
