import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"4b1702f7e5694d48aedfd69b6862d47f","command":"capture_task","params":{"selectors":[{"name":"M4_Far_00"}]}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_86c4edbc6345ff2998a3')
    if _module is None or getattr(_module, '_resident_tag', None) != 'e4ee9d4be4fb2add65999d19a149e7ccbb7fe11c34c993f9c8987e161b5a60d0': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_task_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"4a17a47fb93848c0a7e9c44b33b8d858","epoch":1,"resources":{"mesh:(\'uid\', 173)":2,"mesh:(\'uid\', 172)":3,"mesh:(\'uid\', 161)":4,"mesh:(\'uid\', 160)":1}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))