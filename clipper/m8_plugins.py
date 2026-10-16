"""Plugin SDK manifest/probe contract. Registration never executes third-party code.

Untrusted worker execution requires deployment isolation that this local package
cannot guarantee, so it is reported blocked rather than called sandboxed.
"""
from .m8_contract import only, text


class Plugins:
    def __init__(self, m8):
        self.m8 = m8

    def register(self, actor, data):
        self.m8.workspaces.require(actor, 'manage')
        only(data, ('plugin_id', 'schema_version', 'capabilities', 'runtime', 'probe_evidence'), ('plugin_id', 'schema_version', 'capabilities', 'runtime'))
        if type(data['schema_version']) is not int or data['schema_version'] != 1:
            raise ValueError('Plugin schema tidak didukung')
        plugin_id = text(data['plugin_id'], 'ID plugin', 120)
        capabilities = data['capabilities']
        if not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 30:
            raise ValueError('Daftarkan 1–30 kemampuan')
        capabilities = [text(c, 'Kemampuan plugin', 120) for c in capabilities]
        if data['runtime'] not in ('external_isolated_worker', 'trusted_local_provider'):
            raise ValueError('Runtime plugin belum didukung')
        return self.m8.db.record(actor.workspace, 'plugin', {'plugin_id': plugin_id, 'schema_version': 1,
            'capabilities': capabilities, 'runtime': data['runtime'], 'state': 'registered_unverified',
            'execution_enabled': False, 'probe_evidence': text(data.get('probe_evidence', ''), 'Referensi bukti probe', 1000, 0),
            'blocking_reason': 'Probe hasil nyata, resource budget dan isolasi deployment harus diverifikasi operator sebelum eksekusi.'})

    def listing(self, actor):
        self.m8.workspaces.require(actor)
        return {'plugins': self.m8.db.records(actor.workspace, 'plugin'), 'execution': 'blocked_until_deployment_probe_and_isolation',
                'contract': {'request': ['schema_version', 'job_id', 'project_id', 'revision', 'allowed_artifacts', 'budget'],
                             'response': ['schema_version', 'job_id', 'status', 'artifact_digests', 'measured_resources', 'qc']}}
