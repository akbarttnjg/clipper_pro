"""Real FFmpeg effects on authored geometry; original source is immutable."""
import copy
import json
from pathlib import Path
import pytest
from clipper.m9_effects import recipe
from clipper.m8_contract import AccessDenied
from clipper.studio_worker import execute,StaleJob
from clipper.project_store import JobLeaseLost
from clipper.dependency_cache import content_id
from ._m4_fixture import make_studio


@pytest.fixture
def studio(tmp_path):
    service=make_studio(tmp_path)
    try:yield service
    finally:service.queue.close();service.integrations.close()


@pytest.mark.parametrize('operations',[
    [{'kind':'pan','x':'system()'}], [{'kind':'color','brightness':float('nan')}],
    [{'kind':'upscale','width':640,'height':480}], [{'kind':'blur','rect':[0,0,999,30],'ranges':[[0,1]]}],
    [{'kind':'blur','rect':[0,0,30,30],'ranges':[[2,1]]}], [{'kind':'fade','direction':'out','start':3.9,'duration':1}],
    [{'kind':'color','filter':'movie=https://remote'}], [{'kind':'curves','points':[[.5,0],[.3,1]]}],
    [{'kind':'v360','projection':'flat','width':320,'height':180}],
    [{'kind':'upscale','width':640,'height':360},{'kind':'blur','rect':[0,0,20,20],'ranges':[[0,1]]}],
])
def test_recipe_rejects_unbounded_unsafe_or_unsupported_operations(operations):
    with pytest.raises(ValueError):recipe({'operations':operations,'material_reviewed':True},4,[320,180])


def test_protected_material_and_no_pan_are_enforced():
    with pytest.raises(ValueError,match='area penting'):recipe({'operations':[{'kind':'mosaic','rect':[10,10,20,20],'ranges':[[0,1]]}],'protected_regions':[[0,0,100,100]],'material_reviewed':True},4,[320,180])
    with pytest.raises(ValueError,match='no-pan'):recipe({'operations':[{'kind':'color'}],'material_reviewed':True,'no_pan':False},4,[320,180])


@pytest.mark.parametrize('operations',[
    [{'kind':'color','brightness':.03,'contrast':1.1,'saturation':.9,'gamma':1.02},{'kind':'curves','points':[[0,0],[.5,.55],[1,1]]},{'kind':'denoise','strength':1}],
    [{'kind':'blur','rect':[20,20,80,60],'ranges':[[.2,1.8]],'strength':5},{'kind':'mosaic','rect':[150,30,80,60],'ranges':[[2,2.8]],'strength':8}],
    [{'kind':'fade','direction':'in','start':0,'duration':.2},{'kind':'upscale','width':640,'height':360}],
    [{'kind':'lens','k1':.02,'k2':0,'crop_reviewed':True}],
    [{'kind':'stabilize','crop_reviewed':True}],
    [{'kind':'v360','projection':'equirectangular','width':320,'height':180,'yaw':30,'pitch':0,'fov':90}],
    [{'kind':'interpolate','fps':60}],
])
def test_real_effect_media_decode_duration_provenance_and_original(studio,operations):
    doc=studio.store.get(studio.test_pid);actor=studio.integrations.local_actor();lab=studio.lab
    snapshot=lab.effects.prepare(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],'recipe':{'operations':operations,'material_reviewed':True},'start':0.,'end':3.})
    job=lab.enqueue(actor,'effects_m9',snapshot);result=execute(studio,job)
    derivative=studio.store.get(result['project_id']);info=derivative['source']['info']
    assert abs(info['duration']-3)<.15 and info['audio_tracks']
    manifest=json.loads(Path(result['manifest_path']).read_text());assert manifest['recipe']['no_pan'] and not manifest['recipe']['hook']
    assert manifest['source_revision']==doc['revision'] and manifest['source_content_id']==doc['source']['source_id']
    assert content_id(doc['source']['path'],fresh=True)==doc['source']['source_id']
    assert result['project_id']!=doc['project_id'] and not manifest['editable_native_effects']
    if operations[-1]['kind']=='interpolate':assert info['fps']['numerator']/info['fps']['denominator']==60


