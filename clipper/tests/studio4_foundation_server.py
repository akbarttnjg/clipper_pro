"""Isolated UI fixture: real Studio API/SQLite, synthetic media, no heavy worker."""
import argparse,json,subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from clipper.config import Config
from clipper.studio_service import StudioService,identifier
from clipper.api_studio import create_router
from clipper.api_analysis import create_router as analysis_router
from clipper.dependency_cache import content_id
from clipper.font_catalog import FONTS

parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True);parser.add_argument('--port',type=int,default=8769);parser.add_argument('--check',action='store_true')
args=parser.parse_args()
repo=Path(__file__).resolve().parents[2]
root=Path(args.output).resolve();root.mkdir(parents=True,exist_ok=True)
source=root/'source.mp4'
def ff(args):subprocess.run(['ffmpeg','-nostdin','-hide_banner','-v','error','-y',*map(str,args)],check=True)
ff(['-f','lavfi','-i','color=c=0x243b50:s=640x360:r=30:d=14','-f','lavfi','-i','sine=f=420:r=48000:d=14','-c:v','libx264','-threads','2','-c:a','aac','-shortest',source])
paths={'portrait':root/'portrait.mp4','landscape':root/'landscape.mp4'}
for vid,start,duration,scale in [('portrait',0,9,'180:320'),('landscape',5,8,'320:180')]:
 ff(['-ss',start,'-i',source,'-t',duration,'-vf','scale='+scale,'-c:v','libx264','-threads','2','-c:a','aac',paths[vid]])
svc=StudioService(root,Config(work_dir=str(root/'work'),out_dir=str(root/'clips'),use_nvenc=False,fonts_dir=str(repo/'clipper/fonts')),autostart=False)
doc=svc.create(source,name='Fixture UI · dua klip berbeda')
words=[dict(word_id=i,word=t,start=i*.5,end=i*.5+.4) for i,t in enumerate('Pahami konteks dan jangan mengabaikan risiko saat memilih potongan cerita untuk penonton'.split())]
take=svc.store.save_transcript(doc['project_id'],dict(words=words,raw_words=words,duration=14))
def seed(d):
 d['transcript_id']=take
 svc.add_candidates(d,[dict(title='Cerita pertama',start=0.,end=9.,keywords=[],selection_source='manual'),
                      dict(title='Cerita kedua',start=5.,end=13.,keywords=[],selection_source='manual')])
 for (cid,c),vid in zip(d['clips'].items(),('portrait','landscape')):
  width,height=(180,320) if vid=='portrait' else (320,180)
  c['variants'][vid]['result']=dict(absolute_file=str(paths[vid]),output_content_id=content_id(paths[vid]),
   dependency=svc.dependency(d,cid,vid),input_revision=doc['revision']+1,width=width,height=height,
   length=c['end']-c['start'],broll_count=0,kind='render')
 d['exports']=[dict(variant_id='portrait',note='Contoh paket parsial untuk pemeriksaan UI.',
   editors=dict(capcut=dict(construction_status='failed',structural_status='failed',issues=['Draft CapCut tidak terbentuk']),
                resolve=dict(construction_status='generated',structural_status='passed',issues=[])))]
svc.store.mutate(doc['project_id'],0,identifier('seed'),{},seed)
doc=svc.store.get(doc['project_id']);cid=next(iter(doc['clips']))
svc.changes(dict(project_id=doc['project_id'],clip_id=cid,variant_id='portrait',expected_revision=doc['revision'],
 operation_id=identifier('edit'),operations=[dict(op='settings',values=dict(caption_scale=1.1))]))
app=FastAPI();app.include_router(create_router(svc))
app.include_router(analysis_router(dict(get_snapshot=svc.analysis_snapshot,submit_changes=svc.changes,run_stage=svc.run_stage)))
app.mount('/static',StaticFiles(directory=repo/'static'))
@app.get('/')
def index():return FileResponse(repo/'static/index.html')
@app.get('/api/fonts')
def fonts():return [dict(id=k,**v) for k,v in FONTS.items()]
@app.post('/__test/complete-render')
def complete():
 d=svc.store.get(doc['project_id'])
 for job in svc.queue.list(d['project_id']):
  if job['kind']=='render':svc.queue.update(job['id'],status='completed',progress=100,message='Fixture final diperbarui')
 def update(current):
  result=current['clips'][cid]['variants']['portrait']['result']
  result.update(dependency=svc.dependency(current,cid,'portrait'),input_revision=d['revision']+1)
 svc.store.mutate(d['project_id'],d['revision'],identifier('final'),{},update)
 return {'passed':True}
client=TestClient(app)
class Handler(BaseHTTPRequestHandler):
 def dispatch(self):
  body=self.rfile.read(int(self.headers.get('Content-Length','0')))
  response=client.request(self.command,self.path,content=body,headers={'content-type':self.headers.get('Content-Type','application/json')})
  self.send_response(response.status_code)
  for name,value in response.headers.items():
   if name.lower() not in ('connection','transfer-encoding'):self.send_header(name,value)
  self.end_headers();self.wfile.write(response.content)
 do_GET=dispatch;do_POST=dispatch
 def log_message(self,*args):pass
if args.check:
 public=client.get('/api/studio/projects/'+doc['project_id']).json()
 results=[(c['clip_id'],vid,v) for c in public['clips'].values() for vid,v in c['variants'].items() if v.get('result')]
 assert len(results)==2 and {vid for _,vid,_ in results}=={'portrait','landscape'}
 assert results[0][2]['export_readiness']['status']=='stale' and results[1][2]['export_readiness']['status']=='ready'
 endpoint='/api/studio/projects/'+doc['project_id']+'/jobs'
 payload=dict(clip_id=cid,variant_id='portrait',expected_revision=public['revision'])
 assert client.post(endpoint,json=dict(kind='export',**payload)).status_code==400
 assert client.post(endpoint,json=dict(kind='render',**payload)).status_code==200
 complete();public=client.get('/api/studio/projects/'+doc['project_id']).json()
 payload['expected_revision']=public['revision']
 assert client.post(endpoint,json=dict(kind='export',**payload)).status_code==200
 assert client.get('/').status_code==200 and client.get('/static/studio4.js').status_code==200
 assert client.get('/api/analysis/snapshot',params=dict(project_id=doc['project_id'],clip_id=cid,variant_id='portrait')).status_code==200
 report=dict(passed=True,fixture='Real Studio API/SQLite + synthetic FFmpeg media; heavy worker completion simulated',
  checks=['two_independent_clips','stale_export_blocked','render_then_export_queue','static_UI_and_analysis_routes'])
 (root/'api-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
 svc.queue.close();raise SystemExit(0)
print(json.dumps(dict(url=f'http://127.0.0.1:{args.port}/',project_id=doc['project_id'])),flush=True)
try:ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
finally:svc.queue.close()
