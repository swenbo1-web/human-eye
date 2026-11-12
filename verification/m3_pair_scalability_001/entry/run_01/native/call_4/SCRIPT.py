import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"ee399b3a11b74d008d9118ec7440f43d","command":"capture_task","params":{"selectors":[{"id":"blender:364b717780026b35ad74245b704af33d41cc860ef063cde8d14c8098e3a870f7"},{"id":"blender:576ab516f1739b4b6cf9587d278e8136d40682a0c7161ea0b5b14ed2f46623c2"}]}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_b929a9a877da41849706')
    if _module is None or getattr(_module, '_resident_tag', None) != 'd5cf7c47dcd0f379ec81f03f3aa8a5e31a05205c84c0c08e912f54a28bc22e1d': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_task_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"2ebabdbb7a1a44edbb40b2800cfcd1af","epoch":1,"resources":{"mesh:(\'uid\', 160)":1,"mesh:(\'uid\', 163)":2,"mesh:(\'uid\', 172)":3,"mesh:(\'uid\', 173)":4}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))