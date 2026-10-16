"""Versioned M8 boundaries. No network, credentials or project mutations here."""
import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VERSION = '4.0.19-m8'
SCHEMA = 1
PLATFORMS = ('youtube', 'tiktok', 'instagram', 'facebook', 'linkedin', 'x', 'other')
ROLES = {
    'owner': {'read', 'edit', 'review', 'approve', 'publish', 'manage'},
    'editor': {'read', 'edit'},
    'reviewer': {'read', 'review'},
    'publisher': {'read', 'review', 'approve', 'publish'},
}
SCOPES = {
    'upload': 'https://www.googleapis.com/auth/youtube.upload',
    'read': 'https://www.googleapis.com/auth/youtube.readonly',
    'analytics': 'https://www.googleapis.com/auth/yt-analytics.readonly',
    'manage': 'https://www.googleapis.com/auth/youtube.force-ssl',
}


class AccessDenied(ValueError):
    pass


class Busy(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def only(data, fields, required=()):
    if not isinstance(data, dict) or set(data) - set(fields):
        raise ValueError('Kolom permintaan tidak dikenal')
    if set(required) - set(data):
        raise ValueError('Kolom wajib belum lengkap: ' + ', '.join(sorted(set(required) - set(data))))
    return data


def text(value, name='Teks', maximum=500, minimum=1):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum or '\x00' in value:
        raise ValueError(name + ' tidak valid')
    return value.strip()


def integer(value, name, low=0, high=10**9):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name + ' di luar batas')
    return value


def number(value, name, low=0, high=10**12):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(name + ' di luar batas')
    return float(value)


def zone(name):
    name = text(name, 'Zona waktu', 80)
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        # Windows without tzdata still has an exact, non-DST Jakarta clock.
        if name in ('Asia/Jakarta', 'UTC', 'Etc/UTC'):
            return timezone(timedelta(hours=7) if name == 'Asia/Jakarta' else timedelta())
        raise ValueError('Zona waktu belum tersedia. Pasang tzdata atau gunakan Asia/Jakarta/UTC.') from None


def schedule(local, timezone_name='Asia/Jakarta', fold=None):
    tz = zone(timezone_name)
    if local in (None, ''):
        return {'utc': None, 'local': None, 'timezone': timezone_name, 'fold': None}
    value = datetime.fromisoformat(text(local, 'Jadwal ISO 8601', 60).replace('Z', '+00:00'))
    if value.tzinfo is not None:
        utc = value.astimezone(timezone.utc)
        shown = utc.astimezone(tz)
    else:
        candidates = []
        for choice in (0, 1):
            attached = value.replace(tzinfo=tz, fold=choice)
            back = attached.astimezone(timezone.utc).astimezone(tz)
            if back.replace(tzinfo=None) == value and back.fold == choice:
                candidates.append(attached)
        if not candidates:
            raise ValueError('Waktu lokal tidak ada karena perubahan DST')
        if len(candidates) > 1 and fold not in (0, 1):
            raise ValueError('Waktu lokal ambigu; pilih fold 0 atau 1')
        shown = next((v for v in candidates if v.fold == fold), candidates[0])
        utc = shown.astimezone(timezone.utc)
    return {'utc': utc.timestamp(), 'local': shown.isoformat(), 'timezone': timezone_name, 'fold': shown.fold}


def metadata(platform, value):
    only(value, ('title', 'description', 'tags', 'privacy', 'made_for_kids', 'category_id'), ('title', 'privacy'))
    limits = {'youtube': (100, 5000), 'tiktok': (150, 2200), 'instagram': (150, 2200),
              'facebook': (255, 63206), 'linkedin': (200, 3000), 'x': (200, 280), 'other': (200, 5000)}
    title_limit, body_limit = limits[platform]
    title = text(value['title'], 'Judul', title_limit)
    description = text(value.get('description', ''), 'Deskripsi', body_limit, 0)
    if platform == 'youtube' and (len(description.encode('utf-8')) > 5000 or any(c in title+description for c in '<>')):
        raise ValueError('Metadata YouTube: hindari < > dan batasi deskripsi hingga 5000 byte UTF-8')
    tags = value.get('tags', [])
    if not isinstance(tags, list) or len(tags) > 50:
        raise ValueError('Tag harus berupa daftar, maksimal 50')
    tags = [text(t, 'Tag', 100) for t in tags]
    if sum(len(t) + (2 if ' ' in t else 0) for t in tags) + max(0, len(tags)-1) > 500:
        raise ValueError('Gabungan tag terlalu panjang')
    if value['privacy'] not in ('private', 'unlisted', 'public'):
        raise ValueError('Pilih privacy secara eksplisit')
    kids = value.get('made_for_kids', False)
    if type(kids) is not bool:
        raise ValueError('Pilihan konten anak harus boolean')
    category = value.get('category_id', '22')
    if not isinstance(category, str) or not re.fullmatch(r'\d{1,3}', category):
        raise ValueError('Kategori YouTube tidak valid')
    return {'title': title, 'description': description, 'tags': tags, 'privacy': value['privacy'],
            'made_for_kids': kids, 'category_id': category}


def clean(value):
    """Defense in depth; public records are also constructed from allowlists."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if not any(s in k.lower() for s in
                ('token', 'secret', 'authorization', 'credential', 'session_uri', 'absolute_', 'password'))}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def csv_report(rows, fields):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        safe = {}
        for key in fields:
            value = row.get(key)
            if isinstance(value, (dict, list)):
                value = canonical(value)
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
                value = "'" + value
            safe[key] = value
        writer.writerow(safe)
    return stream.getvalue()
