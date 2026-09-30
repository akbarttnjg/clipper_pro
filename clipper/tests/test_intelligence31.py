"""Editorial evidence, temporal integrity, rejection paths, and automatic workflow."""
import copy
import json
from dataclasses import replace
from pathlib import Path
import pytest
from clipper import boundaries, editplan, intelligence, stock, story, typography
from clipper.config import Config
from clipper.intelligence import core


def example(tmp_path):
    texts = [
        'Bagaimana menjual jasa saat skill belum cukup?',
        'Pelanggan membutuhkan hasil yang berguna untuk pekerjaannya.',
        'Jangan jualan outcome sebelum skill kamu cukup.',
        'Latih kemampuan melalui proyek kecil dan minta masukan pelanggan.',
        'Jadi tawarkan jasa sesuai kemampuan dan tingkatkan kualitasnya.',
    ]
    words = []
    for start, text in zip((0, 8, 14, 22, 30), texts):
        for i, word in enumerate(text.split()):
            words.append({'word_id': len(words), 'word': word, 'start': start + i*.4, 'end': start + i*.4 + .35})
    block = boundaries.segments_from_words(words)
    cfg = Config(work_dir=str(tmp_path), out_dir=str(tmp_path), min_clip_s=5, max_clip_s=60, cold_open=True)
    clip = boundaries.annotate({'start': 0., 'end': words[-1]['end'], 'title': 'Menjual jasa sesuai kemampuan',
        'reason': 'Ada langkah latihan dan batas kemampuan.', 'keywords': ['skill'], 'revision': 0,
        'selection_source': 'context-reviewed', 'rubric': {'value': 4, 'opening': 4, 'closure': 4}}, words, 60, verified=True)
    raw = {'verdict': 'complete', 'summary': 'Pembuka menanyakan batas menjual jasa; penutup menjawab sesuai kemampuan.',
        'opening': {'segment_id': 0, 'quote': texts[0]},
        'development': {'segment_id': 3, 'quote': texts[3]},
        'payoff': {'segment_id': 4, 'quote': texts[4]},
        'emphasis': [{'segment_id': 2, 'quote': 'Jangan jualan outcome'}],
        'hook_segment': 2, 'hook_reason': 'Pernyataan mandiri dengan syarat yang tetap utuh.',
        'risks': [], 'broll': 'contextual', 'broll_reason': 'Latihan proyek bisa diilustrasikan.'}
    clip['intelligence'] = core.assess(raw, clip, block, words, cfg)
    hook = clip['intelligence']['hook']
    clip['cold_open_span'] = [hook['source_start'], hook['source_end']]
    return clip, words, block, raw, cfg


def test_story_evidence_uses_source_timestamps_and_invalidates_changes(tmp_path):
    c, words, block, raw, cfg = example(tmp_path)
    assert intelligence.ready(c, words, cfg)
    assert c['intelligence']['evidence']['payoff']['source_start'] == 30
    assert not intelligence.ready({**c, 'end': c['end']-1}, words, cfg)
    assert not intelligence.ready(c, words, replace(cfg, audience='finance'))
    changed = copy.deepcopy(words); changed[-1]['word'] = 'lainnya.'
    assert not intelligence.ready(c, changed, cfg)
    assert intelligence.ready(c, words, replace(cfg, caption_scale=1.2))


@pytest.mark.parametrize('change', ['invented_quote', 'wrong_segment', 'unfinished', 'production', 'asr_number', 'missing_summary'])
def test_fluent_model_claim_cannot_bypass_evidence_and_local_checks(tmp_path, change):
    c, words, block, raw, cfg = example(tmp_path)
    if change == 'invented_quote': raw['payoff']['quote'] = 'Semua orang pasti sukses.'
    if change == 'wrong_segment': raw['payoff'] = raw['opening']
    if change == 'unfinished': raw['verdict'] = 'unfinished'
    if change == 'production': raw['risks'] = ['Ada arahan kepada editor.']
    if change == 'asr_number': words[10] = {**words[10], 'word': '100.000', 'end': words[10]['start']+7}
    if change == 'missing_summary': raw['summary'] = ''
    assessment = core.assess(raw, c, block, words, cfg)
    assert assessment['status'] == 'needs_review' and assessment['issues']


