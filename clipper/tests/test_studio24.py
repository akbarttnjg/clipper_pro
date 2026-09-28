"""Regression checks for provider contracts, secrets, timing, material and text integrity."""
import copy
import json
from dataclasses import replace
from pathlib import Path
import pytest
from clipper import stock, illustrations, editplan, typography, subtitle_edit, boundaries, story
from clipper.config import Config, validate_overrides


def words(text):
    return [{'word_id':i,'word':w,'start':i*.5,'end':i*.5+.45,'part':'body'} for i,w in enumerate(text.split())]


@pytest.fixture
def stock_home(tmp_path,monkeypatch):
    monkeypatch.setattr(stock,'SETTINGS',tmp_path/'private.json')
    monkeypatch.setattr(stock,'CACHE',tmp_path/'cache')
    for p in stock.PROVIDERS: monkeypatch.delenv(p.upper()+'_API_KEY',raising=False)
    return tmp_path


def test_provider_shapes_and_quality():
    p=stock.normalize('pexels',{'videos':[{'id':42,'duration':5,'url':'https://www.pexels.com/video/coding-42/',
        'user':{'name':'Filmmaker'},'video_files':[{'file_type':'video/mp4','width':1920,'height':1080,'link':'https://videos.pexels.com/test.mp4'}]}]})
    x=stock.normalize('pixabay',{'hits':[{'id':2,'duration':7,'user':'Creator','pageURL':'https://pixabay.com/videos/2/',
        'tags':'typing, laptop','videos':{'medium':{'width':1280,'height':720,'url':'https://cdn.pixabay.com/test.mp4'}}}]})
    c=stock.normalize('coverr',{'hits':[{'id':'a','duration':6,'title':'Work','max_width':1920,'max_height':1080,
        'urls':{'mp4_download':'https://storage.coverr.co/a/download?token=secret'}}]})
    assert p[0]['author']=='Filmmaker' and x[0]['width']==1280
    assert c[0]['url'].endswith('token=secret') and c[0]['license_url'].startswith('https://coverr.co')
    assert stock.normalize('coverr',{'hits':[{'id':'p','premium':True,'duration':8}]})==[]


def test_search_cache_24h_request_auth_and_no_secret_return(stock_home,monkeypatch):
    stock.save_settings({'pexels':'private-test-key','pixabay':'pix-test','coverr':'cover-test'})
    assert 'private-test-key' not in json.dumps(stock.public_settings())
    assert 'private.json' in (stock_home/'.gitignore').read_text().splitlines()
    calls=[]
    class Response:
        status_code=200
        def json(self): return {'videos':[],'hits':[]}
    def get(url,**kw): calls.append((url,kw));return Response()
    monkeypatch.setattr(stock.requests,'get',get)
    for _ in range(2): stock.search('pexels','typing laptop')
    assert len(calls)==1 and calls[0][0]=='https://api.pexels.com/v1/videos/search'
    assert calls[0][1]['headers']['Authorization']=='private-test-key'
    stock.search('pixabay','office team');stock.search('coverr','office team')
    assert calls[1][1]['params']['key']=='pix-test'
    assert calls[2][1]['headers']['Authorization']=='Bearer cover-test' and calls[2][1]['params']['urls']=='true'


def test_provider_error_sanitized_and_no_paid_retry(stock_home,monkeypatch):
    stock.save_settings({'pixabay':'do-not-log-me'})
    class Response: status_code=429
    monkeypatch.setattr(stock.requests,'get',lambda *a,**k:Response())
    with pytest.raises(ValueError,match='429') as exc: stock.search('pixabay','workers')
    assert 'do-not-log-me' not in str(exc.value)
    for url in ('http://127.0.0.1/secret','https://evil.com/a','https://pexels.com.evil/a'):
        with pytest.raises(ValueError): stock._media_url(url)


def test_local_collection_first_no_network(stock_home,monkeypatch):
    folder=stock_home/'Broll';folder.mkdir();p=folder/'typing laptop.mp4';p.write_bytes(b'fixture')
    stock.save_settings({'local_dir':str(folder)})
    monkeypatch.setattr(stock,'search',lambda *a,**k:pytest.fail('must use local collection first'))
    result,notes=stock.find('typing laptop','mengetik keyboard')
    assert result['path']==str(p.resolve()) and not notes
    assert stock.find('forest river','hutan sungai',online=False)[0] is None


def test_no_key_and_board_avoid_llm(stock_home,monkeypatch):
    monkeypatch.setattr(illustrations,'propose',lambda *a:pytest.fail('no asset source'))
    cfg=Config(work_dir=str(stock_home),broll_mode='auto')
    c={'start':0,'end':30};ws=words('Pembahasan bermakna sampai selesai')
    assert illustrations.prepare(ws,c,cfg)['status']=='unavailable'
    assert not illustrations.prepare(ws,c,replace(cfg,source_kind='board'))['scenes']


def test_broll_timestamp_mapping_after_trim_and_material_guard(tmp_path):
    media=tmp_path/'asset.mp4';media.write_bytes(b'fixture')
    scene={'id':'x','enabled':True,'source_start':15,'source_end':18,'asset':{'path':str(media)}}
    plan={'fps':30,'duration':20,'warnings':[],
        'spans':[{'start':0,'end':20,'kind':'body'}],
        'shots':[{'source_start':10,'source_end':30,'start':0,'end':20,'has_material':False}]}
    cfg=Config(broll_mode='local'); illustrations.attach(plan,{'scenes':[scene]},cfg)
    assert (plan['broll'][0]['start'],plan['broll'][0]['end'])==(5,8)
    plan['shots'][0]['has_material']=True
    illustrations.attach(plan,{'scenes':[scene]},cfg);assert plan['broll']==[]
    plan['shots'][0]['has_material']=False;plan['spans'][0]['kind']='cold_open'
    illustrations.attach(plan,{'scenes':[scene]},cfg);assert plan['broll']==[]


