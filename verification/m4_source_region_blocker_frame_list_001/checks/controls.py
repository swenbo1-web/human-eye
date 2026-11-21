"""Replay the frozen 63 controls and frame-list/capture-coherence edge cases."""

import argparse
from copy import deepcopy
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
REUSE = V / 'm4_source_region_blocker_producer_reuse_001'
BASE = REUSE / 'install/PRODUCT_RUN_BINDING.json'
BASE_COMMIT = 'd293fbdd28df2956c17cc902d9b19f6e9d9e3d65'
FAULT = 'returned_constructed_frames_edited'
ARCHIVED_RX = {'A': '8fa2f2a41188cb8085f1ab5c0179af2391e5ac18a4f107d89034d71e2df310e3',
               'B': '89cc166661eaeedf2597d1a95125b749e9880f00cb4614e1210121c822bd62c4'}


def archive_reference(prior):
    index_path = REUSE / 'RAW_INDEX.json'
    index = prior['read'](index_path)
    archive = REUSE / index['archive']['name']
    prior['require'](prior['pin'](archive)['sha256'] == index['archive']['sha256'],
                     'original_failure_archive_changed')
    rows = []
    with ZipFile(archive) as original:
        for arm, expected in ARCHIVED_RX.items():
            member = f'controls/{arm}/{FAULT}_RX.bin'
            raw = original.read(member)
            from hashlib import sha256
            prior['require'](sha256(raw).hexdigest() == index['members'][member]['sha256'] == expected,
                             'original_failure_RX_changed/' + arm)
            rows.append({'arm': arm, 'member': member, 'sha256': expected, 'bytes': len(raw)})
    return {'index': prior['pin'](index_path), 'archive': prior['pin'](archive), 'RX': rows}


def unversioned(source_region, active_host, tools, value, request):
    # The shape of a capture that reports no revision token still reaches ordinary observation.
    capture = deepcopy(tools['frozen_capture']()[0])
    capture.pop('capture_state')
    prepared, selected = tools['prepare'](source_region, active_host, capture, request)
    require = tools['require']
    require(prepared.region_ref['capture_generation'] is None and prepared.binding['capture_state'] is None,
            'derived_unversioned_capture_still_reports_generation')
    if value is not None:
        old_binding = value['binding']
        value['binding'] = {
            **prepared.binding, **{key: old_binding[key] for key in tools['OVERLAYS'] if key in old_binding}}
        value['region_ref'] = deepcopy(prepared.region_ref)
        value['task_result'].update(binding=deepcopy(value['binding']), region_ref=deepcopy(value['region_ref']))
        frame, = value['frames']
        frame['host_binding_sha256'] = prepared.binding['binding_sha256']
        frame['image_ref'] = 'source-region-image:' + source_region.fingerprint((
            prepared.region_ref['region_id'], frame['frame_identity'], frame['image_sha256']))
        value['constructed_frames'] = [deepcopy(frame)]
        value['facts']['visibility']['image_ref'] = frame['image_ref']
    return capture, selected, prepared


def specifications(previous, source_region, inherited, tools, retained_variants):
    from human_eye_plugin import active_observation_host

    cases, pins, geometry, _ = inherited(previous, source_region)
    previous['require'](len(cases) == 63, 'frozen_prior_control_roster_changed')
    reference = cases['actual_P1_4_blockers']
    rows = previous['ORIGINAL_ROWS']
    for name, case in cases.items():
        case['A'] = rows if name == FAULT else case['B']

    def add(name, mutation=None, *, retained=None, a=rows, b=None, full=False):
        case = deepcopy(reference)
        case.update(A=a, B=b, state='matching' if retained is not False else 'active', is_unmodified_archived_call=False)
        if mutation is not None:
            mutation(case['producer'])
        if full:
            case['request']['params']['arguments']['response_detail'] = 'full'
        if callable(retained):
            private = deepcopy(reference['producer'])
            retained(private)
            retained_variants[id(case['producer'])] = private
        cases[name] = case

    def remove_list(value):
        value.pop('constructed_frames')

    def duplicate(value):
        value['constructed_frames'].append(deepcopy(value['constructed_frames'][0]))

    def other_frame(value):
        result = deepcopy(value['constructed_frames'][0])
        result.update(frame_identity='0' * 64, view_name='TOP')
        return result

    def wrong_only(value):
        value['constructed_frames'] = [other_frame(value)]

    def add_after(value):
        value['constructed_frames'].append(other_frame(value))

    def add_before(value):
        value['constructed_frames'].insert(0, other_frame(value))

    add('returned_constructed_list_missing', remove_list, retained=False)
    add('retained_constructed_list_missing', retained=remove_list)
    add('bilateral_constructed_list_missing', remove_list)
    add('bilateral_constructed_list_empty', lambda value: value.update(constructed_frames=[]))
    add('bilateral_constructed_main_frame_absent', wrong_only)
    add('bilateral_constructed_main_frame_double', duplicate)
    add('retained_constructed_main_frame_double', retained=duplicate)
    add('constructed_order_only_differs', add_before, retained=add_after)
    add('constructed_extra_entry_only_differs', add_after, retained=False)
    add('matching_list_main_once_with_other_entry', add_after, b=rows)

    def both_bindings(value, change):
        change(value['binding'])
        change(value['task_result']['binding'])

    add('capture_state_key_missing_but_ref_remains_versioned',
        lambda value: both_bindings(value, lambda binding: binding.pop('capture_state')))
    add('capture_state_is_null_but_ref_remains_versioned',
        lambda value: both_bindings(value, lambda binding: binding.update(capture_state=None)))
    for field, discrepancy in (('revision', 7), ('epoch', 4), ('instance_id', 'different-instance')):
        add('capture_state_' + field + '_contradicts_valid_ref',
            lambda value, key=field, wrong=discrepancy: both_bindings(
                value, lambda binding: binding['capture_state'].update({key: wrong})))
    add('capture_state_revision_absent_but_ref_remains_versioned',
        lambda value: both_bindings(value, lambda binding: binding['capture_state'].pop('revision')))
    add('natural_unversioned_retained_prepared',
        lambda value: unversioned(source_region, active_observation_host, tools, value, reference['request']),
        a=None)
    add('explicit_full_with_duplicate_list_preserves_existing_body', duplicate, a=None, full=True)
    return cases, pins, geometry, 63


