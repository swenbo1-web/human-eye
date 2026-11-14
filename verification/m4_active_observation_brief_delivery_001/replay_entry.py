"""Normal installed MCP serialization of five fixed historical service values.

Only the service value is a harness fixture. The installed MCP dispatcher,
public projection, PNG validation, encoding and stdio loop are used directly.
No host or observation engine is created by this entry.
"""

import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


CASE_ORDER = ('ordinary', 'same_source_repeat', 'recovery_rename_baseline',
              'renamed_source', 'nonplanar_source')
DETAIL_ORDER = ('default', 'brief', 'full')


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                       separators=(',', ':')) + '\n').encode('ascii')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def append(path, value):
    with Path(path).open('ab') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_cases(inputs_path):
    """Validate owned originals and remap only registered image_path fields."""
    path = Path(inputs_path).resolve()
    manifest = json.loads(path.read_bytes())
    assert [row['case'] for row in manifest['cases']] == list(CASE_ORDER)
    cases = []
    for row in manifest['cases']:
        response_path = (path.parent / row['raw_response']).resolve()
        raw = response_path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row['raw_response_sha256']
        response = json.loads(raw)
        assert response['id'] == row['case']
        assert response['result']['isError'] is False
        content = response['result']['content']
        assert content[0]['type'] == 'text' and all(block['type'] == 'image' for block in content[1:])
        original = json.loads(content[0]['text'])
        assert original['result_kind'] == 'active_observation'
        assert len(original['frames']) == len(content) - 1 == len(row['images'])
        replacements = {}
        images = []
        for image, frame, block in zip(row['images'], original['frames'], content[1:]):
            image_path = (path.parent / image['file']).resolve()
            image_raw = image_path.read_bytes()
            assert image['source_image_path'] == frame['image_path']
            assert image['image_ref'] == frame['image_ref']
            assert image['sha256'] == frame['image_sha256'] == hashlib.sha256(image_raw).hexdigest()
            assert image['bytes'] == frame['PNG_bytes'] == len(image_raw)
            assert block['mimeType'] == 'image/png' and base64.b64decode(block['data'], validate=True) == image_raw
            assert image['source_image_path'] not in replacements
            replacements[image['source_image_path']] = str(image_path)
            images.append({'image_ref': frame['image_ref'], 'view_name': frame['view_name'],
                           'source_image_path': frame['image_path'], 'mapped_image_path': str(image_path),
                           'sha256': image['sha256'], 'bytes': len(image_raw)})
        changes = []

        def remap(value, pointer=''):
            if isinstance(value, dict):
                result = {}
                for key, item in value.items():
                    location = pointer + '/' + key.replace('~', '~0').replace('/', '~1')
                    if key == 'image_path':
                        assert item in replacements, 'unregistered_historical_image_path'
                        result[key] = replacements[item]
                        changes.append({'pointer': location, 'original': item, 'mapped': result[key]})
                    else:
                        result[key] = remap(item, location)
                return result
            if isinstance(value, list):
                return [remap(item, pointer + '/' + str(index)) for index, item in enumerate(value)]
            return value

        mapped = remap(original)
        cases.append({'case': row['case'], 'raw_response_path': str(response_path),
                      'raw_response_sha256': row['raw_response_sha256'],
                      'original_response': response, 'historical_value': original,
                      'mapped_value': mapped, 'images': images, 'path_changes': changes,
                      'historical_text_UTF8_bytes': len(content[0]['text'].encode('utf8'))})
    return cases


