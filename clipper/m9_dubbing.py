"""Reviewed, single-voice dubbing of approved M2 cues on a source range.

Generated candidates are not editor projects until the user listens to A/B and
accepts their exact content identity. No voice cloning, lip sync or implicit
background preservation is claimed. Original source and transcript are immutable.
"""
import json
import re
import shutil
import time
import wave
import zipfile
from pathlib import Path
import numpy as np
from .dependency_cache import content_id
from .m8_contract import canonical, integer, only, text
from .m9_contract import artifact, atomic_bytes, checksum, number, safe_media, sha
from .m9_media import run, verify_media
from .project_store import Conflict

RATE = 48000
PLAN_FIELDS = ('project_id', 'expected_revision', 'clip_id', 'track_id', 'voice_id', 'audio_index', 'max_rate')
PLAN_REQUIRED = ('project_id', 'expected_revision', 'clip_id', 'track_id', 'voice_id')


def pcm(path):
    with wave.open(str(path), 'rb') as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, RATE, 'NONE'):
            raise ValueError('PCM dubbing harus mono 48 kHz 16 bit')
        return np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').copy()


def write_pcm(path, samples):
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(RATE)
        stream.writeframes(np.asarray(samples, dtype='<i2').tobytes())


def srt_time(seconds):
    millis = round(seconds * 1000)
    return f'{millis//3600000:02d}:{millis//60000%60:02d}:{millis//1000%60:02d},{millis%1000:03d}'


