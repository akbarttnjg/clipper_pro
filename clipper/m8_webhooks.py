"""Signed event outbox. HTTPS endpoints require an operator host allowlist.

DNS addresses are pinned before TLS, blocking redirects and private address reuse.
Delivery is at-least-once; receivers deduplicate by event ID.
"""
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import secrets
import socket
import ssl
from urllib.parse import urlsplit
from .m8_contract import canonical, only, text
from .m8_store import ident


def destination(address):
    parsed = urlsplit(text(address, 'Webhook HTTPS', 2000))
    allowed = {h.strip().lower() for h in os.environ.get('CLIPPER_M8_WEBHOOK_HOSTS', '').split(',') if h.strip()}
    if parsed.scheme != 'https' or parsed.hostname not in allowed or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Host webhook belum diizinkan oleh operator pada CLIPPER_M8_WEBHOOK_HOSTS')
    return parsed


def send_pinned(address, body, headers):
    parsed = destination(address)
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    ips = {r[4][0] for r in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError('Webhook tidak boleh menunjuk jaringan privat/link-local')
    selected = sorted(ips)[0]
    class Pinned(http.client.HTTPSConnection):
        def connect(self):
            raw = socket.create_connection((selected, 443), timeout=15)
            self.sock = self._context.wrap_socket(raw, server_hostname=parsed.hostname)
    connection = Pinned(parsed.hostname, timeout=15, context=ssl.create_default_context())
    try:
        target = parsed.path or '/'
        if parsed.query:
            target += '?'+parsed.query
        connection.request('POST', target, body=body, headers=headers)
        response = connection.getresponse()
        response.read(65536)
        return response.status
    finally:
        connection.close()


class Webhooks:
    def __init__(self, m8):
        self.m8 = m8
        self.sender = send_pinned

    def save(self, actor, data):
        self.m8.workspaces.require(actor, 'manage')
        only(data, ('url', 'events', 'enabled', 'id'), ('url', 'events'))
        parsed = destination(data['url'])
        if not isinstance(data['events'], list) or not 1 <= len(data['events']) <= 30:
            raise ValueError('Pilih 1–30 jenis event atau *')
        events = [text(v, 'Jenis event', 100) for v in data['events']]
        enabled = data.get('enabled', True)
        if type(enabled) is not bool:
            raise ValueError('Status webhook harus boolean')
        key = data.get('id') or ident('webhook')
        with self.m8.service.store.connect() as db:
            old = db.execute('SELECT * FROM m8_subscriptions WHERE id=? AND workspace=?', (key, actor.workspace)).fetchone()
        if data.get('id') and not old:
            raise KeyError('Webhook tidak ditemukan')
        signing = None if old else secrets.token_urlsafe(32)
        reference = old['secret_ref'] if old else self.m8.vault.put({'signing_key': signing})
        value = {'url': data['url'], 'host': parsed.hostname, 'events': events}
        with self.m8.db.transaction() as db:
            db.execute('INSERT INTO m8_subscriptions VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,enabled=excluded.enabled', (key, actor.workspace, canonical(value), reference, int(enabled)))
            # Start with future events; do not silently replay all historic project data.
            if not old:
                cursor = db.execute('SELECT COALESCE(MAX(seq),0) FROM m8_events').fetchone()[0]
                value['after'] = cursor
                db.execute('UPDATE m8_subscriptions SET data=? WHERE id=?', (canonical(value), key))
            else:
                value['after'] = json.loads(old['data']).get('after', 0)
                db.execute('UPDATE m8_subscriptions SET data=? WHERE id=?', (canonical(value), key))
            self.m8.db.event(db, actor.workspace, 'webhook.configured', data={'id': key, 'host': parsed.hostname})
        # Signing key is returned exactly once here, never through command receipts.
        # The generic command route deliberately omits it; operators may provision an
        # independent secret through the dedicated setup route instead.
        return {'id': key, 'host': parsed.hostname, 'enabled': enabled, 'signing_key_available_locally': True,
                'setup_note': 'Gunakan CLI operator untuk membaca secret sekali; event payload tidak menyertakannya.'}

    def listing(self, actor):
        self.m8.workspaces.require(actor, 'manage')
        with self.m8.service.store.connect() as db:
            rows = db.execute('SELECT id,data,enabled FROM m8_subscriptions WHERE workspace=?', (actor.workspace,)).fetchall()
        return {'webhooks': [{'id': r['id'], 'host': json.loads(r['data'])['host'], 'events': json.loads(r['data'])['events'], 'enabled': bool(r['enabled'])} for r in rows]}

    def signing_key(self, actor, key):
        self.m8.workspaces.require(actor, 'manage')
        with self.m8.service.store.connect() as db:
            row = db.execute('SELECT secret_ref FROM m8_subscriptions WHERE id=? AND workspace=?', (key, actor.workspace)).fetchone()
        if not row:
            raise KeyError('Webhook tidak ditemukan')
        signing = secrets.token_urlsafe(32)
        self.m8.vault.put({'signing_key': signing}, row['secret_ref'])
        with self.m8.db.transaction() as db:
            self.m8.db.event(db, actor.workspace, 'webhook.key_rotated', data={'id': key})
        return {'id': key, 'signing_key': signing, 'previous_key_revoked': True}

    def tick(self):
        # Claim a delivery in a transaction. Unknown outcomes are retried with the
        # same event ID/signature; webhook handlers must be idempotent.
        now = self.m8.db.clock()
        with self.m8.db.transaction() as db:
            subscriptions = db.execute('SELECT * FROM m8_subscriptions WHERE enabled=1').fetchall()
            for subscription in subscriptions:
                data = json.loads(subscription['data'])
                events = db.execute('SELECT * FROM m8_events WHERE workspace=? AND seq>? ORDER BY seq LIMIT 100', (subscription['workspace'], data.get('after', 0))).fetchall()
                for event in events:
                    if '*' in data['events'] or event['type'] in data['events']:
                        db.execute("INSERT OR IGNORE INTO m8_webhook_deliveries VALUES(?,?,'pending',0,?)", (subscription['id'], event['seq'], now))
                if events:
                    data['after'] = events[-1]['seq']
                    db.execute('UPDATE m8_subscriptions SET data=? WHERE id=?', (canonical(data), subscription['id']))
            selected = db.execute("SELECT d.*,s.workspace,s.data,s.secret_ref,e.type,e.project_id,e.revision,e.data AS event_data,e.created FROM m8_webhook_deliveries d JOIN m8_subscriptions s ON s.id=d.subscription JOIN m8_events e ON e.seq=d.event_seq WHERE s.enabled=1 AND d.status IN ('pending','sending') AND d.next_run<=? ORDER BY d.event_seq LIMIT 1", (now,)).fetchone()
            if not selected:
                return {'status': 'idle'}
            db.execute("UPDATE m8_webhook_deliveries SET status='sending',attempts=attempts+1,next_run=? WHERE subscription=? AND event_seq=?", (now+90, selected['subscription'], selected['event_seq']))
        value = {'schema_version': 1, 'id': 'm8-event-'+str(selected['event_seq']), 'type': selected['type'], 'workspace': selected['workspace'],
            'project_id': selected['project_id'], 'revision': selected['revision'], 'data': json.loads(selected['event_data']), 'created': selected['created']}
        body = canonical(value).encode()
        stamp = str(int(now))
        try:
            secret = self.m8.vault.get(selected['secret_ref'])['signing_key']
            signature = hmac.new(secret.encode(), stamp.encode()+b'.'+body, hashlib.sha256).hexdigest()
            code = self.sender(json.loads(selected['data'])['url'], body, {'Content-Type': 'application/json', 'X-Clipper-Event-ID': value['id'],
                'X-Clipper-Timestamp': stamp, 'X-Clipper-Signature': 'sha256='+signature})
            success = 200 <= code < 300
        except Exception:
            success = False
        attempts = selected['attempts']+1
        state = 'delivered' if success else 'failed' if attempts >= 6 else 'pending'
        with self.m8.db.transaction() as db:
            db.execute('UPDATE m8_webhook_deliveries SET status=?,next_run=? WHERE subscription=? AND event_seq=?',
                (state, now+min(3600, 2**min(attempts+3, 11)), selected['subscription'], selected['event_seq']))
        return {'event_id': value['id'], 'status': state, 'attempts': attempts}
