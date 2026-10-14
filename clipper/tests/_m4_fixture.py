"""Authored geometry/timing; no neural model-quality assertion."""
import subprocess
from pathlib import Path
from ..config import Config
from ..studio_service import StudioService,identifier

def video(path):
    path=Path(path)
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','color=c=red:s=320x180:r=30:d=2','-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=2','-f','lavfi','-i','sine=frequency=660:sample_rate=48000:duration=2','-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=2','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a][3:a]concat=n=2:v=0:a=1[a]','-map','[v]','-map','[a]','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-c:a','aac',str(path)],check=True,capture_output=True)
    return path

def make_studio(tmp_path):
    cfg=Config(work_dir=str(tmp_path/'work'),out_dir=str(tmp_path/'clips'),use_nvenc=False,visual_enabled=False,segmentation_enabled=False,align_selected_clips=False,audio_normalize=False,trim_silence=False,punch_zoom=False)
    service=StudioService(tmp_path,cfg,autostart=False);doc=service.create(video(tmp_path/'source.mp4'));pid=doc['project_id']
    words=[{'word_id':0,'word':'Catat biaya usaha.','start':.2,'end':1.8,'probability':None,'speaker_id':'S1','speaker_provenance':'user_review'},{'word_id':1,'word':'Jadi simpan bukti transaksi.','start':2.2,'end':3.8,'probability':None,'speaker_id':'S1','speaker_provenance':'user_review'}]
    take=service.store.save_transcript(pid,{'words':words,'raw_words':words,'duration':4.,'runtime_receipt':{'provider':'authored_reference','inference_performed':False}})
    def seed(d):
        d.update(transcript_id=take,transcript_revision=1);service.add_candidates(d,[{'start':0.,'end':4.,'title':'Synthetic camera fixture','keywords':[]}])
    service.store.mutate(pid,0,identifier('m4-seed'),{},seed);cid=next(iter(service.store.get(pid)['clips']))
    service.test_pid=pid;service.test_cid=cid;return service

def controls(**kw):return {'detect_faces':False,'ocr':False,'active_speaker':'off','frame_budget':8,**kw}

def change(service,op,vid='portrait',revision=None,operation=None):
    doc=service.store.get(service.test_pid)
    return service.changes({'project_id':doc['project_id'],'clip_id':service.test_cid,'variant_id':vid,'expected_revision':doc['revision'] if revision is None else revision,'operation_id':operation or identifier('m4-op'),'operations':[op]})
