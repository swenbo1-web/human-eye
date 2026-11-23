"""Measure the installed TCP read path and the matching in-Blender stages."""

from contextlib import contextmanager
from pathlib import Path


PREVIOUS = Path(__file__).resolve().parents[1]/'m2_source_region_shared_normalization_live_001/meter.py'
COMMANDS = ('capture','capture_source_region_pair')
SETUP = """    import time as _m2_time
    _m2_rows = []
    _m2_before = _host.residency_work()
    def _m2_watch(_m2_name, _m2_fn):
        def _m2_timed(*args, **kwargs):
            _m2_start = _m2_time.perf_counter_ns()
            _m2_value = _m2_fn(*args, **kwargs)
            _m2_close = _m2_time.perf_counter_ns()
            _m2_row = dict(name=_m2_name, started_ns=_m2_start, closed_ns=_m2_close, elapsed_ns=_m2_close-_m2_start)
            if _m2_name == '_objects':
                _m2_row['candidate_objects'] = len(_m2_value)
            elif _m2_name == '_task_objects':
                _m2_row['candidate_objects'] = _m2_value[1]['candidate_count']
            _m2_rows.append(_m2_row)
            return _m2_value
        return _m2_timed
    for _m2_name in ('_objects', '_task_objects', '_capture', '_resident_capture', 'capture_delta'):
        setattr(_host, _m2_name, _m2_watch(_m2_name, getattr(_host,_m2_name)))
        _m2_patched.append(_m2_name)
"""
EMISSION = """
for _m2_name in _m2_patched:
    delattr(_host, _m2_name)
_m2_encode_start = _m2_clock()
_m2_encoded = _json.dumps(_envelope, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
_m2_encode_close = _m2_clock()
if _m2_patched:
    _m2_native_last_work = dict(
        intervals=_m2_rows, residency_before=_m2_before, residency_after=_host.residency_work(),
        envelope_encoding=dict(started_ns=_m2_encode_start,closed_ns=_m2_encode_close,
        elapsed_ns=_m2_encode_close-_m2_encode_start))
print('HUMAN_EYE_BLENDER_MCP:' + _m2_encoded)
"""


def resident_code(original,host,command,params,request_id,limit):
    code = original(host,command,params,request_id,limit)
    if command not in COMMANDS:
        return code
    anchor = '    _host = _module._mcp_resident_host\n'
    body,separator,last = code.rpartition('\n')
    if code.count(anchor) != 1 or not separator or not last.startswith("print('HUMAN_EYE_BLENDER_MCP:'"):
        raise ValueError('actual_native_meter_anchor_changed')
    prefix = 'from time import perf_counter_ns as _m2_clock\n_m2_patched = []\n'
    return prefix + body.replace(anchor,anchor + SETUP,1) + '\n' + EMISSION


def timing_scope():
    inherited = PREVIOUS.read_text(encoding='utf8')
    for before,after in (
        ('if command != "capture":', 'if command not in ("capture", "capture_source_region_pair"):'),
        ('def observed_exchange(host, payload):', 'def observed_exchange(host, payload, **limits):'),
        ('return exchange(host, payload)', 'return exchange(host, payload, **limits)'),
        ('name = "outer_strict_json" if in_exchange else "inner_strict_json"',
         'name = "outer_strict_json" if in_exchange else "inner_strict_json"\n'
         '        if in_exchange: active["response_bytes"] = len(data.encode("utf8"))'),
    ):
        if before not in inherited:
            raise ValueError('retained_transport_meter_anchor_changed')
        inherited = inherited.replace(before,after)
    scope = {'__file__':str(PREVIOUS),'__name__':'_selective_retained_meter'}
    exec(compile(inherited,str(PREVIOUS),'exec'),scope)
    return scope['observe_installed']


@contextmanager
def observe_installed(evidence_dir, source_sha256):
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost

    old_code = BlenderMCPHost._resident_code

    def measured(host,command,params,request_id,limit):
        return resident_code(old_code,host,command,params,request_id,limit)

    scope = timing_scope()
    BlenderMCPHost._resident_code = measured
    try:
        with scope(evidence_dir,source_sha256):
            yield
    finally:
        BlenderMCPHost._resident_code = old_code
