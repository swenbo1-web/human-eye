import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"599a8398ed904afdb95cefd2dfbe53dc","command":"capture","params":{}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_7e2fa6969d1817c69acb')
    if _module is None or getattr(_module, '_resident_tag', None) != '677bc32ffe2b3cfc86abc7c9d6bedfbb789d51c582e1810cf3bc888882c4fd92': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"2cd27d0729be4ebaac73569e6bf6f61a","epoch":1,"resources":{"mesh:(\'uid\', 136)":1}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))