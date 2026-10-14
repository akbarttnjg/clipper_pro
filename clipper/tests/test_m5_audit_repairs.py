"""M5 regressions reproduced independently on 9dd8e73 before repair."""
import copy,json,zipfile,os
from pathlib import Path
import pytest
from PIL import Image
from clipper.config import Config
from clipper.tests._m4_fixture import make_studio,change
from clipper.finishing5_service import assets,map_layers
from clipper.finishing5_plan import caption_plan
from clipper.finishing5_assets import font_info,sfnt
from clipper.finishing5_render import decorations

@pytest.fixture
def studio(tmp_path):
    service=make_studio(tmp_path)
    yield service
    service.queue.close()
def doc(s):return s.store.get(s.test_pid)
def variant(s):return s.variant(doc(s),s.test_cid,'portrait')

def test_kit_cannot_replace_a_locked_illustration_track(studio):
    kit=assets(studio).save_kit({'name':'Reviewed brand','style':{'base_hex':'#EEEEEE'},'layers':[{'id':'title','kind':'title','text':'New layer','start':0.,'end':2.,'rect':[5,5,60,15]}]})
    change(studio,{'op':'track','track':'illustration','values':{'locked':True}})
    before=doc(studio)
    with pytest.raises(ValueError,match='terkunci'):
        change(studio,{'op':'m5_kit','kit_id':kit['id'],'kit_revision':0,'include_layers':True})
    assert doc(studio)==before

def test_censor_cannot_change_locked_voice_audio(studio):
    change(studio,{'op':'track','track':'voice','values':{'locked':True}})
    before=doc(studio)
    with pytest.raises(ValueError,match='terkunci'):
        change(studio,{'op':'m5_style','values':{'censor_mode':'bleep_mask','censor_terms':['biaya'],'censor_approved':True}})
    assert doc(studio)==before

def test_atomic_meaning_unit_must_not_reassign_speaker():
    cfg=Config(target_w=640,target_h=360,semantic_emphasis=False,caption_template_policy='manual',finishing5={'enabled':True,'style':{'speaker_color':True,'speaker_styles':[{'speaker_id':'S1','label':'A','color':'#FF0000','approved':True},{'speaker_id':'S2','label':'B','color':'#0000FF','approved':True}]}})
    words=[{'word_id':0,'word':'tidak','start':0.,'end':.7,'speaker_id':'S1'},{'word_id':1,'word':'naik','start':.8,'end':1.5,'speaker_id':'S2'}]
    result=caption_plan(words,cfg);actual={w['text']:(w.get('speaker_id'),w['color']) for p in result['phrases'] for w in p['words']}
    print({'rendered_speaker_and_color':actual})
    assert actual['naik']==('S2','#0000FF')

def plan(text='A 5 B 50'):
    return {'width':640,'height':360,'duration':2.,'fps':30,'spans':[{'start':0.,'end':2.,'source_start':0.,'source_end':2.}], 'shots':[],'display_words':[{'word_id':0,'word':text,'start':0.,'end':2.}]}
def test_diagram_cannot_swap_values_between_source_labels():
    cfg=Config(finishing5={'enabled':True,'style':{},'decorations':[{'id':'chart','kind':'diagram','start':0.,'end':2.,'rect':[5,5,50,65],'quote':'A 5 B 50','items':['A','B'],'values':[50.,5.]}]})
    p=plan()
    with pytest.raises(ValueError,match='nilai|angka|kutipan|pasangan|Angka|Diagram'):
        map_layers(p,cfg)
    print({'diagram':p.get('finishing5')})

