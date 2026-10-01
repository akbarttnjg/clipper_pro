"""User-facing upgrade contracts: breadth, text fidelity, safe layout and storage."""
import copy
import json
import re
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from clipper.config import Config, validate_overrides
from clipper import library_paths as paths, placement, story, typography
from clipper import transcript_correction as correction
from clipper.storage import read_json
from clipper.subtitle_edit import clean


def words(text, step=.4):
    return [{'word_id': i, 'word': s, 'start': i*step, 'end': i*step+step*.85, 'probability': .94}
            for i, s in enumerate(text.split())]


def test_cache_allowlist_preserves_every_durable_asset(tmp_path):
    work, out = tmp_path/'work', tmp_path/'clips'
    ident = 'a123456789ab'
    disposable = [work/ident/'cache/previews/key/output/preview.mp4',
                  work/ident/'cache/previews/key/work/renders/preview/voice.wav',
                  out/f'{ident}-preview-0-abc123-r1-v31.mp4',
                  work/ident/f'{ident}-preview-0-abc123-r1-v31'/'edit-plan.json']
    durable = [work/'studio-jobs'/f'{ident}.json', work/ident/'transcript.json',
               work/ident/'asr-cache.json', work/ident/'renders/clip/voice.wav',
               work/ident/'renders/clip/edit-plan.json', out/ident/'video/final.mp4',
               out/ident/'projects/export.zip', out/'my-preview-final.mp4']
    for p in disposable+durable:
        p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'keep-or-delete')
    outside = tmp_path/'outside.mp4'; outside.write_bytes(b'not cache')
    (work/ident/'cache/previews/key/link.mp4').symlink_to(outside)
    result = paths.clear_previews(work, out)
    assert result['deleted_files'] == len(disposable)
    assert all(not p.exists() for p in disposable)
    assert all(p.read_bytes() == b'keep-or-delete' for p in durable)
    assert outside.read_bytes() == b'not cache'


def test_paths_reject_escape_and_symlink(tmp_path):
    root = tmp_path/'out'; root.mkdir()
    (root/'link').symlink_to(tmp_path)
    for value in ('../secret', '/etc/passwd', 'link/secret'):
        with pytest.raises(ValueError): paths.contained(root, value)


def test_preview_key_reuses_only_identical_source_edits_and_assets(tmp_path):
    p = tmp_path/'source.mp4'; p.write_bytes(b'one')
    music = tmp_path/'music.wav'; music.write_bytes(b'music')
    cfg = Config(music_path=str(music)); ws = words('Kata yang sama.')
    clip = {'start': 0, 'end': 4, 'revision': 0}
    key = paths.fingerprint(p, ws, clip, cfg)
    assert key == paths.fingerprint(p, copy.deepcopy(ws), clip, cfg)
    assert key != paths.fingerprint(p, words('Kata berbeda.'), clip, cfg)
    assert key != paths.fingerprint(p, ws, clip, replace(cfg, glossary='XAUUSD = hausd'))
    assert key != paths.fingerprint(p, ws, {**clip, 'start': 1}, cfg)
    music.write_bytes(b'new music')
    assert key != paths.fingerprint(p, ws, clip, cfg)


def test_legacy_organization_is_idempotent_and_no_overwrite(tmp_path):
    cfg = Config(out_dir=str(tmp_path), job_id='a123456789ab')
    final = tmp_path/f'{cfg.job_id}-01-test-r0-v31.mp4'; final.write_bytes(b'video')
    subtitle = final.with_suffix('.ass'); subtitle.write_bytes(b'text')
    preview = tmp_path/f'{cfg.job_id}-preview-0-abc123-r1-v31.mp4'; preview.write_bytes(b'preview')
    moved = paths.organize_legacy(cfg)
    assert (tmp_path/moved[final.name]).read_bytes() == b'video'
    assert (tmp_path/moved[subtitle.name]).read_bytes() == b'text'
    assert preview.exists()
    final.write_bytes(b'conflicting newer file')
    assert not paths.organize_legacy(cfg)
    assert final.read_bytes() == b'conflicting newer file'


