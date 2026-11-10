import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"f45b040050b045d0b4070930dbbb5f0f","command":"capture_nearest_candidates","params":{"focal_id":"blender:0f009b2dff3bddcda7f17dfb7422dd76264b45dcf73420cd69a17739bb2968a2","deadline_ns":439437437035500,"max_response_bytes":67108864}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_9f180f143fbf58a86540')
    if _module is None or getattr(_module, '_resident_tag', None) != 'ef2c1bf93548652ba1b802e48e267d400d89daa57bcd91d133719a9cf6c9ad6f': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_nearest_candidates')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"90d263d799ea4a81b1d1683559c1a604","epoch":1,"resources":{"mesh:(\'uid\', 167)":1,"mesh:(\'uid\', 162)":2,"mesh:(\'uid\', 166)":3,"mesh:(\'uid\', 164)":4,"mesh:(\'uid\', 165)":5,"mesh:(\'uid\', 163)":6}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))