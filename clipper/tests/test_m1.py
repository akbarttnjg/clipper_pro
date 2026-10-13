"""M1 behavior checks using real SQLite and the service, without model downloads.

Run: python -m unittest clipper.tests.test_m1 -v
These checks do not substitute for GPU, browser, or original-video acceptance.
"""
import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from clipper.config import Config
from clipper.contracts import fingerprint
from clipper.project_store import Conflict, ProjectStore
from clipper.studio_service import StudioService, identifier


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.svc = StudioService(root, Config(work_dir='work', out_dir='clips',
            visual_enabled=False, align_selected_clips=False, use_nvenc=False), autostart=False)
        source = root / 'source.mp4'
        source.write_bytes(b'controlled-source-not-a-real-video')
        self.svc.store.create({'name': 'M1 fixture', 'settings': asdict(self.svc.base),
            'source': {'path': str(source), 'source_id': 'controlled-source',
                       'info': {'duration': 40., 'audio_tracks': [{'index': 1}], 'display_size': [640, 360]}},
            'clips': {}, 'aliases': [], 'shared_corrections': {}, 'clip_corrections': {},
            'transcript_revision': 0, 'exports': []}, project_id='m1-project')
        self.words = [dict(word_id=i, word=w, start=float(i), end=i+.8, probability=None)
                      for i, w in enumerate(('model', 'xau', 'usd', 'bukan', '5', 'persen', 'CAFÉ', 'literal_%'))]
        self.take = self.svc.store.save_transcript('m1-project',
            {'words': self.words, 'raw_words': self.words, 'duration': 40.})
        def seed(doc):
            doc['transcript_id'] = self.take
            self.svc.add_candidates(doc, [dict(start=0., end=20., title='First', keywords=[]),
                                         dict(start=1., end=21., title='Second', keywords=[])])
        self.svc.store.mutate('m1-project', 0, 'm1-seed-01', {}, seed)
        self.cid, self.other = self.doc()['clips']

    def tearDown(self):
        self.svc.queue.close()
        self.temp.cleanup()

    def doc(self):
        return self.svc.store.get('m1-project')

    def edit(self, operations, cid=None, operation_id=None, revision=None):
        return self.svc.changes(dict(project_id='m1-project', clip_id=cid or self.cid,
            variant_id='portrait', expected_revision=self.doc()['revision'] if revision is None else revision,
            operation_id=operation_id or identifier('m1-edit'), operations=operations))

    def correct(self, word_id, after, scope='clip'):
        return self.edit([dict(op='correct_word', word_id=word_id, after=after, scope=scope,
            transcript_id=self.take, transcript_revision=self.doc()['transcript_revision'])])

    def merge(self, scope='clip'):
        value = dict(transcript_id=self.take, origin_word_ids=[1, 2], after='XAUUSD', provenance='user_approval')
        def merge(doc):
            target = doc['shared_corrections'] if scope == 'shared_utterance' else doc['clip_corrections'].setdefault(self.cid, {})
            target[fingerprint([self.take, [1, 2]])] = value
            doc['transcript_revision'] += 1
        self.svc.store.mutate('m1-project', self.doc()['revision'], identifier('merge'), {}, merge)

    def test_display_search_uses_current_correction_and_keeps_heard_immutable(self):
        self.correct(0, 'modal')
        page = self.svc.page('m1-project', self.cid, q='MODAL')
        self.assertEqual([w['word'] for w in page['words']], ['modal'])
        self.assertEqual(page['words'][0]['heard'], 'model')
        self.assertEqual(self.svc.page('m1-project', self.cid, q='model')['total'], 0)
        self.assertEqual(self.svc.store.transcript(self.take)['raw_words'], self.words)

    def test_heard_and_both_search_modes(self):
        self.correct(0, 'modal')
        self.assertEqual(self.svc.page('m1-project', self.cid, q='model', search_mode='heard')['total'], 1)
        self.assertEqual(self.svc.page('m1-project', self.cid, q='model', search_mode='both')['total'], 1)
        self.assertEqual(self.svc.page('m1-project', self.cid, q='modal', search_mode='heard')['total'], 0)
        with self.assertRaises(ValueError):
            self.svc.page('m1-project', self.cid, search_mode='bogus')

    def test_clip_overrides_do_not_leak_into_source_or_other_clip(self):
        self.correct(0, 'modal')
        self.assertEqual(self.svc.page('m1-project', self.cid, whole=True, q='modal')['total'], 0)
        self.assertEqual(self.svc.page('m1-project', self.other, q='modal')['total'], 0)
        self.merge('shared_utterance')
        self.assertEqual(self.svc.page('m1-project', self.other, q='XAUUSD')['total'], 1)
        self.assertEqual(self.svc.page('m1-project', self.cid, whole=True, q='XAUUSD')['total'], 1)

    def test_merged_phrase_is_paged_once_and_can_be_edited(self):
        self.merge()
        page = self.svc.page('m1-project', self.cid, offset=1, limit=1)
        self.assertEqual(page['total'], 7)
        self.assertEqual(page['next_offset'], 2)
        word = page['words'][0]
        self.assertEqual(word['word'], 'XAUUSD')
        self.assertEqual(word['heard'], 'xau usd')
        self.assertEqual(word['group_origin_word_ids'], [1, 2])
        self.correct(word['word_id'], 'emas')
        updated = self.svc.page('m1-project', self.cid, q='emas')['words'][0]
        self.assertEqual(updated['source_word_ids'], [1, 2])
        self.assertEqual(self.svc.page('m1-project', self.cid, q='XAUUSD')['total'], 0)

    def test_unicode_and_literal_search_not_sql_wildcards(self):
        self.assertEqual(self.svc.page('m1-project', self.cid, q='café')['total'], 1)
        self.assertEqual(self.svc.page('m1-project', self.cid, q='_%')['total'], 1)
        self.assertEqual(self.svc.page('m1-project', self.cid, q="' OR 1=1 --")['total'], 0)

    def test_projection_reused_for_settings_but_invalidated_by_text(self):
        original = self.svc.page('m1-project', self.cid)
        with patch.object(self.svc.store, 'transcript', wraps=self.svc.store.transcript) as transcript:
            self.edit([dict(op='settings', values={'accent_hex': '#00FF00'})])
            latest = self.svc.page('m1-project', self.cid)
            self.assertEqual(latest['view_key'], original['view_key'])
            transcript.assert_not_called()
        self.correct(0, 'modal')
        self.assertNotEqual(self.svc.page('m1-project', self.cid)['view_key'], original['view_key'])

    def test_manual_alignment_and_bounds_filter_are_effective(self):
        self.merge()
        self.edit([dict(op='align_words', scope='clip', transcript_id=self.take,
            transcript_revision=self.doc()['transcript_revision'], origin_word_ids=[1, 2], text='XAUUSD',
            words=[dict(word='XAUUSD', start=1.05, end=2.7)])])
        word = self.svc.page('m1-project', self.cid, q='XAUUSD')['words'][0]
        self.assertEqual(word['aligned_words'][0]['start'], 1.05)
        self.edit([dict(op='bounds', start=3., end=12., title='Cut')])
        self.assertEqual(self.svc.page('m1-project', self.cid, q='XAUUSD')['total'], 0)
        self.assertEqual(self.svc.page('m1-project', self.cid, whole=True)['total'], len(self.words))

    def test_reset_only_selected_manual_fields_and_inherit_project(self):
        self.edit([dict(op='settings', values={'caption_template_policy': 'manual', 'accent_hex': '#00FF00'})])
        self.edit([dict(op='reset_overrides', keys=['caption_template_policy'])])
        variant = self.doc()['clips'][self.cid]['variants']['portrait']
        self.assertNotIn('caption_template_policy', variant['override_keys'])
        self.assertNotIn('caption_template_policy', variant['settings'])
        self.assertEqual(variant['settings']['accent_hex'], '#00FF00')
        self.assertIn('accent_hex', variant['override_keys'])
        self.assertEqual(self.svc.config(self.doc(), self.cid, 'portrait').caption_template_policy,
                         self.doc()['settings']['caption_template_policy'])
        reset_revision = self.doc()['revision']
        timeline_revision = variant['timeline_revision']
        undone = self.svc.store.undo('m1-project', reset_revision, 'm1-undo-reset', reset_revision)
        self.assertEqual(self.svc.config(self.doc(), self.cid, 'portrait').caption_template_policy, 'manual')
        self.svc.store.redo('m1-project', undone['revision'], 'm1-redo-reset', undone['revision'])
        latest = self.doc()['clips'][self.cid]['variants']['portrait']
        self.assertEqual(latest['settings']['accent_hex'], '#00FF00')
        self.assertGreater(latest['timeline_revision'], timeline_revision)
        self.assertEqual(self.doc()['clips'][self.cid]['variants']['landscape']['override_keys'], [])

    def test_reset_recipe_field_and_reject_invalid_keys_atomically(self):
        self.edit([dict(op='style', style_id='lesson')])
        self.edit([dict(op='settings', values={'layout': 'fill'})])
        self.edit([dict(op='reset_overrides', keys=['layout'])])
        self.assertEqual(self.svc.config(self.doc(), self.cid, 'portrait').layout, 'stream')
        before = self.doc()
        for keys in ([], ['pexels_key'], ['unknown'], 'layout'):
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                self.edit([dict(op='reset_overrides', keys=keys)])
            self.assertEqual(self.doc()['revision'], before['revision'])

    def test_m0_render_snapshot_and_revision_guard_preserved(self):
        before = self.doc()
        queued = self.svc.enqueue('m1-project', 'render', self.cid, expected_revision=before['revision'])
        snapshot = copy.deepcopy(queued['request']['snapshot'])
        self.edit([dict(op='settings', values={'accent_hex': '#00FF00'})])
        self.assertEqual(self.svc.queue.get(queued['id'])['request']['snapshot'], snapshot)
        count = len(self.svc.queue.list())
        with self.assertRaises(Conflict):
            self.svc.enqueue('m1-project', 'render', self.cid, expected_revision=before['revision'])
        self.assertEqual(len(self.svc.queue.list()), count)
        canceled = self.svc.queue.cancel(queued['id'])
        self.assertEqual(canceled['status'], 'canceled')


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ProjectStore(Path(self.temp.name) / 'project.sqlite3')
        self.store.create({'settings': {'accent': 'white', 'font': 'main'}, 'transcript_revision': 0,
            'clips': {'c': {'variants': {'portrait': {'timeline_revision': 0, 'override_keys': []}}}}}, 'p')

    def tearDown(self):
        self.temp.cleanup()

    def edit(self, value, field='accent', operation_id=None, label='Edit'):
        def change(doc):
            doc['settings'][field] = value
            doc['transcript_revision'] += 1
        return self.store.mutate('p', self.store.get('p')['revision'], operation_id or identifier('edit'),
                                 {'field': field, 'value': value}, change, label)

    def test_undo_redo_and_monotonic_transcript_revision(self):
        first = self.edit('green')
        undone = self.store.undo('p', first['revision'], 'undo-m1-01', first['revision'])
        self.assertEqual(self.store.get('p')['settings']['accent'], 'white')
        self.assertEqual(self.store.get('p')['transcript_revision'], 2)
        redo = self.store.redo('p', undone['revision'], 'redo-m1-01', undone['revision'])
        self.assertEqual(self.store.get('p')['settings']['accent'], 'green')
        self.assertEqual(self.store.get('p')['transcript_revision'], 3)
        history = self.store.history('p')
        self.assertEqual(history[0]['action'], 'redo')
        self.assertTrue(history[0]['can_undo'])
        self.assertTrue(history[1]['can_redo'])
        self.assertFalse(history[1]['can_undo'])
        self.assertEqual(history[0]['target_revision'], undone['revision'])
        self.assertEqual(redo['revision'], 3)

    def test_undo_preserves_unrelated_later_field(self):
        first = self.edit('green')
        second = self.edit('serif', 'font')
        self.store.undo('p', second['revision'], 'undo-m1-02', first['revision'])
        self.assertEqual(self.store.get('p')['settings'], {'accent': 'white', 'font': 'serif'})

    def test_conflict_does_not_overwrite_later_value(self):
        first = self.edit('green')
        latest = self.edit('blue')
        with self.assertRaises(Conflict) as error:
            self.store.undo('p', latest['revision'], 'undo-m1-03', first['revision'])
        self.assertEqual(error.exception.paths, [['settings', 'accent']])
        self.assertEqual(self.store.get('p')['settings']['accent'], 'blue')
        self.assertEqual(self.store.get('p')['revision'], latest['revision'])

    def test_undo_redo_retries_are_idempotent(self):
        first = self.edit('green')
        args = ('p', first['revision'], 'undo-m1-04', first['revision'])
        undone = self.store.undo(*args)
        self.assertEqual(self.store.undo(*args), undone)
        args = ('p', undone['revision'], 'redo-m1-04', undone['revision'])
        redone = self.store.redo(*args)
        self.assertEqual(self.store.redo(*args), redone)
        self.assertEqual(self.store.get('p')['revision'], redone['revision'])

    def test_no_undo_job_or_empty_changes_and_no_redo_plain_edit(self):
        job = self.edit('green', label='Selesai: render')
        with self.assertRaises(ValueError):
            self.store.undo('p', job['revision'], 'undo-m1-05', job['revision'])
        self.assertFalse(self.store.history('p')[0]['can_undo'])
        edit = self.edit('blue')
        with self.assertRaises(ValueError):
            self.store.redo('p', edit['revision'], 'redo-m1-05', edit['revision'])
        empty = self.store.mutate('p', edit['revision'], 'empty-m1-05', {}, lambda doc: None)
        self.assertFalse(self.store.history('p')[0]['can_undo'])
        with self.assertRaises(ValueError):
            self.store.undo('p', empty['revision'], 'undo-empty-05', empty['revision'])

    def test_old_history_schema_is_compatible(self):
        edit = self.edit('green')
        with self.store.connect() as db:
            db.execute('DROP TABLE history_actions')
            db.execute('DROP TABLE word_view_rows')
            db.execute('DROP TABLE word_views')
        restored = ProjectStore(self.store.path)
        self.assertTrue(restored.history('p')[0]['can_undo'])
        restored.undo('p', edit['revision'], 'undo-legacy-01', edit['revision'])
        self.assertEqual(restored.get('p')['settings']['accent'], 'white')

    def test_large_projection_built_once_and_pagination_bounded(self):
        rows = [dict(word_id=i, word='word-'+str(i), heard='heard-'+str(i), start=i, end=i+.8) for i in range(10000)]
        with patch('builtins.input', side_effect=AssertionError('No interactive action')):
            calls = []
            def factory():
                calls.append(True)
                return rows
            first = self.store.effective_words_page('p', 'take', 'c', 'key', factory, limit=60)
            last = self.store.effective_words_page('p', 'take', 'c', 'key', factory, offset=9999, limit=2000)
            searched = self.store.effective_words_page('p', 'take', 'c', 'key', factory, q='heard-9876', search_mode='heard')
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(first['words']), 60)
        self.assertEqual(first['next_offset'], 60)
        self.assertEqual(last['total'], 10000)
        self.assertIsNone(last['next_offset'])
        self.assertEqual(searched['words'][0]['word_id'], 9876)

    def test_projection_cache_bounded_and_concurrent_pages_consistent(self):
        rows = [dict(word_id=1, word='A', heard='a', start=0., end=1.)]
        for i in range(7):
            self.store.effective_words_page('p', 'take', 'c', 'key'+str(i), lambda: rows)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM word_views').fetchone()[0], 4)
            self.assertEqual(db.execute('SELECT count(*) FROM word_view_rows').fetchone()[0], 4)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.store.effective_words_page('p', 'take', 'c', 'concurrent', lambda: rows), range(8)))
        self.assertTrue(all(result['total'] == 1 and result['words'][0]['word'] == 'A' for result in results))


if __name__ == '__main__':
    unittest.main()