@pytest.mark.parametrize('punctuation', ['minimal', 'original'])
def test_cleanup_preserves_numbers_negation_and_source(punctuation):
    ws = words('bukan 1.250,50 atau 1,5% naik. XAUUSD, USD/JPY. -2,5%')
    original = copy.deepcopy(ws)
    result, _, _ = clean(ws, 'safe', punctuation)
    assert ws == original
    assert [w['word'] for w in result][:4] == ['bukan', '1.250,50', 'atau', '1,5%']
    assert result[-1]['word'] == '-2,5%'
    assert result[4]['word'] == ('naik' if punctuation == 'minimal' else 'naik.')
    assert result[6]['word'] == ('USD/JPY' if punctuation == 'minimal' else 'USD/JPY.')


def test_finance_alias_is_context_gated_and_manual_edit_wins():
    ws = words('trading emas pair hausd, bukan hasil pasti.')
    updated, changes = correction.correct_words(ws, Config())
    assert updated[3]['word'] == 'XAUUSD,' and changes[0]['before'] == 'hausd,'
    plain = words('Dia menyebut hausd, lalu pergi.')
    assert correction.correct_words(plain, Config())[0] == plain
    ws[3]['manually_edited'] = True
    assert correction.correct_words(ws, Config())[0][3]['word'] == 'hausd,'
    assert correction.correct_words(plain, Config(glossary='XAUUSD = hausd'))[0][2]['word'] == 'XAUUSD,'


@pytest.mark.parametrize('value', ['50 = 15', 'untung = tidak untung', 'pasti = mungkin', 'A = '+('b '*8), 'a'*61])
def test_glossary_cannot_rewrite_values_or_negation(value):
    with pytest.raises(ValueError): correction.parse_glossary(value)


def test_corrections_retain_raw_words_timestamps_and_change_log():
    ws = words('Trading emas di hausd.'); original = copy.deepcopy(ws)
    transcript = {'words': ws, 'duration': 4}
    result = correction.refine(transcript, Config())
    assert result['words'][-1]['word'] == 'XAUUSD.'
    assert result['raw_words'] == original and transcript['words'] == original
    assert result['words'][-1]['start'] == original[-1]['start']
    assert result['correction_report']['changes']
    disabled = correction.refine(result, Config(transcript_correction=False))
    assert disabled['words'] == original


def test_audio_recheck_requires_stronger_same_time_spelling():
    ws = words('Cara melakukan scalping dengan baik.')
    ws[2].update(word='scalpin', probability=.3)
    heard = copy.deepcopy(ws); heard[2].update(word='scalping', probability=.95)
    result, changes = correction.merge_recheck(ws, heard)
    assert result[2]['word'] == 'scalping' and len(changes) == 1
    heard[2]['start'] += 2
    assert correction.merge_recheck(ws, heard)[0] == ws
    ws[2]['word'] = '15'; heard[2].update(word='50', start=ws[2]['start'])
    assert correction.merge_recheck(ws, heard)[0] == ws
    ws[2]['word'] = 'tidak'; heard[2]['word'] = 'tindak'
    assert correction.merge_recheck(ws, heard)[0] == ws


def test_recheck_has_a_budget_and_no_overlapping_audio():
    ws = words('kata '*150, step=2)
    for w in ws: w['probability'] = .2
    ranges = correction.recheck_ranges(ws, 300, limit=12)
    assert len(ranges) == 12 and all(a >= 0 and b <= 300 for a, b in ranges)
    assert all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:]))


def test_same_vocabulary_at_different_times_is_not_automatically_duplicate():
    ws = words('emas naik saat pasar menguat dan risiko harus dibatasi. pasar emas harus dibatasi saat risiko naik dan menguat.', 1)
    a = {'start': 0, 'end': 10, 'rubric': {'value': 4}}
    b = {'start': 10, 'end': 20, 'rubric': {'value': 4}}
    assert len(story.distinct([a, b], ws, Config(num_clips=0))) == 2
    assert len(story.distinct([a, {**a, 'start': 1}], ws, Config(num_clips=0))) == 1


def candidate(i):
    return {'start': i*35, 'end': i*35+30, 'title': f'Cerita {i}', 'rubric': {'value': 5-i%3},
            'warnings': [], 'revision': 0, 'selection_source': 'local-topic-review'}


