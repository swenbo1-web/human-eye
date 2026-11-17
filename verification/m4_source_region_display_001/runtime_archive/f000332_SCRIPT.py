import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"32e0d5c573f345ce87d3e4ae10cd81c0","command":"capture","params":{}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_5c6ceda0f3467eb86314')
    if _module is None or getattr(_module, '_resident_tag', None) != '588f12a5001adb5df66b57ca8f8f2c3c20207192b6d141bd3ef8c7e01cb7d7f0': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"6b2772cc8bec44f49d99c5cdffd4a48a","epoch":1,"resources":{"mesh:(\'uid\', 162)":1,"mesh:(\'uid\', 164)":2}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))