def test_failed_pack_import_does_not_publish_a_partial_parent(studio,tmp_path):
    a=assets(studio);parent=a.save_kit({'name':'Parent','style':{'base_hex':'#EEEEEE'}});child=a.save_kit({'name':'Child','parent_id':parent['id'],'style':{'accent_hex':'#FFAA00'}})
    original=tmp_path/'valid.zip';a.export(child['id'],original)
    with zipfile.ZipFile(original) as z:members={n:z.read(n) for n in z.namelist()}
    manifest=json.loads(members['manifest.json']);manifest['kit']['glossary']=[{'heard':'5','preferred':'50'}];members['manifest.json']=json.dumps(manifest).encode()
    bad=tmp_path/'invalid-child.zip'
    with zipfile.ZipFile(bad,'w',zipfile.ZIP_DEFLATED) as z:
        for n,data in members.items():z.writestr(n,data)
    before=copy.deepcopy(a.kits())
    with pytest.raises(ValueError,match='fakta kritis'):a.import_pack(bad)
    after=a.kits();print({'kits_before':len(before),'kits_after_failed_import':len(after),'new_kit_ids':list({k['id'] for k in after}-{k['id'] for k in before})})
    assert after==before

def test_text_decoration_cannot_silently_render_a_missing_glyph(tmp_path):
    cfg=Config(target_w=360,target_h=640,finishing5={'enabled':True,'style':{},'decorations':[]})
    info=font_info(cfg.fonts_dir,'dm_sans');assert ord('漢') not in sfnt(str((Path(cfg.fonts_dir)/info['file']).resolve()),info['sha256'])['glyphs']
    p={'width':360,'height':640,'duration':.2,'fps':30,'finishing5':{'source_mapping':'edit_spans','layers':[{'id':'title','kind':'title','text':'漢','start':0.,'end':.2,'output_rect':[18,32,300,100],'opacity':1.,'transition':'cut','transition_s':0.}]}}
    with pytest.raises(ValueError,match='Glyph|glyph|font|Font'):
        decorations(p,cfg,tmp_path)
    print({'overlay':p['finishing5'].get('overlay')})


@pytest.mark.parametrize('face_name,weight,source',[('Regular',400,'DejaVuSans.ttf'),('Medium',500,'DejaVuSans-Bold.ttf'),('SemiBold',600,'DejaVuSans-Bold.ttf'),('Bold',700,'DejaVuSans-Bold.ttf'),('Italic',400,'DejaVuSans-Oblique.ttf')])
def test_ASS_preserves_selected_face_in_same_family(studio,tmp_path,face_name,weight,source):
    TTFont=pytest.importorskip('fontTools.ttLib').TTFont
    from dataclasses import replace
    import subprocess,shutil
    from clipper import captions_pro,ffmpeg_util
    from clipper.finishing5_render import caption_frame
    records=[]
    for style,face_weight,face_source in [('Regular' if face_name!='Regular' else 'Medium',400 if face_name!='Regular' else 500,'DejaVuSans.ttf' if face_name!='Regular' else 'DejaVuSans-Bold.ttf'),(face_name,weight,source)]:
        original=Path(os.environ.get('CLIPPER_AUDIT_DEJAVU_DIR',Config().fonts_dir))/face_source
        face=TTFont(original)
        vals={1:'AuditM5Family',2:style,3:'AuditM5Family-'+style,4:'AuditM5Family '+style,6:'AuditM5Family-'+style,16:'AuditM5Family',17:style}
        for n in face['name'].names:
            if n.nameID in vals:n.string=vals[n.nameID].encode(n.getEncoding())
        face['OS/2'].usWeightClass=face_weight;face['OS/2'].fsSelection=1 if style=='Italic' else 0x40 if face_weight==400 else 0;face['head'].macStyle=2 if style=='Italic' else 0
        file=tmp_path/(style+'.ttf');face.save(file);face.close()
        records.append(assets(studio).register(file,{'permission':'licensed','license':'DejaVu; renamed fixture family','name':style}))
    change(studio,{'op':'m5_style','values':{'font_main':records[1]['id'],'font_accent':records[0]['id'],'template_id':'minimal','caption_template_policy':'manual','semantic_emphasis':False,'caption_renderer':'ass'}})
    cfg=replace(studio.config(doc(studio),studio.test_cid,'portrait'),target_w=640,target_h=360)
    words=[{'word_id':0,'word':'Contoh','start':0.,'end':1.5}];p=caption_plan(words,cfg);ass=tmp_path/'medium.ass';captions_pro.write_plan(p,ass,cfg)
    selected=p['phrases'][0]['words'][0];assert selected['weight']==weight and selected['style']==face_name
    target=tmp_path/'actual.png';q=subprocess.run(['ffmpeg','-nostdin','-v','verbose','-y','-f','lavfi','-i','color=c=0x101820:s=640x360:r=30:d=1.6','-vf',ffmpeg_util.ass_filter(ass,cfg),'-ss','0.4','-frames:v','1',str(target)],capture_output=True,check=True)
    log=q.stderr.decode('utf-8','replace');choices=[s for s in log.splitlines() if 'fontselect:' in s]
    print({'requested_family':selected['family'],'requested_style':selected['style'],'requested_weight':selected['weight'],'actual_libass_fontselect':choices})
    evidence=Path(os.environ.get('CLIPPER_AUDIT_EVIDENCE',str(tmp_path/'evidence')));evidence=evidence/face_name;evidence.mkdir(parents=True,exist_ok=True)
    Image.new('RGBA',(640,360),'#101820').save(tmp_path/'base.png');expected=Image.open(tmp_path/'base.png').convert('RGBA');expected.alpha_composite(caption_frame(p,cfg,.4));expected.convert('RGB').save(evidence/'medium-expected.png');shutil.copyfile(target,evidence/'medium-actual.png')
    (evidence/'medium-font-selection.json').write_text(json.dumps({'requested_font':{k:selected[k] for k in ['family','style','weight','font_id','file','sha256']},'actual_libass_fontselect':choices},indent=2))
    assert any('-> AuditM5Family-'+face_name in line for line in choices),'ASS must select the reviewed face, not a different weight in the same family'
    import numpy as np
    masks=[np.max(np.array(Image.open(path).convert('RGB')),axis=2)>100 for path in (evidence/'medium-actual.png',evidence/'medium-expected.png')]
    def bbox(mask):
        y,x=np.where(mask);return np.array([x.min(),y.min(),x.max(),y.max()])
    delta=int(np.max(abs(bbox(masks[0])-bbox(masks[1]))));iou=float(np.logical_and(*masks).sum()/max(1,np.logical_or(*masks).sum()))
    assert delta<=4 and iou>=.62,(face_name,delta,iou)
    (evidence/'medium-parity.json').write_text(json.dumps({'face':face_name,'weight':weight,'bbox_delta_px':delta,'glyph_mask_iou':iou,'tolerance_bbox_px':4,'minimum_iou':.62},indent=2))


