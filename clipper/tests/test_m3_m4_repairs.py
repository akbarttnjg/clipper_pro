"""Independent audit probes on pinned M4. Geometry is authored, not model quality."""
import copy
import pytest
from clipper import camera4_contract as c,camera4_plan as camera_plan,selection_service
from clipper.tests.test_m2_transcripts import M2Fixture
from clipper.tests.test_m4_service import studio,doc,variant,analyze,accept
from clipper.tests._m4_fixture import controls,change


class ManualAlignmentAudit(M2Fixture):
    __test__=True
    def test_m3_source_signature_tracks_manual_alignment(self):
        before=selection_service.signature(self.service,self.doc)
        self.command({'op':'align_words','scope':'shared_utterance','origin_word_ids':[4],'text':'XAUUSD',
            'words':[{'word':'XAUUSD','start':4.2,'end':4.6}],'transcript_id':self.take,'transcript_revision':self.doc['transcript_revision']})
        after=selection_service.signature(self.service,self.doc)
        print({'before_signature':before,'after_signature':after,'alignment':self.service.transcript(self.doc)['words'][-1].get('aligned_words')})
        self.assertNotEqual(before,after,'Manual source alignment must invalidate M3 source-time candidates')

    def test_m4_signature_tracks_effective_manual_alignment(self):
        from clipper.camera4_service import signature
        before=signature(self.service,self.doc,self.cid,'portrait')
        frozen=copy.deepcopy(self.service.store.transcript(self.take))
        self.command({'op':'align_words','scope':'shared_utterance','origin_word_ids':[4],'text':'XAUUSD',
            'words':[{'word':'XAUUSD','start':4.2,'end':4.6}],'transcript_id':self.take,'transcript_revision':self.doc['transcript_revision']})
        self.assertNotEqual(before,signature(self.service,self.doc,self.cid,'portrait'))
        self.assertEqual(frozen,self.service.store.transcript(self.take))

    def test_additional_ratio_can_save_scoped_text_without_changing_primary(self):
        self.command({'op':'m4_ratio','variant_id_new':'custom','width':1440,'height':960})
        self.text(1,'bukan','variant',vid='custom')
        self.assertEqual(self.service.transcript(self.doc,self.cid,'custom')['words'][1]['word'],'bukan')
        self.assertEqual(self.service.transcript(self.doc,self.cid,'portrait')['words'][1]['word'],'tidak')


def test_m4_controls_respect_video_track_lock(studio):
    change(studio,{'op':'track','track':'video','values':{'locked':True}})
    before=doc(studio)
    with pytest.raises(ValueError,match='terkunci'):change(studio,{'op':'m4_controls','values':controls(layout='fit')})
    assert doc(studio)==before


def segment(settings,**kw):
    return {'source_size':[320,180],'layout':'fit','subjects':[],'material':None,'speaker':{'selected':None},
            'protected_source':[],'safe_margins':settings['safe_margins'],**kw}


def test_m4_caption_panel_honors_right_safe_margin():
    settings=c.controls(controls(),4.)
    planned=camera_plan.layers(segment(settings),1080,1920,settings)
    x,y,w,h=planned['caption_panel'];sx,sy,sw,sh=planned['safe_rect']
    print({'panel':planned['caption_panel'],'safe_rect':planned['safe_rect'],'right_overflow':x+w-(sx+sw)})
    assert sx<=x and x+w<=sx+sw+.01 and sy<=y and y+h<=sy+sh+.01


def test_m4_manual_path_cannot_remove_the_selected_subject_head():
    settings=c.controls(controls(layout='subject',motion='manual',keyframes=[{'time':0.,'box':[0,0,40,100]},{'time':4.,'box':[0,0,40,100]}]),4.)
    face={'id':'selected','box':[150,30,40,40],'observations':[]}
    planned=segment(settings,layout='subject',subjects=[face],speaker={'selected':'selected'},
                    protected_source=[{'id':'selected','kind':'face','box':[145,20,50,60]}])
    with pytest.raises(ValueError,match='kepala|subjek'):camera_plan.layers(planned,360,640,settings)


