"""Regression tests for the reported manual-position and title-banner failures."""
from dataclasses import replace
from collections import defaultdict
import copy
import json
import pytest
from clipper.config import Config, validate_overrides
from clipper.typography import make_plan
from clipper.captions_pro import write_ass
from clipper.looks import LOOKS, VISUAL_FIELDS
from clipper.qc import inspect_caption_plan


def words():
    return [{'word':t,'start':i*.4,'end':i*.4+.36,'word_id':i}
            for i,t in enumerate('biar lu bisa nge stack skill'.split())]


@pytest.mark.parametrize('style', ['slide', 'narrative', 'clean'])
@pytest.mark.parametrize('position', ['left', 'right', 'bottom'])
@pytest.mark.parametrize('align', ['left', 'right', 'center', 'auto'])
def test_manual_position_and_line_edges_win_over_conflicting_anchor(style,position,align):
    cfg=Config(target_w=1920,target_h=1080,caption_position=position,caption_align=align,
               safe_placement=True,caption_style=style)
    anchor={'time':5,'start':0,'end':10,'position':'bottom','panel':[200,800,1400,220]}
    plan=make_plan(words(),cfg,keywords=['skill'],anchors=[anchor])
    desired=align if align!='auto' else position if position!='bottom' else 'center'
    for p in plan['phrases']:
        assert p['position']==position and p['placement_source']=='manual'
        assert p['panel']!=anchor['panel']
        lines=defaultdict(list)
        for w in p['words']:lines[w['baseline']].append(w)
        edges=[]
        for line in lines.values():
            left=min(w['x']-w['width']/2 for w in line)
            right=max(w['x']+w['width']/2 for w in line)
            edges.append(left if desired=='left' else right if desired=='right' else (left+right)/2)
        assert max(edges)-min(edges)<.02
    assert inspect_caption_plan(plan,cfg)['passed']


@pytest.mark.parametrize('align',['left','right','center'])
def test_portrait_bottom_can_align_independently(align):
    cfg=Config(caption_position='bottom',caption_align=align)
    plan=make_plan(words(),cfg,keywords=['skill'])
    assert inspect_caption_plan(plan,cfg)['passed']
    assert all(p['alignment']==align for p in plan['phrases'])


def test_old_title_flag_cannot_restore_banner(tmp_path):
    cfg=Config(title_card=True)
    path=tmp_path/'test.ass'
    write_ass(words(),path,cfg,hook='HAPUS JUDUL PEMBUKA INI',keywords=['skill'])
    assert 'HAPUS JUDUL' not in path.read_text()
    assert 'Dialogue: 1,' not in path.read_text()
    plan=json.loads(path.with_suffix('.caption-plan.json').read_text())
    assert 'title' not in plan and plan['phrases']
    assert 'title_card' not in validate_overrides({'title_card':'1'})


def test_styles_cannot_change_geometry_and_bad_alignment_is_dropped():
    assert not {'caption_align','caption_position','safe_placement'} & VISUAL_FIELDS
    for p in LOOKS:
        assert not {'caption_align','caption_position','safe_placement'} & p['settings'].keys()
    assert validate_overrides({'caption_align':'right'})['caption_align']=='right'
    assert 'caption_align' not in validate_overrides({'caption_align':'invalid'})


def test_layout_check_detects_old_override_and_misaligned_line():
    cfg=Config(target_w=1920,target_h=1080,caption_position='left',caption_align='left')
    p=make_plan(words(),cfg,keywords=['skill'])
    wrong=copy.deepcopy(p);wrong['phrases'][0]['position']='bottom'
    with pytest.raises(ValueError,match='pilihan manual'):inspect_caption_plan(wrong,cfg)
    wrong=copy.deepcopy(p);wrong['phrases'][0]['words'][0]['x']+=15
    with pytest.raises(ValueError,match='sejajar'):inspect_caption_plan(wrong,cfg)


def test_old_session_and_preset_keep_position_without_banner(tmp_path,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app,'STATES',tmp_path/'sessions')
    monkeypatch.setattr(app,'PRESETS_FILE',tmp_path/'presets.json')
    cfg=Config(work_dir=str(tmp_path),caption_position='right',title_card=True)
    st={'cfg':cfg,'media':'example.mp4','transcript':{'words':words(),'duration':20},
        'scored':[{'start':0,'end':10,'title':'Nama clip','revision':0}],
        'edits':{},'clip_settings':{'0':{'title_card':True,'caption_position':'left'}}}
    monkeypatch.setattr(app,'JOBS',{'placement':{'status':'review','clips':[]}})
    monkeypatch.setattr(app,'JOB_STATE',{'placement':st})
    app.persist('placement');app.JOB_STATE.clear();app.JOBS.clear();app.restore()
    restored=app.JOB_STATE['placement']
    assert not restored['cfg'].title_card
    assert not restored['clip_settings']['0']['title_card']
    client=TestClient(app.app)
    data=client.get('/api/editor/placement/0').json()
    assert data['settings']['caption_align']=='auto' and data['settings']['caption_position']=='left'
    oldpreset={'id':'old','name':'Gaya saya','settings':{**LOOKS[0]['settings'],'safe_placement':True}}
    app.PRESETS_FILE.write_text(json.dumps([oldpreset]))
    assert 'safe_placement' not in client.get('/api/style-presets').json()[0]['settings']
