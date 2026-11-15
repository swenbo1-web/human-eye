import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"e59a632c7e0b4fb7874075e642066735","command":"capture_task","params":{"selectors":[{"name":"M4_Far_00"}]}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_6b28068ddacbfad9020a')
    if _module is None or getattr(_module, '_resident_tag', None) != '6dd3c62ca1469b23f1e4b72531dc4d6e2b4af318234f589fe3dabccff1d3d268': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_task_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"c0ebdf375a2042e99eb89fa3bd4e5b85","epoch":1,"resources":{"mesh:(\'uid\', 162)":2,"mesh:(\'uid\', 169)":3,"mesh:(\'uid\', 165)":4,"mesh:(\'uid\', 170)":5,"mesh:(\'uid\', 163)":6,"mesh:(\'uid\', 166)":7,"mesh:(\'uid\', 171)":8,"mesh:(\'uid\', 164)":9,"mesh:(\'uid\', 173)":10,"mesh:(\'uid\', 168)":11,"mesh:(\'uid\', 172)":12,"mesh:(\'uid\', 167)":13,"mesh:(\'uid\', 161)":14,"mesh:(\'uid\', 160)":1}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))