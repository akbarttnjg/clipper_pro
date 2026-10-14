"""Source/caching and model protocol tests; any doubles are explicit."""
import copy,json,types,sys
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from .. import camera4_contract as c,camera4_observe as observe,camera4_plan as plan,camera4_tracking as tracking
from ..config import Config
from ..dependency_cache import content_id
from ._m4_fixture import video,controls

def test_source_frame_at_end_uses_measured_previous_frame_not_fake_timestamp(tmp_path):
    source=video(tmp_path/'source.mp4');_,path=observe.image_at(source,3.99,tmp_path/'frames');receipt=json.loads(path.with_suffix('.json').read_text());assert 3.94<receipt['time']<=3.99 and receipt['requested_time']==3.99

def test_corrupt_camera_cache_is_not_silently_overwritten(tmp_path):
    source=video(tmp_path/'source.mp4');cfg=Config(work_dir=str(tmp_path/'work'),visual_enabled=False);settings=c.controls(controls(),4.)
    report=observe.analyze(source,content_id(source),[[0.,4.]],settings,cfg,tmp_path/'cache');path=tmp_path/'cache'/(report['analysis_id']+'.json');original=json.loads(path.read_text());original['document']['source_size']=[1,1];path.write_text(json.dumps(original));before=path.read_bytes()
    with pytest.raises(ValueError,match='Cache kamera rusak'):observe.analyze(source,content_id(source),[[0.,4.]],settings,cfg,tmp_path/'cache')
    assert path.read_bytes()==before

def test_same_camera_source_reuses_cache_but_source_changes_keep_old_frames(tmp_path):
    source=video(tmp_path/'source.mp4');cfg=Config(work_dir=str(tmp_path/'work'),visual_enabled=False);settings=c.controls(controls(),4.)
    a=observe.analyze(source,content_id(source),[[0.,4.]],settings,cfg,tmp_path/'cache');b=observe.analyze(source,content_id(source),[[0.,4.]],settings,cfg,tmp_path/'cache');assert b['cache_reused']
    before={r['path']:content_id(r['path'],fresh=True) for r in a['frames']};source.write_bytes(source.read_bytes()+b'new source container bytes')
    d=observe.analyze(source,content_id(source,fresh=True),[[0.,4.]],settings,cfg,tmp_path/'cache');assert d['analysis_id']!=a['analysis_id'];assert all(content_id(p,fresh=True)==h for p,h in before.items())

def test_actual_model_weight_change_during_protocol_call_fails(tmp_path):
    runtime={'directory':str(tmp_path),'generation':'explicit_test_generation'};(tmp_path/'weights').mkdir();file=tmp_path/'weights/model.bin';file.write_bytes(b'original test weights')
    def native(*a,**k):file.write_bytes(b'changed test weights');return {'status':'ready'}
    with patch('clipper.visual4.component_runtime',return_value=runtime),patch('clipper.visual4.backend',side_effect=native):
        with pytest.raises(ValueError,match='Bobot model'):observe.backend('sam2',{},Config(),tmp_path/'out')

@pytest.mark.parametrize('status',['unavailable','failed','disabled'])
def test_unknown_ASD_never_selects_largest_face(status):
    people=[{'id':'large','visibility':1.},{'id':'small','visibility':1.}];settings=c.controls(controls(),4.);result=plan.speaker(people,[{'start':0,'end':2,'speaker_id':'S1'}],0,2,{'status':status},settings);assert result['selected'] is None and result['confidence'] is None

@pytest.mark.parametrize('kind',['screen','gameplay','pip'])
@pytest.mark.parametrize('size',[(360,640),(640,360)])
def test_material_HUD_remains_in_viewport_for_supported_layouts(kind,size):
    settings=c.controls(controls(layout=kind),4.);segment={'source_size':[1280,720],'layout':kind,'subjects':[{'id':'s','box':[1060,120,100,100],'observations':[]}],'material':[0,0,900,720],'speaker':{'selected':None},'protected_source':[{'kind':'hud','box':[50,10,500,40]},{'kind':'material','box':[0,0,900,720]}],'safe_margins':settings['safe_margins']}
    built=plan.layers(segment,*size,settings);main=built['layers'][0];assert c.intersection(main['source_crop'],segment['material'])==segment['material'];assert any(r['kind']=='hud' for r in built['protected_output'])


def test_native_tracker_unavailable_fails_explicitly_instead_of_fabricating_path(tmp_path):
    stub=types.ModuleType('cv2')
    with patch.dict(sys.modules,{'cv2':stub}),pytest.raises(ValueError,match='OpenCV native'):tracking.track('unused',{'start':0,'end':2,'time':0,'box':[0,0,20,20],'mode':'object'},[320,180],tmp_path)


def test_asd_margin_only_uses_measured_audio_window_not_offscreen_scores():
    people=[{'id':'a','visibility':1.},{'id':'b','visibility':1.}];settings=c.controls(controls(),4.)
    active={'status':'ready','audio_windows':[{'start':0,'end':1}],'scores':[{'time':2.,'track_id':i,'score':v} for i,v in [('a',.99),('b',.1)] for _ in range(5)]}
    assert plan.speaker(people,[],0,3,active,settings)['selected'] is None
    active['scores']=[{'time':t,'track_id':i,'score':v} for t in (.2,.3,.4) for i,v in [('a',.9),('b',.2)]]
    assert plan.speaker(people,[],0,1,active,settings)['selected']=='a'
