
import json as residency_json
import os as residency_os
import sys as residency_sys
import time as residency_time
residency_started = residency_time.perf_counter_ns()
residency_slot = '_human_eye_mcp_resident_5c6ceda0f3467eb86314'
residency_module = residency_sys.modules.get(residency_slot)
if residency_module is None:
    raise ValueError('fixed_resident_module_unavailable')
if getattr(residency_module, '_READONLY_LOADED_HOST_SHA256', None) != '2cd8113ab9a59cfa6a95c07b817a71e33a0ee61fca249e58b0b5b1eba6213db5':
    raise ValueError('fixed_resident_module_source_mismatch')
residency_host = getattr(residency_module, '_mcp_resident_host', None)
if residency_host is None:
    raise ValueError('fixed_resident_host_unavailable')
residency_counters = residency_host.residency_work()
if any(type(residency_counters.get(key)) is not int or residency_counters[key] < 0
       for key in ('display_snapshots', 'display_objects', 'display_read_ns')):
    raise ValueError('fixed_resident_display_counters_unavailable')
print('HOST_RESIDENCY_WORK:' + residency_json.dumps({
    'process_id': residency_os.getpid(), 'module_slot': residency_slot,
    'module_file': residency_module.__file__,
    'loaded_host_source_sha256': residency_module._READONLY_LOADED_HOST_SHA256,
    'read_started_ns': residency_started, 'read_complete_ns': residency_time.perf_counter_ns(),
    'counters': residency_counters}, sort_keys=True, allow_nan=False))