def test_recipe_cache_invalidated_by_audience_words_and_source_kind(tmp_path):
    cfg=Config(work_dir=str(tmp_path),broll_mode='local');c={'start':0,'end':30};ws=words('Isi lengkap untuk penonton')
    a=illustrations.recipe_path(ws,c,cfg)
    assert illustrations.recipe_path(ws,c,replace(cfg,audience='creators'))!=a
    assert illustrations.recipe_path(ws,c,replace(cfg,target_w=360,target_h=640))==a
    assert illustrations.recipe_path(ws,c,replace(cfg,source_kind='board'))!=a


def test_phrase_integrity_and_number_dwell_no_raw_edits():
    ws=words('tapi lu harus membangun skill yang berguna untuk pelanggan sekarang')
    before=copy.deepcopy(ws);groups=typography.groups(ws,Config())
    assert [w['word'] for g in groups for w in g]==[w['word'] for w in ws]
    assert all(len(g)>1 for g in groups) and ws==before
    source=[{'word_id':1,'word':'100.000','start':1,'end':9}]
    shown,changes,flags=subtitle_edit.clean(source)
    assert shown[0]['end']==3.8 and source[0]['end']==9 and flags and changes
    assert subtitle_edit.clean(source,'verbatim')[0]==source


def test_defaults_and_ending_question():
    assert Config().cold_open is False and Config().broll_mode=='off'
    ws=words('Kesimpulannya bangun keterampilan yang berguna Gue pengen tau ya')
    assert any('pertanyaan baru' in s for s in boundaries.audit({'start':0,'end':5,'title':'Skill'},ws))
    assert validate_overrides({'broll_max':99,'broll_mode':'auto','audience':'creators'})=={'broll_max':5,'broll_mode':'auto','audience':'creators'}


def test_stock_api_key_never_in_job_persistence_or_editor_response(stock_home,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app,'STATES',stock_home/'sessions')
    cfg=Config(pexels_key='never-export-this',work_dir=str(stock_home))
    st={'cfg':cfg,'transcript':{'words':words('isi lengkap'), 'duration':10},'scored':[{'start':0,'end':5,'title':'t'}]}
    monkeypatch.setattr(app,'JOB_STATE',{'s':st});monkeypatch.setattr(app,'JOBS',{'s':{'status':'review','clips':[]}})
    app.persist('s');assert 'never-export-this' not in (app.STATES/'s.json').read_text()
    client=TestClient(app.app)
    assert 'never-export-this' not in client.get('/api/editor/s/0').text
    r=client.post('/api/stock-settings',json={'pexels':'new-secret'})
    assert r.status_code==200 and 'new-secret' not in r.text


def test_unavailable_illustration_reason_survives_poll_without_poisoning_cache(stock_home,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app,'STATES',stock_home/'sessions')
    cfg=Config(work_dir=str(stock_home),broll_mode='local')
    c={'start':0,'end':20,'title':'Skill','revision':0}
    ws=words('Bangun keterampilan yang berguna untuk pelanggan')
    st={'cfg':cfg,'transcript':{'words':ws,'duration':20},'scored':[c],'edits':{},'clip_settings':{}}
    monkeypatch.setattr(app,'JOB_STATE',{'s':st})
    monkeypatch.setattr(app,'JOBS',{'s':{'status':'review','clips':[]}})
    app.worker('s','illustrating',[0])
    response=TestClient(app.app).get('/api/illustrations/s/0').json()
    assert 'folder koleksi' in ' '.join(response['notes'])
    assert c['revision']==1 and not illustrations.recipe_path(ws,c,cfg).exists()
    st['clip_settings']['0']={'broll_mode':'off'}
    assert 'Siapkan ilustrasi' in ' '.join(TestClient(app.app).get('/api/illustrations/s/0').json()['notes'])


def test_corrupt_stock_does_not_abort_source_render(stock_home,monkeypatch):
    import subprocess
    from clipper import ffmpeg_util
    def bad_probe(*args): raise subprocess.CalledProcessError(1,['ffprobe'])
    monkeypatch.setattr(ffmpeg_util,'probe',bad_probe)
    class Response:
        status_code=200
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def iter_content(self,*args): yield b'not-a-video'
    monkeypatch.setattr(stock.requests,'get',lambda *a,**k:Response())
    with pytest.raises(ValueError,match='tidak terbaca'):
        stock.download({'provider':'pexels','id':'broken','url':'https://videos.pexels.com/broken.mp4'})
    assert not list(stock.CACHE.rglob('*.partial'))
    asset=stock_home/'bad.mp4';asset.write_bytes(b'not-a-video')
    monkeypatch.setattr(stock,'local_assets',lambda:[{'path':str(asset)}])
    monkeypatch.setattr(illustrations,'propose',lambda *a:[{'word_index':10,'query':'typing laptop','reason':'working'}])
    monkeypatch.setattr(stock,'find',lambda *a,**k:({'path':str(asset),'id':'bad'},[]))
    monkeypatch.setattr(illustrations.editorial,'release',lambda *a:None)
    recipe=illustrations.prepare(words('kata '*45),{'start':0,'end':25},Config(work_dir=str(stock_home),broll_mode='local'))
    assert not recipe['scenes'] and any('dilewati' in s for s in recipe['notes'])
