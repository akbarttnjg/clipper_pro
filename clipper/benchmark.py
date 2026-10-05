"""Repeatable local release measurements; no claimed accuracy without references.

python -m clipper.benchmark reference.json hypothesis.json --output report.json
Each file: {"text": "...", "terms": ["XAUUSD"], "clips": [{"start":0,"end":20}]}.
"""
import argparse
import json
import re
from pathlib import Path
from .storage import write_json


def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1):nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]


def tokens(text):return re.findall(r"[\w]+(?:[.,]\d+)?",text.casefold())


def union_length(ranges):
    total=0;right=0
    for a,b in sorted(ranges):
        if b>a:total+=max(0,b-max(a,right));right=max(right,b)
    return total


def evaluate(reference,hypothesis):
    original=tokens(reference.get('text',''));heard=tokens(hypothesis.get('text',''))
    if not original:raise ValueError('Transkrip acuan manusia diperlukan; nilai akurasi tidak boleh ditebak')
    negations={'tidak','bukan','jangan','belum','tak','not','never','no'}
    protected=lambda words:[w for w in words if w in negations or any(c.isdigit() for c in w)]
    terms=[{'term':t,'present':any(heard[i:i+len(tokens(t))]==tokens(t) for i in range(len(heard)))} for t in reference.get('terms',[])]
    refs=[(c['start'],c['end']) for c in reference.get('clips',[])];clips=[(c['start'],c['end']) for c in hypothesis.get('clips',[])]
    matched=sum(any(max(0,min(b,y)-max(a,x))/max(.001,b-a)>=.7 for x,y in clips) for a,b in refs)
    report={'schema_version':1,'wer':distance(original,heard)/len(original),'cer':distance(' '.join(original),' '.join(heard))/len(' '.join(original)),
        'protected_tokens_exact':protected(original)==protected(heard),'terms':terms,'story_reference_count':len(refs),
        'story_coverage':matched/len(refs) if refs else None,'clip_count':len(clips),'unique_source_seconds':union_length(clips),
        'duplicate_seconds':sum(max(0,b-a) for a,b in clips)-union_length(clips),'native_editor_status':'not_tested'}
    report['gates']={'protected_tokens':report['protected_tokens_exact'],'approved_terms':all(t['present'] for t in terms),
        'wer_target_10_percent':report['wer']<=.1,'story_coverage_target_80_percent':report['story_coverage']>=.8 if refs else None}
    report['status']='passed_reference_gates' if all(v is True for v in report['gates'].values()) else 'needs_review'
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('reference');parser.add_argument('hypothesis');parser.add_argument('--output',required=True);args=parser.parse_args()
    report=evaluate(json.loads(Path(args.reference).read_text(encoding='utf-8')),json.loads(Path(args.hypothesis).read_text(encoding='utf-8')))
    write_json(args.output,report);print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
