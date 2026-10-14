import copy,json,zipfile
from pathlib import Path
import pytest
from PIL import Image
from ._m4_fixture import make_studio,change
from ..finishing5_service import assets,snapshot,map_time,map_layers
from ..finishing5_assets import sha,choose_font
from ..project_store import Conflict
from .. import editor_contract as ec
@pytest.fixture
def svc(tmp_path):return make_studio(tmp_path)
def doc(s):return s.store.get(s.test_pid)
def variant(s):return s.variant(doc(s),s.test_cid,'portrait')
def config(s):return s.config(doc(s),s.test_cid,'portrait')
def test_single_color_creates_one_override_and_keeps_other_ratio(svc):
    before=config(svc);change(svc,{'op':'m5_style','values':{'base_hex':'#F0F0F0'}})
    v=variant(svc);after=config(svc);assert v['override_keys']==['base_hex'];assert v['settings']=={'base_hex':'#F0F0F0'}
    assert (before.font_main,before.motion_intensity)==(after.font_main,after.motion_intensity)
    assert not svc.config(doc(svc),svc.test_cid,'landscape').finishing5
def test_preset_inherits_and_reset_returns_to_brand(svc):
    change(svc,{'op':'m5_preset','preset_id':'editorial'});change(svc,{'op':'m5_style','values':{'base_hex':'#F0F0F0'}})
    kit=assets(svc).save_kit({'name':'Brand','style':{'base_hex':'#CCCCCC','font_main':'montserrat','caption_template_policy':'manual'}})
    change(svc,{'op':'m5_kit','kit_id':kit['id'],'kit_revision':0});assert config(svc).base_hex=='#F0F0F0';assert config(svc).font_main=='montserrat'
    change(svc,{'op':'m5_reset','keys':['base_hex']});assert config(svc).base_hex=='#CCCCCC';assert snapshot(svc,svc.test_pid,svc.test_cid,'portrait')['origins']['base_hex']=='brand'
def test_preset_diff_is_readonly_and_undo_restores_all_values(svc):
    before=doc(svc);req={'project_id':svc.test_pid,'clip_id':svc.test_cid,'variant_id':'portrait','expected_revision':before['revision'],'operation_id':'diff-m5-test','operations':[{'op':'m5_preset','preset_id':'social'}]}
    response=svc.changes(req,preview_only=True);assert response['status']=='preview';assert doc(svc)==before
    svc.changes({**req,'operation_id':'apply-m5-test'});d=doc(svc);svc.store.undo(svc.test_pid,d['revision'],'undo-m5-test',d['revision']);assert svc.variant(doc(svc),svc.test_cid,'portrait').get('finishing5') is None
def test_stale_config_invalid_font_and_locked_track_cannot_mutate(svc):
    before=doc(svc)
    with pytest.raises(ValueError):change(svc,{'op':'m5_style','values':{'font_main':'font-missing'}})
    assert doc(svc)==before
    change(svc,{'op':'m5_enable','enabled':True})
    with pytest.raises(Conflict):change(svc,{'op':'m5_enable','enabled':False},revision=before['revision'])
    d=doc(svc)
    def lock(v):v['clips'][svc.test_cid]['variants']['portrait'].setdefault('editor',{})['tracks']={'captions':{'locked':True}}
    svc.store.mutate(svc.test_pid,d['revision'],'lock-m5-test',{},lock)
    with pytest.raises(ValueError,match='terkunci'):change(svc,{'op':'m5_style','values':{'base_hex':'#ABCDEF'}})
def test_invalid_batched_layer_rolls_back_style(svc):
    before=doc(svc);req={'project_id':svc.test_pid,'clip_id':svc.test_cid,'variant_id':'portrait','expected_revision':before['revision'],'operation_id':'invalid-batch','operations':[{'op':'m5_style','values':{'base_hex':'#ABCDEF'}},{'op':'m5_layers','values':[{'id':'bad','kind':'logo','start':0,'end':3,'rect':[0,0,10,10],'asset_id':'missing'}]}]}
    with pytest.raises(ValueError):svc.changes(req)
    assert doc(svc)==before
