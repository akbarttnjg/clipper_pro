"""Nullable, revision-bound observations. No invented views or calibrated scores."""
import json
import secrets
from datetime import date
from urllib.parse import urlsplit
from .m8_contract import canonical, csv_report, digest, integer, number, only, text
from .m8_store import ident
from .project_store import Conflict

METRICS = {'views', 'likes', 'comments', 'shares', 'estimatedMinutesWatched', 'averageViewDuration', 'averageViewPercentage'}


def period(start, end):
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if a > b:
        raise ValueError('Awal periode melewati akhir periode')
    return a.isoformat(), b.isoformat()


class Analytics:
    def __init__(self, m8):
        self.m8 = m8

    def observe(self, actor, data, *, source='operator_import'):
        only(data, ('publish_id', 'start_date', 'end_date', 'values', 'reasons', 'provenance'),
             ('publish_id', 'start_date', 'end_date', 'values'))
        row = self.m8.publishing.get(actor, data['publish_id'], private=True)
        self.m8.workspaces.require(actor, 'review', row['project_id'])
        start, end = period(data['start_date'], data['end_date'])
        values = data['values'];reasons = data.get('reasons', {})
        if not isinstance(values, dict) or set(values)-METRICS or not isinstance(reasons, dict) or set(reasons)-METRICS:
            raise ValueError('Nama metrik tidak dikenal')
        provenance = text(data.get('provenance', ''), 'Sumber data', 500, 0)
        frozen = row['request']
        reference = {k: frozen[k] for k in ('project_id', 'project_revision', 'clip_id', 'variant_id', 'package_content_id', 'output_content_id')}
        reference.update(account_id=row['account_id'], remote_id=(row['remote'] or {}).get('id'), provenance=provenance)
        ids = []
        # One refresh is atomic, with explicit missing values for all metric names.
        with self.m8.db.transaction() as db:
            for metric in sorted(METRICS):
                value = values.get(metric)
                if value is not None:
                    value = number(value, metric, 0, 10**15)
                    if metric in ('views','likes','comments','shares') and not value.is_integer():
                        raise ValueError('Hitungan metrik harus bilangan bulat')
                reason = text(reasons.get(metric, 'not_returned_by_platform' if source != 'operator_import' else 'not_supplied'), 'Alasan metrik', 300) if value is None else None
                key = ident('observation');ids.append(key)
                db.execute('INSERT INTO m8_metrics VALUES(?,?,?,?,?,?,?,?,?,?,?)', (key, actor.workspace, row['id'], metric, value, reason, start, end, source, self.m8.db.clock(), canonical(reference)))
            self.m8.db.event(db, actor.workspace, 'analytics.refreshed', row['project_id'], frozen['project_revision'], {'publish_id': row['id'], 'source': source, 'start_date': start, 'end_date': end})
        return {'observation_ids': ids, 'source': source, 'missing_is_zero': False}

    def refresh(self, actor, data):
        only(data, ('publish_id', 'start_date', 'end_date'), ('publish_id', 'start_date', 'end_date'))
        row = self.m8.publishing.get(actor, data['publish_id'], private=True)
        self.m8.workspaces.require(actor, 'review', row['project_id'])
        account = self.m8.accounts.get(actor, row['account_id'], private=True)
        if account['platform'] != 'youtube' or not (row['remote'] or {}).get('id'):
            raise ValueError('Metrik API memerlukan remote ID YouTube terverifikasi')
        start, end = period(data['start_date'], data['end_date'])
        response = self.m8.youtube.analytics(account, row['remote']['id'], start, end)
        payload = {**data, 'values': response['values'], 'reasons': {k: response['reason'] or 'not_returned_by_platform' for k in METRICS}, 'provenance': 'YouTube Analytics reports.query'}
        return self.observe(actor, payload, source='youtube_analytics_api')

    def rows(self, actor, project_id=None):
        self.m8.workspaces.require(actor, 'read', project_id)
        allowed = {r['id'] for r in self.m8.publishing.listing(actor, project_id)}
        with self.m8.service.store.connect() as db:
            rows = db.execute('SELECT * FROM m8_metrics WHERE workspace=? ORDER BY retrieved DESC,rowid DESC LIMIT 7000', (actor.workspace,)).fetchall()
        latest = {}
        for row in rows:
            if row['publish_id'] not in allowed:
                continue
            key = (row['publish_id'], row['metric'], row['start_date'], row['end_date'])
            if key not in latest:
                latest[key] = {**dict(row), 'reference': json.loads(row['data'])};latest[key].pop('data')
        return list(latest.values())

    def dashboard(self, actor, project_id=None):
        rows = self.rows(actor, project_id)
        periods = sorted({(r['start_date'], r['end_date']) for r in rows})
        summaries = []
        for start, end in periods:
            subset = [r for r in rows if r['start_date'] == start and r['end_date'] == end]
            values = {}
            for metric in sorted(METRICS):
                selected = [r for r in subset if r['metric'] == metric]
                available = [r['value'] for r in selected if r['value'] is not None]
                values[metric] = {'available_posts': len(available), 'total_posts': len(selected),
                    'sum': sum(available) if available and metric not in ('averageViewDuration', 'averageViewPercentage') else None,
                    'mean_of_available_posts': sum(available)/len(available) if available else None,
                    'definition': 'Rata-rata per post yang tersedia; bukan rata-rata tertimbang penonton.'}
            summaries.append({'start_date': start, 'end_date': end, 'metrics': values})
        return {'rows': rows, 'periods': summaries, 'missing_values': 'null + availability reason; never converted to zero',
                'dropoff_prediction': {'status': 'not_calibrated', 'value': None, 'reason': 'Memerlukan corpus berlabel dan evaluasi held-out; belum ada klaim prediksi akurat.'},
                'experiments': self.m8.db.records(actor.workspace, 'experiment'),
                'feedback_policies': self.m8.db.records(actor.workspace, 'feedback_policy')}

    def comment(self, actor, data):
        only(data, ('project_id', 'expected_revision', 'clip_id', 'source_time', 'text', 'status', 'id', 'expected_version'),
             ('project_id', 'expected_revision', 'source_time', 'text'))
        pid = data['project_id'];self.m8.workspaces.require(actor, 'review', pid)
        doc = self.m8.service.store.get(pid)
        if doc['revision'] != data['expected_revision']:
            raise Conflict(doc['revision'])
        cid = data.get('clip_id')
        if cid and cid not in doc.get('clips', {}):
            raise ValueError('Klip tidak ditemukan')
        at = number(data['source_time'], 'Timecode sumber', 0, doc['source']['info']['duration'])
        status = data.get('status', 'open')
        if status not in ('open', 'resolved'):
            raise ValueError('Status komentar tidak valid')
        record = {'project_id': pid, 'project_revision': doc['revision'], 'source_id': doc['source']['source_id'],
            'clip_id': cid, 'source_time': at, 'text': text(data['text'], 'Komentar', 4000), 'status': status, 'user_id': actor.user_id}
        if data.get('id'):
            existing = next((r for r in self.m8.db.records(actor.workspace, 'comment') if r['id'] == data['id']), None)
            if not existing or existing['data']['project_id'] != pid:
                raise ValueError('Komentar tidak cocok dengan proyek')
        return self.m8.db.record(actor.workspace, 'comment', record, data.get('id'), data.get('expected_version'))

    def effort(self, actor, data):
        only(data, ('project_id', 'expected_revision', 'clip_id', 'intervals', 'reason'), ('project_id', 'expected_revision', 'intervals'))
        pid = data['project_id'];self.m8.workspaces.require(actor, 'edit', pid)
        doc = self.m8.service.store.get(pid)
        if doc['revision'] != data['expected_revision']:
            raise Conflict(doc['revision'])
        intervals = data['intervals']
        if not isinstance(intervals, list) or not 1 <= len(intervals) <= 1000:
            raise ValueError('Kirim interval aktif; tiap interval maksimal 120 detik')
        normalized = [];previous = None
        for row in sorted(intervals, key=lambda r: r.get('start', 0)):
            only(row, ('start', 'end', 'activity'), ('start', 'end', 'activity'))
            start = number(row['start'], 'Awal interval');end = number(row['end'], 'Akhir interval', start, start+120)
            if row['activity'] not in ('correction', 'review') or end > self.m8.db.clock()+5 or previous is not None and start < previous:
                raise ValueError('Interval aktif bertabrakan, berada di masa depan, atau memakai aktivitas menunggu render')
            previous = end;normalized.append({'start': start, 'end': end, 'activity': row['activity']})
        cid = data.get('clip_id')
        if cid and cid not in doc['clips']:
            raise ValueError('Klip tidak ditemukan')
        return self.m8.db.record(actor.workspace, 'effort', {'project_id': pid, 'project_revision': doc['revision'], 'clip_id': cid,
            'intervals': normalized, 'active_seconds': sum(r['end']-r['start'] for r in normalized),
            'reason': text(data.get('reason', ''), 'Alasan koreksi', 1000, 0), 'source': 'operator_confirmed_active_intervals', 'render_wait_included': False})

    def cost(self, actor, data):
        only(data, ('project_id', 'expected_revision', 'clip_id', 'stage', 'elapsed_seconds', 'gpu_seconds', 'provider_usd', 'disk_bytes', 'measurement'), ('project_id', 'expected_revision', 'stage', 'elapsed_seconds', 'measurement'))
        pid = data['project_id'];self.m8.workspaces.require(actor, 'edit', pid)
        doc = self.m8.service.store.get(pid)
        if doc['revision'] != data['expected_revision']:
            raise Conflict(doc['revision'])
        if data['measurement'] not in ('measured_import', 'estimate'):
            raise ValueError('Pilih pengukuran atau estimasi secara eksplisit')
        result = {'project_id': pid, 'project_revision': doc['revision'], 'clip_id': data.get('clip_id'),
            'stage': text(data['stage'], 'Tahap', 100), 'measurement': data['measurement'],
            'elapsed_seconds': number(data['elapsed_seconds'], 'Waktu proses', 0, 10**7),
            'gpu_seconds': None if data.get('gpu_seconds') is None else number(data['gpu_seconds'], 'Waktu GPU', 0, 10**7),
            'provider_usd': None if data.get('provider_usd') is None else number(data['provider_usd'], 'Biaya provider USD', 0, 10000),
            'disk_bytes': None if data.get('disk_bytes') is None else integer(data['disk_bytes'], 'Disk bytes', 0, 10**15)}
        return self.m8.db.record(actor.workspace, 'cost', result)

    def experiment(self, actor, data):
        self.m8.workspaces.require(actor, 'review')
        only(data, ('name', 'hypothesis', 'variants', 'mode', 'primary_metric', 'context'), ('name', 'hypothesis', 'variants', 'mode', 'primary_metric', 'context'))
        variants = data['variants']
        if not isinstance(variants, list) or not 2 <= len(variants) <= 10 or len(set(variants)) != len(variants):
            raise ValueError('Eksperimen memerlukan 2–10 nama varian unik')
        variants = [text(v, 'Varian', 80) for v in variants]
        if data['mode'] not in ('randomized_assignment', 'observational') or data['primary_metric'] not in METRICS:
            raise ValueError('Mode/metric eksperimen tidak dikenal')
        return self.m8.db.record(actor.workspace, 'experiment', {'name': text(data['name'], 'Nama', 160),
            'hypothesis': text(data['hypothesis'], 'Hipotesis', 1000), 'variants': variants, 'mode': data['mode'],
            'primary_metric': data['primary_metric'], 'context': text(data['context'], 'Konteks audience/jadwal', 2000),
            'assignments': [], 'causal_effect_established': False})

    def assign(self, actor, data):
        self.m8.workspaces.require(actor, 'publish')
        only(data, ('id', 'expected_version', 'unit_id', 'candidates', 'selected_variant'), ('id', 'expected_version', 'unit_id', 'candidates'))
        experiment = next((r for r in self.m8.db.records(actor.workspace, 'experiment') if r['id'] == data['id']), None)
        if not experiment:
            raise KeyError('Eksperimen tidak ditemukan')
        value = experiment['data'];candidates = data['candidates']
        if not isinstance(candidates, dict) or set(candidates) != set(value['variants']):
            raise ValueError('Setiap varian harus mempunyai draf publikasi')
        rows = [self.m8.publishing.get(actor, key, private=True) for key in candidates.values()]
        if any(r['status'] != 'draft' for r in rows) or len({(r['project_id'], r['request']['clip_id']) for r in rows}) != 1:
            raise ValueError('Randomisasi dilakukan sebelum approval pada unit klip yang sama')
        unit = text(data['unit_id'], 'Unit eksperimen', 160)
        if any(r['unit_id'] == unit for r in value['assignments']):
            raise ValueError('Unit eksperimen sudah memiliki assignment')
        variant = secrets.choice(value['variants']) if value['mode'] == 'randomized_assignment' else data.get('selected_variant')
        if variant not in value['variants']:
            raise ValueError('Pilih varian observasional')
        value['assignments'].append({'unit_id': unit, 'variant': variant, 'publish_id': candidates[variant], 'assigned_at': self.m8.db.clock(), 'candidate_ids': candidates})
        return self.m8.db.record(actor.workspace, 'experiment', value, experiment['id'], data['expected_version'])

    def topic(self, actor, data):
        self.m8.workspaces.require(actor, 'review')
        only(data, ('title', 'source_url', 'published_at', 'retrieved_at', 'provider_usd', 'note'), ('title', 'source_url', 'retrieved_at'))
        address = text(data['source_url'], 'Sumber topik', 2000)
        parsed = urlsplit(address)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Gunakan URL sumber HTTPS tanpa credential')
        return self.m8.db.record(actor.workspace, 'topic', {'title': text(data['title'], 'Topik', 300), 'source_url': address,
            'published_at': data.get('published_at'), 'retrieved_at': number(data['retrieved_at'], 'Waktu perolehan', 0, self.m8.db.clock()+5),
            'provider_usd': None if data.get('provider_usd') is None else number(data['provider_usd'], 'Biaya USD', 0, 10000),
            'note': text(data.get('note', ''), 'Catatan', 2000, 0), 'source': 'operator_authorized_import', 'automatic_scouting': False})

    def export(self, actor, project_id=None):
        report = self.dashboard(actor, project_id)
        fields = ['publish_id', 'metric', 'value', 'reason', 'start_date', 'end_date', 'source', 'retrieved', 'reference']
        csv = csv_report(report['rows'], fields)
        folder = self.m8.service.work/'m8-reports'/ident('report')
        folder.mkdir(parents=True)
        json_path = folder/'analytics.json';csv_path = folder/'analytics.csv'
        json_path.write_text(canonical(report)+'\n', encoding='utf-8')
        csv_path.write_text(csv, encoding='utf-8-sig', newline='')
        return {'json': self.m8.register_file(actor, json_path, project_id), 'csv': self.m8.register_file(actor, csv_path, project_id),
                'period_policy': 'Periods remain separate; missing values are null.'}
