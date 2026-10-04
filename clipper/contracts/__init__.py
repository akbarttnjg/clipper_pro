"""C0 v1: dependency-free boundary between editorial A and production B.

Times are half-open source seconds. Frame endpoints are exclusive. Coordinates
carry their display-space dimensions. Never infer identity from caption text.
"""
from copy import deepcopy
import hashlib
import json
import math

SCHEMA_VERSION = 1
KINDS = {'MediaContext', 'TranscriptSnapshot', 'CandidateSet', 'SceneAnalysis',
         'CaptionPlan', 'AssetProposalSet', 'EditTimeline', 'RenderManifest'}
STATES = {'ready', 'empty', 'blocked', 'error', 'stale'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def envelope(kind, source_id, payload, input_fingerprint, state='ready', producer='B-1'):
    result = dict(schema_version=SCHEMA_VERSION, producer_version=producer, kind=kind,
                  source_id=source_id, input_fingerprint=input_fingerprint, state=state,
                  payload=deepcopy(payload))
    validate(result)
    return result


def validate(value):
    if value.get('schema_version') != 1 or value.get('kind') not in KINDS:
        raise ValueError('Unsupported C0 schema or kind')
    if value.get('state') not in STATES or not isinstance(value.get('payload'), dict):
        raise ValueError('Invalid C0 state/payload')
    for key in ('source_id', 'input_fingerprint', 'producer_version'):
        if not isinstance(value.get(key), str) or not value[key]:
            raise ValueError('Missing C0 '+key)
    return value


def span(start, end):
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, end)) or not 0 <= start < end:
        raise ValueError('Invalid half-open source span')
    return {'start': start, 'end': end}


def words_snapshot(words, source_id, transcript_id, revision=0):
    result = []
    for i, original in enumerate(words):
        word = deepcopy(original)
        # Preserve IDs already supplied by A, including integers in 3.3 sessions.
        word.setdefault('word_id', i)
        word.setdefault('origin_word_ids', [word['word_id']])
        word.update(source_id=source_id, transcript_id=transcript_id)
        span(word['start'], word['end'])
        result.append(word)
    return envelope('TranscriptSnapshot', source_id,
                    {'transcript_id': transcript_id, 'revision': revision, 'words': result},
                    fingerprint(result), producer='legacy-3.3-adapter')