def run_worker(binding_path, out, arm):
    original = run_path(str(REUSE / 'checks/controls.py'))
    worker = original['run_worker']
    scope = worker.__globals__
    retained_variants = {}
    bound_specs = original['specifications']
    raw_replay = run_path(str(REUSE / 'checks/prepared_replay.py'))
    base_restore = raw_replay['restore']

    def restore(source_region, active_host, context, request, producer, *, retained=None):
        if retained is None:
            return base_restore(source_region, active_host, context, request, producer)
        private = retained_variants.get(id(retained), retained)
        if private['region_ref']['capture_generation'] is None:
            capture, selected, prepared = unversioned(source_region, active_host, raw_replay, None, request)
            raw_replay['require'](prepared.region_ref == private['region_ref']
                                  and prepared.binding == raw_replay['original_binding'](private['binding']),
                                  'unversioned_prepared_does_not_match_returned')
            return raw_replay['register'](context, capture, selected, prepared,
                                          raw_replay['original_observation'](private))
        prepared = base_restore(source_region, active_host, context, request, producer, retained=private)
        state = private['binding'].get('capture_state')
        if state != prepared.binding['capture_state']:
            # Derived contradictions affect both public and retained bindings. The valid ref and
            # current ReadContext generation keep their original independently verified values.
            if 'capture_state' in private['binding']:
                prepared.binding['capture_state'] = deepcopy(state)
            else:
                prepared.binding.pop('capture_state')
        return prepared

    def open_known(path):
        if Path(path).name == 'prepared_replay.py':
            return {**raw_replay, 'restore': restore}
        return run_path(path)

    scope.update(BASE_COMMIT=BASE_COMMIT,
                 run_path=open_known,
                 specifications=lambda prior, source_region: specifications(
                     prior, source_region, bound_specs, raw_replay, retained_variants))
    worker(binding_path, out, arm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--arm', choices=('A', 'B'))
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--summary', type=Path)
    args = parser.parse_args()
    if args.worker:
        run_worker(args.worker, args.output, args.arm)
        return
    old = run_path(str(REUSE / 'checks/controls.py'))
    prior = run_path(str(V / 'm4_source_region_blocker_brief_001/checks/controls.py'))
    archive = archive_reference(prior)
    args.output.mkdir(parents=True)
    bindings = {'A': BASE}
    if args.candidate:
        bindings['B'] = args.candidate
    reports = {}
    for arm, source in bindings.items():
        dest = args.output / arm
        result = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--worker', str(source.resolve()),
                                 '--arm', arm, '--output', str(dest.resolve())], capture_output=True, check=False)
        (args.output / (arm + '_STDERR.txt')).write_bytes(result.stderr)
        prior['require'](result.returncode == 0, f'arm {arm} failed: {result.stderr.decode(errors="replace")}')
        reports[arm] = prior['read'](dest / 'REPLAY.json')
    prior['require'](reports['A']['rows'][FAULT]['RX']['sha256'] == ARCHIVED_RX['B'],
                     'old_failed_candidate_raw_error_did_not_reproduce')
    if 'B' not in reports:
        print(f"Replayed {len(reports['A']['rows'])} installed baseline controls and reproduced the archived failure byte-for-byte.")
        return
    outcomes = old['compare'](reports['A'], reports['B'], prior['require'])
    prior['require'](outcomes[FAULT]['wire_sha256_A_B'] == [ARCHIVED_RX['B'], ARCHIVED_RX['A']],
                     'fixed_reply_differs_from_archived_scope_safe_baseline')
    passed = sum(row['passed'] for row in outcomes.values())
    summary = {'passed': passed, 'planned': len(outcomes), 'prior_attempt_still_passed': 62,
               'inherited_cases': reports['A']['inherited_case_count'],
               'new_cases': len(outcomes) - reports['A']['inherited_case_count'],
               'byte_identical': sum(row['wire_identical'] for row in outcomes.values()),
               'historical_fault_receipts': archive,
               'raw_replays': [prior['pin'](args.output / (arm + '/REPLAY.json')) for arm in reports],
               'source_A_B': [report['runtime']['source_sha256'] for report in reports.values()],
               'not_as_expected': [name for name, row in outcomes.items() if not row['passed']], 'outcomes': outcomes}
    prior['write'](args.output / 'CONTROLS.json', summary)
    if args.summary:
        prior['write'](args.summary, summary)
    print(f'Controls {passed}/{len(outcomes)} passed. {args.output / "CONTROLS.json"}')


if __name__ == '__main__':
    main()