@pytest.mark.parametrize('ratio,width,height',[('square',1080,1080),('feed',1080,1350),('custom',1440,960)])
def test_m4_extra_ratio_can_save_variant_word_timing(studio,ratio,width,height):
    change(studio,{'op':'m4_ratio','variant_id_new':ratio,'width':width,'height':height})
    current=doc(studio);take=current['transcript_id']
    change(studio,{'op':'m2_timing','scope':'variant','origin_word_ids':[0],'start':.3,'end':1.7,
                   'transcript_id':take,'transcript_revision':current['transcript_revision']},vid=ratio)
    after=doc(studio);assert studio.transcript(after,studio.test_cid,ratio)['words'][0]['start']==.3
    assert studio.transcript(after,studio.test_cid,'portrait')['words'][0]['start']==.2


@pytest.mark.parametrize('size',[(1080,1920),(1920,1080),(1080,1080),(1080,1350),(1440,960),(64,64)])
@pytest.mark.parametrize('margins',[[.08,.06,.10,.12],[.18,.16,.20,.20],[0,0,0,0]])
def test_m4_source_viewports_and_caption_stay_inside_all_safe_margins(size,margins):
    settings=c.controls(controls(safe_margins=margins),4.)
    planned=camera_plan.layers(segment(settings),*size,settings)
    sx,sy,sw,sh=planned['safe_rect']
    for x,y,w,h in [planned['caption_panel'],*[row['viewport'] for row in planned['layers']]]:
        assert sx<=x and sy<=y and x+w<=sx+sw+.01 and y+h<=sy+sh+.01 and w>0 and h>0


def test_m4_copy_respects_destination_lock_but_allows_locked_source(studio):
    change(studio,{'op':'track','track':'video','values':{'locked':True}},vid='landscape')
    before=doc(studio)
    with pytest.raises(ValueError,match='terkunci'):change(studio,{'op':'m4_copy','variant_ids':['landscape']})
    assert doc(studio)==before
    change(studio,{'op':'track','track':'video','values':{'locked':False}},vid='landscape')
    change(studio,{'op':'track','track':'video','values':{'locked':True}})
    change(studio,{'op':'m4_copy','variant_ids':['landscape']})
    assert variant(studio,'landscape')['camera4_controls']['motion']=='static'


@pytest.mark.parametrize('operation',['m4_disable','m4_decide'])
def test_m4_activation_and_disable_cannot_bypass_video_lock(studio,operation):
    analyze(studio);accept(studio)
    change(studio,{'op':'track','track':'video','values':{'locked':True}})
    before=doc(studio)
    op={'op':operation,'analysis_id':variant(studio)['camera4_report']['analysis_id'],'accepted':False,'reason':'test review','reviewed':[]}
    with pytest.raises(ValueError,match='terkunci'):change(studio,op)
    assert doc(studio)==before


def test_m3_sentences_follow_effective_alignment_without_mutating_take():
    from clipper.selection_contract import sentences
    words=[{'word_id':0,'word':'Dua kata.','start':1.,'end':2.,'aligned_words':[{'word':'Dua','start':3.,'end':3.4},{'word':'kata.','start':3.5,'end':3.9}]}]
    frozen=copy.deepcopy(words);rows,normalized=sentences(words,5.)
    assert rows[0]['start']==3. and rows[0]['end']==3.9
    assert words==frozen and normalized[0]['word_id']==0


def test_m4_manual_path_preserves_complete_selected_head_positive_control():
    settings=c.controls(controls(layout='subject',motion='manual',keyframes=[{'time':0.,'box':[25,0,75,100]},{'time':4.,'box':[20,0,75,100]}]),4.)
    face={'id':'selected','box':[150,30,40,40],'observations':[]}
    planned=segment(settings,layout='subject',subjects=[face],speaker={'selected':'selected'},protected_source=[{'id':'selected','kind':'face','box':[145,20,50,60]}])
    layers=camera_plan.layers(planned,360,640,settings)['layers']
    assert layers[0]['subject_id']=='selected' and len(layers[0]['path'])==2
