"""Real FFmpeg and local HTTP source tests; cloud/platform adapters use explicit doubles."""
import copy
import hashlib
import http.server
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from .test_m2_transcripts import M2Fixture,require_ffmpeg
from ..project_store import Conflict
from .. import source_imports as imp,media_context
from ..config import Config
from ..studio_service import StudioService
from ..dependency_cache import content_id
from ..storage import write_json


class TransferServer(http.server.BaseHTTPRequestHandler):
    body=b'';mode='normal';tag='"original"';ranges=[]
    def log_message(self,*args):pass
    def do_HEAD(self):
        self.send_response(200);self.send_header('Content-Length',str(len(type(self).body)));self.send_header('ETag',type(self).tag);self.end_headers()
    def do_GET(self):
        cls=type(self);cls.ranges.append((self.headers.get('Range'),self.headers.get('If-Range')));start=0
        if self.headers.get('Range') and cls.mode!='ignore':start=int(self.headers['Range'].split('=')[1].split('-')[0])
        self.send_response(206 if start else 200);self.send_header('Content-Length',str(len(cls.body)-start));self.send_header('ETag',cls.tag)
        if start:self.send_header('Content-Range',f'bytes {start}-{len(cls.body)-1}/{len(cls.body)}')
        self.end_headers();body=cls.body[start:]
        if cls.mode=='truncated':body=body[:len(body)//2]
        self.wfile.write(body);self.wfile.flush()
        if cls.mode=='truncated':self.close_connection=True


class DownloadCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):require_ffmpeg()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.audio=self.root/'s.wav';subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=2','-ar','48000',str(self.audio)],check=True)
        TransferServer.body=self.audio.read_bytes();TransferServer.mode='normal';TransferServer.tag='"original"';TransferServer.ranges=[]
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),TransferServer);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.request={'url':f'http://127.0.0.1:{self.server.server_port}/source.wav','max_bytes':1024**2};self.folder=self.root/'download'
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join(1);self.temp.cleanup()
    def partial(self,validator='"original"'):
        self.folder.mkdir();(self.folder/'source.wav.part').write_bytes(TransferServer.body[:1000]);write_json(self.folder/'transfer.json',{'url_hash':imp.fingerprint(self.request['url']),'validator':validator,'complete':False,'committed_bytes':1000,'partial_sha256':hashlib.sha256(TransferServer.body[:1000]).hexdigest()})
    def test_direct_complete_probe_and_checksum(self):
        d=imp.direct_download(self.request,self.folder);self.assertEqual(d['content_id'],content_id(self.audio));self.assertTrue(d['receipt']['complete_media_probed']);self.assertFalse((self.folder/'source.wav.part').exists())
    def test_validated_resume_reuses_only_verified_prefix(self):
        self.partial();d=imp.direct_download(self.request,self.folder);self.assertEqual(d['receipt']['resumed_bytes'],1000);self.assertEqual(d['content_id'],content_id(self.audio));self.assertEqual(TransferServer.ranges[-1],('bytes=1000-','"original"'))
    def test_changed_etag_restarts_download(self):
        self.partial('"previous"');d=imp.direct_download(self.request,self.folder);self.assertEqual(d['receipt']['resumed_bytes'],0);self.assertEqual(d['content_id'],content_id(self.audio))
    def test_resume_corrupt_local_prefix_restarts(self):
        self.partial();(self.folder/'source.wav.part').write_bytes(b'corrupt'+TransferServer.body[7:1000]);d=imp.direct_download(self.request,self.folder);self.assertEqual(d['receipt']['resumed_bytes'],0);self.assertEqual(d['content_id'],content_id(self.audio))
    def test_resume_discards_uncommitted_tail(self):
        self.partial()
        with (self.folder/'source.wav.part').open('ab') as f:f.write(b'uncommitted bytes')
        d=imp.direct_download(self.request,self.folder);self.assertEqual(d['receipt']['resumed_bytes'],1000);self.assertEqual(d['content_id'],content_id(self.audio))
    def test_server_ignores_range_restarts_without_duplicate_prefix(self):
        self.partial();TransferServer.mode='ignore';d=imp.direct_download(self.request,self.folder);self.assertEqual(d['receipt']['resumed_bytes'],0);self.assertEqual(Path(d['path']).read_bytes(),self.audio.read_bytes())
    def test_truncated_download_never_publishes_complete_source(self):
        TransferServer.mode='truncated'
        with self.assertRaises(Exception):imp.direct_download(self.request,self.folder)
        self.assertFalse((self.folder/'source.wav').is_file());self.assertFalse(json.loads((self.folder/'transfer.json').read_text())['complete'])
    def test_download_sha_mismatch_does_not_publish(self):
        with self.assertRaises(ValueError):imp.direct_download({**self.request,'sha256':'0'*64},self.folder)
        self.assertFalse((self.folder/'source.wav').is_file())
    def test_download_head_size_limit(self):
        with self.assertRaises(ValueError):imp.direct_download({**self.request,'max_bytes':1024},self.folder)
    def test_cached_complete_enforces_new_size_limit(self):
        imp.direct_download(self.request,self.folder)
        with self.assertRaises(ValueError):imp.direct_download({**self.request,'max_bytes':1024},self.folder)
    def test_cached_complete_enforces_new_expected_hash(self):
        imp.direct_download(self.request,self.folder)
        with self.assertRaises(ValueError):imp.direct_download({**self.request,'sha256':'0'*64},self.folder)
    def test_limits_reject_boolean(self):
        with self.assertRaises(ValueError):imp.limit_bytes(True)
    def test_url_credentials_and_non_http_rejected(self):
        for url in ('file:///etc/passwd','https://user:secret@example.com/video','javascript:alert(1)'):
            with self.assertRaises(ValueError):imp.url(url)


class MediaCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):require_ffmpeg()
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.cfg=Config(work_dir=str(self.root/'work'),out_dir=str(self.root/'clips'),use_nvenc=False,output_fps=30)
    def tearDown(self):self.temp.cleanup()
    def runff(self,args):subprocess.run(['ffmpeg','-v','error','-nostdin','-y',*map(str,args)],check=True,capture_output=True)
    def test_wav_mp3_flac_canonical_audio_and_no_video(self):
        for suffix in ('wav','mp3','flac'):
            p=self.root/('source.'+suffix);self.runff(['-f','lavfi','-i','sine=frequency=700:duration=2',p]);d=media_context.prepare(p,self.cfg);self.assertEqual(d['payload']['kind'],'audio');self.assertEqual(d['payload']['display_size'],[0,0]);self.assertEqual(d['payload']['source_content_id'],content_id(p));self.assertEqual(media_context.inspect(d['payload']['working_path'])['kind'],'audio')
    def test_multi_audio_track_selection_is_measurable(self):
        p=self.root/'multi.mkv';self.runff(['-f','lavfi','-i','color=s=320x180:r=30:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-f','lavfi','-i','sine=frequency=700:duration=2','-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-threads','2','-c:a','pcm_s16le',p]);cfg=copy.copy(self.cfg);cfg.audio_stream_index=2;d=media_context.prepare(p,cfg)
        import numpy as np
        raw=subprocess.run(['ffmpeg','-v','error','-i',d['payload']['working_path'],'-map','0:a:0','-ar','4000','-ac','1','-f','f32le','pipe:1'],capture_output=True,check=True).stdout;x=np.frombuffer(raw,dtype='<f4');frequency=np.argmax(abs(np.fft.rfft(x)))*4000/len(x);self.assertAlmostEqual(frequency,700,delta=3);self.assertEqual(d['payload']['selected_audio_index'],2)
    def test_invalid_audio_stream_rejected(self):
        p=self.root/'s.wav';self.runff(['-f','lavfi','-i','sine=duration=1',p]);cfg=copy.copy(self.cfg);cfg.audio_stream_index=9
        with self.assertRaises(ValueError):media_context.prepare(p,cfg)
    def test_proxy_identity_clock_and_corruption_rebuilt(self):
        p=self.root/'s.mp4';self.runff(['-f','lavfi','-i','testsrc2=s=320x180:r=30:d=2','-f','lavfi','-i','sine=duration=2','-c:v','libx264','-threads','2','-c:a','aac',p]);d=media_context.proxy(p,self.cfg);self.assertEqual(d['mapping'],'identity');self.assertAlmostEqual(d['duration'],2.,delta=.05);Path(d['path']).write_bytes(b'corrupt');again=media_context.proxy(p,self.cfg);self.assertEqual(d['content_id'],again['content_id'])
    def test_audio_proxy_is_explicitly_not_applicable(self):
        p=self.root/'s.wav';self.runff(['-f','lavfi','-i','sine=duration=1',p]);self.assertEqual(media_context.proxy(p,self.cfg)['status'],'not_applicable')
    def test_vfr_probe_and_canonical_source_clock(self):
        p=self.root/'vfr.mkv';self.runff(['-f','lavfi','-i','testsrc2=s=160x90:r=30:d=3','-f','lavfi','-i','sine=duration=3','-vf',"select='if(lt(t,1),1,not(mod(n,3)))'",'-fps_mode','vfr','-c:v','libx264','-threads','2','-c:a','aac',p]);d=media_context.prepare(p,self.cfg);self.assertTrue(d['payload']['vfr']['detected']);self.assertTrue(d['payload']['normalized']);self.assertEqual(media_context.inspect(d['payload']['working_path'])['fps'],{'numerator':30,'denominator':1})
    def test_rotation_is_applied_once_to_canonical_geometry(self):
        original=self.root/'base.mp4';rotated=self.root/'rotated.mp4';self.runff(['-f','lavfi','-i','testsrc2=s=160x90:r=30:d=2','-f','lavfi','-i','sine=duration=2','-c:v','libx264','-threads','2','-c:a','aac',original]);self.runff(['-display_rotation','90','-i',original,'-c','copy',rotated]);info=media_context.inspect(rotated);self.assertEqual(info['display_size'],[90,160]);result=media_context.prepare(rotated,self.cfg);decoded=media_context.inspect(result['payload']['working_path']);self.assertEqual(decoded['display_size'],[90,160]);self.assertEqual(decoded['rotation'],0)
    def test_hdr_conversion_records_actual_sdr_output(self):
        source=self.root/'hdr.mkv';self.runff(['-f','lavfi','-i','testsrc2=s=160x90:r=30:d=2','-f','lavfi','-i','sine=duration=2','-vf','format=yuv420p10le','-color_primaries','bt2020','-color_trc','smpte2084','-colorspace','bt2020nc','-c:v','ffv1','-c:a','pcm_s16le',source]);result=media_context.prepare(source,self.cfg);self.assertEqual(result['payload']['color_conversion'],'HDR_to_SDR_bt709');decoded=media_context.inspect(result['payload']['working_path']);self.assertEqual(decoded['color_transfer'],'bt709');self.assertAlmostEqual(decoded['duration'],2.,delta=.05)
    def test_editor_uses_proxy_only_when_original_identity_is_current(self):
        source=self.root/'base.mp4';self.runff(['-f','lavfi','-i','testsrc2=s=160x90:r=30:d=2','-f','lavfi','-i','sine=duration=2','-c:v','libx264','-threads','2','-c:a','aac',source]);service=StudioService(self.root,self.cfg,autostart=False);doc=service.create(source);proxy=media_context.proxy(source,service.config(doc));service.store.mutate(doc['project_id'],doc['revision'],'attach-proxy-test',{},lambda d:d['source'].update(edit_proxy=proxy));public=service.public(doc['project_id']);self.assertTrue(public['source']['proxy_used'])
        with source.open('ab') as f:f.write(b'original changed')
        public=service.public(doc['project_id']);self.assertTrue(public['source']['changed']);self.assertFalse(public['source'].get('proxy_used',False));service.queue.close()
    def test_non_media_cannot_be_project(self):
        p=self.root/'bad.wav';p.write_text('not media');service=StudioService(self.root,self.cfg,autostart=False)
        with self.assertRaises(subprocess.SubprocessError):service.create(p)