def test_style_changes_render_dependency_but_not_ASR_or_M4(svc):
    from ..camera4_service import signature
    d=doc(svc);render=svc.dependency(d,svc.test_cid,'portrait');asr=svc.dependency(d,kind='analyze');camera=signature(svc,d,svc.test_cid,'portrait')
    change(svc,{'op':'m5_style','values':{'base_hex':'#ABCDEF'}});d=doc(svc)
    assert svc.dependency(d,svc.test_cid,'portrait')!=render;assert svc.dependency(d,kind='analyze')==asr;assert signature(svc,d,svc.test_cid,'portrait')==camera
def test_asset_search_records_rights_and_tampering_blocks(svc,tmp_path):
    p=tmp_path/'logo.png';Image.new('RGBA',(20,20),'red').save(p);a=assets(svc);r=a.register(p,{'name':'Logo Akbar','permission':'user_owned','license':'original','tags':['education'],'collections':['Brand'],'object':'logo','text':'Akbar'})
    assert a.list('akbar education','Brand')[0]['id']==r['id'];assert a.register(p,{'permission':'unknown'})==r
    Image.new('RGBA',(20,20),'blue').save(r['path'])
    with pytest.raises(ValueError,match='berubah'):a.get(r['id'])
def test_real_custom_font_cmap_metadata_and_folder_used(svc):
    p=Path(config(svc).fonts_dir)/'DejaVuSans.ttf';r=assets(svc).register(p,{'permission':'licensed','license':'DejaVu font license','name':'Regular custom'})
    change(svc,{'op':'m5_style','values':{'font_main':r['id'],'font_accent':r['id']}});cfg=config(svc);f=choose_font(cfg.fonts_dir,r['id'],[],'Biaya 5 persen')
    assert f['sha256']==sha(p);assert f['family']=='DejaVu Sans';assert f['weight']==400;assert f['source']=='local_import'
    from ..editor_service import render_summary
    r=render_summary(svc,doc(svc),[{'clip_id':svc.test_cid,'variant_id':'portrait'}]);assert r['targets'][0]['fonts']['font_main']['installed']
def test_unknown_font_license_cannot_enter_render(svc):
    r=assets(svc).register(Path(config(svc).fonts_dir)/'DejaVuSans.ttf',{'permission':'unknown'})
    with pytest.raises(ValueError,match='izin'):change(svc,{'op':'m5_style','values':{'font_main':r['id']}})
def test_versioned_brand_roundtrip_subbrands_on_other_installation(svc,tmp_path):
    a=assets(svc);p=tmp_path/'logo.png';Image.new('RGBA',(20,20),'red').save(p);r=a.register(p,{'permission':'user_owned','origin':'drawn by user','license':'owned','attribution':'Akbar'})
    parent=a.save_kit({'name':'Parent','style':{'base_hex':'#DDDDDD','caption_template_policy':'manual'}})
    kit=a.save_kit({'name':'Sub-brand','parent_id':parent['id'],'style':{'font_main':'dm_sans','template_id':'focus','stroke_px':3.,'caption_template_policy':'manual'},'asset_ids':[r['id']],'glossary':[{'heard':'Akbr','preferred':'Akbar'}]})
    target=tmp_path/'kit.zip';a.export(kit['id'],target)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None;meta=json.loads(z.read('manifest.json'));assert 'path' not in meta['assets'][0];assert meta['assets'][0]['sha256']==r['sha256']
    (tmp_path/'other').mkdir();other=make_studio(tmp_path/'other');new=assets(other).import_pack(target)
    assert new['style']==kit['style'];assert new['asset_digests']==kit['asset_digests'];assert assets(other).kit(new['parent_id'])['name']=='Parent';assert new['glossary']==kit['glossary']
    updated=a.save_kit({**{k:kit[k] for k in ('id','name','style','layers','asset_ids','glossary','parent_id')},'expected_revision':0});assert updated['revision']==1
    with pytest.raises(Conflict):a.save_kit({'id':kit['id'],'name':'Stale','style':{},'expected_revision':0})
    with pytest.raises(ValueError,match='Kit berubah'):change(svc,{'op':'m5_kit','kit_id':kit['id'],'kit_revision':0})
