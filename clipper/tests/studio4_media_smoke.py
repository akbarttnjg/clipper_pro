"""Opt-in real FFmpeg/SQLite/worker smoke. Synthetic words are not an ASR score."""
import argparse,json,subprocess,time
from pathlib import Path
from dataclasses import replace
from clipper.config import Config
from clipper.studio_service import StudioService,identifier
from clipper.studio_worker import execute
from clipper import media_context,analysis_adapter
from clipper.storage import read_json,write_json


def ff(args):subprocess.run(['ffmpeg','-nostdin','-hide_banner','-v','error','-y',*map(str,args)],check=True)


def run(output):
    root=Path(output).resolve();root.mkdir(parents=True,exist_ok=True)
    source=root/'source.mp4';asset=root/'illustration.mp4'
    ff(['-f','lavfi','-i','color=c=0x243b50:s=640x360:r=30:d=14','-f','lavfi','-i','sine=f=420:r=48000:d=14',
        '-vf','drawbox=x=420:y=60:w=150:h=250:color=0x769397:t=fill','-c:v','libx264','-threads','2','-c:a','aac','-shortest',source])
    ff(['-f','lavfi','-i','testsrc2=s=640x360:r=30:d=4','-an','-c:v','libx264','-threads','2',asset])
    cfg=Config(work_dir=str(root/'work'),out_dir=str(root/'clips'),use_nvenc=False,trim_silence=False,
        punch_zoom=False,broll_mode='local',source_kind='speaker',layout='fit',ocr_enabled=False,visual_cues=False)
    svc=StudioService(Path(__file__).resolve().parents[2],cfg,autostart=False)
    doc=svc.create(source,{},'Studio 4 · Pengujian A+B');pid=doc['project_id'];local=svc.config(doc)
    media=media_context.prepare(source,local)
    text='Pahami konteks timeframe sebelum memilih arah trading XAUUSD Kelola risiko dengan stop loss dan jangan mengabaikan kondisi pasar'
    words=[dict(word_id=i,word=w,start=.4+i*.53,end=.4+i*.53+.49) for i,w in enumerate(text.split())]
    take=svc.store.save_transcript(pid,{'words':words,'raw_words':words,'duration':14.})
    recipe={'scenes':[{'id':'illustration-one','source_start':5.,'source_end':8.,'enabled':True,'reason':'Aset sintetis untuk menguji sambungan shot','query':'Pola pengujian',
        'asset':{'provider':'local','id':'test-pattern','path':str(asset),'duration':4.,'title':'Synthetic test pattern','attribution':'FFmpeg testsrc2 / synthetic fixture'}}],'notes':[]}
    proposals=analysis_adapter.asset_proposal_set(recipe,source_id=media['source_id'],input_fingerprint='synthetic-proposal',cfg=local)
    def seed(d):
        d['source']['media_context']=media;d['transcript_id']=take
        svc.add_candidates(d,[{'title':'Konteks dan risiko XAUUSD','start':0.,'end':14.,'keywords':['XAUUSD','risiko'],'selection_source':'manual','reason':'Fixture sintetis; bukan hasil pemilihan AI'}])
        for c in d['clips'].values():
            for v in c['variants'].values():v.update(recipe=recipe,asset_proposals=proposals,timeline={'keep_spans':[[0.,6.],[6.,14.]]})
    svc.store.mutate(pid,0,identifier('seed'),{},seed);doc=svc.store.get(pid);cid=next(iter(doc['clips']))
    results=[]
    for kind,vid in [('preview','portrait'),('preview','landscape'),('render','portrait'),('render','landscape')]:
        doc=svc.store.get(pid);job=svc.enqueue(pid,kind,cid,vid,doc['revision']);svc.queue.update(job['id'],status='running')
        result=execute(svc,job);plan=read_json(result['plan_path']);assert result['qc']['passed']
        assert [(r['start'],r['end'],r['asset_start']) for r in plan['broll_schedule'] if r['status']=='scheduled']==[(5.,6.,0.),(6.,8.,1.)]
        assert result['broll_count']==2
        exchange=read_json(result['exchange_path'])
        from clipper.contracts import validate
        for value in exchange.values():validate(value)
        assert all(str(t).startswith('tok-') for p in exchange['caption_plan']['payload']['phrases'] for t in p['token_references'])
        assert plan['caption_checks']['passed'],plan['caption_checks']
        ff(['-ss','5.5','-i',result['absolute_file'],'-frames:v','1',root/f'{kind}-{vid}.png'])
        results.append({k:result[k] for k in ('kind','variant_id','absolute_file','width','height','length','broll_count','qc')})
        print(kind,vid,'OK',flush=True)
    # Same input reuses an existing validated render, not a new encode.
    final=svc.variant(svc.store.get(pid),cid,'landscape')['result'];stamp=Path(final['absolute_file']).stat().st_mtime_ns
    job=svc.enqueue(pid,'render',cid,'landscape',svc.store.get(pid)['revision']);svc.queue.update(job['id'],status='running');execute(svc,job)
    assert Path(final['absolute_file']).stat().st_mtime_ns==stamp
    # The real persistent process queue launches a worker and commits the waveform.
    svc.queue.autostart=True;j=svc.enqueue(pid,'waveform',expected_revision=svc.store.get(pid)['revision'])
    deadline=time.monotonic()+30
    while time.monotonic()<deadline and svc.queue.get(j['id'])['status'] not in ('completed','failed','stale'):
        time.sleep(.1)
    assert svc.queue.get(j['id'])['status']=='completed',svc.queue.get(j['id']);svc.queue.close();svc.queue.autostart=False
    # Export uses real native project writers; no assertion of desktop import success.
    j=svc.enqueue(pid,'export',cid,'landscape',svc.store.get(pid)['revision']);svc.queue.update(j['id'],status='running');export=execute(svc,j)
    verification=read_json(Path(export['folder'])/'verification.json');assert verification['structural_status']=='passed',verification
    report={'project_id':pid,'clip_id':cid,'database':str(svc.store.path),'renders':results,'cache_reused':True,'persistent_worker':'passed',
        'export':export,'export_verification':verification,'synthetic':True,
        'not_tested':['Real Whisper accuracy','Ollama content selection','Windows NVENC','CapCut/DaVinci desktop import']}
    write_json(root/'report.json',report);print(json.dumps({'report':str(root/'report.json'),'project_id':pid}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();run(args.output)
