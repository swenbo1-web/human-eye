"""Root review of the original sessions and the independent saved qualifications."""

import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_global_local_001')
LABELS = ('global', 'local_open', 'local_covered')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    started = time.perf_counter_ns()
    qualification = read(HERE / 'QUALIFICATION.json')
    runtime = read(HERE / 'RUNTIME_REVIEW.json')
    frames = {label: read(HERE / 'checks' / (label + '_FRAMES_R2.json')) for label in LABELS}
    reports = {'QUALIFICATION.json': qualification, 'RUNTIME_REVIEW.json': runtime}
    reports.update({'checks/' + label + '_FRAMES_R2.json': value for label, value in frames.items()})
    pins = {}
    for report in reports.values():
        for row in report['input_pins']:
            path = Path(row['path'])
            if sha(path) != row['sha256'] or ('bytes' in row and path.stat().st_size != row['bytes']):
                raise ValueError('qualification_input_changed/' + str(path))
            previous = pins.setdefault(str(path), row['sha256'])
            if previous != row['sha256']:
                raise ValueError('qualification_input_conflict')
    sources = {}
    checks = []
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
    costs = []
    target_pixels = []
    for label in LABELS:
        folder = RUNTIME / 'sessions' / label
        slot = read(folder / 'SLOT_RESULT.json')
        publication = read(folder / 'SLOT_PUBLICATION.json')
        public = read(folder / 'product_calls/call_001/RESPONSE.json')
        original = read(folder / 'product_full/call_001/SERVICE_RESULT.json')
        sources[label] = original
        check(label + '/original_public_success', slot['status'] == publication['status'] == 'completed'
              and slot['errors'] == [] and public['result'].get('isError') is False)
        check(label + '/one_actual_request', slot['public_requests_attempted'] == 1)
        check(label + '/full_actual_image_query', slot['request_arguments']['response_detail'] == 'full'
              and slot['request_arguments']['include_image'] is True)
        check(label + '/original_publication_hash', publication['result_sha256'] == sha(folder / 'SLOT_RESULT.json'))
        check(label + '/600_second_complete_bound', publication['complete_slot_ns'] < 600_000_000_000)
        request_ns = slot['clocks']['public_returned_ns'] - slot['clocks']['public_started_ns']
        check(label + '/30_second_request_bound', 0 <= request_ns < 30_000_000_000)
        check(label + '/independent_frame_check', frames[label]['passed_checked_scope'] is True)
        check(label + '/read_only_contract', original['read_only'] is True and original['execution_authority'] is False)
        costs.append(dict(label=label, complete_slot_ms=publication['complete_slot_ns']/1e6,
            public_request_ms=request_ns/1e6, raster_attempts=original['work']['raster_attempts'],
            PNG_bytes=original['work']['PNG_bytes'], NPZ_bytes=original['work']['NPZ_bytes'],
            capture_objects=original['work']['capture_object_count'], capture_triangles=original['work']['captured_triangle_count'],
            rendered_views=[frame['view_name'] for frame in original['frames']],
            unrendered_views=frames[label]['unrendered_views']))
        target_pixels.extend(dict(label=label, view=row['view'], object_name=row['object_name'],
            surface_pixels=row['visible_surface_pixels'], boundary_pixels=row['contrasting_boundary_pixels'], readable=row['readable'])
            for observation in original['facts']['observations'] for row in observation['pixel_rows']
            if row['object_name'] in ('Obj_02', 'Obj_06', 'Obj_09'))
    global_regions = {row['object_name']: row for row in sources['global']['facts']['regions']
                      if row['object_name'] in ('Obj_02', 'Obj_06', 'Obj_09')}
    for name in ('Obj_02', 'Obj_09'):
        check('global/' + name + '/pixel_insufficient', global_regions[name]['status'] == 'unknown'
              and global_regions[name]['reason'] == 'pixel_evidence_insufficient')
    positive = sources['local_open']['facts']['regions'][0]
    check('local_open/covered', positive['object_name'] == 'Obj_02' and positive['status'] == 'covered'
          and positive['reason'] == 'observed_readable')
    for label in ('global', 'local_covered'):
        region = next(row for row in sources[label]['facts']['regions'] if row['object_name'] == 'Obj_06')
        evidence = next(row for row in sources[label]['facts']['region_evidence'] if row['roi_id'] == region['roi_id'])
        check(label + '/genuine_occlusion_unknown', region['status'] == 'unknown'
              and region['reason'] == 'finite_camera_pool_uncovered'
              and evidence['unobserved_reason'] == 'positive_area_occlusion_all_front_views'
              and len(evidence['view_reasons']['positive_area_occlusion']) == 6
              and evidence['complete_witness'] is None)
    check('three_independent_sessions', qualification['denominator'] == qualification['qualified_count'] == 3)
    check('three_owned_eight_actual_rasters', runtime['budget']['qualification_owned_starts'] == 3
          and runtime['budget']['raster_attempts_actual'] == 8)
    check('zero_experiment_models_and_paid_API', runtime['budget']['consumers'] == runtime['budget']['paid_API_calls'] == 0)
    geometry_passed = qualification['passed_checked_scope'] is True
    frame_passed = all(value['passed_checked_scope'] is True for value in frames.values()) and all(row['passed'] for row in checks)
    accepted = geometry_passed and frame_passed and runtime['passed_checked_scope'] is True
    baseline = read(HERE / 'BASELINE.json')
    decision = dict(schema='m4-global-local-root-decision-v1', accepted_qualification=accepted,
        independent_geometry_passed=geometry_passed, saved_frame_passed=frame_passed,
        pending_administrator_review=True, checks=checks, costs=costs, target_pixels=target_pixels,
        direct_review_input_count=len(pins), report_pins={name: sha(HERE / name) for name in reports},
        fixture_asset_sha256=read(HERE / 'fixture/ASSET_BINDING.json')['asset_sha256'],
        next_candidate='Task-eligible global regions with pixel_evidence_insufficient receive one bounded existing local fit, with current source and witness explicitly associated back to their global region.',
        saved_checker_corrections='Frozen scripts and each failed saved-only attempt remain. Derived validators correct PID location, optional scope, post-core metadata hashing, rational direction parsing and frustum sample handling. Actual requests and fixture geometry were each executed once.',
        experiment_model_consumers=0, experiment_paid_API_calls=0,
        AL_registration='pending_current_chat_host_binding',
        started_ns=started, closed_ns=time.perf_counter_ns(),
        root_registration_to_decision_seconds=(time.perf_counter_ns()-baseline['started_ns'])/1e9)
    save(HERE / 'DECISION.json', decision)
    print(json.dumps(dict(accepted=accepted, root_checks=len(checks), costs=costs, direct_inputs=len(pins))))


if __name__ == '__main__':
    main()