def test_selection_reviews_reserves_until_limit_of_verified_clips(tmp_path, monkeypatch):
    ws = words('contoh '+('topik '*300), 1)
    monkeypatch.setattr(story, 'request', lambda *args, **kwargs: [candidate(i) for i in range(6)])
    monkeypatch.setattr(story, 'ground', lambda raw, *args: raw)
    monkeypatch.setattr(story, 'duplicate', lambda a,b,w: a['start'] == b['start'])
    monkeypatch.setattr(story.editorial, 'release', lambda cfg: None)
    checked = []
    def review(c, *args):
        checked.append(c['start'])
        return {**c, 'intelligence': {'status': 'ready' if c['start'] >= 70 else 'needs_review'}}
    monkeypatch.setattr(story, 'review_candidate', review)
    monkeypatch.setattr(story.intelligence, 'ready', lambda c,*args: c.get('intelligence', {}).get('status') == 'ready')
    cfg = Config(work_dir=str(tmp_path), num_clips=3, search_depth='balanced')
    found = story.select({'words': ws, 'duration': 310}, cfg)
    assert len(found) == 3 and all(c['intelligence']['status'] == 'ready' for c in found)
    assert len(checked) > 3
    assert read_json(tmp_path/'selection-report.json')['candidate_pool'] == 6
    assert read_json(tmp_path/'selection-report.json')['reviewed'] == len(checked)


def test_failed_windows_do_not_abandon_later_source_and_are_retried(tmp_path, monkeypatch):
    segments = [{'id': i, 'start': i*100, 'end': i*100+99, 'text': 'Kalimat lengkap.'} for i in range(6)]
    monkeypatch.setattr(story, 'segments_from_words', lambda _: segments)
    monkeypatch.setattr(story, 'windows', lambda seg,cfg: [[s] for s in seg])
    seen=[]
    def request(block, *args, **kwargs):
        i=block[0]['id'];seen.append(i)
        if i in (1,3): raise ValueError('malformed')
        return []
    monkeypatch.setattr(story, 'request', request)
    monkeypatch.setattr(story.editorial, 'release', lambda c: None)
    cfg=Config(work_dir=str(tmp_path), search_depth='balanced')
    story.select({'words': [], 'duration': 600}, cfg)
    report=read_json(tmp_path/'selection-report.json')
    assert 5 in seen and report['missing_windows'] == [2,4]
    assert not report['coverage_complete'] and report['processed_windows'] == 4
    assert seen.count(1) == 2 and seen.count(3) == 2
    monkeypatch.setattr(story, 'request', lambda *args,**kwargs: [])
    story.select({'words': [], 'duration': 600}, cfg)
    assert read_json(tmp_path/'selection-report.json')['coverage_complete']


def test_adaptive_limit_can_return_more_than_ten_without_filling(tmp_path, monkeypatch):
    ws=words('x '*500)
    monkeypatch.setattr(story, 'request', lambda *args,**kwargs: [candidate(i) for i in range(14)])
    monkeypatch.setattr(story, 'ground', lambda raw,*args: raw)
    monkeypatch.setattr(story, 'duplicate', lambda a,b,w: a['start']==b['start'])
    monkeypatch.setattr(story.editorial, 'release', lambda cfg: None)
    cfg=Config(work_dir=str(tmp_path), num_clips=0, topic_review=False, search_depth='balanced')
    result=story.select({'words':ws, 'duration':600}, cfg)
    assert len(result)==14
    assert validate_overrides({'num_clips':'0'})['num_clips']==0
    assert validate_overrides({'num_clips':'800'})['num_clips']==100
    assert read_json(tmp_path/'selection-report.json')['reviewed'] == 0


