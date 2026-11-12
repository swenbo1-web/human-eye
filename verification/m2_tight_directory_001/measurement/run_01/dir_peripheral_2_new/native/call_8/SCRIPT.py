import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"61da165f1b3140048c42ac063fea41e4","command":"capture_directory","params":{"deadline_ns":553326463581900,"max_response_bytes":67108864}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_26cd17d73a6be03d1f59')
    if _module is None or getattr(_module, '_resident_tag', None) != 'd5cf7c47dcd0f379ec81f03f3aa8a5e31a05205c84c0c08e912f54a28bc22e1d': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_directory')(**_request['params'])
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))