class SourceQueueCase(M2Fixture):
    __test__=True
    # Inherit the real source fixture, but not parent test methods.
    def batch(self,items=None,**kw):return self.service.imports.submit({'operation_id':'batch-'+str(time.time_ns()),'items':items or [{'kind':'local','path':str(self.source)}],**kw})
    def test_import_deduplicates_and_replays_operation(self):
        data={'operation_id':'fixed-batch-operation','items':[{'kind':'local','path':str(self.source)}]};a=self.service.imports.submit(data);b=self.service.imports.submit(data);self.assertEqual(a['items'][0]['id'],b['items'][0]['id']);other=self.batch();self.assertEqual(a['items'][0]['id'],other['items'][0]['id'])
    def test_import_independent_failure_does_not_stop_next_item(self):
        other=self.root/'other.wav';shutil.copyfile(self.source,other);batch=self.batch([{'kind':'local','path':str(self.source)},{'kind':'local','path':str(other)}]);self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.service.imports.process(batch['items'][0]['id'])
        result=self.service.imports.process(batch['items'][1]['id']);self.assertEqual(self.service.imports.get(batch['items'][0]['id'])['status'],'failed');self.assertEqual(self.service.imports.get(batch['items'][1]['id'])['status'],'completed');self.assertTrue(result['project_id'])
    def test_import_cancel_resume_and_original_project_unchanged(self):
        before=self.service.store.get(self.doc['project_id']);iid=self.batch()['items'][0]['id'];self.assertEqual(self.service.imports.cancel(iid)['status'],'canceled');self.assertEqual(self.service.imports.resume(iid)['status'],'queued');self.service.imports.process(iid);self.assertEqual(self.service.store.get(self.doc['project_id']),before)
    def test_source_changed_after_enqueue_is_rejected(self):
        iid=self.batch()['items'][0]['id'];self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.service.imports.process(iid)
    def test_import_maximum_50_bound(self):
        with self.assertRaises(ValueError):self.batch([{'kind':'local','path':str(self.source)}]*51)
    def test_import_boolean_settings_are_strict(self):
        with self.assertRaises(ValueError):self.batch(auto_analyze='yes')
    def test_folder_stability_dedup_and_persistent_history(self):
        folder=self.root/'watch';folder.mkdir();shutil.copyfile(self.source,folder/'video.wav');m=self.service.imports.save_monitor({'kind':'folder','path':str(folder),'enabled':False});self.assertEqual(self.service.imports.scan(m['id'],now=10)['added'],[]);first=self.service.imports.scan(m['id'],now=13)['added'];self.assertEqual(len(first),1);self.assertEqual(self.service.imports.scan(m['id'],now=20)['added'],[])
        other=StudioService(self.root,self.service.base,db_path=self.service.store.path,autostart=False);self.assertEqual(other.imports.scan(m['id'],now=30)['added'],[]);other.queue.close()
    def test_folder_changed_copy_waits_before_enqueue(self):
        folder=self.root/'watch';folder.mkdir();path=folder/'video.wav';shutil.copyfile(self.source,path);m=self.service.imports.save_monitor({'kind':'folder','path':str(folder),'enabled':False});self.service.imports.scan(m['id'],now=10)
        with path.open('ab') as f:f.write(b'new bytes')
        self.assertEqual(self.service.imports.scan(m['id'],now=13)['added'],[])
    def test_channel_declaration_filters_and_history(self):
        m=self.service.imports.save_monitor({'kind':'channel','url':'https://www.youtube.com/@fixture','own_channel_confirmed':True,'enabled':False,'title_contains':'Clip','date_after':'20261001'})
        with patch('clipper.source_imports.inspect_playlist',return_value={'items':[{'id':'a','url':'https://example.com/a','title':'Clip A','upload_date':'20261012'},{'id':'b','url':'https://example.com/b','title':'Other','upload_date':'20261012'}]}):
            self.assertEqual(len(self.service.imports.scan(m['id'])['added']),1);self.assertEqual(self.service.imports.scan(m['id'])['added'],[])
        self.assertIn('OAuth_ownership_pending',m['config']['ownership_status'])
    def test_channel_without_ownership_declaration_rejected(self):
        with self.assertRaises(ValueError):self.service.imports.save_monitor({'kind':'channel','url':'https://example.com/channel'})
    def test_platform_vod_adapter_checks_media_and_preserves_source_receipt(self):
        script=self.root/'platform_fixture.py';script.write_text('import sys,shutil,json\nfrom pathlib import Path\np=Path(sys.argv[sys.argv.index("-o")+1].replace("%(ext)s","wav"));shutil.copyfile('+repr(str(self.source))+',p);p.with_name("source.info.json").write_text(json.dumps({"id":"fixture-vod","extractor_key":"TwitchStream"}))\n')
        with patch('clipper.source_imports.yt_command',return_value=[sys.executable,str(script)]):result=imp.platform_download({'url':'https://example.com/vod','max_bytes':1024**2},self.root/'vod')
        self.assertEqual(result['receipt']['extractor'],'TwitchStream');self.assertEqual(result['content_id'],content_id(self.source));self.assertTrue(result['receipt']['complete_media_probed'])
    def test_optional_connectors_record_verified_provider_identity(self):
        class Response:
            def __init__(self,data):self.data=data
            def raise_for_status(self):pass
            def json(self):return self.data
        def response(address,**kwargs):
            if '/about' in address:return Response({'user':{'permissionId':'account-id','emailAddress':'fixture@example.invalid'}})
            if 'googleapis' in address:return Response({'id':'abcde','capabilities':{'canDownload':True}})
            if '/users/me' in address:return Response({'id':'zoom-account','email':'fixture@example.invalid'})
            return Response({'recording_files':[{'id':'rec','status':'completed','file_type':'M4A','download_url':'https://example.com/audio'}]})
        result={'path':str(self.source),'info':media_context.inspect(self.source),'content_id':content_id(self.source),'receipt':{'provider':'direct_http'}}
        with patch.dict('os.environ',{'CLIPPER_DRIVE_ACCESS_TOKEN':'token-secret','CLIPPER_ZOOM_ACCESS_TOKEN':'zoom-secret'}),patch('requests.get',side_effect=response),patch('clipper.source_imports.direct_download',side_effect=lambda *a,**kw:copy.deepcopy(result)):
            drive=imp.connector_download({'kind':'drive','file_id':'abcde'},self.root/'drive');zoom=imp.connector_download({'kind':'zoom','meeting_id':'123456'},self.root/'zoom')
        self.assertEqual(drive['receipt']['account_identity']['permission_id'],'account-id');self.assertEqual(zoom['receipt']['account_identity']['id'],'zoom-account');self.assertNotIn('token-secret',json.dumps(drive));self.assertTrue(zoom['receipt']['access_verified_by_provider'])
    def test_connector_no_token_is_actionable_and_does_not_make_project(self):
        with patch.dict('os.environ',{'CLIPPER_DRIVE_ACCESS_TOKEN':''}):
            with self.assertRaisesRegex(ValueError,'CLIPPER_DRIVE_ACCESS_TOKEN'):imp.connector_download({'kind':'drive','file_id':'abcde'},self.root/'drive')
    def test_multi_source_assembly_has_unique_origins_and_source_clock(self):
        before=self.service.store.get(self.doc['project_id']);rows=[{'project_id':self.doc['project_id'],'revision':self.doc['revision'],'start':0.,'end':2.},{'project_id':self.doc['project_id'],'revision':self.doc['revision'],'start':3.,'end':5.}];batch=self.batch([{'kind':'assembly','segments':rows}]);result=self.service.imports.process(batch['items'][0]['id']);derived=self.service.store.get(result['project_id']);words=self.service.store.transcript(derived['transcript_id'])['words'];self.assertEqual(len({w['word_id'] for w in words}),len(words));self.assertEqual(words[-1]['origin_project_id'],self.doc['project_id']);self.assertEqual(words[-1]['origin_source_id'],self.doc['source']['source_id']);self.assertEqual(self.service.store.get(self.doc['project_id']),before);self.assertAlmostEqual(derived['source']['info']['duration'],4.,delta=.03)
    def test_multi_source_stale_revision_rejected_before_queue(self):
        with self.assertRaises(Conflict):self.batch([{'kind':'assembly','segments':[{'project_id':self.doc['project_id'],'revision':0,'start':0.,'end':2.}]}])
    def test_recovery_marks_old_unlaunched_import_interrupted(self):
        iid=self.batch()['items'][0]['id']
        with self.service.store.connect() as db:db.execute("UPDATE m2_imports SET status='running',updated=? WHERE id=?",(time.time()-30,iid))
        self.service.imports.recover();self.assertEqual(self.service.imports.get(iid)['status'],'interrupted')
    def test_recovery_respects_worker_launch_grace(self):
        iid=self.batch()['items'][0]['id']
        with self.service.store.connect() as db:db.execute("UPDATE m2_imports SET status='running',updated=? WHERE id=?",(time.time(),iid))
        self.service.imports.recover();self.assertEqual(self.service.imports.get(iid)['status'],'running')
    def test_close_does_not_cancel_import_owned_by_another_session(self):
        iid=self.batch()['items'][0]['id']
        with self.service.store.connect() as db:db.execute("UPDATE m2_imports SET status='running',lease=? WHERE id=?",('different-owner:lease',iid))
        self.service.imports.close();self.assertEqual(self.service.imports.get(iid)['status'],'running')
    def test_background_worker_imports_real_source_and_shutdown(self):
        self.service.queue.autostart=True;iid=self.batch()['items'][0]['id'];deadline=time.monotonic()+10
        try:
            while self.service.imports.get(iid)['status'] in ('queued','running') and time.monotonic()<deadline:time.sleep(.05)
            self.assertEqual(self.service.imports.get(iid)['status'],'completed',self.service.imports.get(iid)['error'])
        finally:self.service.imports.close()
    def test_api_upload_accepts_audio_and_rejects_corrupt(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from ..api_studio import create_router
        app=FastAPI();app.include_router(create_router(self.service));client=TestClient(app);response=client.post('/api/studio/upload',files={'file':('audio.wav',self.source.read_bytes(),'audio/wav')});self.assertEqual(response.status_code,200);self.assertEqual(media_context.inspect(response.json()['path'])['kind'],'audio');bad=client.post('/api/studio/upload',files={'file':('bad.wav',b'bad bytes','audio/wav')});self.assertEqual(bad.status_code,400)

