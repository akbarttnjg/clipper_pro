"""Explicit, project-local spelling approvals. Never learn from an unapproved edit."""
import hashlib
import threading
from pathlib import Path
from .storage import read_json, write_json

LOCK = threading.RLock()


def path(cfg):
    return Path(cfg.work_dir) / 'correction-memory.json'


def entries(cfg):
    data = read_json(path(cfg), {})
    return data.get('entries', []) if isinstance(data, dict) else []


def save(cfg, canonical, alias, topic='*', enabled=True):
    from .transcript_correction import parse_glossary
    canonical, alias = str(canonical).strip(), str(alias).strip()
    if not alias or any(c in canonical + alias for c in '\n\r=|'):
        raise ValueError('Isi satu istilah dan satu alias; pemisah kamus tidak boleh dipakai.')
    parse_glossary(f'{canonical}={alias}')
    if topic not in ('*', 'general', 'creators', 'business', 'finance', 'students'):
        raise ValueError('Topik memori tidak dikenal.')
    key = hashlib.sha256(f'{topic}|{alias.casefold()}'.encode()).hexdigest()[:16]
    with LOCK:
        rows = [r for r in entries(cfg) if r.get('id') != key]
        if len(rows) >= 80:
            raise ValueError('Memori proyek maksimal 80 alias; hapus entri yang tidak digunakan.')
        rows.append(dict(id=key, canonical=canonical, alias=alias, topic=topic,
                         enabled=bool(enabled), approved_by='user'))
        # Validate the combined size too, not only the last entry.
        parse_glossary('\n'.join(f"{r['canonical']}={r['alias']}" for r in rows))
        write_json(path(cfg), {'version': 1, 'entries': rows})
    return rows


def remove(cfg, key):
    with LOCK:
        rows = [r for r in entries(cfg) if r.get('id') != key]
        write_json(path(cfg), {'version': 1, 'entries': rows})
    return rows


def glossary(cfg):
    supplied=getattr(cfg,'approved_aliases',None)
    return '\n'.join(f"{r['canonical']}={r['alias']}" for r in (supplied if supplied is not None else entries(cfg))
                     if r.get('enabled') and r.get('topic') in ('*', cfg.audience)
                     and r.get('approved_by') == 'user')


def propose_change(rows,operation):
    """Pure memory update. B commits the returned rows in its revision transaction."""
    from .transcript_correction import parse_glossary
    import copy
    rows=copy.deepcopy(rows)
    if operation.get('op')=='alias_remove':
        return [r for r in rows if r.get('id')!=operation.get('id')]
    canonical=str(operation.get('canonical','')).strip();alias=str(operation.get('alias','')).strip()
    topic=operation.get('topic','*');enabled=operation.get('enabled',True)
    if not canonical or not alias or any(c in canonical+alias for c in '\n\r=|'):raise ValueError('Istilah atau alias tidak valid')
    if type(enabled) is not bool:raise ValueError('Status alias harus boolean')
    if topic not in ('*','general','creators','business','finance','students'):raise ValueError('Topik tidak valid')
    parse_glossary(f'{canonical}={alias}')
    key=hashlib.sha256(f'{topic}|{alias.casefold()}'.encode()).hexdigest()[:16]
    rows=[r for r in rows if r.get('id') not in (key,operation.get('id'))]
    rows.append(dict(id=key,canonical=canonical,alias=alias,topic=topic,enabled=enabled,approved_by='user'))
    parse_glossary('\n'.join(f"{r['canonical']}={r['alias']}" for r in rows))
    return rows


def signature(cfg):
    return hashlib.sha256(glossary(cfg).encode()).hexdigest()
