"""Recoverable browser capture and progressive room uploads.

Chunks are byte fragments of one MediaRecorder stream, never assumed playable
alone. Clock estimates are explicit; no RTP sync or live latency claim is made.
"""
import hashlib
import json
import secrets
import shutil
import time
import zipfile
from pathlib import Path
from .m8_contract import AccessDenied, canonical, integer, only, text
from .m8_store import ident
from .m8_workspace import Actor
from .m9_contract import KINDS, MAX_CHUNK, MAX_CHUNKS, MAX_RECORDING, MIME, artifact, atomic_bytes, checksum, number, sha, spans
from .project_store import Conflict


class Recording:
    def __init__(self, lab):
        self.lab = lab;self.service = lab.service;self.store = lab.store;self.m8 = lab.m8
        self.root = lab.root/'recordings';self.root.mkdir(parents=True, exist_ok=True)

    def create(self, actor, data):
        only(data, ('name', 'mode', 'consent'), ('name', 'consent'))
        if data['consent'] is not True:raise ValueError('Persetujuan merekam diperlukan')
        mode = data.get('mode', 'local')
        if mode not in ('local', 'room'):raise ValueError('Mode rekaman tidak dikenal')
        return self.store.create(actor, 'recording', {'name': text(data['name'], 'Nama', 160), 'mode': mode,
            'status': 'capturing', 'clock_origin': self.m8.db.clock(), 'consent': {'host': True},
            'participants': {'host': {'name': 'Host', 'onstage': True, 'intervals': [[0., None]]}},
            'layout': {'primary_track': None, 'preserve_slides': True}, 'project_id': None,
            'quality_acceptance': 'device_and_network_test_required', 'jobs': []})

    def view(self, actor, key):
        row = self.store.get(actor, key)
        if row['kind'] != 'recording':raise ValueError('Item bukan rekaman')
        with self.service.store.connect() as db:
            tracks = [self.track(actor, t['id'], db=db) for t in db.execute('SELECT id FROM m9_tracks WHERE session_id=?', (key,)).fetchall()]
        row['tracks'] = tracks
        row['jobs'] = [self.service.queue.get(j) for j in row['data']['jobs'][-30:]]
        return row

    def invite(self, actor, data):
        only(data, ('id', 'name', 'expires_minutes'), ('id', 'name'))
        self.m8.workspaces.require(actor, 'manage')
        row = self.store.get(actor, data['id'], 'edit')
        if row['data']['mode'] != 'room' or row['data']['status'] != 'capturing':raise ValueError('Room tidak menerima tamu')
        participant = ident('guest');token = secrets.token_urlsafe(32);key = ident('invite')
        expires = self.m8.db.clock()+60*integer(data.get('expires_minutes', 120), 'Masa undangan', 1, 1440)
        def change(value, db):
            if len(value['participants']) >= 6:raise ValueError('Room lokal maksimal enam peserta')
            value['participants'][participant] = {'name': text(data['name'], 'Nama tamu', 100), 'onstage': False, 'intervals': []}
            db.execute('INSERT INTO m9_invites VALUES(?,?,?,?,?,0)', (key, row['id'], participant, sha(token.encode()), expires))
        self.store.change(actor, row['id'], row['version'], change)
        # Caller displays this once; token is absent from records/events/command receipts.
        return {'id': key, 'participant': participant, 'expires': expires, 'join_fragment': '#room='+row['id']+'&token='+token,
                'network_requirement': 'same-origin HTTPS and explicit server workspace configuration outside localhost',
                'live_monitoring': False}

    def guest(self, token, session_id):
        if not isinstance(token, str) or not 30 <= len(token) <= 100:raise AccessDenied('Undangan tidak valid')
        with self.service.store.connect() as db:
            invite = db.execute('SELECT i.*,s.workspace,s.data FROM m9_invites i JOIN m9_items s ON s.id=i.session_id WHERE i.token_hash=? AND i.session_id=?',
                                (sha(token.encode()), session_id)).fetchone()
        if not invite or invite['revoked'] or invite['expires'] <= self.m8.db.clock():raise AccessDenied('Undangan kedaluwarsa atau dicabut')
        value = json.loads(invite['data'])
        if value['status'] != 'capturing':raise AccessDenied('Room telah ditutup untuk unggahan')
        return {'actor': self.lab.operator(invite['workspace']), 'participant': invite['participant'], 'session_id': session_id,
                'name': value['name'], 'clock_origin': value['clock_origin'], 'server_time': self.m8.db.clock()}

    def stage(self, actor, data):
        only(data, ('id', 'expected_version', 'participant', 'onstage'), ('id', 'expected_version', 'participant', 'onstage'))
        if type(data['onstage']) is not bool:raise ValueError('Onstage harus boolean')
        if data['participant']=='host':raise ValueError('Kontrol backstage berlaku pada tamu; host tetap menjadi track utama')
        def change(value, db):
            if value['status'] != 'capturing':raise ValueError('Room sudah ditutup')
            p = value['participants'][data['participant']]
            now = max(0., self.m8.db.clock()-value['clock_origin'])
            if p['onstage'] != data['onstage']:
                if data['onstage']:p['intervals'].append([now, None])
                else:p['intervals'][-1][1] = now
                p['onstage'] = data['onstage']
        return self.store.change(actor, data['id'], data['expected_version'], change)

    def revoke(self, actor, data):
        only(data, ('id', 'participant'), ('id', 'participant'))
        self.store.get(actor, data['id'], 'edit')
        with self.m8.db.transaction() as db:
            db.execute('UPDATE m9_invites SET revoked=1 WHERE session_id=? AND participant=?', (data['id'], data['participant']))
        return {'revoked': True}

    def add_track(self, actor, data, participant='host'):
        only(data, ('id', 'kind', 'mime', 'started_at', 'clock_uncertainty_ms', 'consent'), ('id', 'kind', 'mime', 'started_at', 'consent'))
        if data['consent'] is not True:raise ValueError('Persetujuan pemilik track diperlukan')
        row = self.store.get(actor, data['id'], 'edit');value = row['data']
        if row['kind'] != 'recording' or value['status'] != 'capturing':raise ValueError('Rekaman tidak aktif')
        kind = text(data['kind'],'Jenis track',30);mime = text(data['mime'],'MIME',100).split(';', 1)[0]
        if kind not in KINDS or mime not in MIME:raise ValueError('Jenis track/MIME tidak didukung')
        if participant not in value['participants']:raise AccessDenied('Peserta tidak terdaftar')
        start = number(data['started_at'], 'Waktu mulai', value['clock_origin']-5, self.m8.db.clock()+5)
        uncertainty = number(data.get('clock_uncertainty_ms', 1000), 'Ketidakpastian jam', 0, 30000)
        key = ident('track');metadata = {'offset': max(0., start-value['clock_origin']), 'clock_uncertainty_ms': uncertainty,
            'status': 'open', 'expected_chunks': None, 'consent': True, 'bytes': 0, 'manual_offset': False}
        with self.m8.db.transaction() as db:
            # Recheck under the same lock used by finalize/chunk writers.
            self.store.get(actor, row['id'], 'edit', db)
            active = json.loads(db.execute('SELECT data FROM m9_items WHERE id=?', (row['id'],)).fetchone()['data'])
            if active['status'] != 'capturing':raise ValueError('Rekaman telah ditutup')
            if db.execute('SELECT COUNT(*) n FROM m9_tracks WHERE session_id=?', (row['id'],)).fetchone()['n'] >= 18:raise ValueError('Maksimal 18 track')
            db.execute('INSERT INTO m9_tracks VALUES(?,?,?,?,?,0,?)', (key, row['id'], participant, kind, mime, canonical(metadata)))
        return self.track(actor, key)

    def track(self, actor, key, participant=None, db=None):
        if db is None:
            with self.service.store.connect() as connection:return self.track(actor, key, participant, connection)
        row = db.execute('SELECT * FROM m9_tracks WHERE id=?', (key,)).fetchone()
        if not row:raise KeyError('Track tidak ditemukan')
        self.store.get(actor, row['session_id'], db=db)
        if participant is not None and row['participant'] != participant:raise AccessDenied('Track milik peserta lain')
        result = dict(row);result['data'] = json.loads(result['data'])
        result['chunks'] = [dict(r) for r in db.execute('SELECT seq,sha256,bytes,data FROM m9_chunks WHERE track_id=? ORDER BY seq', (key,))]
        for chunk in result['chunks']:chunk['data'] = json.loads(chunk['data'])
        return result

    def chunk(self, actor, key, seq, data, digest, elapsed, participant=None):
        integer(seq, 'Urutan chunk', 0, MAX_CHUNKS-1);checksum(digest)
        elapsed = number(elapsed, 'Jam monotonic chunk', 0, 12*3600)
        if not data or len(data) > MAX_CHUNK:raise ValueError('Chunk harus 1 byte sampai 25 MiB')
        if sha(data) != digest:raise ValueError('SHA chunk tidak cocok')
        with self.m8.db.transaction() as db:
            row = self.track(actor, key, participant, db);self.store.get(actor, row['session_id'], 'edit', db)
            session = self.store.get(actor, row['session_id'], db=db)['data']
            old = db.execute('SELECT * FROM m9_chunks WHERE track_id=? AND seq=?', (key, seq)).fetchone()
            path = self.root/row['session_id']/key/(str(seq).zfill(6)+'.chunk')
            if old:
                if old['sha256'] != digest or old['bytes'] != len(data) or json.loads(old['data'])['elapsed'] != elapsed:raise ValueError('Urutan chunk telah mempunyai isi/jam berbeda')
                if not path.is_file() or sha(path.read_bytes()) != digest:atomic_bytes(path, data)
                return {'seq': seq, 'sha256': digest, 'durable': True, 'duplicate': True}
            if row['data']['status'] != 'open' or session['status'] != 'capturing':raise ValueError('Track/room sudah ditutup')
            # Limits include all participants, not only the current track.
            used = db.execute('SELECT COALESCE(SUM(c.bytes),0) n FROM m9_chunks c JOIN m9_tracks t ON t.id=c.track_id WHERE t.session_id=?', (row['session_id'],)).fetchone()['n']
            if used+len(data) > MAX_RECORDING:raise ValueError('Batas rekaman 30 GiB tercapai')
            if shutil.disk_usage(self.root).free < len(data)+1024**3:raise ValueError('Ruang kosong kurang dari cadangan 1 GiB')
            previous = db.execute('SELECT seq,data FROM m9_chunks WHERE track_id=? AND seq!=?', (key, seq)).fetchall()
            if any((p['seq'] < seq and json.loads(p['data'])['elapsed'] > elapsed) or (p['seq'] > seq and json.loads(p['data'])['elapsed'] < elapsed) for p in previous):raise ValueError('Jam chunk tidak berurutan')
            atomic_bytes(path, data)  # fsync and replace precede the SQLite receipt/HTTP acknowledgement.
            db.execute('INSERT INTO m9_chunks VALUES(?,?,?,?,?)', (key, seq, digest, len(data), canonical({'elapsed': elapsed})))
            row['data']['bytes'] += len(data)
            db.execute('UPDATE m9_tracks SET data=?,version=version+1 WHERE id=?', (canonical(row['data']), key))
        return {'seq': seq, 'sha256': digest, 'durable': True, 'duplicate': False}

    def seal(self, actor, data, participant=None):
        only(data, ('track_id', 'expected_chunks', 'recover_prefix'), ('track_id', 'expected_chunks'))
        count = integer(data['expected_chunks'], 'Jumlah chunk', 1, MAX_CHUNKS)
        recover = data.get('recover_prefix', False)
        if type(recover) is not bool:raise ValueError('Recover prefix harus boolean')
        if recover and participant is not None:raise AccessDenied('Pemulihan prefix memerlukan host')
        with self.m8.db.transaction() as db:
            row = self.track(actor, data['track_id'], participant, db);self.store.get(actor, row['session_id'], 'edit', db)
            seqs = [r['seq'] for r in row['chunks']]
            if (not recover and seqs != list(range(count))) or (recover and seqs[:count] != list(range(count))):raise ValueError('Chunk belum lengkap/berurutan. Pulihkan unggahan sebelum menutup track.')
            if row['data']['status'] != 'open':
                if row['data']['expected_chunks'] == count and row['data']['recovered_prefix'] == recover:return row
                raise ValueError('Track sudah ditutup dengan manifest berbeda')
            row['data'].update(status='sealed', expected_chunks=count, recovered_prefix=recover)
            db.execute('UPDATE m9_tracks SET data=?,version=version+1 WHERE id=?', (canonical(row['data']), row['id']))
        return self.track(actor, row['id'], participant)

    def offset(self, actor, data):
        only(data, ('track_id', 'offset', 'reason'), ('track_id', 'offset', 'reason'))
        with self.m8.db.transaction() as db:
            row = self.track(actor, data['track_id'], db=db);session = self.store.get(actor, row['session_id'], 'edit', db)
            if session['data']['status'] != 'capturing':raise ValueError('Offset sudah dibekukan untuk finalisasi')
            row['data'].update(offset=number(data['offset'], 'Offset', 0, 12*3600), manual_offset=True, offset_reason=text(data['reason'], 'Alasan', 1000))
            db.execute('UPDATE m9_tracks SET data=?,version=version+1 WHERE id=?', (canonical(row['data']), row['id']))
        return self.track(actor, row['id'])

    def finalize(self, actor, data):
        only(data, ('id', 'expected_version', 'primary_track', 'camera_track','sync_reviewed'), ('id', 'expected_version', 'primary_track', 'sync_reviewed'))
        row = self.view(actor, data['id'])
        if data['sync_reviewed'] is not True:raise ValueError('Periksa sinkronisasi dan backstage dahulu')
        if row['data']['status'] != 'capturing':raise ValueError('Finalisasi sudah diajukan; periksa antrean')
        tracks = row['tracks'];primary = next((t for t in tracks if t['id'] == data['primary_track']), None)
        if not primary or primary['participant'] != 'host':raise ValueError('Pilih track host sebagai visual/audio utama')
        camera=next((t for t in tracks if t['id']==data.get('camera_track')),None)
        if data.get('camera_track') and (not camera or camera['kind']!='camera' or camera['participant']!='host' or primary['kind'] not in ('screen','slides')):
            raise ValueError('Layout materi + speaker memerlukan track layar/slide dan kamera host terpisah')
        if not tracks or any(t['data']['status'] != 'sealed' for t in tracks):raise ValueError('Tutup semua track sebelum finalisasi')
        if shutil.disk_usage(self.root).free < sum(t['data']['bytes'] for t in tracks)*3+1024**3:
            raise ValueError('Ruang disk belum cukup untuk track, program dan arsip final; fragment original dipertahankan')
        if not any(t['kind'] in ('microphone', 'system_audio') or t['mime'].startswith('audio/') for t in tracks):raise ValueError('Sediakan track audio terpisah')
        def change(value, db):
            if value['status'] != 'capturing':raise ValueError('Finalisasi sudah berjalan')
            actual=[(r['id'],r['version']) for r in db.execute('SELECT id,version FROM m9_tracks WHERE session_id=? ORDER BY id',(row['id'],))]
            if actual!=sorted((t['id'],t['version']) for t in tracks):raise ValueError('Daftar/offset track berubah; periksa ulang sebelum finalisasi')
            value.update(status='finalizing', sync_reviewed=True)
            value['layout']['primary_track'] = primary['id']
            value['layout']['camera_track'] = camera['id'] if camera else None
            now = max(0., self.m8.db.clock()-value['clock_origin'])
            for p in value['participants'].values():
                if p['onstage']:p['intervals'][-1][1] = now;p['onstage'] = False
            from dataclasses import asdict
            snapshot = {'session_id': row['id'], 'workspace': actor.workspace, 'tracks': tracks, 'session': value, 'input_version': row['version']+1,
                'config':{k:v for k,v in asdict(self.service.base).items() if k!='pexels_key'}}
            # Insert job in the SAME SQLite transaction as the state transition.
            jobid = ident('job');now = time.time();request = {'m9': snapshot, 'queue_key': sha(canonical(snapshot).encode())}
            self.m8.workspaces.reserve(db,actor,'job',jobid)
            db.execute('INSERT INTO jobs(id,project_id,kind,target,status,request,created,updated,message) VALUES(?,?,?,?,?,?,?,?,?)',
                (jobid, row['id'], 'recording_m9', '{}', 'queued', canonical(request), now, now, 'M9 merakit track; satu proses berat pada satu waktu.'))
            value['jobs'].append(jobid)
            db.execute('UPDATE m9_invites SET revoked=1 WHERE session_id=?', (row['id'],))
        result = self.store.change(actor, row['id'], data['expected_version'], change)
        self.service.queue.start();return result

    def execute(self, job):
        from .m9_media import run, verify_media
        from .dependency_cache import content_id
        from .studio_worker import StaleJob
        snap = job['request']['m9'];key = snap['session_id'];session = snap['session'];actor = self.lab.operator(snap['workspace'])
        folder = self.root/key/'final'/job['id'];folder.mkdir(parents=True, exist_ok=True)
        def check():
            self.lab.check_job(job)
            current = self.store.get(actor, key)
            if current['version'] != snap['input_version'] or current['data']['status'] != 'finalizing':raise StaleJob('Manifest rekaman berubah')
        check();tracks = []
        for index, track in enumerate(snap['tracks']):
            joined = folder/(track['id']+'.input')
            with joined.open('wb') as target:
                for chunk in track['chunks'][:track['data']['expected_chunks']]:
                    data = (self.root/key/track['id']/(str(chunk['seq']).zfill(6)+'.chunk')).read_bytes()
                    if sha(data) != chunk['sha256']:raise ValueError('Chunk berubah di disk')
                    target.write(data)
            audio = track['kind'] in ('microphone', 'system_audio') or track['mime'].startswith('audio/')
            output = folder/(track['id']+('.wav' if audio else '.mp4'))
            args = ['-i', str(joined)]
            args += ['-vn', '-c:a', 'pcm_s16le', '-ar', '48000'] if audio else ['-an', '-vf', 'scale=w=min(1920\\,iw):h=-2', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p']
            run(args+[str(output)], check=check, timeout=3600)
            info = verify_media(output, check=check);joined.unlink()
            tracks.append({**track, 'path': str(output), 'info': info, 'artifact': artifact(output)})
            self.service.queue.update_owned(job, progress=5+int(45*(index+1)/len(snap['tracks'])), message='Track tersimpan; memeriksa durasi dan jam sumber')
        primary = next(t for t in tracks if t['id'] == session['layout']['primary_track'])
        camera=next((t for t in tracks if t['id']==session['layout'].get('camera_track')),None)
        audios = [t for t in tracks if t['info']['audio_tracks']]
        duration = max(t['data']['offset']+t['info']['duration'] for t in tracks)
        if duration > 12*3600:raise ValueError('Durasi di luar batas')
        output = folder/('program.mp4' if primary['info']['kind'] == 'video' else 'program.wav')
        args = [];filters = [];maps = [];input_index = {}
        inputs = ([primary] if primary['info']['kind'] == 'video' else [])+([camera] if camera else [])+audios
        for i, track in enumerate(inputs):args += ['-i', track['path']];input_index[track['id']] = i
        labels = []
        for n, track in enumerate(audios):
            offset = track['data']['offset'];intervals = session['participants'][track['participant']]['intervals']
            terms = [f'between(t,{max(0.,a-offset):.6f},{max(0.,b-offset):.6f})' for a,b in intervals if b > offset]
            enabled = '+'.join(terms) or '0'
            label = 'a'+str(n);labels.append('['+label+']')
            filters.append(f'[{input_index[track["id"]]}:a:0]asetpts=PTS-STARTPTS,volume=0:enable=\'not({enabled})\',adelay={round(offset*1000)}:all=1,apad,atrim=duration={duration:.6f}[{label}]')
        filters.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0,alimiter=level=false:limit=0.95[audio]')
        if primary['info']['kind'] == 'video':
            offset = primary['data']['offset']
            timefilter=f'setpts=PTS-STARTPTS,tpad=start_duration={offset:.6f}:start_mode=add:stop_duration={duration:.6f},trim=duration={duration:.6f}'
            if camera:
                w,h=primary['info']['display_size'];w=min(w,1920);h=min(h,1080);w=max(80,w//10*10);h=max(64,h//2*2);left=w*8//10;right=w-left
                filters.append(f'[0:v:0]{timefilter},scale={left}:{h}:force_original_aspect_ratio=decrease,pad={left}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1[slide]')
                co=camera['data']['offset'];ci=input_index[camera['id']]
                filters.append(f'[{ci}:v:0]setpts=PTS-STARTPTS,tpad=start_duration={co:.6f}:start_mode=add:stop_duration={duration:.6f},trim=duration={duration:.6f},scale={right}:{h}:force_original_aspect_ratio=decrease,pad={right}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1[camera]')
                filters.append('[slide][camera]hstack=inputs=2[v]')
            else:filters.append(f'[0:v:0]{timefilter},setsar=1[v]')
            maps = ['-map', '[v]', '-map', '[audio]', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-movflags', '+faststart']
        else:maps = ['-map', '[audio]', '-c:a', 'pcm_s16le', '-ar', '48000']
        run(args+['-filter_complex', ';'.join(filters)]+maps+['-t', f'{duration:.6f}', str(output)], check=check, timeout=3600)
        info = verify_media(output, check=check);check()
        manifest = {'schema_version': 1, 'kind': 'recording9', 'session_id': key, 'program': artifact(output),
            'tracks': [{k: t[k] for k in ('id', 'participant', 'kind', 'mime', 'data', 'artifact')} for t in tracks],
            'participants': session['participants'], 'timebase': 'actual decoded stream timestamps plus recorded offset; not chunk count',
            'sync_reviewed': True, 'program_duration': info['duration'], 'quality': 'device sync needs listening/frame review',
            'backstage': 'excluded from program by explicit onstage intervals; isolated originals retained for host',
            'layout':session['layout'], 'slides_policy':'whole frame fitted with padding; camera occupies separate panel',
            'source_synthetic': False, 'live_room_monitoring': False}
        manifest_path = folder/'recording9.json';atomic_bytes(manifest_path, (canonical(manifest)+'\n').encode())
        archive = folder/'recording-tracks.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
            zipped.write(manifest_path, 'recording9.json');zipped.write(output, output.name)
            for track in tracks:zipped.write(track['path'], 'tracks/'+Path(track['path']).name)
        return self.lab.publish_derivative(job, actor, output, session['name'],
            {'kind': 'recording9', 'session_id': key,'capture_primary_kind':primary['kind'], 'manifest': str(manifest_path), 'recording_archive':str(archive),'program_content_id': content_id(output, fresh=True)},
            manifest_path, item_id=key, extra={'session_id': key, 'archive_path': str(archive), 'recording_version': snap['input_version']})