def test_censor_word_does_not_bleep_a_neighboring_negation():
    cfg=Config(target_w=640,target_h=360,semantic_emphasis=False,caption_template_policy='manual',finishing5={'enabled':True,'style':{'censor_mode':'bleep_mask','censor_terms':['rahasia'],'censor_approved':True}})
    words=[{'word_id':0,'word':'tidak','start':.1,'end':.4,'speaker_id':'S1'},{'word_id':1,'word':'rahasia','start':.5,'end':.9,'speaker_id':'S1'}]
    p=caption_plan(words,cfg)
    print({'source_words':words,'censor_intervals':p['censor_intervals'],'rendered_words':[{k:w.get(k) for k in ['text','start','end','censored','continuation']} for phrase in p['phrases'] for w in phrase['words']]})
    assert p['censor_intervals'] and all(a>=.5 and b<=.9 for a,b in p['censor_intervals']),'Only rahasia was approved for censorship; tidak must remain audible'

@pytest.mark.parametrize('quote,items,values',[
    ('A 5 B 50',['A','B'],[5,50]),
    ('A -5,5 B 50.25',['B','A'],[50.25,-5.5]),
    ('Biaya 0 persen',['Biaya'],[0]),
])
def test_diagram_records_proven_pair_spans(quote,items,values):
    cfg=Config(finishing5={'enabled':True,'style':{},'decorations':[{'id':'chart','kind':'diagram','start':0.,'end':2.,'rect':[5,5,50,65],'quote':quote,'items':items,'values':values}]})
    p=plan(quote);map_layers(p,cfg)
    evidence=p['finishing5']['layers'][0]['provenance']['label_value_evidence']
    assert {e['label']:e['value'] for e in evidence}==dict(zip(items,values))
    for row in evidence:
        assert quote[slice(*row['label_span'])]==row['label']
        assert float(quote[slice(*row['value_span'])].replace(',','.'))==row['value']

