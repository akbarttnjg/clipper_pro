import copy,json,math
from pathlib import Path
from dataclasses import replace
import pytest
from ..config import Config
from .. import finishing5_contract as c
from ..finishing5_plan import caption_plan,check,bilingual
from ..typography import make_plan
def cfg(**kw):return Config(target_w=640,target_h=360,finishing5={'enabled':True,'style':{}},**kw)
def words(value='Biaya tidak naik 5 persen jadi simpan bukti'):
    return [dict(word_id=i,word=t,start=.1+i*.4,end=.1+(i+1)*.4,speaker_id='S1') for i,t in enumerate(value.split())]
@pytest.mark.parametrize('value',[None,[],{'unknown':1},{'karaoke':'false'},{'emoji':1},{'motion_budget':float('nan')},{'glow_px':13},{'stroke_px':-1},{'display_width_px':360.5},{'font_main':'missing'},{'minimum_glyph_px':13},{'base_hex':'red'},{'fallback_fonts':['']},{'censor_terms':'x'},{'manual_panel':[90,0,30,10]},{'builder':{'id':'x','name':'x','motion':'eval'}},{'speaker_styles':[{'speaker_id':'S1','label':'A','color':'#FFFFFF','approved':False}]},{'source_captions':[{'rect':[0,0,10,10],'start':2,'end':1,'approved':True}]}])
def test_invalid_fields_rejected_without_mutating_input(value):
    old=copy.deepcopy(value)
    with pytest.raises((ValueError,TypeError)):c.style(value)
    if not isinstance(value,dict) or not any(isinstance(v,float) and math.isnan(v) for v in value.values()):assert value==old
@pytest.mark.parametrize('W,H',[(360,640),(640,360),(1080,1920),(1920,1080)])
@pytest.mark.parametrize('template',[r['id'] for r in c.TEMPLATES])
def test_final_ink_all_templates_both_ratios_and_full_HD(W,H,template):
    config=replace(cfg(),target_w=W,target_h=H,caption_template_policy='manual',finishing5={'enabled':True,'style':{'template_id':template}});w=words();before=copy.deepcopy(w);p=caption_plan(w,config)
    assert p['m5_checks']['passed'];assert w==before;assert all(min(r['minimum_glyph_px'] for r in ph['clear_time_metrics'])>=14 for ph in p['m5_checks']['phrase_rows'])
    assert all(t['original_text'] for ph in p['phrases'] for t in ph['words'])
    owner=[(p['phrase_id'],w['original_text']) for p in p['phrases'] for w in p['words'] if w['original_text'].startswith('tidak')]
    assert len({r[0] for r in owner})==1;assert all('tidak naik 5 persen' in t for _,t in owner)
@pytest.mark.parametrize('position',['left','right','bottom'])
def test_manual_anchor_all_motion_extrema(position):
    config=cfg(caption_position=position,caption_align=position if position!='bottom' else 'center',motion_intensity='dynamic');p=caption_plan(words('Simpan bukti transaksi'),config)
    assert all(r['position']==position for r in p['phrases']);assert check(p,config,words('Simpan bukti transaksi'))['passed']
@pytest.mark.parametrize('style',['clean','editorial','narrative','pop','blur','impact'])
def test_emphasis_off_legacy_paths_and_M5(style):
    config=Config(target_w=640,target_h=360,semantic_emphasis=False,caption_style=style)
    p=make_plan(words('risiko biaya usaha'),config,['biaya']);assert not any(w['emphasis'] for p in p['phrases'] for w in p['words'])
    p=make_plan(words('risiko biaya usaha'),replace(config,finishing5={'enabled':True,'style':{}}),['biaya']);assert p['cues']['emphasis']==0
def test_every_optional_toggle_off_produces_no_related_cue():
    s={**c.DEFAULTS,'emoji_map':[{'keyword':'biaya','icon':'★'}],'speaker_styles':[{'speaker_id':'S1','label':'Akbar','color':'#00FF00','approved':True}],'censor_terms':['biaya']}
    p=caption_plan(words(),replace(cfg(),semantic_emphasis=False,finishing5={'enabled':True,'style':s}))
    assert p['cues']==dict(emphasis=0,karaoke=0,emoji=0,speaker_color=False,speaker_labels=False,censor=0);assert not p['censor_intervals']
def test_emoji_and_speaker_approval_use_explicit_identity():
    s={'emoji':True,'emoji_map':[{'keyword':'Biaya','icon':'★'}],'speaker_color':True,'speaker_labels':True,'speaker_styles':[{'speaker_id':'S1','label':'Akbar','color':'#00FF00','approved':True}]}
    p=caption_plan(words('Biaya usaha'),replace(cfg(),finishing5={'enabled':True,'style':s}))
    assert p['cues']['emoji']==1;assert any(w['text']=='Akbar:' for r in p['phrases'] for w in r['words']);assert any(w['color']=='#00FF00' for r in p['phrases'] for w in r['words'])
def test_missing_glyph_does_not_silently_use_tofu():
    with pytest.raises(ValueError,match='Glyph'):caption_plan(words('biaya \U0010ffff'),cfg())
def test_censor_requires_review_and_keeps_raw_words_and_ids():
    w=words('catat biaya');s={'censor_mode':'bleep_mask','censor_terms':['biaya']};config=replace(cfg(),finishing5={'enabled':True,'style':s})
    with pytest.raises(ValueError,match='setujui'):caption_plan(w,config)
    s['censor_approved']=True;p=caption_plan(w,config);assert p['censor_intervals'];assert w[-1]['word']=='biaya';assert check(p,config,w)['passed']
def test_clear_hold_intermittent_fixture_cannot_pass():
    p=caption_plan(words('catat biaya'),cfg());w=p['phrases'][0]['words'][0]
    for k in w['keyframes']:k['opacity']=1. if k['frame']%4==0 else .1
    with pytest.raises(ValueError,match='Hold'):check(p,cfg())
def test_protected_geometry_precedes_size_and_manual_choice():
    config=replace(cfg(),finishing5={'enabled':True,'style':{'manual_panel':[5,10,80,70]}})
    with pytest.raises(ValueError,match='materi'):caption_plan(words('catat biaya'),config,anchors=[{'start':0,'end':9,'protected':[{'kind':'material','box':[0,0,640,360]}]}])
def test_builder_round_trip_preserves_schema_and_policy():
    v={'builder':{'id':'brand','name':'Brand','motion':'rise','accent_ratio':1.12,'max_rows':2,'line_gap':.3,'roles':['narration']},'template_id':'custom'};s=c.style(v);assert c.style(json.loads(json.dumps(s)))==s
    p=caption_plan(words('catat biaya'),replace(cfg(),finishing5={'enabled':True,'style':s}));assert p['phrases'][0]['design']['template']=='brand'
def test_bilingual_bands_cover_both_tracks_and_do_not_overlap():
    config=replace(cfg(),target_w=360,target_h=640);src=words('catat biaya');translated=words('record cost');p=bilingual(src,translated,config)
    a=p['source_plan']['phrases'][0]['panel'];b=p['translation_plan']['phrases'][0]['panel'];assert a[1]+a[3]<=b[1]+.01
    assert check(p['source_plan'],config,src)['passed'];assert check(p['translation_plan'],config,translated)['passed']
