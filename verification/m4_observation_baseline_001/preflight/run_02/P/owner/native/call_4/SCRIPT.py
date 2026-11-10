import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"9fcafe7097214253bd5c447cdec075db","command":"capture_nearest_candidates","params":{"focal_id":null,"deadline_ns":446102788745700,"max_response_bytes":67108864,"selector":{"name":"N01"}}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_9f4246b978908b23a43d')
    if _module is None or getattr(_module, '_resident_tag', None) != 'ef2c1bf93548652ba1b802e48e267d400d89daa57bcd91d133719a9cf6c9ad6f': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_nearest_candidates')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"977369ac9ac441818f72608fb0814289","epoch":1,"resources":{"mesh:(\'uid\', 160)":1,"mesh:(\'uid\', 161)":2}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))