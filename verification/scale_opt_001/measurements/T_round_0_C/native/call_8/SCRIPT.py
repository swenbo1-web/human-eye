import json as _json, contextlib as _cl, io as _io
_request = _json.loads('{"id":"ce12de82a8eb487f9f1716794899881a","command":"capture_nearest_candidates","params":{"focal_id":null,"deadline_ns":406324019890400,"max_response_bytes":67108864,"selector":{"name":"Target"}}}')
try:
    import sys as _sys
    _module = _sys.modules.get('_human_eye_mcp_resident_2530d3fca55050c3300a')
    if _module is None or getattr(_module, '_resident_tag', None) != 'ef2c1bf93548652ba1b802e48e267d400d89daa57bcd91d133719a9cf6c9ad6f': raise RuntimeError('Resident Blender host unavailable; reconnect with a new connector')
    _host = _module._mcp_resident_host
    with _cl.redirect_stdout(_io.StringIO()):
        _result = getattr(_host, 'capture_nearest_candidates')(**_request['params'])
    _result = _host.capture_delta(_result, _json.loads('{"instance_id":"184b759fefc0487486374cdaa12d90de","epoch":1,"resources":{"mesh:(\'uid\', 160)":1,"mesh:(\'uid\', 187)":2,"mesh:(\'uid\', 190)":3,"mesh:(\'uid\', 186)":4,"mesh:(\'uid\', 191)":5,"mesh:(\'uid\', 170)":6,"mesh:(\'uid\', 166)":7,"mesh:(\'uid\', 163)":8,"mesh:(\'uid\', 161)":9,"mesh:(\'uid\', 178)":10,"mesh:(\'uid\', 200)":11,"mesh:(\'uid\', 181)":12,"mesh:(\'uid\', 197)":13,"mesh:(\'uid\', 199)":14,"mesh:(\'uid\', 206)":15,"mesh:(\'uid\', 179)":16,"mesh:(\'uid\', 203)":17,"mesh:(\'uid\', 168)":18,"mesh:(\'uid\', 169)":19,"mesh:(\'uid\', 171)":20,"mesh:(\'uid\', 204)":21,"mesh:(\'uid\', 193)":22,"mesh:(\'uid\', 175)":23,"mesh:(\'uid\', 164)":24,"mesh:(\'uid\', 205)":25,"mesh:(\'uid\', 185)":26,"mesh:(\'uid\', 167)":27,"mesh:(\'uid\', 176)":28,"mesh:(\'uid\', 162)":29,"mesh:(\'uid\', 188)":30,"mesh:(\'uid\', 183)":31,"mesh:(\'uid\', 195)":32,"mesh:(\'uid\', 202)":33,"mesh:(\'uid\', 207)":34,"mesh:(\'uid\', 184)":35,"mesh:(\'uid\', 196)":36,"mesh:(\'uid\', 177)":37,"mesh:(\'uid\', 174)":38,"mesh:(\'uid\', 173)":39,"mesh:(\'uid\', 201)":40,"mesh:(\'uid\', 182)":41,"mesh:(\'uid\', 189)":42,"mesh:(\'uid\', 194)":43,"mesh:(\'uid\', 198)":44,"mesh:(\'uid\', 192)":45,"mesh:(\'uid\', 165)":46,"mesh:(\'uid\', 172)":47,"mesh:(\'uid\', 180)":48}}'))
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'result': _result}
except Exception as _exc:
    _envelope = {'protocol_version': '1.0', 'id': _request['id'], 'error': {'type': type(_exc).__name__, 'message': str(_exc)[:2000], 'mutation_uncertain': _request['command'] == 'apply'}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':')))