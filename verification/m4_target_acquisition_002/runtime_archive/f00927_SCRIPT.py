import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"37cff214d36740a3a12a6447828158ed","command":"capture_task","params":{"selectors":[{"name":"M4_Far_00"}]}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_0afc0ef3c66fc9d31b46')
    if _module is None or getattr(_module, '_resident_tag', None) != 'bc7abdb18e4bd5f246f9add9054bdf37e56adfb25b4850c001507fb56b4ed1df': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_task_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"2d6f6df289b34920a11f032eeed9b6e7","epoch":1,"resources":{"mesh:(\'uid\', 160)":1}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))