class HistoricalService:
    def __init__(self, cases, evidence, deadline_ns):
        self.cases = cases
        self.evidence = evidence
        self.deadline_ns = deadline_ns
        self.calls = []

    def _check_request_budget(self, stage, **kwargs):
        if time.perf_counter_ns() >= self.deadline_ns:
            raise TimeoutError('original_replay_deadline_exceeded:' + stage)

    def observe(self, session_id, task_instruction='', focal_id=None, reference_id=None,
                *, include_image=True, query=None):
        self._check_request_budget('historical_service_intake')
        index = len(self.calls)
        if index >= len(self.cases) * len(DETAIL_ORDER):
            raise ValueError('fixed_fifteen_replay_calls_exhausted')
        case = self.cases[index // len(DETAIL_ORDER)]
        detail = DETAIL_ORDER[index % len(DETAIL_ORDER)]
        assert query == {'mode': 'active_observation'} and include_image is True
        assert not task_instruction and focal_id is None and reference_id is None
        assert session_id == case['historical_value']['session_id']
        row = {'index': index + 1, 'case': case['case'], 'response_detail': detail,
               'started_ns': time.perf_counter_ns(), 'transport_replay': True,
               'historical_response_sha256': case['raw_response_sha256'],
               'actual_new_capture_calls': 0, 'actual_new_prepare_calls': 0,
               'actual_new_raster_attempts': 0, 'actual_new_local_image_constructions': 0}
        value = copy.deepcopy(case['mapped_value'])
        row['closed_ns'] = time.perf_counter_ns()
        row['elapsed_ns'] = row['closed_ns'] - row['started_ns']
        self.calls.append(row)
        append(self.evidence / 'SERVICE_CALLS.jsonl', row)
        return value

    def record_event(self, event, **fields):
        append(self.evidence / 'PRODUCT_EVENTS.jsonl', {
            'event': event, 'fields': fields, 'at_ns': time.perf_counter_ns(),
            'transport_replay': True,
            'call': None if not self.calls else self.calls[-1],
        })

    def close(self):
        save(self.evidence / 'STUB_CLOSE.json', {
            'calls': len(self.calls), 'fixed_call_count_completed': len(self.calls) == 15,
            'transport_replay': True, 'actual_new_capture_prepare_raster_calls': 0,
            'model_calls': 0, 'closed_ns': time.perf_counter_ns(),
        })


def serve(inputs_path, binding_path, bootstrap_path, evidence_directory, deadline_ns):
    started = time.perf_counter_ns()
    evidence = Path(evidence_directory).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    cases = load_cases(inputs_path)
    for case in cases:
        save(evidence / 'injected' / case['case'] / 'MAPPED_VALUE.json', case['mapped_value'])
        save(evidence / 'injected' / case['case'] / 'PATH_MAPPING.json', {
            'raw_response_sha256': case['raw_response_sha256'], 'path_changes': case['path_changes'],
            'images': case['images'], 'only_image_path_fields_mapped': True,
            'historical_work_and_source_fields_retained': True,
        })
    binding_raw = Path(binding_path).read_bytes()
    bootstrap = load('_brief_replay_verified_bootstrap', bootstrap_path)
    guard = bootstrap.bootstrap(json.loads(binding_raw))
    from human_eye_plugin import live_spatial_mcp as mcp

    mcp._configure_utf8_stdio()
    service = HistoricalService(cases, evidence, deadline_ns)
    original_content = mcp._active_observation_content
    original_projection = mcp.project_active_observation_brief
    original_encode = mcp.wire.encode_response

    def project(value):
        mark = time.perf_counter_ns()
        failed = None
        projected = None
        try:
            projected = original_projection(value)
            return projected
        except BaseException as exc:
            failed = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            closed = time.perf_counter_ns()
            append(evidence / 'PROJECTION_PHASES.jsonl', {
                'call': service.calls[-1] if service.calls else None,
                'started_ns': mark, 'closed_ns': closed, 'elapsed_ns': closed - mark,
                'returned_projection': isinstance(projected, dict), 'error': failed,
                'transport_replay': True, 'nesting': 'inside original active-content call',
                'wrapper_evidence_write_outside_measured_original_call': True,
            })

    def content(value, **kwargs):
        mark = time.perf_counter_ns()
        failed = None
        try:
            return original_content(value, **kwargs)
        except BaseException as exc:
            failed = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            closed = time.perf_counter_ns()
            append(evidence / 'CONTENT_PHASES.jsonl', {
                'call': service.calls[-1] if service.calls else None,
                'started_ns': mark, 'closed_ns': closed, 'elapsed_ns': closed - mark,
                'error': failed, 'transport_replay': True,
                'wrapper_evidence_write_outside_measured_original_call': True,
            })

    def encode(response, *args, **kwargs):
        mark = time.perf_counter_ns()
        value = original_encode(response, *args, **kwargs)
        closed = time.perf_counter_ns()
        append(evidence / 'WIRE_ENCODING_PHASES.jsonl', {
            'request_id': response.get('id'), 'started_ns': mark, 'closed_ns': closed,
            'elapsed_ns': closed - mark, 'UTF8_bytes': len(value.encode('utf8')),
            'transport_replay': True, 'wrapper_evidence_write_outside_measured_original_call': True,
        })
        return value

    mcp._active_observation_content = content
    mcp.project_active_observation_brief = project
    mcp.wire.encode_response = encode
    guard.verify_loaded()
    save(evidence / 'START.json', {
        'pid': os.getpid(), 'started_ns': started, 'ready_ns': time.perf_counter_ns(),
        'binding_sha256': hashlib.sha256(binding_raw).hexdigest(),
        'inputs_sha256': hashlib.sha256(Path(inputs_path).read_bytes()).hexdigest(),
        'transport_replay': True, 'fixed_service_calls': 15,
        'original_content_source': original_content.__code__.co_filename,
        'original_content_source_sha256': hashlib.sha256(Path(original_content.__code__.co_filename).read_bytes()).hexdigest(),
        'original_projection_callable': original_projection.__qualname__,
        'instrumentation': ['original active content callable once',
                            'original brief projection callable once when invoked',
                            'original wire encode callable once'],
    })
    failure = None
    try:
        mcp.run_stdio_mcp_server(service)
    except BaseException as exc:
        failure = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        source_error = None
        try:
            guard.verify_loaded()
        except BaseException as exc:
            source_error = {'type': type(exc).__name__, 'message': str(exc)}
        save(evidence / 'FINISH.json', {
            'pid': os.getpid(), 'started_ns': started, 'closed_ns': time.perf_counter_ns(),
            'failure': failure, 'source_error': source_error, 'service_calls': len(service.calls),
            'transport_replay': True, 'actual_new_capture_prepare_raster_calls': 0,
            'model_calls': 0, 'evidence_wrapper_writes_in_outer_wallclock': True,
        })
        if source_error is not None and failure is None:
            raise RuntimeError('final_source_check_failed:' + str(source_error))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--binding', required=True)
    parser.add_argument('--bootstrap', required=True)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--deadline-ns', required=True, type=int)
    args = parser.parse_args()
    serve(args.inputs, args.binding, args.bootstrap, args.evidence, args.deadline_ns)
