"""MCP 2025-06-18 stdio transport with lifecycle and explicit tool error receipts."""
import json
import sys
from .m8_client import Client, ClientError

TOOLS = [
    {'name': 'clipper_status', 'description': 'Status Clipper, workspace, worker dan batas kemampuan. Tidak membuat pekerjaan.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}, 'annotations': {'readOnlyHint': True}},
    {'name': 'clipper_projects', 'description': 'Daftar proyek dalam workspace sesi aktif.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}, 'annotations': {'readOnlyHint': True}},
    {'name': 'clipper_command', 'description': 'Perintah M8 berversi dengan command_id stabil. Buat proposal/draf untuk ditinjau; approval publish tetap wajib. Job queued bukan hasil QC selesai. Role, revisi dan budget diperiksa server.',
     'inputSchema': {'type': 'object', 'properties': {'action': {'type': 'string'}, 'args': {'type': 'object'}, 'command_id': {'type': 'string', 'minLength': 8}},
                     'required': ['action', 'args', 'command_id'], 'additionalProperties': False},
     'annotations': {'readOnlyHint': False, 'destructiveHint': True, 'openWorldHint': True}},
]


class Protocol:
    def __init__(self, client):
        self.client = client
        self.initialized = False
        self.ready = False

    def handle(self, request):
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str):
            return {'jsonrpc': '2.0', 'id': request.get('id') if isinstance(request, dict) else None, 'error': {'code': -32600, 'message': 'Invalid Request'}}
        ident = request.get('id');method = request['method'];params = request.get('params', {})
        if method == 'notifications/initialized':
            self.ready = self.initialized
            return None
        if 'id' not in request:
            return None
        result = None
        if method == 'initialize':
            self.initialized = True;self.ready = False
            result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {'listChanged': False}},
                      'serverInfo': {'name': 'clipper-m8', 'version': '4.0.19'},
                      'instructions': 'Persetujuan mengacu pada revisi dan file tepat. Tidak ada klaim publish sebelum konfirmasi remote.'}
        elif method == 'ping':
            result = {}
        elif not self.ready:
            return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32002, 'message': 'Server not initialized'}}
        elif method == 'tools/list':
            result = {'tools': TOOLS}
        elif method == 'tools/call':
            try:
                if not isinstance(params, dict):
                    raise ValueError('Invalid tool params')
                name = params.get('name');args = params.get('arguments', {})
                if not isinstance(args, dict):
                    raise ValueError('Tool arguments must be an object')
                if name == 'clipper_status' and not args:
                    value = self.client.command('status')
                elif name == 'clipper_projects' and not args:
                    value = self.client.command('project.list')
                elif name == 'clipper_command' and set(args) == {'action', 'args', 'command_id'}:
                    value = self.client.command(args['action'], args['args'], args['command_id'])
                else:
                    raise ValueError('Tool/arguments not supported')
                result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False, allow_nan=False)}], 'structuredContent': value, 'isError': False}
            except (ValueError, KeyError, TypeError) as exc:
                result = {'content': [{'type': 'text', 'text': str(exc)}], 'isError': True}
        else:
            return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32601, 'message': 'Method not found'}}
        return {'jsonrpc': '2.0', 'id': ident, 'result': result}


def serve(client=None, input_stream=None, output_stream=None):
    protocol = Protocol(client or Client())
    incoming = input_stream or sys.stdin
    outgoing = output_stream or sys.stdout
    while True:
        line = incoming.readline(1024**2+1)
        if not line:
            break
        try:
            if len(line) > 1024**2:
                raise ValueError('Message too large')
            response = protocol.handle(json.loads(line))
        except (ValueError, TypeError):
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        if response is not None:
            outgoing.write(json.dumps(response, ensure_ascii=False, allow_nan=False)+'\n');outgoing.flush()


if __name__ == '__main__':
    serve()
