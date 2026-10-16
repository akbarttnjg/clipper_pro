"""Typed adapter for legacy assembly rows and M9 derivative provenance."""
import copy


def describe(source):
    lineage = source.get('lineage', [])
    if isinstance(lineage, list):
        return {'schema_version': 1, 'kind': 'assembly' if lineage else 'original',
                'origins': [copy.deepcopy(row) for row in lineage if isinstance(row, dict)], 'provenance': {}}
    if not isinstance(lineage, dict):
        raise ValueError('Format asal sumber tidak dikenal')
    provenance = copy.deepcopy(lineage)
    parent = lineage.get('parent_project_id') or lineage.get('source_project') or lineage.get('source_project_id')
    source_ref = lineage.get('source', {})
    if not parent and isinstance(source_ref, dict):
        parent = source_ref.get('project_id')
    origins = []
    if parent:
        bounds = lineage.get('source_range',lineage.get('range',source_ref.get('source_range',[None,None])))
        if not isinstance(bounds,list) or len(bounds)!=2:raise ValueError('Rentang provenance sumber tidak valid')
        origins.append({'project_id': parent, 'start': bounds[0], 'end': bounds[1],
                        'source_content_id': lineage.get('parent_source_content_id',lineage.get('source_content_id',source_ref.get('source_content_id'))),
                        'available': False, 'url': None})
    return {'schema_version': 1, 'kind': lineage.get('kind', 'derivative'), 'origins': origins, 'provenance': provenance}