def test_complete_hook_moves_once_and_leaves_all_other_words_in_order(tmp_path):
    c, words, _, _, cfg = example(tmp_path)
    original = copy.deepcopy(words)
    plan = editplan.build(words, c, replace(cfg, trim_silence=False))
    assert plan['spans'][0]['kind'] == 'cold_open'
    ids = [w['word_id'] for w in plan['words']]
    assert len(ids) == len(set(ids)) == len(words)
    hook_ids = [w['word_id'] for w in words if 14 <= w['start'] < 18]
    assert ids == hook_ids + [w['word_id'] for w in words if w['word_id'] not in hook_ids]
    assert plan['duration'] == pytest.approx(c['end'], abs=1/30)
    assert words == original
    assert all(0 <= w['start'] < w['end'] <= plan['duration']+.001 for w in plan['words'])


def test_partial_or_final_hook_is_not_moved(tmp_path):
    c, words, _, _, cfg = example(tmp_path)
    for hook in ([14.4, 16], [30, c['end']]):
        plan = editplan.build(words, {**c, 'cold_open_span': hook}, replace(cfg, trim_silence=False))
        assert all(s['kind'] == 'body' for s in plan['spans'])
        assert plan['warnings']


def test_semantic_phrase_preserves_negation_and_survives_timeline_mapping(tmp_path):
    c, words, _, _, cfg = example(tmp_path)
    marked = intelligence.annotate_words(words, c, cfg)
    assert [w['word'] for w in marked if w.get('meaning_emphasis')] == ['Jangan', 'jualan', 'outcome']
    plan = editplan.build(marked, c, cfg)
    groups = typography.groups(plan['words'], cfg)
    phrase = next(g for g in groups if any(w.get('meaning_emphasis') for w in g))
    assert {'Jangan', 'jualan', 'outcome'} <= {w['word'] for w in phrase}
    emph = typography.emphasis_indices(phrase)
    assert {phrase[i]['word'] for i in emph} == {'Jangan', 'jualan', 'outcome'}
    assert not any(w.get('meaning_emphasis') for w in words)
    edited = {**c, 'title': 'Judul lain'}
    assert intelligence.annotate_words(words, edited, cfg) == words


def test_final_context_review_emits_grounded_contract_and_caches(tmp_path, monkeypatch):
    c, words, block, raw, cfg = example(tmp_path)
    response = {'start_segment': 0, 'end_segment': 4, 'title': c['title'], 'reason': c['reason'],
        'value': 4, 'opening': 4, 'closure': 4, 'complete': True, 'ending_evidence': block[-1]['text'],
        'hook_quote': '', 'keywords': ['skill'], 'intelligence': raw}
    calls = []
    monkeypatch.setattr(story, 'request', lambda *a: calls.append(a) or [response])
    transcript = {'words': words, 'duration': c['end']}
    result = story.review_candidate(c, transcript, cfg)
    assert intelligence.ready(result, words, cfg)
    assert result['revision'] == 1
    assert story.review_candidate(c, transcript, cfg) == result and len(calls) == 1


def test_failed_rereview_removes_old_success_and_invalidates_render(tmp_path, monkeypatch):
    c, words, _, _, cfg = example(tmp_path)
    monkeypatch.setattr(story, 'request', lambda *a: [])
    result = story.review_candidate(c, {'words': words, 'duration': c['end']}, cfg)
    assert not intelligence.ready(result, words, cfg)
    assert result['intelligence']['status'] == 'needs_review'
    assert result['revision'] == 1


def test_stock_semantic_selection_can_reject_all_and_never_uses_first_blindly(tmp_path, monkeypatch):
    cfg = Config()
    monkeypatch.setattr(stock, 'CACHE', tmp_path)
    monkeypatch.setattr(story.editorial, 'release', lambda *a: None)
    assets = [{'id': 'mine', 'title': 'Coal mining site'}, {'id': 'work', 'title': 'Person practicing coding on laptop'}]
    data = {'index': 1, 'reason': 'Latihan proyek mengembangkan keahlian.', 'metadata_quote': 'practicing coding'}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'response': json.dumps(data)}
    monkeypatch.setattr(stock.requests, 'post', lambda *a, **k: Response())
    result, _ = stock.choose(assets, 'person practicing coding', 'Tingkatkan skill melalui latihan.', cfg)
    assert result['id'] == 'work' and result['relevance']['visual_verified'] is False
    data.update(index=-1, reason='Tidak relevan.', metadata_quote='')
    assert stock.choose(assets, 'forest', 'Membahas hutan.', cfg)[0] is None
    data.update(index=0, metadata_quote='beautiful coding office')
    assert stock.choose(assets, 'office', 'Membahas kantor.', cfg)[0] is None


