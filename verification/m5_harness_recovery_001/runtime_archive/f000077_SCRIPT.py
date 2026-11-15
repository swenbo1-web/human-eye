import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"b32eb2466026486286f7a1f6c31b068c","command":"capture_active_observation","params":{"selector":{"name":"M4_Far_00"},"deadline_ns":277605021096599,"max_response_bytes":67108864}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_86c4edbc6345ff2998a3')
    if _module is None or getattr(_module, '_resident_tag', None) != 'e4ee9d4be4fb2add65999d19a149e7ccbb7fe11c34c993f9c8987e161b5a60d0': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_active_observation')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"aa4cf9e8b5f641b3b635c890f3abc7c5","epoch":1,"resources":{"mesh:(\'uid\', 162)":2,"mesh:(\'uid\', 163)":3,"mesh:(\'uid\', 173)":4,"mesh:(\'uid\', 172)":5,"mesh:(\'uid\', 161)":6,"mesh:(\'uid\', 160)":1}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))