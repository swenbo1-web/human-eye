"""Pure installed formatter worker with separately measured work and memory."""
import argparse
import base64
import copy
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import tracemalloc
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    options = parser.parse_args()
    binding = json.loads(options.binding.read_bytes())
    sys.path.insert(0, binding['dependency_root'])
    loader = ROOT / 'verification/m4_source_region_display_001/harness/reused/verified_bootstrap.py'
    spec = importlib.util.spec_from_file_location('_projection_installed_bootstrap', loader)
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    guard = bootstrap.bootstrap(binding)
    from human_eye_plugin import live_spatial_mcp as mcp
    from PIL import Image
    import numpy as np
    def forbidden_encoding(*args, **kwargs):
        raise AssertionError('PNG_NPZ_or_raster_construction_forbidden')
    Image.Image.save = forbidden_encoding
    np.savez_compressed = forbidden_encoding
    import human_eye_plugin.active_observation_images as image_module
    image_module.rasterize_attention = forbidden_encoding
    cases = json.loads((HERE / 'BASELINE.json').read_bytes())['cases']
    values = {row['case_id']: json.loads(Path(row['full_path']).read_bytes()) for row in cases}
    original_sha = {key: digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()) for key, value in values.items()}
    originals = {row['case_id']: Path(row['PNG_path']).read_bytes() for row in cases}
    std_copy, std_json = mcp.copy, mcp.json
    for raw in sys.stdin.buffer:
        request = json.loads(raw)
        try:
            args = request.get('params', {})
            case = args['case']
            value = values[case]
            operation = request['method']
            count = args.get('iterations', 1)
            if type(count) is not int or not 1 <= count <= 100:
                raise ValueError('bounded_projection_iterations')
            detail = args.get('detail')
            counters = {'formatter_deepcopy_calls': 0, 'deepcopy_argument_JSON_UTF8_bytes': 0,
                        'formatter_json_dumps_calls': 0, 'formatter_json_dumps_UTF8_bytes': 0}
            def counted_copy(item, *args, **kwargs):
                counters['formatter_deepcopy_calls'] += 1
                counters['deepcopy_argument_JSON_UTF8_bytes'] += len(std_json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode())
                return std_copy.deepcopy(item, *args, **kwargs)
            def counted_json(item, *args, **kwargs):
                output = std_json.dumps(item, *args, **kwargs)
                counters['formatter_json_dumps_calls'] += 1
                counters['formatter_json_dumps_UTF8_bytes'] += len(output.encode())
                return output
            if operation == 'profile':
                mcp.copy = types.SimpleNamespace(deepcopy=counted_copy)
                mcp.json = types.SimpleNamespace(dumps=counted_json)
            if operation == 'memory':
                gc.collect()
                tracemalloc.start()
            audits = []
            started = time.perf_counter_ns()
            try:
                previous = None
                call_elapsed = 0
                for _ in range(count):
                    audit = {}
                    call_started = time.perf_counter_ns()
                    result = mcp._tool_result(value, is_error=False, response_detail=detail, active_delivery_audit=audit)
                    call_elapsed += time.perf_counter_ns() - call_started
                    if previous is not None and result != previous:
                        raise ValueError('repeated_pure_format_output_changed')
                    previous = result
                    audits.append(audit)
                elapsed = call_elapsed
                window_elapsed = time.perf_counter_ns() - started
                memory = tracemalloc.get_traced_memory() if operation == 'memory' else None
            finally:
                if operation == 'memory':
                    tracemalloc.stop()
                mcp.copy, mcp.json = std_copy, std_json
            text = result['content'][0]['text']
            images = []
            for block in result['content'][1:]:
                image = base64.b64decode(block['data'], validate=True)
                if image != originals[case]:
                    raise ValueError('original_PNG_bytes_changed')
                images.append({'sha256': digest(image), 'bytes': len(image), 'base64_bytes': len(block['data'])})
            after = digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())
            assert after == original_sha[case]
            guard.verify_loaded()
            reply = {'case': case, 'operation': operation, 'detail': detail, 'iterations': count,
                'elapsed_ns': elapsed, 'window_elapsed_ns': window_elapsed,
                'text': text, 'text_UTF8_bytes': len(text.encode()),
                'text_sha256': digest(text.encode()), 'native_images': images, 'counters': counters,
                'Python_tracemalloc_current_peak_bytes': memory, 'input_unchanged': True,
                'source_sha256': binding['source_sha256'], 'import_path': mcp.__file__, 'audit': audits[-1],
                'PNG_NPZ_encodes': 0, 'raster': 0}
            if operation == 'export':
                reply['tool_result'] = result
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': reply}
        except BaseException as error:
            mcp.copy, mcp.json = std_copy, std_json
            response = {'jsonrpc': '2.0', 'id': request.get('id'), 'error': {'type': type(error).__name__, 'message': str(error)}}
        sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False, separators=(',', ':')) + '\n').encode())
        sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
