assert bpy.app.version_string == '5.2.1 LTS', 'frozen_Blender_version_changed'
import importlib.util as _iu, json as _json, contextlib as _cl, io as _io, hashlib as _hl
_request = _json.loads('{"id":"47db10c011ee4bb38e881ab2e9d9d036","command":"capture_nearest_candidates","params":{"focal_id":"blender:e6734ab318ec55bba83f2b582c44f2469b8634c63aa4d4fa7ec74ea7dcaad75d","deadline_ns":161043032219500,"max_response_bytes":8388608}}')
try:
    from pathlib import Path as _Path
    _source = _Path('D:\\hefe\\verification\\fixes\\20261107_m4_acquisition\\review_qa_001\\baseline_A\\human_eye_plugin\\blender_host.py')
    if _source.resolve()!=_source: raise ValueError('Readonly host source escaped its fixed root')
    with _source.open('rb') as _stream: _source_bytes = _stream.read(512*1024+1)
    _source_sha = _hl.sha256(_source_bytes).hexdigest()
    if len(_source_bytes)>512*1024 or _source_sha!='ba83c5455f0e2a9a3e67443f04f4519fa064eabd6af108a6b94d3537783baa22': raise ValueError('Readonly host source differs from the fixed connector snapshot')
    _spec = _iu.spec_from_file_location('_human_eye_blender_native_read', 'D:\\hefe\\verification\\fixes\\20261107_m4_acquisition\\review_qa_001\\baseline_A\\human_eye_plugin\\blender_host.py')
    if _spec is None or _spec.loader is None: raise RuntimeError('Cannot load trusted native read host')
    _module = _iu.module_from_spec(_spec)
    exec(compile(_source_bytes,str(_source),'exec',dont_inherit=True),_module.__dict__)
    _module._READONLY_LOADED_HOST_SHA256 = _source_sha
    _host = _module.BlenderSceneHost(bpy_module=bpy, execution_metadata=True, identity_metadata=True)
    _supported = getattr(_host,'native_observation_protocol',None)=='typed-native-readonly-observation-v1-20261031'
    if _request['command'] in ('capture','capture_evidence'):
        if _request['params']: raise ValueError('Capture accepts no arguments')
        _result = _host.capture_scene() if _request['command']=='capture' else _host.capture_evidence()
    elif _request['command']=='capture_task':
        _result = _host.capture_task_scene(_request['params']['selectors'])
    elif _request['command']=='capture_nearest_candidates':
        _result = _host.capture_nearest_candidates(**_request['params'])
    elif _request['command']=='native_observation_capabilities':
        if _request['params']: raise ValueError('Capabilities accepts no arguments')
        _result = _host.native_observation_capabilities() if _supported else {'supported':False}
    else:
        if not _supported: raise ValueError('Typed native observation unavailable')
        with _cl.redirect_stdout(_io.StringIO()):
            if _request['command']=='observe_readonly_native':
                if set(_request['params'])!={'request_id','focal_id','reference_id','expected_capture_revision','deadline_ns','view'}: raise ValueError('Invalid readonly native arguments')
                _result = _host.observe_readonly_native(**_request['params'])
            elif _request['command']=='last_readonly_native_audit':
                if set(_request['params'])!={'request_id'}: raise ValueError('Invalid native audit arguments')
                _result = _host.last_readonly_native_audit(**_request['params'])
            else: raise ValueError('Unsupported fixed native observation command')
    _envelope = {'protocol_version':'1.0','id':_request['id'],'result':_result}
except Exception as _exc:
    _envelope = {'protocol_version':'1.0','id':_request['id'],'error':{'type':type(_exc).__name__,'message':str(_exc)[:2000],'mutation_uncertain':False}}
print('HUMAN_EYE_BLENDER_MCP:' + _json.dumps(_envelope,ensure_ascii=True,allow_nan=False,separators=(',',':')))