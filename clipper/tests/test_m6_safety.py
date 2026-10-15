"""Meaning, snapshots, dependency drift and cancellation on real local media."""
import copy,json
from pathlib import Path
import pytest
from .test_m6_service import svc,doc,cfg
from ._m4_fixture import change
from ..studio_service import identifier
from ..audio6_service import snapshot
from ..audio6_cleanup import proposals
from ..editor_contract import segments_for

def seed_words(s,words):
    rows=[{'word_id':i,'word':text,'start':a,'end':b} for i,(text,a,b) in enumerate(words)]
    take=s.store.save_transcript(s.test_pid,{'words':rows,'raw_words':rows,'duration':4.})
    s.store.mutate(s.test_pid,doc(s)['revision'],identifier('m6-words'),{},lambda d:d.update(transcript_id=take,transcript_revision=d['transcript_revision']+1))
    return rows

def test_disabled_M6_snapshot_shows_saved_settings_without_activating_them(svc):
    change(svc,{'op':'m6_settings','values':{'target_lufs':-23.,'source_gain_db':5}})
    view=snapshot(svc,svc.test_pid,svc.test_cid,'portrait')
    assert view['settings']['target_lufs']==-23 and view['settings']['source_gain_db']==5
    assert not view['enabled'] and not view['normalization_target_active'] and cfg(svc).audio6 is None

def test_all_M6_draft_fields_roundtrip_to_validated_commands_and_do_not_mutate(svc):
    from ..editor_drafts import request
    before=doc(svc);key=f'clipper-m6-fields|{svc.test_pid}|{svc.test_cid}|portrait'
    fields={'normalize':'false','source_gain_db':'3.5','hum_hz':'50','eq_bands':'[{"hz":80,"gain_db":-3,"q":1}]','enabled':'true',
        'tracks':json.dumps([{'id':'pending','role':'music','asset_id':'asset-local','start':'0','end':'3','gain_db':'-24'}])}
    out=request(svc,before,{'operation_id':'m6-snapshot-test','stores':{key:json.dumps({'revision':before['revision'],'fields':fields})}})
    assert [o['op'] for o in out['operations']]==['m6_settings','m6_tracks','m6_enable']
    assert out['operations'][0]['values']['source_gain_db']==3.5 and out['operations'][1]['values'][0]['gain_db']==-24
    assert doc(svc)==before

@pytest.mark.parametrize('fields',[{'source_gain_db':'-'},{'normalize':'False'},{'target_lufs':'NaN'},{'mystery':'2'},
    {'tracks':'[{"id":"m","role":"music","asset_id":"a","start":"","end":"2"}]'}])
def test_incomplete_M6_snapshot_is_rejected_without_losing_original_draft(fields):
    from ..audio6_draft import operations
    original=copy.deepcopy(fields)
    with pytest.raises(ValueError):operations({'fields':fields})
    assert fields==original

def cleanup_fixture(s):
    seed_words(s,[('eh',.2,.4),('tidak',.6,.9),('5',1.0,1.2),('persen',1.3,1.6),('lanjut',3.,3.6)])
    return proposals(s,doc(s),s.test_cid,'portrait')

def test_reviewed_cleanup_changes_both_ratio_video_audio_together_and_preserves_heard_source(svc):
    p=cleanup_fixture(svc);before=svc.transcript(doc(svc));fill=next(r for r in p['proposals'] if r['kind']=='filler')
    assert not p['automatic_deletion'] and all(r['word_ids'] not in ([1],[2]) for r in p['proposals'])
    change(svc,{'op':'m6_cleanup','signature':p['signature'],'proposal_ids':[fill['id']],'reviewed':True})
    d=doc(svc);v=d['clips'][svc.test_cid]['variants']
    assert v['portrait']['editor']['segments']==v['landscape']['editor']['segments']
    assert v['portrait']['audio6']['cleanup_history'][-1]['source_unchanged']
    assert svc.transcript(d)==before
    assert not any(r['kind']=='filler' for r in proposals(svc,d,svc.test_cid,'portrait')['proposals'])