@pytest.mark.parametrize('quote,items,values',[
    ('A 5 A 50',['A'],[5]),('A 5 atau 50',['A'],[50]),
    ('A 15',['A'],[5]),('A 5 B 50',['A','B'],[50,5]),
])
def test_diagram_rejects_ambiguous_or_inverted_evidence(quote,items,values):
    cfg=Config(finishing5={'enabled':True,'style':{},'decorations':[{'id':'chart','kind':'diagram','start':0.,'end':2.,'rect':[5,5,50,65],'quote':quote,'items':items,'values':values}]})
    with pytest.raises(ValueError):map_layers(plan(quote),cfg)

@pytest.mark.parametrize('command',[
    {'op':'m5_enable','enabled':False},
    {'op':'m5_style','values':{'censor_terms':['naik']}},
    {'op':'m5_reset','keys':['censor_mode']},
])
def test_existing_bleep_audio_is_owned_by_voice(studio,command):
    change(studio,{'op':'m5_style','values':{'censor_mode':'bleep_mask','censor_terms':['biaya'],'censor_approved':True}})
    change(studio,{'op':'track','track':'voice','values':{'locked':True}})
    before=doc(studio)
    with pytest.raises(ValueError,match='terkunci'):change(studio,command)
    assert doc(studio)==before

def test_unrelated_color_can_change_while_voice_and_illustration_locked(studio):
    for name in ('voice','illustration'):change(studio,{'op':'track','track':name,'values':{'locked':True}})
    change(studio,{'op':'m5_style','values':{'base_hex':'#FF0011'}})
    kit=assets(studio).save_kit({'name':'Colors only','style':{'accent_hex':'#112233'}})
    change(studio,{'op':'m5_kit','kit_id':kit['id'],'kit_revision':0,'include_layers':False})
    assert studio.config(doc(studio),studio.test_cid,'portrait').base_hex=='#FF0011'

def test_project_kit_checks_second_ratio_before_mutation(studio):
    kit=assets(studio).save_kit({'name':'Title','style':{},'layers':[{'id':'t','kind':'title','text':'Test','start':0,'end':2,'rect':[5,5,30,20]}]})
    change(studio,{'op':'track','track':'illustration','values':{'locked':True}},vid='landscape')
    before=doc(studio)
    with pytest.raises(ValueError,match='terkunci'):change(studio,{'op':'m5_kit','kit_id':kit['id'],'kit_revision':0,'scope':'project'})
    assert doc(studio)==before

@pytest.mark.parametrize('term,expected',[
    ('rahasia',[[.5,.9]]),('tidak rahasia',[[.1,.4],[.5,.9]]),('5 persen',[[1.,1.4],[1.5,1.9]])
])
def test_censor_preserves_exact_leaf_clocks_and_logical_coverage(term,expected):
    from clipper.finishing5_plan import check
    words=[{'word_id':i,'word':t,'start':a,'end':b,'speaker_id':'S1'} for i,(t,a,b) in enumerate([('tidak',.1,.4),('rahasia',.5,.9),('5',1.,1.4),('persen',1.5,1.9)])]
    before=copy.deepcopy(words);cfg=Config(target_w=640,target_h=360,semantic_emphasis=False,finishing5={'enabled':True,'style':{'censor_mode':'bleep_mask','censor_terms':[term],'censor_approved':True}})
    p=caption_plan(words,cfg);assert p['censor_intervals']==expected;assert words==before;assert check(p,cfg,words)['passed']
    if term=='rahasia':
        neg=next(w for ph in p['phrases'] for w in ph['words'] if w['text']=='tidak')
        assert (neg['start'],neg['end'],neg['censored'])==(.1,.4,False)

def test_partial_unaligned_cue_requires_word_alignment_for_audio():
    cfg=Config(finishing5={'enabled':True,'style':{'censor_mode':'bleep_mask','censor_terms':['rahasia'],'censor_approved':True}})
    with pytest.raises(ValueError,match='alignment kata'):caption_plan([{'word_id':0,'word':'tidak rahasia','start':0.,'end':2.}],cfg)


