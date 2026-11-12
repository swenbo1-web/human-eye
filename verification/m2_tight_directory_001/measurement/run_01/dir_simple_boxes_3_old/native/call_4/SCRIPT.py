import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"5386e44a6d4a4e8eae66c32fddbb1a10","command":"capture","params":{}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_d0424797dbdc718c3caf')
    if _module is None or getattr(_module, '_resident_tag', None) != 'ef2c1bf93548652ba1b802e48e267d400d89daa57bcd91d133719a9cf6c9ad6f': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"92ffb493fa6649eaa2a62a43e2c46201","epoch":1,"resources":{"mesh:(\'uid\', 162)":1,"mesh:(\'uid\', 161)":2,"mesh:(\'uid\', 160)":3}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))