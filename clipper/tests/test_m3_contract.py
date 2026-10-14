import copy
import math
import pytest
from .. import selection_contract as sc
from ..selection_engine import expand
from ._m3_fixture import reference,options


@pytest.mark.parametrize('field,value',[('start',True),('end',float('nan')),('min_seconds',0),('max_seconds',601),('count',2.1),('count',-1),('candidate_budget',1001),('provider','cloud'),('retrieval','fake'),('profile','unsupported_game'),('scope','caption'),('signals','true'),('topics','usaha'),('keywords',['']),('speakers',[None]),('chunk_seconds',10),('overlap_seconds',240),('padding_after',3),('frame_budget',49),('visual_model','unknown')])
def test_invalid_constraints_rejected(field,value):
    with pytest.raises(ValueError):sc.constraints({field:value},100.)


@pytest.mark.parametrize('value',[0,-1,86401,float('inf'),None,True])
def test_invalid_source_duration(value):
    with pytest.raises(ValueError):sc.constraints({},value)


def test_no_unknown_constraint_silently_changes_selection():
    with pytest.raises(ValueError,match='tidak dikenal'):sc.constraints({'pretend_complete':True},50.)


def test_cross_chunk_story_is_inside_at_least_one_overlapping_window():
    data=reference(['Kalimat sumber lengkap.']*400,step=1.)
    rows,_=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(chunk_seconds=90,overlap_seconds=20,max_seconds=70),data['duration'])
    blocks=sc.chunks(rows,request)
    assert any(b['start']<=85.2 and b['end']>=140.8 for b in blocks)
    assert len(blocks)>1 and blocks[-1]['end']==rows[-1]['end']
    assert all(b['effective_overlap_seconds']>=request['max_seconds']+request['grace_seconds'] for b in blocks)


@pytest.mark.parametrize('change',[{'word_id':True},{'start':float('nan')},{'end':0},{'start':-1},{'word':''}])
def test_invalid_source_units_fail_before_candidate(change):
    data=reference();data['words'][0].update(change)
    with pytest.raises(ValueError):sc.sentences(data['words'],data['duration'])


def test_duplicate_word_identity_is_not_reassigned():
    data=reference();data['words'][1]['word_id']=0
    with pytest.raises(ValueError,match='ganda'):sc.sentences(data['words'],data['duration'])


def test_cut_through_creator_cue_is_rejected_without_fake_word_timing():
    data=reference();rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(),data['duration'])
    with pytest.raises(ValueError,match='unit kata/cue'):sc.candidate([{'start':1.,'end':5.8}],rows,words,request,'source')
    assert words[0]['start']==.2 and words[0]['end']==5.8


def test_partial_sentence_is_hard_blocker_even_if_each_word_is_whole():
    words=[{'word_id':0,'word':'Keuntungan','start':0.,'end':1.},{'word_id':1,'word':'bukan','start':1.,'end':2.},{'word_id':2,'word':'pasti.','start':2.,'end':3.}]
    rows,words=sc.sentences(words,4.);request=sc.constraints(options(min_seconds=1,max_seconds=5),4.)
    c=sc.candidate([{'start':0.,'end':2.}],rows,words,request,'source')
    assert 'partial_sentence' in c['completeness']['hard_blockers']


def test_following_caveat_cannot_be_overridden_by_appeal():
    data=reference(['Keuntungan investasi bisa 10 persen.','Tetapi keuntungan tidak pasti karena risiko pasar.','Jadi periksa risiko sebelum investasi.'])
    rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(profile='finance',min_seconds=5,max_seconds=18),data['duration'])
    c=sc.candidate([{'start':.2,'end':5.8}],rows,words,request,'source');c['scores']={'appeal':{'value':999},'relevance':{'value':999}}
    assert 'following_caveat_missing' in c['completeness']['hard_blockers']
    assert sc.rank_set([c],request)['recommended_ids']==[]
    span,repair=expand(rows,0,0,request,'source',words);expanded=sc.candidate([span],rows,words,request,'source')
    assert expanded['caveats'] and not expanded['completeness']['hard_blockers'];assert repair['after']['end_segment']==2
    assert expanded['conclusion'][0]['quote']=='Jadi periksa risiko sebelum investasi.'


def test_list_expansion_keeps_all_promised_items():
    data=reference(['Ada tiga langkah untuk menjaga saldo.','Pertama catat pengeluaran.','Kedua hitung pemasukan.','Ketiga simpan dana cadangan.'])
    rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(min_seconds=10,max_seconds=25),data['duration'])
    span,_=expand(rows,0,1,request,'source',words);c=sc.candidate([span],rows,words,request,'source')
    assert 'Ketiga' in c['text'];assert 'incomplete_numbered_list' not in c['completeness']['hard_blockers']