def test_preserve_speaker_avoids_stock_calls(tmp_path, monkeypatch):
    from clipper import illustrations
    c, words, _, _, cfg = example(tmp_path)
    c['intelligence']['broll'] = 'preserve_speaker'
    cfg = replace(cfg, broll_mode='auto')
    monkeypatch.setattr(stock, 'local_assets', lambda: pytest.fail('Should not search for stock'))
    assert illustrations.prepare(words, c, cfg)['status'] == 'skipped'


@pytest.mark.parametrize('mode', ['new', 'existing', 'all_rejected', 'export_error'])
def test_automatic_workflow_keeps_rejected_candidates_and_existing_outputs(tmp_path, monkeypatch, mode):
    import app
    from clipper import projects
    c, words, _, _, cfg = example(tmp_path)
    cfg = replace(cfg, workflow='automatic', job_id='auto-test')
    rejected = {**copy.deepcopy(c), 'title': 'Belum tuntas'}
    rejected['intelligence']['status'] = 'needs_review'
    rejected['intelligence']['issues'] = ['Janji belum dijawab.']
    candidates = [rejected] if mode == 'all_rejected' else [c, rejected]
    transcript = {'words': words, 'duration': c['end']}
    state = {'cfg': cfg, 'media': 'source.mp4', 'transcript': transcript, 'scored': candidates, 'edits': {}, 'clip_settings': {}}
    monkeypatch.setattr(app, 'STATES', tmp_path/'states')
    monkeypatch.setattr(app, 'JOB_STATE', {'auto-test': state})
    monkeypatch.setattr(app, 'JOBS', {'auto-test': {'status': 'review', 'clips': []}})
    monkeypatch.setattr(app.pipeline, 'analyze', lambda *a: (transcript, candidates))
    monkeypatch.setattr(app.pipeline.ffmpeg_util, 'filter_file_args', lambda *a: [])
    monkeypatch.setattr(story, 'review_candidate', lambda clip, *a: clip)
    monkeypatch.setattr(story.editorial, 'release', lambda *a: None)
    rendered, exported = [], []
    def render(media, ws, clip, name, config, progress):
        rendered.append(clip['title']); (tmp_path/'done.mp4').write_bytes(b'mp4')
        return {'file': 'done.mp4', 'revision': clip['revision'], 'render_version': app.pipeline.RENDER_VERSION}
    def export(items, config, progress):
        exported.extend(items)
        if mode == 'export_error': raise RuntimeError('Simulated export error')
        return {'zip': str(tmp_path/'editor.zip'), 'capcut_error': None}
    monkeypatch.setattr(app.pipeline, 'render_clip', render)
    monkeypatch.setattr(projects, 'export_bundle', export)
    app.worker('auto-test', 'automatic' if mode == 'existing' else 'analyzing', [0, 1] if mode == 'existing' else None)
    job = app.JOBS['auto-test']
    assert len(job['automation']['skipped']) == 1
    assert len(state['scored']) == len(candidates)
    if mode == 'all_rejected':
        assert not rendered and not exported and job['status'] == 'review'
    else:
        assert rendered == [c['title']] and len(exported) == 1
        assert job['status'] == 'done' and len(job['clips']) == 1
        if mode == 'export_error': assert 'export_error' in job and 'export' not in job


def test_manual_content_edit_marks_assessment_stale_but_style_edit_does_not(tmp_path, monkeypatch):
    import app
    from fastapi.testclient import TestClient
    c, words, _, _, cfg = example(tmp_path)
    monkeypatch.setattr(app, 'STATES', tmp_path/'states')
    monkeypatch.setattr(app, 'JOB_STATE', {'s': {'cfg': cfg, 'media': '', 'scored': [c],
        'transcript': {'words': words, 'duration': c['end']}, 'edits': {}, 'clip_settings': {}}})
    monkeypatch.setattr(app, 'JOBS', {'s': {'status': 'review', 'clips': []}})
    client = TestClient(app.app)
    data = {**c, 'words': words, 'settings': {'caption_scale': 1.2}}
    assert client.post('/api/editor/s/0', json=data).json()['clip']['intelligence']['status'] == 'ready'
    data['title'] = 'Judul yang berbeda'
    assert client.post('/api/editor/s/0', json=data).json()['clip']['intelligence']['status'] == 'stale'
