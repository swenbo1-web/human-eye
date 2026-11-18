"""Summarize measured work and preserve exact offline RPC and input artifacts."""

import hashlib
import json
from pathlib import Path
import statistics
import zipfile


NS = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_assembly_evidence_first_001')
INSTALLS = {'first': 'first_canonical', 'optimized': 'optimized_canonical'}
CASES = ('second_assembly', 'assembly001')
VARIANTS = ('A', *INSTALLS)
MAIN_SPANS = ('service.observe', 'host.capture', 'scene.validate', 'scene.hash', 'observation.task_facts',
              'observation.task_capture_evidence', 'observation.task_capture_evidence.validate',
              'observation.task_capture_evidence.construct', 'mcp.content_encode', 'mcp.wire_encode')


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open('w', encoding='utf8', newline='\n') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def copy_bytes(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())


def measure(samples):
    return {'cold_ns': samples[0], 'warmed_median_ns': statistics.median(samples[1:]), 'raw_ns': samples}


def timing_summary():
    metrics = {}
    kernel_equivalence = {case: [] for case in CASES}
    for variant in VARIANTS:
        metrics[variant] = cases = {}
        for case in CASES:
            root = RUNTIME / 'timing' / variant / case / 'brief'
            run = read(root / 'RUN.json')
            cold = run['attempts'][0]
            assert run['passed'] and run['capture_count'] == len(run['attempts']) == 7
            assert run['Blender_starts'] == run['model_starts'] == run['API_calls'] == 0
            assert all(a['raster_actual'] == 0 for a in run['attempts'])
            stages = {name: [] for name in MAIN_SPANS}
            for attempt in run['attempts']:
                trace = attempt['product_trace']
                assert trace['annotations']['mcp_native_image_block_count'] == 0
                for name, series in stages.items():
                    # Only the outer validation span is attributed to this stage.
                    matches = [s['duration_ns'] for s in trace['spans'] if s['name'] == name
                               and (name != 'scene.validate' or s['source_name'] == 'live_service')]
                    assert len(matches) <= 1
                    series.append(next(iter(matches), 0))
            work = [a['task_work'] for a in run['attempts']]
            kernel_equivalence[case].append(work)
            cases[case] = {
                'request_to_flush_with_archive': measure([a['request_to_flush_with_archive_ns'] for a in run['attempts']]),
                'capture_fixture_preparation': measure([a['capture_fixture_preparation_ns'] for a in run['attempts']]),
                'installed_spans': {name: measure(series) for name, series in stages.items()},
                'capture_count': run['capture_count'], 'counts': {key: cold[key] for key in ('capture_objects',
                    'capture_vertices', 'capture_triangles', 'public_UTF8_bytes')},
                'source_sha256': run['source_sha256'],
                'peak_process_RSS_bytes': max(row['product_trace']['peak_rss']['bytes'] for row in run['attempts']),
                'kernel_work': [{key: value.get(key) for key in ('pair_calls', 'rank_calls', 'surface_pair_count',
                    'closed_solid_pair_count', 'result_cache_hit')} for value in work],
                'encode_counts': {name: sum(value > 0 for value in stages[name])
                                  for name in ('mcp.content_encode', 'mcp.wire_encode')},
                'normalization_and_hash_stage_counts': {name: sum(value > 0 for value in stages[name])
                                                        for name in ('scene.validate', 'scene.hash')},
            }
    assert all(sequence[0] == sequence[1] == sequence[2] for sequence in kernel_equivalence.values())
    return {'scope': 'A, first, optimized run serially. Each cell is a fresh installed stdio with seven '
                     'requests to the same capture generation. Inclusive spans can nest. Six repeats '
                     'reuse the existing read cache and do not represent different assets or model latency.',
            'full_task_work_equal_for_each_corresponding_variant_and_case': True, 'variants': metrics}


def publish():
    summary = timing_summary()
    for variant, install in INSTALLS.items():
        path = RUNTIME / install / 'BINDING.json'
        copy_bytes(path, NS / 'install' / f'{variant.upper()}_BINDING.json')
        copy_bytes(RUNTIME / f'{variant.upper()}_CANONICAL_PROJECTION.json',
                   NS / 'checks' / f'{variant.upper()}_PROJECTION.json')
        summary['variants'][variant]['preparation_install_ns'] = read(path)['preparation_ns']
    write(NS / 'checks/INSTALLED_TIMING.json', summary)
    replay = RUNTIME / 'replay'
    for variant in VARIANTS:
        for publication in sorted((replay / variant).rglob('PUBLIC.json')):
            copy_bytes(publication, NS / 'public' / publication.relative_to(replay))
        for case in CASES:
            path = replay / variant / case / 'brief'
            copy_bytes(path / 'TOOL_SCHEMA.json', NS / 'public' / variant / case / 'TOOL_SCHEMA.json')
            if variant == 'A':
                for name in ('CAPTURE.json', 'NORMALIZED_CAPTURE.json', 'PROVENANCE.json'):
                    copy_bytes(path / name, NS / 'public' / 'capture' / case / name)

    files = sorted(path for stem in ('source', 'replay', 'timing') for path in (RUNTIME / stem).rglob('*')
                   if path.is_file())
    for name in ('first', 'first_verified', 'optimized', *INSTALLS.values()):
        files += sorted((RUNTIME / name / 'wheel').glob('*.whl'))
        files += sorted((RUNTIME / name).glob('*.log'))
        files += sorted((RUNTIME / name).glob('BINDING.json'))
    files += sorted(RUNTIME.glob('*_PROJECTION.json'))
    archive = RUNTIME / 'OFFLINE_ORIGINALS.zip'
    rows = []
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            rel = path.relative_to(RUNTIME).as_posix()
            raw = path.read_bytes()
            bundle.write(path, rel)
            rows.append({'path': rel, 'bytes': len(raw), 'sha256': sha(raw)})
    with zipfile.ZipFile(archive, 'r') as bundle:
        assert len(rows) == len(set(bundle.namelist())) == len(bundle.namelist())
        for item in rows:
            assert sha(bundle.read(item['path'])) == item['sha256']
    write(NS / 'OFFLINE_ORIGINAL_INDEX.json', {'files': rows, 'count': len(rows),
          'archive': {'path': str(archive), 'bytes': archive.stat().st_size, 'sha256': sha(archive.read_bytes())}})


if __name__ == '__main__':
    publish()