def test_actual_plan_censor_preserves_neighboring_negation_audio(tmp_path):
    import subprocess,numpy as np
    from clipper.finishing5_render import censor_audio
    cfg=Config(target_w=640,target_h=360,semantic_emphasis=False,finishing5={'enabled':True,'style':{'censor_mode':'bleep_mask','censor_terms':['rahasia'],'censor_approved':True}})
    captions=caption_plan([{'word_id':0,'word':'tidak','start':.1,'end':.4},{'word_id':1,'word':'rahasia','start':.5,'end':.9}],cfg)
    source=tmp_path/'source.wav';subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','sine=frequency=250:sample_rate=48000:duration=1.2','-ac','2',str(source)],check=True)
    p={'duration':1.2,'audio':{'mix':str(source)},'captions':captions};target=censor_audio(p,cfg,str(source),tmp_path)
    def samples(path):return np.frombuffer(subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','s16le','-ac','1','-ar','48000','-'],capture_output=True,check=True).stdout,dtype='<i2').astype(float)
    before,after=samples(source),samples(target)
    assert np.max(abs(before[7200:16800]-after[7200:16800]))<=2
    for a,b,hz in ((.15,.35,250),(.6,.8,1000),(1.,1.15,250)):
        window=after[round(a*48000):round(b*48000)];frequency=np.fft.rfftfreq(len(window),1/48000)[np.argmax(abs(np.fft.rfft(window)))];assert abs(frequency-hz)<8


def test_pack_publish_fault_rolls_back_assets_parents_and_retries(studio,tmp_path,monkeypatch):
    import contextlib
    a=assets(studio);image=tmp_path/'image.png';Image.new('RGB',(20,20),'red').save(image)
    registered=a.register(image,{'permission':'user_owned'});parent=a.save_kit({'name':'Parent','style':{},'asset_ids':[registered['id']]});child=a.save_kit({'name':'Child','parent_id':parent['id'],'style':{}})
    packed=a.export(child['id'],tmp_path/'kit.zip')
    # A separate clean destination registry receives the pack.
    from types import SimpleNamespace
    from clipper.project_store import ProjectStore
    from clipper.finishing5_assets import Assets
    folder=tmp_path/'destination';folder.mkdir();store=ProjectStore(folder/'live.sqlite3');dest=Assets(SimpleNamespace(work=folder,store=store));connect=store.connect
    class FailAfterParent:
        def __init__(self,db):self.db=db;self.count=0
        def execute(self,sql,*args):
            if sql.startswith('INSERT INTO kits5'):
                self.count+=1
                if self.count==2:raise OSError('controlled child publish fault')
            return self.db.execute(sql,*args)
        def __getattr__(self,key):return getattr(self.db,key)
    @contextlib.contextmanager
    def faulty():
        with connect() as db:yield FailAfterParent(db)
    with monkeypatch.context() as m:
        m.setattr(store,'connect',faulty)
        with pytest.raises(OSError,match='controlled child'):dest.import_pack(packed)
    assert dest.list()==[] and dest.kits()==[]
    assert not [p for p in dest.root.iterdir() if p.is_file()]
    imported=dest.import_pack(packed);assert imported['name']=='Child';assert len(dest.kits())==2 and len(dest.list())==1
    with store.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM kit_history5').fetchone()[0]==2

@pytest.mark.parametrize('kind',['title','intro','outro','lower_third','diagram'])
def test_all_text_layers_check_actual_font_before_render(tmp_path,kind,monkeypatch):
    import clipper.finishing5_render as render
    cfg=Config(target_w=360,target_h=640,finishing5={'enabled':True,'style':{}})
    row={'id':'t','kind':kind,'text':'漢','items':['漢'],'start':0.,'end':.2,'output_rect':[18,32,300,150],'opacity':1.,'transition':'cut','transition_s':0.}
    p={'width':360,'height':640,'duration':.2,'fps':30,'finishing5':{'layers':[row],'source_mapping':'edit_spans'}}
    def carrier_must_not_start(*args,**kw):raise AssertionError('Carrier started before glyph check')
    monkeypatch.setattr(render,'carrier',carrier_must_not_start)
    with pytest.raises(ValueError,match='Glyph'):render.decorations(p,cfg,tmp_path)


@pytest.mark.parametrize('value,font_id',[('Audit','dm_serif_italic'),('Ж','dejavu')])
def test_actual_selected_decoration_font_and_fallback_are_measured(tmp_path,value,font_id):
    import subprocess
    from clipper.finishing5_render import decorations
    cfg=Config(target_w=360,target_h=640,font_main='dm_serif_italic',finishing5={'enabled':True,'style':{'fallback_fonts':['dejavu']}})
    p={'width':360,'height':640,'duration':.2,'fps':30,'finishing5':{'source_mapping':'edit_spans','layers':[{'id':'t','kind':'title','text':value,'start':0.,'end':.2,'output_rect':[18,32,300,100],'opacity':1.,'transition':'cut','transition_s':0.}]}}
    decorations(p,cfg,tmp_path)
    row=p['finishing5']['layers'][0];assert row['text_fonts'][0]['font_id']==font_id
    assert row['text_fonts'][0]['sha256']==font_info(cfg.fonts_dir,font_id)['sha256']
    subprocess.run(['ffmpeg','-nostdin','-v','error','-i',p['finishing5']['overlay']['path'],'-f','null','-'],capture_output=True,check=True)


def test_actual_render_freezes_fallback_font_used_only_by_decoration(tmp_path):
    from clipper import pipeline
    from clipper.artifact_store import verify
    from clipper.finishing5_contract import layers
    from clipper.tests._m4_fixture import video
    source=video(tmp_path/'source.mp4')
    cfg=Config(work_dir=str(tmp_path/'work'),out_dir=str(tmp_path/'out'),target_w=360,target_h=640,font_main='bebas',font_accent='bebas',semantic_emphasis=False,caption_position='bottom',use_nvenc=False,visual_enabled=False,segmentation_enabled=False,align_selected_clips=False,audio_normalize=False,trim_silence=False,punch_zoom=False,finishing5={'enabled':True,'style':{'fallback_fonts':['dejavu']},'decorations':layers([{'id':'title','kind':'title','text':'Ж','start':0.,'end':1.,'rect':[5,5,80,20]}])})
    result=pipeline.render_clip(source,[{'word_id':0,'word':'Catat','start':.1,'end':.8}],{'start':0.,'end':2.,'title':'Fixture'},'decoration-font',cfg)
    p=json.loads(Path(result['plan_path']).read_text());assert verify(result,fresh=True)
    assert not any(w['font_id']=='dejavu' for ph in p['captions']['phrases'] for w in ph['words'])
    fallback=next(f for f in p['m5_fonts'] if f['font_id']=='dejavu')
    assert Path(fallback['path']).is_file() and Path(fallback['path']).is_relative_to(result['artifact_root'])
    title=p['finishing5']['layers'][0];assert title['text_fonts'][0]['font_id']=='dejavu'
    assert Path(title['text_fonts'][0]['path']).is_relative_to(result['artifact_root'])


def test_bilingual_censor_audio_uses_source_clock_only():
    from clipper.finishing5_plan import bilingual
    cfg=Config(target_w=360,target_h=640,semantic_emphasis=False,finishing5={'enabled':True,'style':{'censor_mode':'bleep_mask','censor_terms':['rahasia'],'censor_approved':True}})
    source=[{'word_id':0,'word':'tidak','start':.1,'end':.4},{'word_id':1,'word':'rahasia','start':.5,'end':.9}]
    translation=[{'word_id':'translated','word':'mungkin rahasia','start':.1,'end':.9}]
    p=bilingual(source,translation,cfg)
    assert p['censor_intervals']==[[.5,.9]]
    assert p['translation_plan']['censor_intervals']==[]
    assert any('•' in w['text'] for ph in p['translation_plan']['phrases'] for w in ph['words'])
