import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"e04919cb7f8f4221b97c09eada38f312","command":"capture","params":{}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_88c504056a21b011ecca')
    if _module is None or getattr(_module, '_resident_tag', None) != 'e4ee9d4be4fb2add65999d19a149e7ccbb7fe11c34c993f9c8987e161b5a60d0': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"51fbab38fc7842fab8f677f10f887a8d","epoch":1,"resources":{"mesh:(\'uid\', 164)":1,"mesh:(\'uid\', 170)":2,"mesh:(\'uid\', 166)":3,"mesh:(\'uid\', 165)":4,"mesh:(\'uid\', 160)":5,"mesh:(\'uid\', 163)":6,"mesh:(\'uid\', 169)":7,"mesh:(\'uid\', 167)":8,"mesh:(\'uid\', 161)":9,"mesh:(\'uid\', 168)":10,"mesh:(\'uid\', 162)":11}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))