"""Long-source selection, evidence identity and co-editor target guards."""
import copy
import pytest
from clipper.project_store import Conflict
from ._m4_fixture import make_studio


@pytest.fixture
def studio(tmp_path):
    service=make_studio(tmp_path)
    try:yield service
    finally:service.queue.close();service.integrations.close()


def long_source(service):
    doc=service.store.get(service.test_pid)
    words=[{'word_id':i,'word':('Kata dan angka '+str(i)+' ')*4,'start':i*.2,'end':i*.2+.15,'probability':None} for i in range(35000)]
    take=service.store.save_transcript(doc['project_id'],{'words':words,'raw_words':words,'duration':7200})
    def change(d):
        d.update(transcript_id=take,transcript_revision=2);d['source']['info']['duration']=7200
        d['clips'][service.test_cid].update(start=3600.,end=3620.)
    service.store.mutate(doc['project_id'],doc['revision'],'authored-two-hour-context',{},change)
    return service.store.get(doc['project_id'])


def test_clip_selection_precedes_whole_source_limits_and_preserves_word_ids(studio):
    doc=long_source(studio);actor=studio.integrations.local_actor();creative=studio.lab.creative
    with pytest.raises(ValueError):creative.source(actor,doc['project_id'],doc['revision'])
    context=creative.source(actor,doc['project_id'],doc['revision'],studio.test_cid)
    ids=[i for row in context['sources'] for i in row['word_ids']]
    assert ids==list(range(18000,18100))
    assert context['selection']['start']==3600 and context['selection']['end']==3620
    job=creative.generate(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],'clip_id':studio.test_cid,
        'mode':'summary','instruction':'Ringkas bagian ini','language':'id'})
    snap=job['request']['m9'];assert snap['sources']==context['sources'] and len(snap['sources'])<30
    assert studio.store.get(doc['project_id'])==doc


def test_manual_range_on_long_source_and_saved_script_selection(studio):
    doc=long_source(studio);actor=studio.integrations.local_actor();creative=studio.lab.creative
    context=creative.source(actor,doc['project_id'],doc['revision'],start=6980,end=6990)
    assert [i for row in context['sources'] for i in row['word_ids']]==list(range(34900,34950))
    item=creative.save(actor,{'name':'Catatan bagian akhir','mode':'notes','text':'Draf yang ditinjau','language':'id','license':'Authored',
        'project_id':doc['project_id'],'expected_revision':doc['revision'],'start':6980,'end':6990})
    assert item['data']['source']['selection']['start']==6980
    with pytest.raises(ValueError,match='belum mempunyai'):creative.source(actor,doc['project_id'],doc['revision'],start=7010,end=7020)


@pytest.mark.parametrize('fields',[{'clip_id':'missing'},{'start':-1},{'start':2,'end':1},{'start':float('nan')},{'end':10000},{'clip_id':'valid','start':3599}])
def test_invalid_selection_does_not_enqueue(studio,fields):
    doc=studio.store.get(studio.test_pid);actor=studio.integrations.local_actor()
    if fields.get('clip_id')=='valid':fields={**fields,'clip_id':studio.test_cid}
    with pytest.raises(ValueError):studio.lab.creative.generate(actor,{'project_id':doc['project_id'],'expected_revision':doc['revision'],
        'mode':'summary','instruction':'test','language':'id',**fields})
    assert not studio.queue.list(studio.test_pid)


def test_effective_corrections_and_whole_boundary_unit_are_explicit(studio):
    doc=studio.store.get(studio.test_pid);actor=studio.integrations.local_actor()
    selected=studio.lab.creative.source(actor,doc['project_id'],doc['revision'],start=1,end=1.5)
    assert selected['sources'][0]['word_ids']==[0]
    assert selected['sources'][0]['start']==.2 and selected['selection']['start']==1
    assert selected['selection']['policy']=='whole_transcript_units_overlapping_selected_range'


def test_coeditor_suggestion_cannot_be_applied_to_another_clip_or_ratio(studio):
    actor=studio.integrations.local_actor();doc=studio.store.get(studio.test_pid);cid=studio.test_cid
    item=studio.lab.store.create(actor,'creative',{'mode':'coeditor','project_id':doc['project_id'],
        'source':{'project_id':doc['project_id'],'source_content_id':doc['source']['source_id'],'transcript_id':doc['transcript_id'],
                  'input_revision':doc['revision'],'clip_id':cid,'variant_id':'portrait'},
        'operations':[{'op':'settings','values':{'caption_scale':1.1}}]})
    for target in [{'clip_id':'other'},{'clip_id':cid,'variant_id':'landscape'}]:
        with pytest.raises(ValueError,match='terikat klip'):studio.lab.creative.propose(actor,{'id':item['id'],'expected_revision':doc['revision'],**target},'cross-target-test')