class Dubbing:
    def __init__(self, lab):
        self.lab = lab; self.m8 = lab.m8; self.service = lab.service

    def plan(self, actor, data):
        only(data, PLAN_FIELDS, PLAN_REQUIRED)
        pid = data['project_id']; self.m8.workspaces.require(actor, 'read', pid)
        doc = self.service.store.get(pid)
        revision = integer(data['expected_revision'], 'Revisi', 0, 2**53-1)
        if doc['revision'] != revision: raise Conflict(doc['revision'])
        clip = doc.get('clips', {}).get(data['clip_id'])
        if not clip: raise ValueError('Pilih klip sumber yang masih tersedia')
        a = number(clip['start'], 'Awal klip', 0, doc['source']['info']['duration'])
        b = number(clip['end'], 'Akhir klip', a, doc['source']['info']['duration'])
        if not .15 <= b-a <= 300: raise ValueError('Dubbing dibatasi 0,15–300 detik per klip sumber')
        if doc['source']['info'].get('color_transfer') in ('smpte2084', 'arib-std-b67'):
            raise ValueError('Dubbing video HDR belum didukung; siapkan turunan SDR yang ditinjau')
        meta = doc.get('translation_tracks', {}).get(data['track_id'])
        if not meta or meta.get('approved') is not True or meta['source_take'] != doc.get('transcript_id') or meta['source_revision'] != doc.get('transcript_revision'):
            raise ValueError('Pilih track terjemahan M2 yang sudah disetujui dan belum usang')
        track = self.service.store.transcript(data['track_id'])
        if track.get('source_id') != doc['source']['source_id']: raise ValueError('Identitas sumber track terjemahan berbeda')
        voice = self.lab.store.get(actor, data['voice_id'])
        if voice['kind'] != 'voice': raise ValueError('Pilih model suara Piper terdaftar')
        language = track['language']
        if language.replace('-', '_').split('_')[0] != voice['data']['language'].replace('-', '_').split('_')[0]:
            raise ValueError('Bahasa terjemahan berbeda dari model suara; tidak ada fallback otomatis')
        from .transcript_tracks import cues_from_words
        source = {canonical(c['origin_word_ids']): c for c in cues_from_words(self.service.transcript(doc)['words'])}
        rows = []; previous = a; seen = set(); covered = set()
        for cue in track.get('cues', []):
            if cue['end'] <= a or cue['start'] >= b: continue
            start = number(cue['start'], 'Awal cue', a, b); end = number(cue['end'], 'Akhir cue', start, b)
            if start < previous or end-start < .15 or end-start > 60:
                raise ValueError('Cue harus utuh, berurutan, tanpa overlap, dengan durasi 0,15–60 detik')
            origin = canonical(cue['origin_word_ids']); original = source.get(origin)
            if not original or original['start'] != start or original['end'] != end:
                raise ValueError('Waktu/asal cue berbeda dari transkrip aktif; tinjau ulang terjemahan')
            target = text(cue['text'], 'Teks terjemahan', 2000)
            if re.findall(r'\d+(?:[.,]\d+)*', original['text']) != re.findall(r'\d+(?:[.,]\d+)*', target):
                raise ValueError('Angka literal berubah pada track terjemahan')
            key = str(cue['cue_id'])
            if key in seen: raise ValueError('ID cue terjemahan harus unik')
            seen.add(key); covered.add(origin); previous = end
            rows.append({'cue_id': key, 'start': start, 'end': end, 'output_start': start-a, 'output_end': end-a,
                         'source_text': original['text'], 'text': target, 'origin_word_ids': cue['origin_word_ids'],
                         'speaker_id': original.get('speaker_id'), 'review_required': 'names_numbers_negation_units_glossary'})
        if not rows or len(rows) > 40 or sum(len(c['text']) for c in rows) > 12000:
            raise ValueError('Pilih 1–40 cue dan maksimal 12.000 karakter terjemahan')
        if covered != {key for key,c in source.items() if c['end']>a and c['start']<b}:
            raise ValueError('Terjemahan belum mencakup seluruh ucapan pada rentang klip')
        tracks = doc['source']['info']['audio_tracks']
        if not tracks: raise ValueError('Sumber harus mempunyai audio untuk pembanding A/B')
        selected = data.get('audio_index', self.service.config(doc).audio_stream_index)
        if selected == -1: selected = tracks[0]['index']
        selected = integer(selected, 'Stream audio A/B', 0, 1000)
        if selected not in [t['index'] for t in tracks]: raise ValueError('Stream audio A/B tidak tersedia')
        value = {'schema_version': 1, 'project_id': pid, 'input_revision': revision, 'clip_id': data['clip_id'],
                 'source_content_id': doc['source']['source_id'], 'transcript_id': doc['transcript_id'],
                 'transcript_revision': doc['transcript_revision'], 'track_id': data['track_id'], 'language': language,
                 'voice_id': voice['id'], 'voice_version': voice['version'],
                 'voice': {k: voice['data'][k] for k in ('name', 'engine', 'language', 'license', 'permission', 'executable_content_id', 'model_content_id', 'config_content_id')},
                 'source_range': [a, b], 'duration': b-a, 'audio_index': selected, 'cues': rows,
                 'glossary': text(doc['settings'].get('glossary', ''), 'Glossary', 20000, 0),
                 'max_rate': number(data.get('max_rate', 1.15), 'Percepatan maksimum', 1, 1.25),
                 'basis': 'continuous_source_range_before_editor_cuts_or_effects',
                 'audio_policy': 'synthetic_voice_only; silence_between_cues; original_background_not_preserved',
                 'speaker_policy': 'one_explicit_voice_for_all_cues', 'quality_acceptance': 'not_measured_requires_AB_listening',
                 'synthetic': True, 'lip_sync': False, 'paid_api_cost_usd': 0}
        return {**value, 'plan_digest': sha(canonical(value).encode())}

    def submit(self, actor, data):
        only(data, (*PLAN_FIELDS, 'plan_digest', 'reviewed_cue_ids', 'facts_reviewed', 'rights_reviewed'),
             (*PLAN_REQUIRED, 'plan_digest', 'reviewed_cue_ids', 'facts_reviewed', 'rights_reviewed'))
        self.m8.workspaces.require(actor, 'edit', data['project_id'])
        plan = self.plan(actor, {k: data[k] for k in PLAN_FIELDS if k in data})
        if checksum(data['plan_digest']) != plan['plan_digest']: raise ValueError('Rencana dubbing berubah; buka tinjauan terbaru')
        reviewed = data['reviewed_cue_ids']
        if not isinstance(reviewed, list) or any(not isinstance(k, str) for k in reviewed) or len(set(reviewed)) != len(reviewed) or set(reviewed) != {c['cue_id'] for c in plan['cues']}:
            raise ValueError('Periksa setiap cue terjemahan dalam rencana ini')
        if data['facts_reviewed'] is not True or data['rights_reviewed'] is not True:
            raise ValueError('Periksa nama, angka, negasi, istilah serta hak penggunaan suara dan materi')
        voice = self.lab.store.get(actor, plan['voice_id']); self.lab.providers.verify_voice(voice['data'])
        doc = self.service.store.get(plan['project_id'])
        if content_id(doc['source']['path'], fresh=True) != plan['source_content_id']: raise ValueError('Sumber dubbing berubah')
        return self.lab.enqueue(actor, 'dubbing_m9', {'project_id': plan['project_id'], 'input_revision': plan['input_revision'],
            'plan': plan, 'voice': voice['data'], 'source_path': doc['source']['path'],
            'source_kind': doc['source']['info']['kind'], 'name': doc['name']+' — dubbing '+plan['language'],
            'review': {'actor': actor.user_id, 'cue_ids': reviewed, 'facts_reviewed': True, 'rights_reviewed': True}})

    def accept(self, actor, data):
        only(data, ('id', 'expected_version', 'output_content_id', 'listened', 'timing_reviewed', 'facts_reviewed'),
             ('id', 'expected_version', 'output_content_id', 'listened', 'timing_reviewed', 'facts_reviewed'))
        item = self.lab.store.get(actor, data['id'], 'edit'); value = item['data']
        if item['kind'] != 'dubbing' or value['status'] != 'awaiting_listening': raise ValueError('Pilih kandidat dubbing yang menunggu tinjauan dengar')
        if item['version'] != data['expected_version']: raise Conflict(item['version'])
        if data['output_content_id'] != value['output']['content_id'] or any(data[k] is not True for k in ('listened', 'timing_reviewed', 'facts_reviewed')):
            raise ValueError('Dengarkan A/B, periksa timing dan pengucapan fakta pada hasil yang sama sebelum menerima')
        plan = value['plan']; doc = self.service.store.get(plan['project_id'])
        if doc['revision'] != plan['input_revision']: raise Conflict(doc['revision'])
        if content_id(doc['source']['path'], fresh=True) != plan['source_content_id']: raise ValueError('Sumber dubbing berubah')
        return self.lab.enqueue(actor, 'dubbing_accept_m9', {'project_id': plan['project_id'], 'input_revision': plan['input_revision'],
            'item_id': item['id'], 'item_version': item['version'], 'source_path': doc['source']['path'],
            'review': {'actor': actor.user_id, 'output_content_id': data['output_content_id'], 'listened': True, 'timing_reviewed': True, 'facts_reviewed': True}})

    def execute(self, job):
        snap = job['request']['m9']; actor = self.lab.operator(snap['workspace'])
        if job['kind'] == 'dubbing_accept_m9': return self.execute_accept(job, actor, snap)
        plan = snap['plan']; started = time.monotonic()
        folder = self.lab.root/'dubbing'/job['id']; folder.mkdir(parents=True, exist_ok=True)
        def check():
            self.lab.check_job(job)
            current = self.service.store.get(plan['project_id'])
            if current['revision'] != plan['input_revision']: raise Conflict(current['revision'])
            if self.lab.store.get(actor, plan['voice_id'])['version'] != plan['voice_version']: raise ValueError('Profil suara dubbing berubah')
            if time.monotonic()-started > 900: raise ValueError('Anggaran dubbing 900 detik terlampaui')
        check(); self.lab.providers.verify_voice(snap['voice'])
        if content_id(snap['source_path'], fresh=True) != plan['source_content_id']: raise ValueError('Sumber dubbing berubah')
        if shutil.disk_usage(folder).free < 1024**3 + int(plan['duration']*2*1024**2):
            raise ValueError('Ruang bebas dubbing memerlukan 1 GiB ditambah cadangan media 2 MiB/detik')
        mix = np.zeros(round(plan['duration']*RATE), dtype='<i2'); measurements = []; members = []
        for i, cue in enumerate(plan['cues']):
            check(); raw = folder/f'cue-{i:03d}-raw.wav'; fitted = folder/f'cue-{i:03d}-fitted.wav'
            begin = round(cue['output_start']*RATE); end = round(cue['output_end']*RATE); slot = (end-begin)/RATE
            info = self.lab.providers.synthesize(job, snap['voice'], cue['text'], raw, slot*plan['max_rate']+.1, timeout=min(120, max(1, 900-(time.monotonic()-started))))
            # Leave a small margin for FFmpeg atempo frame rounding. Never trim a
            # nonzero tail merely to force the utterance into its approved slot.
            rate = max(1., info['duration']/max(.01, slot-.03))
            if rate > plan['max_rate']+1e-9:
                raise ValueError('Cue '+cue['cue_id']+' terlalu panjang; ringkas terjemahan atau perluas timing lewat review M2')
            run(['-i', raw, '-vn', '-af', f'atempo={rate:.12f}', '-ar', str(RATE), '-ac', '1', '-c:a', 'pcm_s16le', fitted], check=check, timeout=120)
            samples = pcm(fitted)
            if not len(samples) or len(samples) > end-begin: raise ValueError('Cue '+cue['cue_id']+' belum muat; ekor suara tidak dipotong')
            peak = int(np.max(np.abs(samples.astype(np.int32))))
            if peak == 0: raise ValueError('Cue '+cue['cue_id']+' hanya berisi keheningan')
            mix[begin:begin+len(samples)] = samples
            measurements.append({'cue_id': cue['cue_id'], 'raw_seconds': info['duration'], 'atempo': rate,
                'output_start_sample': begin, 'output_end_sample': begin+len(samples), 'slot_end_sample': end,
                'truncated_samples': 0, 'peak_pcm': peak, 'possible_clipping_requires_listening': peak >= 32760})
            members.extend([raw, fitted])
        dubbed = folder/'dubbed.wav'; write_pcm(dubbed, mix); verify_media(dubbed, check=check)
        original = folder/'original.wav'
        run(['-ss', str(plan['source_range'][0]), '-i', snap['source_path'], '-t', str(plan['duration']),
             '-map', '0:'+str(plan['audio_index']), '-vn', '-ar', str(RATE), '-ac', '1', '-c:a', 'pcm_s16le', original], check=check)
        original_info = verify_media(original, check=check)
        if abs(original_info['duration']-plan['duration']) > .03: raise ValueError('Coverage audio A/B tidak mencakup seluruh rentang sumber')
        if snap['source_kind'] == 'video':
            output = folder/'dubbed-candidate.mp4'
            run(['-ss', str(plan['source_range'][0]), '-i', snap['source_path'], '-i', dubbed, '-t', str(plan['duration']),
                 '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
                 '-c:a', 'aac', '-ar', str(RATE), '-movflags', '+faststart', output], check=check)
        else: output = dubbed
        info = verify_media(output, check=check)
        if abs(info['duration']-plan['duration']) > .06: raise ValueError('Durasi kandidat dubbing berbeda dari rencana')
        subtitles = folder/'translated-cues.srt'
        atomic_bytes(subtitles, ('\n\n'.join(f"{i+1}\n{srt_time(c['output_start'])} --> {srt_time(c['output_end'])}\n{c['text']}" for i,c in enumerate(plan['cues']))+'\n').encode())
        members.extend([dubbed, original, subtitles]);
        if output != dubbed: members.append(output)
        check(); self.lab.providers.verify_voice(snap['voice'])
        if content_id(snap['source_path'], fresh=True) != plan['source_content_id']: raise ValueError('Sumber dubbing berubah')
        manifest = {'schema_version': 1, 'kind': 'dubbing9', 'synthetic': True, 'plan': plan, 'translation_review': snap['review'],
            'measurements': measurements, 'members': [artifact(p) for p in members], 'output': artifact(output),
            'quality_acceptance': 'awaiting_user_AB_listening_not_automatic', 'actual_neural_quality_measured': False,
            'runtime': 'registered_local_piper_cli', 'paid_api_cost_usd': 0, 'wall_seconds': round(time.monotonic()-started, 3),
            'not_source_evidence': True, 'automatic_ASR_or_word_alignment': False}
        manifest_path = folder/'dubbing9.json'; atomic_bytes(manifest_path, (canonical(manifest)+'\n').encode())
        archive = folder/'dubbing9.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
            for path in [*members, manifest_path]: zipped.write(path, path.name)
        with zipfile.ZipFile(archive) as zipped:
            if zipped.testzip(): raise ValueError('Arsip kandidat dubbing rusak')
        key = 'm9dub-'+sha(job['id'].encode())[:24]; now = self.m8.db.clock()
        value = {'name': snap['name'], 'project_id': plan['project_id'], 'status': 'awaiting_listening', 'synthetic': True,
            'plan': plan, 'output': artifact(output), 'program_path': str(output), 'original_path': str(original),
            'dubbed_path': str(dubbed), 'manifest_path': str(manifest_path), 'manifest_content_id': content_id(manifest_path, fresh=True),
            'archive_path': str(archive), 'archive_content_id': content_id(archive, fresh=True), 'not_source_evidence': True}
        result = {'item_id': key, 'requires_listening': True, 'editor_project_created': False,
                  'archive_path': str(archive), 'manifest_path': str(manifest_path), 'path': str(output), 'project_id': plan['project_id']}
        with self.m8.db.transaction() as db:
            check()
            db.execute('INSERT INTO m9_items VALUES(?,?,?,0,?,?,?)', (key, actor.workspace, 'dubbing', canonical(value), now, now))
            self.lab.finish(db, job, result)
        return result

    def execute_accept(self, job, actor, snap):
        self.lab.check_job(job); item = self.lab.store.get(actor, snap['item_id'], 'edit'); value = item['data']; plan = value['plan']
        if item['version'] != snap['item_version'] or value['status'] != 'awaiting_listening': raise Conflict(item['version'])
        manifest_path = safe_media(value['manifest_path'], self.lab.root)
        if content_id(manifest_path, fresh=True) != value['manifest_content_id']: raise ValueError('Manifest dubbing berubah')
        if content_id(safe_media(value['archive_path'], self.lab.root), fresh=True) != value['archive_content_id']:
            raise ValueError('Arsip dubbing berubah')
        manifest = json.loads(manifest_path.read_text()); folder = manifest_path.parent
        for member in manifest['members']:
            path = safe_media(folder/member['name'], folder)
            if content_id(path, fresh=True) != member['content_id']: raise ValueError('Media kandidat dubbing berubah')
        output = safe_media(value['program_path'], folder)
        if content_id(output, fresh=True) != snap['review']['output_content_id']: raise ValueError('Output dubbing yang didengar berbeda')
        if content_id(snap['source_path'], fresh=True) != plan['source_content_id']: raise ValueError('Sumber dubbing berubah')
        review_path = folder/'listening-review.json'
        atomic_bytes(review_path, (canonical({'plan_digest': plan['plan_digest'], **snap['review'], 'reviewed_at': self.m8.db.clock()})+'\n').encode())
        return self.lab.publish_derivative(job, actor, output, value['name'],
            {'kind': 'synthetic_dubbing9', 'manifest': str(manifest_path), 'listening_review': str(review_path),
             'source': {'project_id': plan['project_id'], 'source_content_id': plan['source_content_id'], 'source_range': plan['source_range']},
             'source_quote': False, 'lip_sync': False, 'synthetic': True}, manifest_path,
            source_guard={'project_id': plan['project_id'], 'revision': plan['input_revision'], 'content_id': plan['source_content_id']},
            item_id=item['id'], extra={'dubbing_version': item['version'], 'listening_reviewed': True, 'source_project_id': plan['project_id']})
