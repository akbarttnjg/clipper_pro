"""Acceptance for fixes found while building the installable Stage 3 release."""
import json
from types import SimpleNamespace
from clipper import speech_jobs, discovery
from clipper.config import Config


def test_neighbouring_selected_words_are_both_inside_checked_audio():
    words = [{'start': 4., 'end': 4.5}, {'start': 9., 'end': 9.5}]
    ranges = speech_jobs.selected_ranges(words, 30., 1)
    assert ranges == [[1., 12.5]]
    assert all(any(a <= w['start'] and w['end'] <= b for a, b in ranges) for w in words)


def test_long_selection_stays_bounded_without_losing_its_tail():
    words = [{'start': float(i), 'end': i+.5} for i in range(2, 56, 3)]
    ranges = speech_jobs.selected_ranges(words, 60., 24)
    assert all(b-a <= 20. for a, b in ranges)
    assert all(any(a <= w['start'] and w['end'] <= b for a, b in ranges) for w in words)


def test_semantic_duplicate_review_keeps_different_time_units(tmp_path, monkeypatch):
    proposals = [dict(start=0, end=30, title='Hari', story_kind='explanation', main_claim='Latihan setiap hari'),
                 dict(start=40, end=70, title='Minggu', story_kind='explanation', main_claim='Latihan setiap minggu')]
    monkeypatch.setattr(discovery.requests, 'post', lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {'response': json.dumps({'pairs': [{'keep': 0, 'duplicate': 1, 'reason': 'Topik latihan'}]})}))
    removed, _ = discovery.semantic_groups(proposals, Config(work_dir=str(tmp_path)))
    assert not removed
