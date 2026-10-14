"""Inference worker protocol tested with explicit model doubles, not weights."""
import sys,types
import numpy as np
from unittest.mock import patch
from ..visual_worker import run


def test_e5_worker_cpu_local_only_and_prefixes_with_explicit_model_double(tmp_path):
    calls=[]
    torch=types.ModuleType('torch');torch.set_num_threads=lambda n:calls.append(('threads',n))
    module=types.ModuleType('sentence_transformers')
    class Model:
        def __init__(self,path,**kw):calls.append(('load',path,kw))
        def encode(self,texts,**kw):
            calls.append(('encode',texts,kw));return np.asarray([[1.,0.] for _ in texts])
    module.SentenceTransformer=Model
    request={'component':'e5','directory':str(tmp_path/'local-model'),'output_dir':str(tmp_path/'out'),
        'operation':'m3_embeddings','prefix':'passage','items':[{'id':'source-passage','text':'Modal usaha bukan jaminan keuntungan.'}]}
    with patch.dict(sys.modules,{'torch':torch,'sentence_transformers':module}):
        a=run(request);b=run({**request,'prefix':'query','items':[{'id':'query','text':'risiko modal'}]})
    assert a['device']==b['device']=='cpu' and a['vectors'][0]['id']=='source-passage'
    assert [c[1] for c in calls if c[0]=='encode']==[['passage: Modal usaha bukan jaminan keuntungan.'],['query: risiko modal']]
    assert all(c[2]=={'device':'cpu','local_files_only':True,'trust_remote_code':False} for c in calls if c[0]=='load')
