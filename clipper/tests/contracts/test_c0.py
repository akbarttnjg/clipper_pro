import pytest
from clipper.contracts import words_snapshot, validate, span

def test_adapter_preserves_lineage_and_copies():
    words=[dict(word='uang',word_id=17,start=1.,end=2.)]
    snap=words_snapshot(words,'source','transcript')
    assert snap['payload']['words'][0]['origin_word_ids']==[17]
    snap['payload']['words'][0]['word']='income'
    assert words[0]['word']=='uang'
    assert validate(snap) is snap

def test_invalid_versions_and_spans_rejected():
    with pytest.raises(ValueError): validate({'schema_version':2})
    with pytest.raises(ValueError): span(2,2)
