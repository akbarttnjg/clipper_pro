"""Real FFmpeg, actual writer serialization and moved-folder regression; no native editor claim."""
import copy,json,shutil,subprocess,sys,zipfile
from pathlib import Path
import pytest
from clipper import pipeline,delivery7
from clipper.config import Config
from clipper.artifact_store import verify
from clipper.delivery7_install import prepare,verify as verify_package
from clipper.dependency_cache import content_id
from clipper.delivery7_exchange import readback
from ._m4_fixture import video
from .test_m5_contract import words

@pytest.fixture(scope='module')
def rendered(tmp_path_factory):
    root=tmp_path_factory.mktemp('m7-media');source=video(root/'source.mp4');source_id=content_id(source,fresh=True);results=[]
    for i,(a,b) in enumerate([(0.,2.),(2.,4.)]):
        for ratio,w,h in [('portrait',180,320),('landscape',320,180)]:
            cfg=Config(work_dir=str(root/'work'/f'{i}-{ratio}'),out_dir=str(root/'out'),target_w=w,target_h=h,
                use_nvenc=False,visual_enabled=False,segmentation_enabled=False,align_selected_clips=False,audio_normalize=False,
                trim_silence=False,punch_zoom=False,broll_mode='off',illustration_mode='off',
                audio6={'enabled':True,'settings':{'normalize':True},'tracks':[]},finishing5={'enabled':True,'style':{},'decorations':[]})
            result=pipeline.render_clip(source,words(),{'start':a,'end':b,'title':f'Cerita {i+1}','keywords':['uji']},f'm7-{i}-{ratio}',cfg)
            result.update(clip_id='clip-'+str(i),variant_id=ratio);results.append(result)
    assert content_id(source,fresh=True)==source_id
    return root,source,results,cfg

@pytest.fixture(scope='module')
def delivery(rendered):
    root,source,results,cfg=rendered
    package=delivery7.build(results,cfg,{'alpha':True},project_id='project-authored',revision=9)
    (root/'package-result.json').write_text(json.dumps(package,indent=2));return package


def test_real_four_final_coverage_full_decode_codec_alpha_stems_and_revision(delivery,rendered):
    assert verify(delivery,fresh=True)
    data=json.loads(Path(delivery['delivery_manifest_path']).read_text());assert len(data['coverage'])==4
    assert {(r['clip_id'],r['variant_id']) for r in data['coverage']}=={(c,v) for c in ('clip-0','clip-1') for v in ('portrait','landscape')}
    assert len(data['merged'])==2 and all(len(r['members'])==2 for r in data['merged'])
    assert all(r['qc']['frames']==r['frames'] for r in data['merged'])
    for row in data['checks']:
        assert row['final_qc']['passed'] and row['final_qc']['full_decode']=='passed'
        assert row['final_qc']['streams']['video']['codec_name']=='h264'
        assert row['derived']['alpha']['pix_fmt']=='argb' and row['derived']['alpha']['sample_alpha_range'][0]==0
        assert row['derived']['alpha']['sample_alpha_range'][1]>0
        assert row['sidecar_qc']['formats']==['srt','vtt','ass','txt','json']
    assert all(r['native_status']=='not_tested' for r in data['editors'].values())
    for row in data['coverage']:
        folder=Path(delivery['folder'])/'Clips'/row['key']
        transcript=json.loads((folder/'Sidecars/transcript.json').read_text())
        assert transcript['reference']['requested_revision']==9
        assert transcript['reference']['output_content_id']==content_id(folder/'final.mp4',fresh=True)
        pub=json.loads((folder/'Publish/metadata.json').read_text());assert pub['delivered_output_content_id']==row['output_content_id']
        assert (folder/'Publish/cover.jpg').stat().st_size>100
        stems=json.loads((folder/'Stems/manifest.json').read_text());assert any(r['name']=='master' for r in stems['tracks'])
        assert all(r['qc']['full_decode']=='passed' for r in stems['tracks'])
    with zipfile.ZipFile(delivery['zip']) as z:assert z.testzip() is None


def test_native_candidates_use_one_exact_final_master_never_double_premaster(delivery):
    root=Path(delivery['folder']);p=json.loads((root/'Editors/CapCut/CLIP_01/draft_content.json').read_text())
    audio=[t for t in p['tracks'] if t['type']=='audio' and t['segments']]
    assert len(audio)==1 and audio[0]['name']=='master'
    plan=json.loads((root/'Editors/edit-plan-01.json').read_text());assert set(plan['audio']['stems'])=={'master'}
    assert plan['audio']['stems']['master']==plan['audio']['mix']
    manifest=json.loads((root/'Editors/manifest.json').read_text());assert manifest['audio_policy']=='single_final_master'
    for ratio in ('portrait','landscape'):
        merged=json.loads((root/'Merged'/ratio/'Editors/CapCut/CLIP_01/draft_content.json').read_text())
        assert len([t for t in merged['tracks'] if t['type']=='audio'])==1
        assert not any(t['type']=='text' and t['segments'] for t in merged['tracks'])
        assert len(merged['tracks'][0]['segments'])==2


