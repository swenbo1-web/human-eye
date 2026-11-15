"""Closed B-first-qualification counters and stages, with frozen A context."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = Path('D:/he_m5_observe_measure_001/qualification/B_initial_qual')


def load(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def main():
    result = load(RUN / 'RESULT.json')
    published = load(RUN / 'PUBLICATION.json')
    producer = load(RUN / 'producer/call_001/SERVICE_RESULT.json')
    wire = load(RUN / 'SAVED_WIRE.json')
    context = load(RUN / 'producer/call_001/READ_CONTEXT.json')
    binding = load(result['binding_path'])
    checks = []

    def check(name, condition):
        checks.append(dict(name=name, passed=bool(condition)))
        if not condition:
            raise ValueError(name)

    check('closed first B transport scope', published['passed_transport_scope'] and not result['errors'])
    check('actual source matches frozen B binding', result['source_sha256'] == binding['source_sha256'])
    check('raw producer original SHA', pin(result['requests'][0]['producer']['path'])['sha256']
          == result['requests'][0]['producer']['sha256'])
    check('one combined public call', len(result['requests']) == 1 and 'task_result' in producer)
    calls = [row for row in wire['steps'] if row['type'] == 'execute_code']
    check('one actual active capture command', len(calls) == 1
          and calls[0]['command']['command'] == 'capture_active_observation')
    task = producer['work']['task_query']
    check('one solve no extra capture or raster', task['surface_pair_count'] == 1
          and task['supplemental_capture_calls'] == 0 and task['additional_raster_attempts'] == 0)
    check('actual source payloads match installation', all(pin(Path(binding['install_root']) / row['path'])['sha256']
          == row['sha256'] for row in wire['loaded_source_payloads']))
    arrays = context['after']['selections'][-1]['mesh_arrays']
    retained_bytes = sum(row['vertices_nbytes'] + row['faces_nbytes'] for row in arrays)
    check('task normalized mesh count and dimensions', len(arrays) == 2
          and sum(row['vertex_shape'][0] for row in arrays) == 296
          and sum(row['face_shape'][0] for row in arrays) == 515)
    check('retained arrays size actual metadata', retained_bytes == 13284)
    check('reported normalization bytes distinct retained size', task['normalized_array_payload_bytes'] == 19748)
    audit = [json.loads(line) for line in (RUN / 'audit.jsonl').read_bytes().splitlines()]
    traces = [row['trace'] for row in audit if row['event'] == 'request_trace']
    check('one actual server trace', len(traces) == 1)
    a = load(HERE / 'A_RESOURCE_BASELINE.json')
    pins = [pin(__file__), pin(HERE / 'A_RESOURCE_BASELINE.json'), pin(result['binding_path'])]
    pins += [pin(path) for path in sorted(RUN.rglob('*')) if path.is_file()
             and (path.suffix in {'.json', '.jsonl'} or path.name in {'REQUEST.bin', 'RESPONSE.bin', 'SCRIPT.py'})]
    pins += [pin(Path(binding['install_root']) / row['path']) for row in wire['loaded_source_payloads']]
    report = dict(schema='m5-b-initial-resource-review-v1', passed_checked_scope=True,
        author_association='Author wrote engineering harness and passive archive instrumentation; saved-only counters/stages review, separate quality/source acceptance by scoring agent.',
        qualification_only=True, A_samples=1, B_initial_samples=1, actual_new_owned=0,
        actual_new_rasters=0, checks=checks, input_pins=pins, source_sha256=result['source_sha256'],
        initial_B_work=producer['work'], initial_B_stages=producer['stages'],
        initial_B_task_normalized_arrays=arrays, retained_task_array_payload_bytes=retained_bytes,
        initial_B_trace=traces[0],
        diagnostic_time_only=dict(A_continuous_business_ns=a['business']['continuous_business_ns'],
            A_complete_session_ns=a['timing']['complete_session_ns'],
            B_initial_continuous_business_ns=result['business_windows'][0]['continuous_business_ns'],
            B_initial_complete_session_ns=published['complete_session_ns']),
        measured_hotspots=[
            dict(name='task_source_prepare', elapsed_ns=producer['stages']['task_source_prepare']['elapsed_ns'],
                 scope='source qualification before raster; includes ordered hash and alias preparation; nested children not separately timed'),
            dict(name='task_measurement', elapsed_ns=producer['stages']['task_measurement']['elapsed_ns'],
                 scope='normalization/binding/one surface solve/cache result path combined; solve-only elapsed unknown'),
            dict(name='geometry', elapsed_ns=producer['stages']['geometry']['elapsed_ns']),
            dict(name='mesh_arrays', elapsed_ns=producer['stages']['mesh_arrays']['elapsed_ns'])],
        optimization_basis='Examine duplicate geometry-to-alias normalization of two reused observation objects. Keep ordered geometry/source-face/generation verification and one M3 solve. Exact array reuse and savings require final B actual counters and source/quality review.',
        limitations=[
            'A and first B are separate single qualification sessions, no paired or formal benefit conclusion.',
            'A second host resource build/transform was already zero. Combined B removes an RPC, not a repeated to_mesh build.',
            'First B task counters report 19748 bytes at normalization construction, retained ReadContext metadata is 13284 bytes. These are different representations. Allocation/copy count and transient bytes remain unknown.',
            'Source preparation 7.1598ms and task_measurement 69.5979ms are inclusive stages. Alias parse/hash/kernel elapsed is not individually available.',
            'Independent source/quality PASS is outside this resource review. No source, installation or archived producer bytes were changed.'
        ])
    target = HERE / 'B_INITIAL_RESOURCE_REVIEW.json'
    target.write_bytes((json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2)+'\n').encode('utf8'))
    print(json.dumps(dict(passed=True, checks=len(checks), report=pin(target))))


if __name__ == '__main__':
    main()
