"""Verify a v3 standalone ordered reply whose public binding omits host identity."""

import json
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
retained = run_path(str(HERE / 'review.py'))
RUN, SOURCE, INSTALL, DenseReview, require = (
    retained[key] for key in ('RUN', 'SOURCE', 'INSTALL', 'DenseReview', 'require'))


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('registered_interpreter_required')
    install = json.loads(INSTALL.read_bytes())
    sys.path[:0] = [install['install_root'], install['dependency_root']]
    from human_eye_plugin import auto_router
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256'] == SOURCE
            and Path(auto_router.__file__).resolve().is_relative_to(install['install_root']),
            'capture_fingerprint_code_must_be_current_candidate')
    audit = DenseReview(RUN / 'slots/P1')
    audit.check_source()
    audit.collect_calls()
    first = audit.json(HERE / 'P1.json')
    rows = []
    for call in audit.calls:
        query = call['args'].get('query', {})
        if call['error'] or query.get('mode') != 'task' or 'objects' not in query:
            continue
        doc, = call['texts']
        binding = doc['binding']
        require(doc == call['producer'] and doc['schema_version'] == 'task-query-v3'
                and binding['capture_scope'] == 'selected_objects'
                and binding['selected_count'] == len(query['objects']) == 2
                and binding['candidate_count'] == len(audit.terminal['objects'])
                and len(binding['objects']) == 2 and binding['runtime_source_sha256'] == SOURCE
                and 'host_identity' not in binding, 'standalone_replay_not_the_v3_public_scope')
        ordered = [(row['object_id'], row['name']) for row in binding['objects']]
        matches = [capture for capture in audit.native_sources()
                   if capture['revision'] == binding['scene_revision']
                   and capture['host_identity']['capture_scope'] == binding['capture_scope']
                   and capture.get('task_selection', {}).get('selectors') == query['objects']
                   and capture['task_selection']['bindings'] == binding['objects']
                   and {(mesh['object_id'], mesh['name']) for mesh in capture['meshes']} == set(ordered)]
        require(len(matches) == 1, 'expected_one_current_selected_native_capture_for_standalone')
        source = matches[0]
        audit.same_geometry(source, audit.terminal)
        require(all(source['host_identity']['object_instances'][oid] == audit.by_id[oid]['instance_id']
                    for oid, _ in ordered), 'selected_capture_instance_mismatch')
        _, _, rebuilt = auto_router._validated_scene(source, _task_capture=True, _annotate_scene=False)
        require(rebuilt == binding['scene_fingerprint'], 'public_binding_does_not_match_current_normalized_capture')
        checked = audit.measure_body(doc, audit.meshes)
        rows.append({'attempt': call['attempt'], 'wire': call['rx'], 'producer': call['producer_pin'],
            'scene_fingerprint_from_ordered_native_capture': rebuilt, 'scope': binding['capture_scope'], **checked})
    require(rows and first['structural_errors'] ==
            [{'attempt': item['attempt'], 'measurement': "'host_identity'"} for item in rows],
            'original_dynamic_checker_and_supplement_differ')
    original, = first['whole_measurements']
    require(all(item['fact'] == original['fact'] for item in rows), 'standalone_returned_new_measurement_value')
    result = {'schema': 'perf050-dense-pair-standalone-v3-supplement-v1', 'passed': True, 'source': SOURCE,
              'replays': rows, 'same_facts_as_initial_bound_measurement': True,
              'frozen_checker_diagnostic': first['structural_errors'],
              'source_pins': [audit.pin(path) for path in sorted(audit.files)]}
    with (HERE / 'P1_STANDALONE.json').open('x', encoding='utf8', newline='\n') as out:
        json.dump(result, out, indent=2, allow_nan=False, ensure_ascii=False)
        out.write('\n')


if __name__ == '__main__':
    main()
