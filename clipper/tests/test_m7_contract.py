"""Adversarial M7 choices, sidecar fidelity and independent exchange readbacks."""
import copy,json,math
from pathlib import Path
import pytest
from clipper.delivery7_contract import options,capabilities
from clipper.delivery7_sidecars import write,validate
from clipper.delivery7_exchange import write as exchange,readback

@pytest.mark.parametrize('value',[
 {'auto_upload':True},{'ratios':[]},{'ratios':['portrait','portrait']},{'ratios':['unknown_ratio']},{'ratios':'portrait'},
 {'editors':['aftereffects']},{'editors':['capcut','capcut']},{'alpha':1},{'profile':[]},{'profile':'nvenc_unmeasured'},
 {'mode':'magic'},{'mode':'preserved'},{'merged':'false'},['bad']])
def test_invalid_or_ambiguous_delivery_choices_block(value):
    with pytest.raises(ValueError):options(value)

def test_choices_are_isolated_and_no_native_acceptance_is_implied():
    first=options();first['editors'].clear();assert options()['editors']
    matrix={r['editor']:r for r in capabilities({},'hybrid')}
    assert matrix['capcut']['target_version']=='4.7.0' and matrix['resolve']['target_version']=='18.6.6'
    assert matrix['resolve']['layers']['caption_font_style']=='backlog'
    for e in ('premiere','finalcut','otio'):assert matrix[e]['layers']['caption_text_timing']=='baked'
    assert all(r['native_acceptance']=='not_tested' for r in matrix.values())

@pytest.fixture
def caption_plan(tmp_path):
    ass=tmp_path/'master.ass';ass.write_text('[Script Info]\n[Events]\nDialogue: 0,0:00:00.10,0:00:00.80,Default,,0,0,0,,tidak 5 persen\n')
    return {'revision':7,'duration':1.,'language':'id','display_language':'en','publication':{'requested_revision':15},'subtitle_path':str(ass),
        'captions':{'phrases':[{'start':.100123,'end':.800456,'words':[{'text':'tidak','start':.1,'end':.4},{'text':'5 < 8 & aman','start':.4,'end':.8}]}]}}

def test_all_sidecars_share_revision_text_language_and_millisecond_bounds(tmp_path,caption_plan):
    folder=tmp_path/'sidecars';write(caption_plan,folder,reference={'output_content_id':'sha256:reviewed'})
    result=validate(folder,caption_plan);assert result['passed'] and len(result['formats'])==5
    value=json.loads((folder/'transcript.json').read_text());assert value['language']=='en' and value['source_language']=='id'
    assert value['publication']['requested_revision']==15 and value['reference']['output_content_id']=='sha256:reviewed'
    assert value['cues'][0]['text']=='tidak 5 < 8 & aman'
    assert '00:00:00,100 --> 00:00:00,800' in (folder/'captions.srt').read_text(encoding='utf-8-sig')

@pytest.mark.parametrize('bounds',[(0,2),(math.nan,1),(.8,.2),(-.1,.2)])
def test_out_of_bounds_or_nonfinite_subtitles_cannot_publish(tmp_path,caption_plan,bounds):
    caption_plan['captions']['phrases'][0].update(start=bounds[0],end=bounds[1])
    with pytest.raises(ValueError):write(caption_plan,tmp_path/'sidecars')

@pytest.mark.parametrize('name',['captions.srt','captions.vtt','transcript.json','transcript.txt'])
def test_changed_subtitle_is_rejected(tmp_path,caption_plan,name):
    folder=tmp_path/'sidecars';write(caption_plan,folder);p=folder/name
    if name.endswith('json'):
        data=json.loads(p.read_text());data['revision']=8;p.write_text(json.dumps(data))
    else:p.write_text(p.read_text(encoding='utf-8-sig').replace('tidak','ya'))
    with pytest.raises(ValueError):validate(folder,caption_plan)

@pytest.mark.parametrize('fps',[25,30,60,30000/1001])
def test_multiclip_exchange_roundtrip_preserves_order_frames_and_references(tmp_path,fps):
    rows=[]
    for i,n in enumerate([1,109,1001]):
        media=tmp_path/f'clip {i}.mp4';media.write_bytes(b'authored structural fixture')
        rows.append({'key':str(i),'title':'Judul <'+str(i)+'>','frames':n,'fps':fps,'width':1920,'height':1080,'path':str(media),'local_path':str(media)})
    target=tmp_path/'Exchange';report=exchange(rows,target,'Gabungan',('premiere','finalcut','otio'))
    assert len(report)==3
    for path in target.iterdir():
        back=readback(path);assert [r['frames'] for r in back]==[1,109,1001];assert [r['key'] for r in back]==['0','1','2']
        assert all(r['path'] for r in back)
    data=json.loads((target/'timeline.otio').read_text());refs=[c['media_references']['DEFAULT_MEDIA']['target_url'] for c in data['tracks']['children'][0]['children']]
    assert all(not Path(p).is_absolute() and (target/p).resolve().is_file() for p in refs)
    assert all(r['native_status']=='not_tested' for r in report.values())


@pytest.mark.parametrize('mode',['translation','bilingual'])
def test_translation_and_bilingual_sidecars_keep_source_and_display_language(tmp_path,caption_plan,mode):
    from types import SimpleNamespace
    from clipper.delivery7_sidecars import capture_language
    p=copy.deepcopy(caption_plan);p['captions']['bilingual']=mode=='bilingual'
    if mode=='bilingual':p['captions']['phrases']=[{**p['captions']['phrases'][0],'language_track':'source'},
        {**copy.deepcopy(p['captions']['phrases'][0]),'language_track':'translation'}]
    capture_language(p,{'_source_language':'id','_display_language':'en','_display_mode':mode},SimpleNamespace(language='auto'))
    folder=tmp_path/mode;write(p,folder);data=json.loads((folder/'transcript.json').read_text())
    assert data['source_language']=='id' and data['display_mode']==mode
    assert data['languages']==(['id','en'] if mode=='bilingual' else ['en'])
    assert data['language']==('mul' if mode=='bilingual' else 'en')
    assert [r['language'] for r in data['cues']]==(['id','en'] if mode=='bilingual' else ['en'])
