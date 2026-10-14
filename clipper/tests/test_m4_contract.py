import pytest
from .. import camera4_contract as c,camera4_observe as observe,camera4_plan as plan
from ._m4_fixture import controls

@pytest.mark.parametrize('key,value',[('profile','finance'),('layout','nonsense'),('motion','auto'),('background','stretch'),('detect_faces','true'),('ocr',1),('frame_budget',True),('frame_budget',7),('interval_seconds',0),('scene_threshold',float('nan')),('deadzone',-.1),('smoothing',1),('max_speed',2),('safe_margins',[1,0,0,0]),('regions',{}),('keyframes',[{'time':True,'box':[0,0,50,50]}]),('speaker_links',[{'speaker_id':'S1','track_id':'a','reviewed':False}]),('mask',{'start':0,'end':7,'time':1,'box':[0,0,20,20]}),('tracker',{'start':0,'end':2,'time':1,'box':[0,0,20,20],'mode':'magic'})])
def test_invalid_controls_fail_without_coercion(key,value):
    with pytest.raises(ValueError):c.controls(controls(**{key:value}),20.)

@pytest.mark.parametrize('value',[[0,0,0,1],[-1,0,5,5],[95,0,10,10],[0,0,float('inf'),2],[True,0,10,10],[],None])
def test_invalid_source_boxes_rejected(value):
    with pytest.raises(ValueError):c.box(value)

def test_education_no_pan_cannot_be_changed_by_tracking_or_keyframes():
    for motion in ('track','manual'):
        with pytest.raises(ValueError,match='no-pan'):c.controls(controls(profile='education',motion=motion),4.)
    assert c.controls(controls(profile='education'),4.)['motion']=='static'

def test_manual_keyframes_require_fixed_size_and_strict_source_time():
    good=controls(motion='manual',keyframes=[{'time':0.,'box':[0,0,40,80]},{'time':4.,'box':[50,0,40,80]}]);assert c.controls(good,4.)['keyframes']==good['keyframes']
    for mutated in ([{'time':2,'box':[0,0,40,80]},{'time':1,'box':[50,0,40,80]}],[{'time':0,'box':[0,0,40,80]},{'time':4,'box':[50,0,30,80]}]):
        with pytest.raises(ValueError):c.controls(controls(motion='manual',keyframes=mutated),4.)

def test_crop_track_speed_is_bounded():
    settings=c.controls(controls(motion='track',deadzone=.03,smoothing=.1,max_speed=.1),4.)
    rows=[{'time':0.,'box':[0,10,30,30]},{'time':1.,'box':[200,10,30,30]},{'time':2.,'box':[250,10,30,30]}]
    path=c.smoothed_path(rows,[0,0,100,100],settings,320,180)
    assert all(abs(b['box'][0]-a['box'][0])<=32.001 for a,b in zip(path,path[1:]))

def test_ambiguous_crossings_and_cuts_do_not_switch_face_identity():
    rows=[{'time':0,'cut':True,'faces':[{'box':[0,0,20,20]},{'box':[20,0,20,20]}]},{'time':.5,'cut':False,'faces':[{'box':[10,0,20,20]}]},{'time':1.,'cut':True,'faces':[{'box':[10,0,20,20]}]}]
    observe.associate(rows);assert rows[1]['faces'][0]['association']=='ambiguous_new_track';assert rows[2]['faces'][0]['track_id']!=rows[1]['faces'][0]['track_id'];assert all(f.get('confidence') is None for r in rows for f in r['faces'])

def test_overlap_offscreen_and_no_face_have_explicit_speaker_fallbacks():
    people=[{'id':'face-a','visibility':1.},{'id':'face-b','visibility':1.}];settings=c.controls(controls(),5.)
    words=[{'start':0,'end':2,'speaker_id':'S1'},{'start':1,'end':3,'speaker_id':'S2'}];result=plan.speaker(people,words,0,3,{'status':'unavailable'},settings)
    assert result['selected'] is None and result['reason']=='overlapping_voices_preserve_grid'
    settings['speaker_links']=[{'speaker_id':'S1','track_id':'absent','reviewed':True}];result=plan.speaker(people,words[:1],0,2,{},settings);assert result['selected'] is None and 'offscreen' in result['reason'];assert plan.speaker([],[],0,2,{},settings)['reason']=='no_face_or_detector_unavailable'

def test_diarization_is_not_visual_identity_without_reviewed_link():
    settings=c.controls(controls(),4.);people=[{'id':'face-a','visibility':1.}];words=[{'start':0,'end':2,'speaker_id':'S1'}]
    assert plan.speaker(people,words,0,2,{},settings)['selected'] is None
    settings['speaker_links']=[{'speaker_id':'S1','track_id':'face-a','reviewed':True}];assert plan.speaker(people,words,0,2,{},settings)['reason']=='human_reviewed_voice_face_link'

@pytest.mark.parametrize('size',[(360,640),(640,360),(400,400),(400,500),(720,480)])
def test_grid_three_subjects_and_platform_safe_caption_geometry(size):
    settings=c.controls(controls(layout='grid'),4.);segment={'source_size':[1280,720],'layout':'grid','subjects':[{'id':str(i),'box':[i*350,100,80,80],'observations':[]} for i in range(3)],'material':None,'speaker':{'selected':None},'protected_source':[],'safe_margins':settings['safe_margins']}
    result=plan.layers(segment,*size,settings);W,H=size;assert len(result['layers'])==3
    for row in result['layers']:
        x,y,w,h=row['viewport'];assert 0<=x<x+w<=W and 0<=y<y+h<=H
    x,y,w,h=result['caption_panel'];assert y+h<=H*(1-settings['safe_margins'][3])+1

def test_same_speaker_words_do_not_split_every_word_into_camera_shots():
    observation={'source_size':[320,180],'shots':[{'shot_id':'s','start':0,'end':10}],'frames':[]};words=[{'start':i*.1,'end':i*.1+.08,'speaker_id':'S1'} for i in range(90)]
    assert len(plan.build(observation,c.controls(controls(),10.),words,{}))==1


def test_odd_material_pixels_are_expanded_outward_instead_of_cut():
    settings=c.controls(controls(layout='screen'),4.);segment={'source_size':[1280,720],'layout':'screen','subjects':[],'material':[1,1,901,719],'speaker':{'selected':None},'protected_source':[{'kind':'material','box':[1,1,901,719]}],'safe_margins':settings['safe_margins']}
    result=plan.layers(segment,640,360,settings);region=result['layers'][0]['source_crop'];assert c.intersection(region,segment['material'])==segment['material']
