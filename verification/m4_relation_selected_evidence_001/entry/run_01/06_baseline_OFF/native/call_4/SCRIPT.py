import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"a85e6854ee0442b38d7769d6604d2fd6","command":"capture_task","params":{"selectors":[{"name":"N16"},{"name":"N13"},{"name":"N08"},{"name":"N28"}]}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_fb1b662dfcfd5df13bf6')
    if _module is None or getattr(_module, '_resident_tag', None) != 'ef2c1bf93548652ba1b802e48e267d400d89daa57bcd91d133719a9cf6c9ad6f': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_task_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"06216037b5e040aeba5a271305a669b4","epoch":1,"resources":{"mesh:(\'uid\', 187)":1,"mesh:(\'uid\', 172)":2,"mesh:(\'uid\', 175)":3,"mesh:(\'uid\', 167)":4}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))