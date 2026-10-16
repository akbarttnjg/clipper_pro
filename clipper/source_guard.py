"""Fresh source identity at review, execution and publication boundaries."""
from .dependency_cache import content_id
from .project_store import Conflict


def verify(service, guard, document=None, revision=None):
    if not guard or not guard.get('project_id'):
        raise ValueError('Identitas sumber proyek tidak lengkap')
    doc = document if document is not None else service.store.get(guard['project_id'])
    if doc.get('project_id') != guard['project_id']:
        raise ValueError('Draf merujuk proyek sumber berbeda')
    actual_revision = doc.get('revision') if revision is None else revision
    expected = guard.get('input_revision', guard.get('revision'))
    if actual_revision != expected:
        raise Conflict(actual_revision)
    expected_id = guard.get('source_content_id', guard.get('content_id'))
    source = doc['source']
    if not expected_id or source['source_id'] != expected_id or content_id(source['path'], fresh=True) != expected_id:
        raise ValueError('Sumber berubah; tautkan dan analisis ulang sebelum melanjutkan')
    for field in ('transcript_id', 'transcript_revision'):
        if field in guard and doc.get(field) != guard[field]:
            raise ValueError('Transkrip sumber berubah; buat draf baru')
    return doc
