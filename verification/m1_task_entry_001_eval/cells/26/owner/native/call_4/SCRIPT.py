import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"857df5b9148f48dc8b8342f9f6c5ea6c","command":"capture_task","params":{"selectors":[{"name":"Mesh_D17AB2"},{"name":"Mesh_A7A7A6"},{"name":"Mesh_A89EE8"},{"name":"Mesh_A9E055"}]}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_9f180f143fbf58a86540')
    if _module is None or getattr(_module, '_resident_tag', None) != 'ef2c1bf93548652ba1b802e48e267d400d89daa57bcd91d133719a9cf6c9ad6f': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_task_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"7d0129021b5c4583815f7f08b2e75d3e","epoch":1,"resources":{"mesh:(\'uid\', 164)":1,"mesh:(\'uid\', 165)":2,"mesh:(\'uid\', 170)":3,"mesh:(\'uid\', 163)":4}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))