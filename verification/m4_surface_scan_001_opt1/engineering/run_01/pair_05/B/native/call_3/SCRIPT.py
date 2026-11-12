import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"9b6f5189a9d4439db7d3c3ecd1f57997","command":"capture_surface_scan","params":{"threshold_m":0.002,"deadline_ns":599292459642300,"max_response_bytes":67108864}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_cb1e9cb5d601826fd610')
    if _module is None or getattr(_module, '_resident_tag', None) != '677bc32ffe2b3cfc86abc7c9d6bedfbb789d51c582e1810cf3bc888882c4fd92': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_surface_scan')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"f8f123ec4e0d4f1fa9d3ebcbc2968c2d","epoch":1,"resources":{"mesh:(\'uid\', 173)":1,"mesh:(\'uid\', 168)":2,"mesh:(\'uid\', 175)":3,"mesh:(\'uid\', 184)":4,"mesh:(\'uid\', 181)":5,"mesh:(\'uid\', 164)":6,"mesh:(\'uid\', 177)":7,"mesh:(\'uid\', 165)":8,"mesh:(\'uid\', 178)":9,"mesh:(\'uid\', 163)":10,"mesh:(\'uid\', 180)":11,"mesh:(\'uid\', 182)":12,"mesh:(\'uid\', 176)":13,"mesh:(\'uid\', 185)":14,"mesh:(\'uid\', 170)":15,"mesh:(\'uid\', 169)":16,"mesh:(\'uid\', 167)":17,"mesh:(\'uid\', 171)":18,"mesh:(\'uid\', 183)":19,"mesh:(\'uid\', 166)":20,"mesh:(\'uid\', 174)":21,"mesh:(\'uid\', 172)":22,"mesh:(\'uid\', 179)":23,"mesh:(\'uid\', 162)":24}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))