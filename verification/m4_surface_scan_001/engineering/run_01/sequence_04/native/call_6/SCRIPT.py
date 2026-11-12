import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"15a82733b0734fb9b0aee28699ac416b","command":"capture_surface_scan","params":{"threshold_m":0.002,"deadline_ns":595863792351600,"max_response_bytes":67108864}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_846fa1ed5299be061216')
    if _module is None or getattr(_module, '_resident_tag', None) != '58605b7b7de3417d5206d62386977602a711208567b4b2d77458839af63b2598': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_surface_scan')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"ea60b17fb2ab448fb0aefcc6ee3b63f5","epoch":1,"resources":{"mesh:(\'uid\', 173)":1,"mesh:(\'uid\', 168)":2,"mesh:(\'uid\', 175)":3,"mesh:(\'uid\', 184)":4,"mesh:(\'uid\', 181)":5,"mesh:(\'uid\', 164)":6,"mesh:(\'uid\', 177)":7,"mesh:(\'uid\', 165)":8,"mesh:(\'uid\', 178)":9,"mesh:(\'uid\', 163)":10,"mesh:(\'uid\', 180)":11,"mesh:(\'uid\', 182)":12,"mesh:(\'uid\', 176)":13,"mesh:(\'uid\', 185)":14,"mesh:(\'uid\', 170)":15,"mesh:(\'uid\', 169)":16,"mesh:(\'uid\', 167)":17,"mesh:(\'uid\', 171)":18,"mesh:(\'uid\', 183)":19,"mesh:(\'uid\', 166)":20,"mesh:(\'uid\', 174)":21,"mesh:(\'uid\', 172)":22,"mesh:(\'uid\', 179)":23,"mesh:(\'uid\', 162)":24}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))