@pytest.mark.parametrize('kind',['traversal','symlink','extra','tamper'])
def test_portable_pack_rejects_unsafe_files(svc,tmp_path,kind):
    a=assets(svc);p=tmp_path/'l.png';Image.new('RGBA',(10,10),'red').save(p);r=a.register(p,{'permission':'user_owned'});kit=a.save_kit({'name':'Test','asset_ids':[r['id']]});good=tmp_path/'kit.zip';a.export(kit['id'],good);bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(good) as src,zipfile.ZipFile(bad,'w') as z:
        for n in src.namelist():z.writestr(n,src.read(n)+(b'bad' if kind=='tamper' and n.startswith('assets/') else b''))
        if kind in ('traversal','extra'):z.writestr('../escape' if kind=='traversal' else 'extra.txt',b'bad')
        if kind=='symlink':i=zipfile.ZipInfo('assets/link');i.external_attr=(0o120777<<16);z.writestr(i,b'/private')
    with pytest.raises(ValueError):a.import_pack(bad)
    assert not (tmp_path/'escape').exists()
def test_brand_glossary_cannot_change_numbers_or_negations(svc):
    for before,after in [('5 persen','6 persen'),('tidak aman','aman')]:
        with pytest.raises(ValueError):assets(svc).save_kit({'name':'Invalid','glossary':[{'heard':before,'preferred':after}]})
def test_source_clock_reorder_reverse_freeze_repeat():
    rows=ec.validate_segments([{'id':'b','start':2,'end':4,'reverse':True},{'id':'f','start':.5,'end':.6,'kind':'freeze','freeze_duration':1},{'id':'a','start':0,'end':2},{'id':'again','start':0,'end':1}],{'start':0,'end':4});clock=ec.build_clock(rows,30)
    p={'duration':clock['duration'],'fps':30,'editor':{'clock':clock},'spans':[]};windows=map_time(p,.4,1.)
    assert any(a<=2 and b>=3 for a,b in windows);assert len(windows)>=3
def test_layers_budget_protection_and_diagram_quote(svc):
    change(svc,{'op':'m5_enable','enabled':True});cfg=config(svc);cfg.finishing5['decorations']=[{'id':'card','kind':'diagram','start':0,'end':2,'rect':[10,10,30,20],'opacity':1.,'items':['biaya','bukti'],'quote':'biaya bukti'}]
    p={'duration':4,'fps':30,'width':640,'height':360,'spans':[{'start':0,'end':4,'source_start':0,'source_end':4}],'shots':[{'start':0,'end':4,'protected_output':[]}],'display_words':[{'word':'biaya bukti'}]};map_layers(p,cfg);assert p['finishing5']['extra_seconds']==0
    p['shots'][0]['protected_output']=[{'kind':'material','box':[0,0,640,360]}]
    with pytest.raises(ValueError,match='menutupi'):map_layers(p,cfg)
def test_gallery_queued_after_save_with_bounded_options(svc):
    d=doc(svc)
    with pytest.raises(ValueError,match='Aktifkan'):svc.enqueue(svc.test_pid,'gallery_m5',svc.test_cid,'portrait',d['revision'])
    change(svc,{'op':'m5_enable','enabled':True});d=doc(svc);j=svc.enqueue(svc.test_pid,'gallery_m5',svc.test_cid,'portrait',d['revision'],{'templates':['editorial'],'seconds':2});assert j['status']=='queued'
    with pytest.raises(ValueError):svc.enqueue(svc.test_pid,'gallery_m5',svc.test_cid,'portrait',d['revision'],{'templates':['eval']})



def test_asset_permission_update_is_versioned_and_does_not_mutate_bytes(svc):
    a=assets(svc);p=Path(config(svc).fonts_dir)/'DejaVuSans.ttf';r=a.register(p,{'permission':'unknown'})
    new=a.update_metadata(r['id'],0,{'permission':'licensed','license':'DejaVu license'})
    assert new['sha256']==r['sha256'];assert new['metadata_revision']==1
    with pytest.raises(Conflict):a.update_metadata(r['id'],0,{'permission':'user_owned'})
    change(svc,{'op':'m5_style','values':{'font_main':r['id']}});assert config(svc).font_main==r['id']