def test_source_revision_change_and_cancel_never_publish(studio):
    lab=studio.lab;actor=lab.m8.local_actor();doc=studio.store.get(studio.test_pid)
    snap=lab.effects.prepare(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],'recipe':{'operations':[{'kind':'color'}],'material_reviewed':True}})
    job=lab.enqueue(actor,'effects_m9',snap);studio.store.mutate(doc['project_id'],doc['revision'],'m9-revision-race',{},lambda d:d.update(name='Changed'))
    before=len(studio.store.list())
    with pytest.raises(StaleJob):execute(studio,job)
    assert studio.queue.get(job['id'])['status']=='stale' and len(studio.store.list())==before
    doc=studio.store.get(studio.test_pid);snap=lab.effects.prepare(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],'recipe':{'operations':[{'kind':'color'}],'material_reviewed':True}})
    job=lab.enqueue(actor,'effects_m9',snap);claimed=studio.queue.claim(job['id']);studio.queue.cancel(job['id'])
    with pytest.raises(JobLeaseLost):lab.effects.execute(claimed)
    assert len(studio.store.list())==before


def test_valid_cube_lut_copy_checksum_and_render(studio,tmp_path):
    path=tmp_path/'identity.cube';path.write_text('LUT_3D_SIZE 2\n'+'\n'.join(f'{r} {g} {b}' for b in (0,1) for g in (0,1) for r in (0,1))+'\n')
    actor=studio.integrations.local_actor();lab=studio.lab;lut=lab.effects.register_lut(actor,{'name':'Authored identity','path':str(path),'license':'Authored test fixture'})
    doc=studio.store.get(studio.test_pid);snap=lab.effects.prepare(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],'recipe':{'operations':[{'kind':'lut','asset_id':lut['id']}],'material_reviewed':True}})
    result=execute(studio,lab.enqueue(actor,'effects_m9',snap));assert studio.store.get(result['project_id'])['source']['lineage']['kind']=='effects9'


def test_real_chroma_pixels_overlay_order_and_pack_roundtrip(studio,tmp_path):
    import subprocess
    from PIL import Image
    actor=studio.integrations.local_actor();lab=studio.lab;source=tmp_path/'green.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=0x00ff00:s=320x180:r=30:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-vf','drawbox=x=100:y=40:w=100:h=100:color=red:t=fill','-c:v','libx264','-threads','2','-c:a','aac',str(source)],check=True,capture_output=True)
    doc=studio.create(source);image=tmp_path/'overlay.png';Image.new('RGBA',(30,30),(255,255,255,255)).save(image)
    asset=lab.providers.media_import(actor,{'path':str(image),'kind':'image','name':'Authored white overlay','model':'authored fixture','prompt':'solid white box','license':'Authored','permission':'own','reviewed':True})
    ops=[{'kind':'chroma','key_color':'#00ff00','background':'#0000ff','similarity':.15,'blend':.01,'edges_reviewed':True},
         {'kind':'overlay','asset_id':asset['id'],'rect':[10,10,30,30],'ranges':[[0,1.9]],'opacity':1}]
    snap=lab.effects.prepare(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],'recipe':{'operations':ops,'material_reviewed':True}})
    result=execute(studio,lab.enqueue(actor,'effects_m9',snap));path=studio.store.get(result['project_id'])['source']['path']
    raw=subprocess.run(['ffmpeg','-v','error','-ss','0.5','-i',path,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],check=True,capture_output=True).stdout
    import numpy as np
    frame=np.frombuffer(raw,dtype=np.uint8).reshape((180,320,3))
    assert frame[130,250,2]>180 and frame[130,250,1]<80,'green background replaced by blue'
    assert frame[90,140,0]>180 and frame[90,140,2]<80,'foreground remains red'
    assert frame[20,20].min()>180,'explicit later overlay is above chroma result'
    preset=lab.dispatch(actor,'m9.preset.save',{'name':'Authored color pack','recipe':{'operations':[{'kind':'color','contrast':1.1}],'material_reviewed':True},'size':[320,180],'duration':2,'license':'Authored'})
    exported=lab.dispatch(actor,'m9.preset.export',{'id':preset['id']});cloned=lab.dispatch(actor,'m9.preset.import',{'file_id':exported['url'].rsplit('/',1)[-1]})
    assert cloned['data']['recipe']==preset['data']['recipe'] and cloned['id']!=preset['id']
