import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"b7fda955af6b4cee98547d858ef33589","command":"capture_task","params":{"selectors":[{"id":"blender:afcc51e411ca68b983a0694feb774b3957d8d7c8b77c3891c64370769c3b2322"},{"id":"blender:323b5565fcb5014a11333bca5ce3d9f10f7582ab3fe12ad54a3226cf8862f275"},{"id":"blender:062df577dcad016bc47d3e4751883d679b4e30e6cbf9b94d4cf53f8bc2e77d25"},{"id":"blender:1c2752f8185d38e88855c532967fc0309620ea0744c6d72a5dd1c462462dd116"}]}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_1ef94ba05142eafe9251')
    if _module is None or getattr(_module, '_resident_tag', None) != 'd5cf7c47dcd0f379ec81f03f3aa8a5e31a05205c84c0c08e912f54a28bc22e1d': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_task_scene')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('null'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))