def test_diagram_numeric_substring_is_not_evidence_for_a_different_number(svc):
    change(svc,{'op':'m5_enable','enabled':True});cfg=config(svc);cfg.finishing5['decorations']=[{'id':'d','kind':'diagram','start':0,'end':2,'rect':[5,5,30,20],'opacity':1.,'items':['biaya'],'quote':'biaya 15 persen','values':[5]}]
    p={'duration':4,'fps':30,'width':640,'height':360,'spans':[{'start':0,'end':4,'source_start':0,'source_end':4}],'shots':[],'display_words':[{'word':'biaya 15 persen'}]}
    with pytest.raises(ValueError,match='Angka'):map_layers(p,cfg)

def test_subbrand_pins_parent_revision_and_batch_apply_keeps_manual_fields(svc):
    a=assets(svc);parent=a.save_kit({'name':'Parent','style':{'base_hex':'#DDDDDD','font_main':'montserrat'}})
    child=a.save_kit({'name':'Child','parent_id':parent['id'],'style':{'accent_hex':'#FFDD88'}})
    a.save_kit({'id':parent['id'],'expected_revision':0,'name':'Parent','style':{'base_hex':'#EEEEEE','font_main':'dm_sans'}})
    assert child['parent_revision']==0 and child['effective_style']['base_hex']=='#DDDDDD'
    change(svc,{'op':'m5_style','values':{'base_hex':'#AAAAAA'}})
    change(svc,{'op':'m5_kit','kit_id':child['id'],'kit_revision':0,'scope':'project'})
    d=doc(svc);assert svc.config(d,svc.test_cid,'portrait').base_hex=='#AAAAAA'
    assert svc.config(d,svc.test_cid,'landscape').base_hex=='#DDDDDD'
    assert svc.config(d,svc.test_cid,'landscape').font_main=='montserrat'
def test_portable_subbrand_preserves_old_parent_when_parent_has_newer_revision(svc,tmp_path):
    a=assets(svc);p=a.save_kit({'name':'P','style':{'base_hex':'#CCCCCC'}});c=a.save_kit({'name':'C','parent_id':p['id'],'style':{'accent_hex':'#FFDD88'}})
    a.save_kit({'id':p['id'],'expected_revision':0,'name':'P','style':{'base_hex':'#AAAAAA'}});z=tmp_path/'pinned.zip';a.export(c['id'],z)
    (tmp_path/'other').mkdir();other=make_studio(tmp_path/'other');new=assets(other).import_pack(z)
    assert new['effective_style']==c['effective_style'];assert new['effective_style']['base_hex']=='#CCCCCC'
def test_real_HTTP_M5_diff_and_asset_metadata_routes(svc):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from ..api_studio import create_router
    app=FastAPI();app.include_router(create_router(svc));client=TestClient(app);before=doc(svc)
    response=client.get(f"/api/studio/projects/{svc.test_pid}/finishing5",params={'clip_id':svc.test_cid,'variant_id':'portrait'})
    assert response.status_code==200
    request={'clip_id':svc.test_cid,'variant_id':'portrait','expected_revision':before['revision'],'operation_id':'m5-http-diff','operations':[{'op':'m5_preset','preset_id':'social'}]}
    response=client.post(f"/api/studio/projects/{svc.test_pid}/finishing5/diff",json=request)
    assert response.status_code==200 and response.json()['effective_style']['font_main']=='montserrat';assert doc(svc)==before
    response=client.post('/api/studio/finishing5/assets',json={'path':str(Path(config(svc).fonts_dir)/'DejaVuSans.ttf'),'metadata':{'permission':'unknown'}});assert response.status_code==200;key=response.json()['id']
    response=client.post('/api/studio/finishing5/assets/metadata',json={'asset_id':key,'expected_revision':0,'values':{'permission':'licensed','license':'DejaVu'}});assert response.status_code==200
    response=client.post('/api/studio/finishing5/assets/metadata',json={'asset_id':key,'expected_revision':0,'values':{'permission':'unknown'}});assert response.status_code==409