def test_actual_extracted_package_moves_twice_checks_all_members_and_native_paths(delivery,tmp_path):
    unpack=tmp_path/'first extraction'
    with zipfile.ZipFile(delivery['zip']) as z:z.extractall(unpack)
    root=unpack/'Clipper_M7_Delivery'
    result=subprocess.run([sys.executable,'-I',str(root/'SIAPKAN_PAKET.py')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    verify_package(root)
    moved=tmp_path/'second location';shutil.move(root,moved);prepare(moved);verify_package(moved)
    from clipper.project_install import verify_package as verify_editor
    verify_editor(moved/'Editors','capcut');verify_editor(moved/'Editors','resolve')
    for ratio in ('portrait','landscape'):
        verify_editor(moved/'Merged'/ratio/'Editors','capcut')
    draft=json.loads((moved/'Editors/CapCut/CLIP_01/draft_content.json').read_text())
    for kind in ('videos','audios'):
        for row in draft['materials'][kind]:assert Path(row['path']).is_file() and Path(row['path']).is_relative_to(moved)
    for path in moved.rglob('*.otio'):
        for row in readback(path):assert (path.parent/row['path']).resolve().is_file()
    for path in moved.rglob('*.fcpxml'):
        from urllib.parse import urlparse,unquote
        for row in readback(path):assert Path(unquote(urlparse(row['path']).path)).is_file()


def test_missing_or_corrupt_member_and_incomplete_coverage_block(delivery,rendered,tmp_path):
    root,source,results,cfg=rendered
    with pytest.raises(ValueError,match='Coverage'):delivery7.build(results[:1],cfg,{'merged':False})
    copy=tmp_path/'changed';shutil.copytree(delivery['folder'],copy)
    target=next(copy.rglob('final.mp4'));target.write_bytes(b'broken')
    with pytest.raises(ValueError,match='hilang/berubah'):prepare(copy)
    assert verify(delivery,fresh=True)


def test_failed_decode_during_new_delivery_keeps_previous_complete_set(delivery,rendered,monkeypatch):
    _,_,results,cfg=rendered;before=content_id(delivery['zip'],fresh=True)
    def fail(*a,**k):raise ValueError('injected full decode failure')
    monkeypatch.setattr(delivery7.media,'qc',fail)
    with pytest.raises(ValueError,match='full decode failure'):delivery7.build(results,cfg,{'editors':[],'merged':False,'clean':False,'stems':False,'publish':False})
    assert content_id(delivery['zip'],fresh=True)==before and verify(delivery,fresh=True)


@pytest.mark.parametrize('profile',['balanced','archive','compact'])
def test_explicit_delivery_profiles_encode_measured_H264_AAC(rendered,tmp_path,profile):
    _,_,results,cfg=rendered;result=results[0];plan=json.loads(Path(result['plan_path']).read_text())
    from clipper.delivery7_media import final
    receipt=final(result['absolute_file'],tmp_path/(profile+'.mp4'),plan,cfg,profile)
    assert receipt['passed'] and receipt['full_decode']=='passed' and receipt['actual_encoder']=='libx264'
    assert receipt['encoding_policy']=='explicit_CPU_delivery_transcode'
    assert receipt['requested_profile']['crf']=={'balanced':18,'archive':16,'compact':23}[profile]


def test_caption_free_picture_preserves_reviewed_source_caption_cover(rendered,tmp_path):
    import numpy as np
    from clipper.delivery7_media import clean
    _,_,results,cfg=rendered;p=json.loads(Path(results[0]['plan_path']).read_text())
    p['captions'].setdefault('effective_style',{}).update(source_caption_mode='cover',source_captions=[{'rect':[0,0,100,100],'start':0.,'end':1.}])
    path=tmp_path/'clean-cover.mp4';report=clean(p,cfg,path);assert report['passed']
    def pixel(at):
        data=subprocess.run(['ffmpeg','-nostdin','-v','error','-ss',str(at),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
        return np.frombuffer(data,dtype=np.uint8).reshape(p['height'],p['width'],3)[p['height']//2-5:p['height']//2+5,p['width']//2-5:p['width']//2+5].mean(axis=(0,1))
    assert np.max(abs(pixel(.5)-[14,18,24]))<5
    assert np.max(abs(pixel(1.5)-[14,18,24]))>15


def test_actual_M4_extra_ratios_keep_canvas_and_complete_delivery_coverage(tmp_path):
    from .test_m5_contract import words as timed_words
    source=video(tmp_path/'source.mp4');results=[]
    for ratio,w,h in [('square',160,160),('feed',160,200),('custom',192,128)]:
        cfg=Config(work_dir=str(tmp_path/'work'/ratio),out_dir=str(tmp_path/'out'),target_w=w,target_h=h,
            use_nvenc=False,visual_enabled=False,segmentation_enabled=False,align_selected_clips=False,audio_normalize=False,
            trim_silence=False,punch_zoom=False,broll_mode='off',illustration_mode='off')
        r=pipeline.render_clip(source,timed_words('tes satu dan dua'),{'start':0.,'end':2.,'title':'Rasio tambahan','keywords':[]},ratio,cfg)
        r.update(clip_id='clip-extra',variant_id=ratio);results.append(r)
    package=delivery7.build(results,cfg,{'ratios':['square','feed','custom'],'editors':['capcut'],'merged':False,'clean':False,'stems':False,'publish':False})
    assert verify(package,fresh=True) and len(package['coverage'])==3
    for i,(ratio,w,h,ratio_label) in enumerate([('square',160,160,'1:1'),('feed',160,200,'4:5'),('custom',192,128,'original')],1):
        data=json.loads((Path(package['folder'])/f'Editors/CapCut/CLIP_{i:02d}/draft_content.json').read_text())
        assert data['canvas_config']['width']==w and data['canvas_config']['height']==h and data['canvas_config']['ratio']==ratio_label
