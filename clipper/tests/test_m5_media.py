"""Actual FFmpeg/Pillow/libass tests; authored speech/geometry is not real G5 acceptance."""
import copy,json,os,shutil,subprocess
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import numpy as np
from PIL import Image,ImageDraw
import pytest
from ..config import Config
from .. import pipeline,camera4_contract as camera,ffmpeg_util,captions_pro,editor_contract as ec
from ..finishing5_contract import TEMPLATES
from ..finishing5_plan import caption_plan
from ..finishing5_render import caption_frame,decorations,censor_audio
from ..finishing5_service import map_layers
from ..finishing5_assets import sha
from ..artifact_store import verify
from ._m4_fixture import video,controls,make_studio,change
from .test_m4_media import report_for
from .test_m4_service import analyze,accept
from .test_m5_contract import words
def run(args):return subprocess.run(['ffmpeg','-nostdin','-v','error',*map(str,args)],capture_output=True,check=True)
def frame(path,t,W,H):return np.frombuffer(run(['-ss',t,'-i',path,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']).stdout,dtype=np.uint8).reshape(H,W,3)
def evidence(name,path,receipt):
    if not os.environ.get('CLIPPER_M5_MEDIA_EVIDENCE'):return
    folder=Path(os.environ['CLIPPER_M5_MEDIA_EVIDENCE']);folder.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,folder/(name+Path(path).suffix));(folder/(name+'.json')).write_text(json.dumps(receipt,indent=2))
@pytest.mark.parametrize('size',[(360,640),(640,360)])
@pytest.mark.parametrize('engine',['ass','raster'])
def test_actual_core_M4_M5_render_both_ratios_freezes_fonts_and_decodes(tmp_path,size,engine):
    source=video(tmp_path/'source.mp4');before=sha(source);W,H=size;config=Config(work_dir=str(tmp_path/'work'),out_dir=str(tmp_path/'output'),target_w=W,target_h=H,use_nvenc=False,visual_enabled=False,segmentation_enabled=False,align_selected_clips=False,audio_normalize=False,trim_silence=False,punch_zoom=False,finishing5={'enabled':True,'style':{},'decorations':[]},caption_renderer=engine)
    clip={'start':0.,'end':4.,'title':'Authored M5 media','keywords':['tidak naik'],'_m4_camera':report_for(camera.controls(controls(),4.))}
    result=pipeline.render_clip(source,words(),clip,'m5',config);p=json.loads(Path(result['plan_path']).read_text());assert verify(result,fresh=True)
    info=ffmpeg_util.probe(result['absolute_file']);assert (info['width'],info['height'])==size;assert abs(info['duration']-4)<.07
    assert p['caption_renderer']['engine']==engine;assert p['caption_checks']['passed'];assert p['m4']['no_pan'];assert sha(source)==before
    assert p['raster_qc']['decoded_frames']>0 and p['raster_qc']['contrast_ratio']>4.5
    assert all(Path(r['path']).is_file() for r in p['m5_fonts']);assert all(Path(r['path']).is_relative_to(Path(result['artifact_root'])) for r in p['m5_fonts'])
    run(['-i',result['absolute_file'],'-f','null','-'])
    evidence(engine+'-'+str(W)+'x'+str(H),result['absolute_file'],{'source':'authored colors, tones, transcript and M4 geometry','dimensions':size,'renderer':engine,'fonts':p['m5_fonts'],'full_decode':'passed','gate_g5':'pending_real_corpus','caption_checks':p['caption_checks']})
@pytest.mark.parametrize('size',[(360,640),(640,360)])
@pytest.mark.parametrize('template',[r['id'] for r in TEMPLATES])
def test_actual_ASS_and_Pillow_glyph_geometry_parity(tmp_path,size,template):
    W,H=size;config=Config(target_w=W,target_h=H,caption_template_policy='manual',motion_intensity='balanced',finishing5={'enabled':True,'style':{'template_id':template}})
    w=words('Catat biaya');p=caption_plan(w,config);ass=tmp_path/'p.ass';captions_pro.write_plan(p,ass,config)
    target=tmp_path/'ass.png'
    run(['-y','-f','lavfi','-i',f'color=c=0x101820:s={W}x{H}:r=30:d=1.6','-vf',ffmpeg_util.ass_filter(ass,config),'-ss','0.4','-frames:v','1',target])
    with Image.open(target) as im:actual=np.array(im.convert('RGB'))
    expected=Image.new('RGBA',(W,H),'#101820');expected.alpha_composite(caption_frame(p,config,.4));expected=np.array(expected.convert('RGB'))
    masks=[np.max(a,axis=2)>100 for a in (actual,expected)]
    def box(m):
        y,x=np.where(m);return np.array([x.min(),y.min(),x.max(),y.max()])
    delta=np.max(np.abs(box(masks[0])-box(masks[1])));iou=np.logical_and(*masks).sum()/max(1,np.logical_or(*masks).sum())
    assert delta<=4,(template,size,delta);assert iou>=.62,(template,size,iou)
    evidence('parity-'+template+'-'+str(W),target,{'tolerance_bbox_px':4,'observed_bbox_delta_px':int(delta),'glyph_mask_iou':float(iou),'minimum_iou':.62,'timing_tolerance_frames':1,'scope':'actual ASS raster vs actual Pillow raster; fixture text/font/timing'})
def test_actual_bleep_replaces_only_approved_output_intervals(tmp_path):
    source=video(tmp_path/'source.mp4');mix=tmp_path/'mix.wav';run(['-y','-i',source,'-vn','-ac','2','-ar','48000',mix])
    p={'duration':4.,'audio':{'mix':str(mix)},'captions':{'censor_intervals':[[1.,1.5]]}};target=censor_audio(p,Config(),str(mix),tmp_path)
    def samples(path):return np.frombuffer(run(['-i',path,'-f','s16le','-ac','1','-ar','48000','-']).stdout,dtype='<i2').astype(float)
    original,changed=samples(mix),samples(target);assert np.max(abs(original[:40000]-changed[:40000]))<=2
    segment=changed[50000:70000];freq=np.fft.rfftfreq(len(segment),1/48000)[np.argmax(abs(np.fft.rfft(segment)))];assert abs(freq-1000)<4
    assert p['audio']['censor']['dictionary_approved'];assert p['audio']['uncensored_mix']==str(mix)
def test_actual_video_overlay_follows_reverse_freeze_and_source_reorder(tmp_path):
    source=video(tmp_path/'stock.mp4');W,H=320,180
    clock=ec.build_clock(ec.validate_segments([{'id':'b','start':2,'end':4,'reverse':True},{'id':'f','start':.5,'end':.6,'kind':'freeze','freeze_duration':1},{'id':'a','start':0,'end':2}],{'start':0,'end':4}),30)
    asset={'id':'test','path':str(source),'kind':'video','name':'Authored tones/colors','sha256':sha(source),'metadata':{'duration':4},'permission':'user_owned'}
    cfg=Config(target_w=W,target_h=H,work_dir=str(tmp_path),use_nvenc=False,broll_ranker='off',finishing5={'enabled':True,'style':{},'decorations':[{'id':'broll','kind':'video','asset_id':'test','asset':asset,'start':0,'end':4,'rect':[5,5,20,20],'opacity':1.,'anchor':'manual','transition':'cut','transition_s':0.}]})
    p={'width':W,'height':H,'duration':clock['duration'],'fps':30,'editor':{'clock':clock},'spans':[],'shots':[],'display_words':[]};map_layers(p,cfg);decorations(p,cfg,tmp_path);target=p['finishing5']['overlay']['path']
    assert np.argmax(frame(target,.5,W,H)[20,30])==2
    assert np.argmax(frame(target,2.5,W,H)[20,30])==0
    assert np.argmax(frame(target,3.5,W,H)[20,30])==0
    assert not list(tmp_path.glob('*.rgba'));run(['-i',target,'-f','null','-'])
def test_required_ranker_fails_without_measured_score(tmp_path):
    source=video(tmp_path/'stock.mp4');a={'id':'stock','name':'Stock','path':str(source),'metadata':{'duration':4}}
    cfg=Config(broll_ranker='siglip2',finishing5={'enabled':True,'style':{},'decorations':[{'id':'s','kind':'video','asset':a,'start':0,'end':1,'rect':[5,5,20,20]}]})
    p={'duration':4,'fps':30,'width':640,'height':360,'spans':[{'start':0,'end':4,'source_start':0,'source_end':4}],'shots':[],'display_words':[]}
    with patch('clipper.asset_rank.rerank',return_value=([],['explicit unavailable protocol double'])),pytest.raises(ValueError,match='diwajibkan'):map_layers(p,cfg)
def test_actual_gallery_queue_uses_user_source_and_cancel_preserves_previous(tmp_path):
    from ..studio_worker import execute,StaleJob
    s=make_studio(tmp_path);analyze(s);accept(s);change(s,{'op':'m5_style','values':{'caption_renderer':'ass'}})
    old=copy.deepcopy(s.store.transcript(s.store.get(s.test_pid)['transcript_id']));job=s.enqueue(s.test_pid,'gallery_m5',s.test_cid,'portrait',options={'templates':['editorial','quote'],'seconds':2});result=execute(s,job);assert len(result['gallery']['items'])==2
    assert s.store.transcript(s.store.get(s.test_pid)['transcript_id'])==old
    j=s.enqueue(s.test_pid,'gallery_m5',s.test_cid,'portrait',options={'templates':['focus'],'seconds':2});s.queue.cancel(j['id'])
    with pytest.raises(StaleJob):execute(s,j)
    assert s.variant(s.store.get(s.test_pid),s.test_cid,'portrait')['finishing5']['gallery']==result['gallery']

@pytest.mark.parametrize('engine',['ass','raster'])
def test_actual_audio_audiogram_M5_uses_requested_renderer(tmp_path,engine):
    from ..audio_project import render_clip
    source=tmp_path/'speech.wav';run(['-y','-f','lavfi','-i','sine=frequency=440:duration=4','-ar','48000',source])
    cfg=Config(source_media_kind='audio',work_dir=str(tmp_path/'work'),out_dir=str(tmp_path/'out'),target_w=360,target_h=640,use_nvenc=False,audio_normalize=False,finishing5={'enabled':True,'style':{},'decorations':[]},caption_renderer=engine)
    result=pipeline.render_clip(source,words(),{'start':0,'end':4,'title':'Audio M5'},'audio',cfg)
    p=json.loads(Path(result['plan_path']).read_text());assert p['caption_renderer']['engine']==engine;assert p['source_kind']=='audio';assert p['caption_checks']['passed']
    assert verify(result,fresh=True);run(['-i',result['absolute_file'],'-f','null','-'])
    evidence('audio-'+engine,result['absolute_file'],{'kind':'actual audiogram; authored tone/transcript','renderer':engine,'full_decode':'passed'})
def test_actual_cover_is_bound_to_current_ratio_and_measured_frame(tmp_path):
    from ..studio_worker import execute
    from ..contracts import fingerprint
    s=make_studio(tmp_path);analyze(s);accept(s);change(s,{'op':'m5_enable','enabled':True})
    job=s.enqueue(s.test_pid,'preview',s.test_cid,'portrait',options={'quality':'draft'});result=execute(s,job)
    assert Path(result['absolute_file']).is_file()
    d=s.store.get(s.test_pid)
    def stale_final(current):s.variant(current,s.test_cid,'portrait')['result']={'dependency':'stale','absolute_file':'missing.mp4'}
    s.store.mutate(s.test_pid,d['revision'],'seed-stale-final',{},stale_final)
    job=s.enqueue(s.test_pid,'cover_m5',s.test_cid,'portrait',options={'time':.57,'text':'Simpan bukti biaya'})
    result=execute(s,job)['cover']
    assert .57<=result['output_time']<.57+1/30+.001;assert result['variant_id']=='portrait'
    with Image.open(result['path']) as im:assert im.height>im.width
    assert result['origin_output_digest'];evidence('cover-portrait',result['path'],result)
@pytest.mark.parametrize('transition',['cut','fade','blur','glitch'])
def test_actual_logo_transitions_keep_source_duration_and_layer_order(tmp_path,transition):
    image=tmp_path/'logo.png';Image.new('RGBA',(40,40),'#FFFFFF').save(image)
    cfg=Config(target_w=320,target_h=180,finishing5={'enabled':True,'style':{},'decorations':[{'id':'logo','kind':'logo','asset_id':'logo','asset':{'path':str(image),'sha256':sha(image)},'start':0.,'end':1.,'rect':[10,10,15,25],'opacity':.8,'transition':transition,'transition_s':.2,'reason':'operator selected'}]})
    p={'width':320,'height':180,'fps':30,'duration':1.,'spans':[{'start':0,'end':1,'source_start':0,'source_end':1}],'shots':[],'display_words':[]}
    map_layers(p,cfg);decorations(p,cfg,tmp_path);target=p['finishing5']['overlay']['path'];info=ffmpeg_util.probe(target)
    assert abs(info['duration']-1)<.04;assert p['finishing5']['extra_seconds']==0;run(['-i',target,'-f','null','-'])

def test_actual_raster_without_protective_paint_is_unknown_not_zero(tmp_path):
    source=video(tmp_path/'source.mp4')
    cfg=Config(work_dir=str(tmp_path/'work'),out_dir=str(tmp_path/'out'),target_w=360,target_h=640,use_nvenc=False,visual_enabled=False,segmentation_enabled=False,align_selected_clips=False,audio_normalize=False,trim_silence=False,punch_zoom=False,caption_backdrop=False,finishing5={'enabled':True,'style':{},'decorations':[]})
    clip={'start':0.,'end':4.,'title':'No paint reference','_m4_camera':report_for(camera.controls(controls(),4.))}
    r=pipeline.render_clip(source,words('Catat biaya'),clip,'unmeasured',cfg);p=json.loads(Path(r['plan_path']).read_text())
    assert p['raster_qc']['status']=='needs_review';assert p['raster_qc']['contrast_ratio'] is None
    assert p['raster_qc']['samples'] and all(x['contrast_ratio'] is None for x in p['raster_qc']['samples'])



