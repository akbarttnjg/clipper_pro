"""Reproducible A/C0 proposal fixture; no ASR/model or production save is run."""
import argparse
import json
from pathlib import Path
from clipper import analysis_adapter as adapter
from clipper.analysis_options import AnalysisConfig


def run(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    cfg=AnalysisConfig(work_dir=str(output/'work'),audience='finance',approved_aliases=[])
    source={'fixture':True,'duration':5,'words':[
        dict(word_id=i,word=w,start=i*.4,end=i*.4+.35,probability=.35 if w=='hausd' else .95)
        for i,w in enumerate('trading forex hausd time frame tidak 1.250,50'.split())]}
    snapshot=adapter.transcript_snapshot(source,cfg,source_id='fixture:synthetic-media',
        transcript_id='fixture:asr-take-1',revision=3,input_fingerprint='fixture:correction-1',audio_stream_id='audio:0')
    token=next(t for t in snapshot['payload']['display_tokens'] if t['text']=='XAUUSD')
    request=adapter.correction_proposal(snapshot,token['token_id'],'XAUUSD',expected_revision=19,
        expected_transcript_revision=3,operation_id='fixture-manual-approval')
    request.update(project_id='fixture-project',clip_id='fixture-clip',variant_id='portrait')
    for name,value in [('transcript-input.json',source),('transcript-output.json',snapshot),('correction-request.json',request)]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'fixture':True,'output':str(output),'raw_word':'hausd','display_word':token['text'],
        'source_word_ids':token['origin_word_ids'],'project_revision':19,'transcript_revision':3}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    run(parser.parse_args().output)