def test_output_anchor_may_not_clip_a_wide_asset(svc):
    change(svc,{'op':'m5_enable','enabled':True});cfg=config(svc);cfg.finishing5['decorations']=[{'id':'wide','kind':'title','text':'Title','start':0,'end':2,'rect':[0,0,100,5],'opacity':1.,'anchor':'top_right'}]
    p={'duration':4,'fps':30,'width':640,'height':360,'spans':[{'start':0,'end':4,'source_start':0,'source_end':4}],'shots':[],'display_words':[]}
    with pytest.raises(ValueError,match='canvas'):map_layers(p,cfg)

def test_local_ranker_weights_change_M5_cache_identity_without_inference_claim(svc,tmp_path):
    asset=assets(svc).register(doc(svc)['source']['path'],{'permission':'user_owned','name':'Authored stock'})
    change(svc,{'op':'m5_enable','enabled':True})
    change(svc,{'op':'m5_layers','values':[{'id':'b','kind':'video','asset_id':asset['id'],'start':0,'end':1,'rect':[5,5,20,20]}]})
    cfg=config(svc);root=Path(cfg.visual_runtime_root);generation=root/'generations'/'siglip-cache-fixture';(generation/'weights').mkdir(parents=True)
    weight=generation/'weights'/'fixture.bin';weight.write_bytes(b'cache identity bytes v1; not a model')
    active=root/'components/siglip2/active.json';active.parent.mkdir(parents=True);active.write_text(json.dumps({'generation':'siglip-cache-fixture'}))
    before=svc.dependency(doc(svc),svc.test_cid,'portrait',fresh=True);weight.write_bytes(b'cache identity bytes v2; not a model')
    after=svc.dependency(doc(svc),svc.test_cid,'portrait',fresh=True);assert before!=after




@pytest.mark.parametrize('mode',['cover','reconstruct'])
def test_hybrid_cannot_drop_M5_source_caption_cover(tmp_path,mode):
    from ..workflow6 import export_options
    p=tmp_path/'plan.json';p.write_text(json.dumps({'finishing5':{'style':{'source_caption_mode':mode,'source_captions':[{'rect':[5,70,80,10]}]}},'captions':{}}))
    rows=export_options({'result':{'plan_path':str(p)}})
    assert not next(r for r in rows if r['id']=='hybrid')['available']
    assert next(r for r in rows if r['id']=='preserved')['available']

def test_M1_illustration_mute_and_solo_disable_M5_layers_without_deleting_them(svc,tmp_path):
    image=tmp_path/'logo.png';Image.new('RGBA',(10,10),'white').save(image)
    a=assets(svc).register(image,{'permission':'user_owned'});change(svc,{'op':'m5_enable','enabled':True})
    change(svc,{'op':'m5_layers','values':[{'id':'logo','kind':'logo','asset_id':a['id'],'start':0,'end':1,'rect':[5,5,10,10]}]})
    before=svc.dependency(doc(svc),svc.test_cid,'portrait')
    change(svc,{'op':'track','track':'illustration','values':{'mute':True}})
    assert not config(svc).finishing5['decorations'];assert variant(svc)['finishing5']['decorations']
    assert svc.dependency(doc(svc),svc.test_cid,'portrait')!=before
    change(svc,{'op':'track','track':'illustration','values':{'mute':False}})
    assert config(svc).finishing5['decorations'][0]['id']=='logo'
    change(svc,{'op':'track','track':'voice','values':{'solo':True}})
    assert not config(svc).finishing5['decorations']

def test_disabling_M5_after_custom_font_and_raster_keeps_legacy_renderable(svc):
    from ..typography import make_plan
    before=config(svc)
    asset=assets(svc).register(Path(before.fonts_dir)/'DejaVuSans.ttf',{'permission':'licensed','license':'DejaVu'})
    change(svc,{'op':'m5_style','values':{'font_main':asset['id'],'font_accent':asset['id'],'caption_renderer':'raster'}})
    change(svc,{'op':'m5_enable','enabled':False});off=config(svc)
    assert off.finishing5 is None;assert off.font_main==before.font_main;assert off.font_accent==before.font_accent;assert off.caption_renderer==before.caption_renderer
    assert make_plan([{'word_id':0,'word':'biaya','start':0.,'end':1.}],off)['phrases']
    change(svc,{'op':'m5_enable','enabled':True});on=config(svc)
    assert on.font_main==asset['id'] and on.caption_renderer=='raster'
