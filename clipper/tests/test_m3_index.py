import copy
import json
import sqlite3
from unittest.mock import patch
import pytest
from .. import selection_contract as sc
from ..selection_index import SelectionIndex,validate_vectors,documents
from ._m3_fixture import reference,config

RUNTIME={'generation':'explicit-model-generation','model_commit':'a'*40,'source_commit':'b'*40}


def test_index_generation_is_immutable_and_detects_corrupt_stored_bytes(tmp_path):
    index=SelectionIndex(tmp_path);rows,_=sc.sentences(reference()['words'],48.);cfg=config(tmp_path)
    before=index.build(rows,source_id='source',take='take',scope='display',cfg=cfg,policy='lexical')
    with index.connect() as db:db.execute('UPDATE m3_indexes SET document=? WHERE id=?',('{}',before['index_id']))
    with pytest.raises(ValueError,match='rusak'):index.build(rows,source_id='source',take='take',scope='display',cfg=cfg,policy='lexical')
    with index.connect() as db:assert db.execute('SELECT document FROM m3_indexes').fetchone()[0]=='{}'


def test_scope_and_timing_are_part_of_index_identity(tmp_path):
    index=SelectionIndex(tmp_path);rows,_=sc.sentences(reference()['words'],48.);cfg=config(tmp_path)
    a=index.build(rows,source_id='s',take='t',scope='raw',cfg=cfg,policy='lexical');b=index.build(rows,source_id='s',take='t',scope='display',cfg=cfg,policy='lexical')
    altered=copy.deepcopy(rows);altered[0]['start']+=.01;c=index.build(altered,source_id='s',take='t',scope='display',cfg=cfg,policy='lexical')
    assert len({a['index_id'],b['index_id'],c['index_id']})==3


def test_lexical_index_has_no_fake_embeddings_and_queries_are_reused(tmp_path):
    index=SelectionIndex(tmp_path);rows,_=sc.sentences(reference()['words'],48.);cfg=config(tmp_path)
    built=index.build(rows,source_id='s',take='t',scope='display',cfg=cfg,policy='lexical');assert built['vectors']==[] and built['model_digest'] is None
    a=index.query(built,'uang usaha',cfg);b=index.query(built,'uang usaha',cfg);assert b['cache_reused'] and a['query_id']==b['query_id'];assert b['probability_of_correct_topic'] is None


@pytest.mark.parametrize('mutation',['wrong_id','missing_vector','zero_vector','nonfinite','wrong_dimension','generation_changed','failed'])
def test_invalid_embedding_output_fails_before_cache_commit(mutation):
    items=[{'id':'a'},{'id':'b'}];result={'status':'ready','provenance':RUNTIME,'vectors':[{'id':'a','values':[1.,0.]},{'id':'b','values':[0.,1.]}]}
    if mutation=='wrong_id':result['vectors'][0]['id']='forged'
    elif mutation=='missing_vector':result['vectors'].pop()
    elif mutation=='zero_vector':result['vectors'][0]['values']=[0.,0.]
    elif mutation=='nonfinite':result['vectors'][0]['values']=[float('nan'),1.]
    elif mutation=='wrong_dimension':result['vectors'][1]['values']=[1.]
    elif mutation=='generation_changed':result['provenance']={**RUNTIME,'generation':'new'}
    else:result['status']='unavailable'
    with pytest.raises(ValueError):validate_vectors(items,result,RUNTIME)


def test_imported_long_cue_retains_time_and_text_with_explicit_embedding_limit():
    data=reference(['kata '*900+'.']);rows,_=sc.sentences(data['words'],6.);result=documents(rows)
    assert len(result)>1 and all(not r['embedding_truncated'] and len(r['embedding_text'])<=1800 for r in result)
    assert ''.join(r['text'] for r in result)==data['words'][0]['word'];assert all(r['start']==.2 and r['end']==5.8 for r in result)


def test_query_cache_corruption_is_not_silently_reused(tmp_path):
    index=SelectionIndex(tmp_path);rows,_=sc.sentences(reference()['words'],48.);cfg=config(tmp_path)
    built=index.build(rows,source_id='s',take='t',scope='display',cfg=cfg,policy='lexical');query=index.query(built,'usaha',cfg)
    with index.connect() as db:db.execute('UPDATE m3_queries SET document=? WHERE id=?',('{}',query['query_id']))
    with pytest.raises(ValueError,match='Cache query'):index.query(built,'usaha',cfg)


def test_e5_generation_and_prefix_cache_contract_with_explicit_protocol_double(tmp_path):
    """No real model-quality claim: checks the subprocess receipt/cache boundary."""
    runtime={**RUNTIME,'weights_digest':'sha256:actual-test-digest'};calls=[]
    def backend(component,request,cfg,folder):
        calls.append(request)
        return {'status':'ready','provenance':runtime,'vectors':[{'id':i['id'],'values':[1.,0.]} for i in request['items']]}
    index=SelectionIndex(tmp_path);rows,_=sc.sentences(reference()['words'],48.);cfg=config(tmp_path)
    with patch('clipper.selection_index.model_runtime',return_value=runtime),patch('clipper.visual4.backend',side_effect=backend):
        first=index.build(rows,source_id='s',take='t',scope='display',cfg=cfg,policy='e5');n=len(calls)
        again=index.build(rows,source_id='s',take='t',scope='display',cfg=cfg,policy='e5')
        assert again['cache_reused'] and len(calls)==n and calls[0]['prefix']=='passage'
        query=index.query(first,'usaha',cfg);index.query(first,'usaha',cfg)
        assert len(calls)==n+1 and calls[-1]['prefix']=='query' and query['probability_of_correct_topic'] is None
        index.query(first,'modal',cfg);assert len(calls)==n+2
    with patch('clipper.selection_index.model_runtime',side_effect=[runtime,{**runtime,'weights_digest':'changed'}]),patch('clipper.visual4.backend',side_effect=backend):
        with pytest.raises(ValueError,match='Bobot E5 berubah'):index.build(rows,source_id='changed-s',take='t',scope='display',cfg=cfg,policy='e5')
    with index.connect() as db:assert db.execute('SELECT COUNT(*) FROM m3_indexes').fetchone()[0]==1