@pytest.mark.parametrize('failure',['unreviewed','stale','locked-other-ratio'])
def test_cleanup_rejects_unreviewed_stale_or_locked_other_ratio_before_any_change(svc,failure):
    p=cleanup_fixture(svc);selected=p['proposals'][0];op={'op':'m6_cleanup','signature':p['signature'],'proposal_ids':[selected['id']],'reviewed':True}
    if failure=='unreviewed':op['reviewed']=False
    if failure=='stale':op['signature']='obsolete'
    if failure=='locked-other-ratio':change(svc,{'op':'track','track':'voice','values':{'locked':True}},vid='landscape')
    before=doc(svc)
    with pytest.raises(ValueError):change(svc,op)
    assert doc(svc)==before

def test_repeated_negation_and_numbers_are_never_suggested_as_retake(svc):
    seed_words(svc,[(t,.1+i*.4,.3+i*.4) for i,t in enumerate(['tidak','5','persen']*2)])
    assert not any(p['kind']=='retake' for p in proposals(svc,doc(svc),svc.test_cid,'portrait')['proposals'])

def test_M1_music_mute_and_solo_resolve_only_audible_M6_assets(svc):
    change(svc,{'op':'m6_tracks','values':[{'id':'missing-muted','role':'music','asset_id':'not-installed','start':0,'end':3,'muted':True}]})
    change(svc,{'op':'m6_enable','enabled':True});assert 'asset' not in cfg(svc).audio6['tracks'][0]
    change(svc,{'op':'track','track':'voice','values':{'solo':True}})
    change(svc,{'op':'m6_tracks','values':[{'id':'missing-muted','role':'music','asset_id':'not-installed','start':0,'end':3}]})
    assert not cfg(svc).audio6['track_state']['music'] and 'asset' not in cfg(svc).audio6['tracks'][0]
    before=doc(svc)
    with pytest.raises(ValueError):change(svc,{'op':'track','track':'voice','values':{'solo':False}})
    assert doc(svc)==before

def test_audio_asset_bytes_are_in_dependency_identity_even_with_same_name(tmp_path):
    from ..audio6_contract import asset_signature
    p=tmp_path/'same.wav';p.write_bytes(b'first')
    state={'tracks':[{'id':'m','enabled':True,'muted':False,'asset':{'path':str(p)}}],'settings':{}}
    before=asset_signature(state,fresh=True);p.write_bytes(b'other')
    assert asset_signature(state,fresh=True)!=before

@pytest.mark.parametrize('failure',['cancel','dependency'])
def test_completed_but_canceled_or_stale_mix_never_replaces_prior_review(svc,monkeypatch,failure):
    from .. import audio6
    from ..studio_worker import execute,StaleJob
    change(svc,{'op':'m6_enable','enabled':True})
    def seed(d):svc.variant(d,svc.test_cid,'portrait')['audio6']['review']={'master':'prior-reviewed-result','dependency':'old'}
    svc.store.mutate(svc.test_pid,doc(svc)['revision'],identifier('m6-old-review'),{},seed)
    job=svc.enqueue(svc.test_pid,'audio_m6',svc.test_cid,'portrait',doc(svc)['revision'],{'seconds':2})
    original=audio6.finalize
    def finalize(*a,**kw):
        value=original(*a,**kw)
        if failure=='cancel':svc.queue.cancel(job['id'])
        else:change(svc,{'op':'m6_settings','values':{'source_gain_db':1.}})
        return value
    monkeypatch.setattr(audio6,'finalize',finalize)
    with pytest.raises(StaleJob):execute(svc,job)
    assert svc.variant(doc(svc),svc.test_cid,'portrait')['audio6']['review']['master']=='prior-reviewed-result'