def test_maximum_duration_that_loses_list_discloses_shortfall():
    data=reference(['Ada tiga langkah untuk menjaga saldo.','Pertama catat pengeluaran.','Kedua hitung pemasukan.','Ketiga simpan dana cadangan.'])
    rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(min_seconds=10,max_seconds=12,grace_seconds=0),data['duration'])
    span,_=expand(rows,0,1,request,'source',words);c=sc.candidate([span],rows,words,request,'source')
    assert 'incomplete_numbered_list' in c['completeness']['hard_blockers'];assert sc.rank_set([c],request)['shortfall']==2


def test_question_and_answer_crossing_seed_boundary_are_kept():
    data=reference(['Bagaimana cara menjaga uang usaha?','Pisahkan uang usaha dari belanja pribadi.','Jadi simpan bukti transaksi usaha.'])
    rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(min_seconds=5,max_seconds=20),data['duration'])
    span,repair=expand(rows,1,1,request,'source',words)
    assert span['start']<=rows[0]['start'];assert repair['after']['start_segment']==0


def test_unknown_confidence_is_null_and_does_not_become_one():
    data=reference(['Ini penjelasan sumber yang lengkap.']);rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(),data['duration'])
    c=sc.candidate([{'start':.2,'end':5.8}],rows,words,request,'source')
    assert c['confidence']['mean'] is None and c['confidence']['status']=='unknown';assert c['confidence']['unknown_units']==1


@pytest.mark.parametrize('left,right',[('Keuntungan 10 persen.','Keuntungan 100 persen.'),('Keuntungan bukan 10 juta.','Keuntungan 10 juta.'),('Saldo -10 juta.','Saldo 10 juta.'),('Dana 5 kg.','Dana 5 km.'),('Angka 1,5 persen.','Angka 1.5 persen.')])
def test_similar_source_text_with_different_critical_facts_is_distinct(left,right):
    a={'candidate_id':'a','text':left,'critical_tokens':sc.critical(left)};b={'candidate_id':'b','text':right,'critical_tokens':sc.critical(right)}
    assert not sc.equivalent(a,b)


def test_same_meaning_at_different_times_keeps_alternative_without_rendering_it():
    data=reference(['Catat uang usaha sebelum belanja.','Catat uang usaha sebelum belanja.']);rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(),data['duration'])
    a=sc.candidate([{'start':.2,'end':5.8}],rows,words,request,'source');b=sc.candidate([{'start':6.2,'end':11.8}],rows,words,request,'source')
    for c in (a,b):c['scores']={'relevance':{'value':1.},'appeal':{'value':1.}}
    selected=sc.rank_set([a,b],request);assert len(selected['recommended_ids'])==1;assert a['alternatives']==[b['candidate_id']];assert b['selection_status']=='proposed'


def test_reordered_nonadjacent_story_uses_sum_duration_and_flags_order():
    data=reference();rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(min_seconds=5,max_seconds=15),data['duration'])
    c=sc.candidate([{'start':42.2,'end':47.8},{'start':6.2,'end':11.8}],rows,words,request,'source')
    assert c['duration']==pytest.approx(11.2);assert c['end']-c['start']>30;assert 'source_order_changed' in c['completeness']['review_flags']


@pytest.mark.parametrize('spans',[[],[{'start':.2,'end':5.8,'source_id':'different'}],[{'start':.2,'end':5.8},{'start':.2,'end':5.8}],[{'start':0,'end':60}],[{'start':5,'end':1}]])
def test_invalid_story_spans_are_not_silently_fixed(spans):
    data=reference();rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(),data['duration'])
    with pytest.raises(ValueError):sc.candidate(spans,rows,words,request,'source')


def test_late_list_item_does_not_become_an_independent_complete_story():
    data=reference(['Ada tiga langkah untuk menjaga saldo.','Pertama catat pengeluaran.','Kedua hitung pemasukan.','Ketiga simpan dana cadangan.'])
    rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(min_seconds=5,max_seconds=25),data['duration'])
    short=sc.candidate([{'start':18.2,'end':23.8}],rows,words,request,'source')
    assert 'numbered_list_context_missing' in short['completeness']['hard_blockers']
    span,_=expand(rows,3,3,request,'source',words);whole=sc.candidate([span],rows,words,request,'source')
    assert 'Ada tiga' in whole['text'] and not whole['completeness']['hard_blockers']


def test_unrelated_next_topic_about_risk_does_not_extend_a_finished_story():
    data=reference(['Catat uang usaha dengan benar.','Jadi saldo dapat diperiksa.','Ada tiga langkah untuk memeriksa risiko.'])
    rows,words=sc.sentences(data['words'],data['duration']);request=sc.constraints(options(min_seconds=5,max_seconds=20),data['duration'])
    span,repair=expand(rows,0,0,request,'source',words)
    assert repair['after']['end_segment']==1 and span['end']<rows[2]['start']


def test_currency_signs_attached_to_prefix_are_preserved():
    assert sc.critical('Saldo Rp-10.000 rupiah.')['numbers']==['-10.000 rupiah']
