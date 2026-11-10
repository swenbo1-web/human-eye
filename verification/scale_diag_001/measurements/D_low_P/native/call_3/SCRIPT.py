import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"79e9578ff9a04be1a530249d9c7e6407","command":"capture_nearest_candidates","params":{"focal_id":null,"deadline_ns":402641491062000,"max_response_bytes":67108864,"selector":{"name":"Target"}}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_336ea59b4e1c0363bc2d')
    if _module is None or getattr(_module, '_resident_tag', None) != 'ef2c1bf93548652ba1b802e48e267d400d89daa57bcd91d133719a9cf6c9ad6f': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_nearest_candidates')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"79f887549050416fb230574d9ccfd2e5","epoch":1,"resources":{"mesh:(\'uid\', 160)":1,"mesh:(\'uid\', 166)":2,"mesh:(\'uid\', 163)":3,"mesh:(\'uid\', 161)":4,"mesh:(\'uid\', 170)":5,"mesh:(\'uid\', 168)":6,"mesh:(\'uid\', 169)":7,"mesh:(\'uid\', 164)":8,"mesh:(\'uid\', 167)":9,"mesh:(\'uid\', 162)":10,"mesh:(\'uid\', 171)":11,"mesh:(\'uid\', 165)":12}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))