@pytest.mark.parametrize('dark', [False, True])
def test_text_geometry_detects_light_and_dark_boards(dark):
    frame=np.full((360,640,3), 20 if dark else 245, np.uint8)
    color=(245,)*3 if dark else (20,)*3
    cv2.putText(frame, 'XAUUSD 1.250,50', (60,150), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
    boxes=placement.text_regions(frame)
    assert boxes and any(placement.overlap(b,[60,115,350,40])>300 for b in boxes)


def shot(boxes=()):
    return {'start':0,'end':5,'mode':'fit','rect':[0,0,1920,1080], 'face_rect':None,
            'caption_panel':None,'position':'bottom','zoom_at':None,
            'protected_source':list(boxes)}


@pytest.mark.parametrize('size', [(1920,1080), (1080,1920)])
def test_crowded_scenes_reserve_a_collision_free_band(size):
    cfg=Config(target_w=size[0],target_h=size[1],caption_style='magazine')
    s=shot([{'kind':'material','box':[0,0,1920,1080]}])
    placement.place_shot(s,cfg)
    assert s['caption_panel']
    assert all(placement.overlap(s['caption_panel'],b['box'])==0 for b in s['protected_output'])
    p={'shots':[s]}
    layout=typography.make_plan(words('Jangan abaikan risiko ketika trading XAUUSD.'), cfg, keywords=['risiko'], anchors=placement.caption_anchors(p))
    from clipper.qc import inspect_caption_plan
    assert inspect_caption_plan(layout,cfg)['passed']


def test_moving_faces_use_union_and_manual_placement_wins():
    cfg=Config(target_w=1920,target_h=1080)
    s=shot([{'kind':'face','box':[120,150,300,350]}, {'kind':'face','box':[1400,150,300,350]}])
    placement.place_shot(s,cfg)
    assert all(placement.overlap(s['caption_panel'],b['box'])==0 for b in s['protected_output'])
    manual=shot(s['protected_source'])
    placement.place_shot(manual,replace(cfg,caption_position='left'))
    assert manual['caption_panel'] is None and manual['placement']['mode']=='manual'


def test_broll_protection_and_shot_change_keep_subtitle_safe():
    cfg=Config(target_w=1920,target_h=1080,caption_style='magazine')
    first=shot();second={**shot(), 'start':5,'end':10}
    plan={'shots':[first,second], 'source':{'width':1920,'height':1080},
          'broll':[{'start':4,'end':6,'duration':2}]}
    placement.protect_broll(plan,cfg)
    assert plan['broll'][0]['image_height']==first['image_height']==second['image_height']
    ws=words('Pembahasan pertama kemudian lanjut pembahasan berikutnya.',step=1.1)
    layout=typography.make_plan(ws,cfg,anchors=placement.caption_anchors(plan))
    assert all(not(p['start']<5<p['end']) for p in layout['phrases'])


def app_fixture(tmp_path, monkeypatch):
    import app
    from fastapi.testclient import TestClient
    ident='a123456789ab'
    cfg=Config(work_dir=str(tmp_path/'work'/ident),out_dir=str(tmp_path/'clips'),job_id=ident)
    source=tmp_path/'source.mp4';source.write_bytes(b'source')
    st={'cfg':cfg,'media':str(source),'transcript':{'words':words('Cerita lengkap.'),'duration':10},
        'scored':[{'start':0,'end':10,'title':'Uji','revision':0}], 'edits':{},'clip_settings':{}}
    job={'status':'review','clips':[]}
    monkeypatch.setattr(app,'STATES',tmp_path/'work/studio-jobs')
    monkeypatch.setattr(app,'base_cfg',replace(cfg,work_dir=str(tmp_path/'work')))
    monkeypatch.setattr(app,'JOB_STATE',{ident:st});monkeypatch.setattr(app,'JOBS',{ident:job})
    return app,TestClient(app.app),ident,st,job


def test_cache_endpoint_rejects_active_process_and_preserves_final(tmp_path,monkeypatch):
    app,client,ident,st,job=app_fixture(tmp_path,monkeypatch)
    path=Path(st['cfg'].work_dir)/'cache/previews/key/output/a.mp4'
    path.parent.mkdir(parents=True);path.write_bytes(b'preview')
    job['status']='queued'
    assert client.post('/api/storage/clear-cache').status_code==409 and path.exists()
    job['status']='review'
    assert client.get('/api/storage').json()['files']==1
    assert client.post('/api/storage/clear-cache').json()['deleted_files']==1
    assert not path.exists() and Path(st['media']).is_file()


def test_identical_preview_does_not_render_twice(tmp_path,monkeypatch):
    app,client,ident,st,job=app_fixture(tmp_path,monkeypatch)
    calls=[]
    def render(media,ws,c,name,cfg,progress):
        calls.append(cfg)
        out=Path(cfg.out_dir);out.mkdir(parents=True,exist_ok=True);(out/'preview.mp4').write_bytes(b'preview')
        return {'file':'preview.mp4','revision':0,'render_version':'3.2','length':10}
    monkeypatch.setattr(app.pipeline,'render_clip',render)
    app.worker(ident,'previewing',[0]);app.worker(ident,'previewing',[0])
    assert len(calls)==1 and 'cache' in calls[0].out_dir
    assert client.get(job['preview']['url']).content==b'preview'
    st['edits'][0]=words('Kalimat yang dikoreksi.')
    app.worker(ident,'previewing',[0])
    assert len(calls)==2


def test_organized_output_and_legacy_urls_both_work(tmp_path,monkeypatch):
    app,client,ident,st,job=app_fixture(tmp_path,monkeypatch)
    folder=Path(st['cfg'].out_dir);folder.mkdir()
    name=ident+'-01-title-r0-v31.mp4';(folder/name).write_bytes(b'mp4')
    job['clips']=[{'file':name}]
    assert client.post('/api/storage/organize').json()['moved_files']==1
    assert client.get(job['clips'][0]['url']).content==b'mp4'
    assert client.get('/clips/'+name).content==b'mp4'
    assert client.get('/clips/%2E%2E/app.py').status_code==404


def test_discovery_appends_without_overwriting_manual_corrections(tmp_path,monkeypatch):
    app,client,ident,st,job=app_fixture(tmp_path,monkeypatch)
    st['edits'][0]=words('Koreksi manual.')
    existing=copy.deepcopy(st['scored'][0]);edits=copy.deepcopy(st['edits'])
    monkeypatch.setattr(story,'select',lambda *args: [existing,{**candidate(2),'start':20,'end':50}])
    app.worker(ident,'discovering')
    assert st['scored'][0]==existing and st['edits']==edits and len(st['scored'])==2


def test_locked_windows_preview_is_skipped_without_losing_other_files(tmp_path, monkeypatch):
    work, out = tmp_path/'work', tmp_path/'clips'
    folder = work/'a123456789ab'/'cache/previews/key'
    folder.mkdir(parents=True)
    locked, removable = folder/'locked.mp4', folder/'other.mp4'
    locked.write_bytes(b'locked'); removable.write_bytes(b'free')
    original_unlink = Path.unlink
    def unlink(p, *args, **kwargs):
        if p == locked:
            raise PermissionError('file is open in player')
        return original_unlink(p, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', unlink)
    result = paths.clear_previews(work, out)
    assert result == {'deleted_files': 1, 'freed_bytes': 4, 'skipped_files': ['locked.mp4']}
    assert locked.read_bytes() == b'locked' and not removable.exists()


def test_locked_final_does_not_interrupt_organization_or_new_render(tmp_path, monkeypatch):
    cfg = Config(out_dir=str(tmp_path), job_id='a123456789ab')
    legacy = tmp_path/f'{cfg.job_id}-01-test-r0-v31.mp4'
    previous = tmp_path/cfg.job_id/'video/clip-r0-v32.mp4'
    current = tmp_path/cfg.job_id/'video/clip-r1-v32.mp4'
    current.parent.mkdir(parents=True)
    for p in (legacy, previous, current): p.write_bytes(b'video')
    original_rename = Path.rename
    def rename(p, *args, **kwargs):
        if p in (legacy, previous): raise PermissionError('file is open in editor')
        return original_rename(p, *args, **kwargs)
    monkeypatch.setattr(Path, 'rename', rename)
    assert paths.organize_legacy(cfg) == {}
    paths.archive_previous(cfg, {'file': previous.relative_to(tmp_path).as_posix()},
                           {'file': current.relative_to(tmp_path).as_posix()})
    assert all(p.read_bytes() == b'video' for p in (legacy, previous, current))
