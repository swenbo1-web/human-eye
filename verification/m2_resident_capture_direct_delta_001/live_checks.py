"""Qualify the closed real Blender pair and preserve the preceding rejection evidence."""

import argparse
import ast
from copy import deepcopy
from pathlib import Path
from runpy import run_path
import subprocess
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'m2_source_region_shared_normalization_live_001'
PRIOR_RUNTIME = Path('D:/he_m2_source_region_shared_normalization_live_001')
PRIOR_GIT = '6ea9597f492c393c2267c0197d3c19dcf9876072'
PRIOR_SCORE_SHA = '3cf1d5c89667afafdc91e694a388cfe7b029b31b46e47e6853284e27facf65da'
SCORE_PATH, METER_PATH = (PRIOR/name for name in ('score.py', 'meter.py'))
SCORE = SimpleNamespace(**run_path(str(SCORE_PATH)))
METER = SimpleNamespace(**run_path(str(METER_PATH)))
read, write, pin, require, selection = (getattr(SCORE, key) for key in ('read', 'write', 'pin', 'require', 'selection'))
observe_installed = METER.observe_installed
FROZEN_FAILURE = {'type': 'ValueError', 'message': 'transport_and_decoder_boundaries_out_of_order'}
STRICT_NPZ_FAILURE = 'live_candidate_png_npz_or_source_pixel_mapping_changed'
SLOT_MEMBERS = {'display_identity', 'image_scope_identity'}
NECESSARY_ARRAYS = {'triangle_ids', 'owners', 'depth', 'color', 'face_patch_offsets', 'display_object_mask'}


def retained_sources():
    return (SCORE_PATH, METER_PATH, SCORE.PRIOR, PRIOR/'FROZEN.json', PRIOR/'RESULT.json')


def amended(module, name, substitutions, **bindings):
    """Retain the known verifier and replace only the versioned comparison anchors."""
    path = Path(module.__file__)
    fn, = [node for node in ast.parse(path.read_bytes()).body
           if isinstance(node, ast.FunctionDef) and node.name == name]
    replacements = {ast.dump(ast.parse(old, mode='eval').body): ast.parse(new, mode='eval').body
                    for old, new in substitutions.items()}

    class Replace(ast.NodeTransformer):
        def visit(self, node):
            match = replacements.pop(ast.dump(node), None) if isinstance(node, ast.expr) else None
            return ast.copy_location(match, node) if match is not None else super().visit(node)

    Replace().visit(fn)
    require(not replacements, 'retained_comparison_anchor_changed/' + name)
    namespace = dict(vars(module), **bindings)
    compiled = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    exec(compile(compiled, str(path), 'exec'), namespace)
    return namespace[name]


def captured_before_parse(owner, exchange, transfer):
    return (METER._within(owner, exchange)
            and transfer['started_ns'] <= transfer['closed_ns']
            and owner['closed_ns'] <= transfer['closed_ns']
            and METER._overlap(owner, transfer) > 0)


_TIMING = amended(METER, 'summarize', {
    '_within(native_call["owner_execute_and_guards"], transfer)':
        'captured_before_parse(native_call["owner_execute_and_guards"], '
        'host["tcp_exchange_including_outer_json"], transfer)',
    'transfer["elapsed_ns"] - native_call["owner_execute_and_guards"]["elapsed_ns"]':
        'transfer["elapsed_ns"] - _overlap(transfer, native_call["owner_execute_and_guards"])',
}, captured_before_parse=captured_before_parse)


def summarize(slot, window=None):
    report = _TIMING(Path(slot), window)
    for call in report['calls']:
        host, owner = call['host'], call['native']['owner_execute_and_guards']
        transfer = host['tcp_send_wait_receive_until_outer_json']
        host['owner_overlap_with_connect_ns'] = METER._overlap(owner, host['tcp_connect'])
        host['owner_overlap_with_post_connect_transfer_ns'] = METER._overlap(owner, transfer)
    report['scope']['tcp'] = 'owner/guard interval inside inclusive exchange; post-connect transfer excludes only their overlap'
    report['scope']['native_separation'] = (
        'native owner time includes experiment guards; display read and resident work are separately observed; '
        'Blender capture/copy/encode do not have separate reliable live timers')
    return report


_SLOT = amended(SCORE, 'verify_slot', {'arm == \'B\' and n == 1': 'n == 1'})
_PAIR = amended(SCORE, 'verify_pair', {
    "all(prev[key]['sha256'] == cand[key]['sha256'] for key in ('PNG', 'NPZ'))":
        "prev['PNG']['sha256'] == cand['PNG']['sha256']",
})


def verify_display(frame, binding, snapshot, terminal, npz_identities):
    core = {key: value for key, value in snapshot.items() if key != 'sha256'}
    scope = frame['image_scope']
    true_layer = {'name': terminal['source']['view_layer'],
                  'instance_id': terminal['source']['view_layer_id']}
    display_id = SCORE.canonical_sha(core)
    scope_id = SCORE.canonical_sha(scope)
    require(snapshot['status'] == scope['status'] == 'captured' and snapshot['scope'] == 'active_view_layer'
            and snapshot['view_layer'] == scope['view_layer'] == true_layer
            and frame['display_identity'] == binding['display_identity'] == snapshot['sha256']
            == scope['identity'] == scope['snapshot_sha256'] == display_id == npz_identities['display_identity']
            and frame['image_scope_identity'] == scope_id == npz_identities['image_scope_identity']
            and binding['image_scope'] == scope
            and scope['participation_mask'] == terminal['display_object_mask'], 'live_NPZ_scope_not_its_current_ViewLayer')
    require(len(scope['objects']) == len(snapshot['objects']) == len(terminal['objects']),
            'live_display_roster_length_changed')
    for index, (public, captured, obj) in enumerate(zip(scope['objects'], snapshot['objects'], terminal['objects'], strict=True)):
        require({k: public[k] for k in captured} == captured
                and public['object_index'] == index and public['object_name'] == obj['name']
                and captured['host_id'] == obj['object_id'] and captured['instance_id'] == obj['instance_id']
                and public['participates'] is captured['visible_get'] is obj['visible_get']
                and all(captured[k] == obj['display'][k] for k in ('hide_get', 'hide_viewport', 'hide_render')),
                'live_display_object_not_its_current_ViewLayer')
    canonical_scope = {k: deepcopy(v) for k, v in scope.items() if k not in ('identity', 'snapshot_sha256')}
    del canonical_scope['view_layer']['instance_id']
    return {'view_layer': true_layer, 'display_identity': display_id, 'image_scope_identity': scope_id,
            'cross_slot_scope_sha256': SCORE.canonical_sha(canonical_scope)}


def scope_evidence(slot, result, clocks):
    terminal = read(slot/'TERMINAL_SOURCE.json')
    native_probes = read(slot/'mcp_io/REAL_HOST_STAGES.json')['requests']
    with SCORE.np.load(result['image']['NPZ']['path'], allow_pickle=False) as npz:
        npz_ids = {key: npz[key].item() for key in SLOT_MEMBERS}
    scopes = []
    for idx in (2, 3):
        raw = clocks['calls'][idx]
        path = Path(raw['native']['rx']['path'])
        proof = pin(path)
        require(proof == raw['native']['rx'] and path.is_relative_to(slot), 'live_display_TCP_receipt_changed')
        native = read(path)['result']['result']
        require(native.startswith(METER.HOST_RPC_PREFIX), 'live_display_TCP_prefix_changed')
        wire = METER.json.loads(native[len(METER.HOST_RPC_PREFIX):])
        capture = wire['result']['capture']
        value = read(Path(raw['producer']['path']))
        require(wire['id'] == native_probes[idx]['host_request_id']
                and capture['capture_state'] == result['state'] == value['binding']['capture_state'],
                'live_display_capture_not_its_actual_wire')
        frame, = value['frames']
        scopes.append(verify_display(frame, value['binding'], capture['display_snapshot'], terminal, npz_ids))
    require(scopes[0] == scopes[1], 'live_cold_and_warm_image_scope_changed')
    return scopes[0]


def verify_slot(slot, arm):
    slot = Path(slot).resolve(strict=True)
    result = _SLOT(slot, arm)
    clocks = summarize(slot)
    result['NPZ_scope'] = scope_evidence(slot, result, clocks)
    return result


def bound_pair(a, b):
    result = _PAIR(a, b)
    scope_a, scope_b = (arm['NPZ_scope'] for arm in (a, b))
    require(scope_a['cross_slot_scope_sha256'] == scope_b['cross_slot_scope_sha256'],
            'cross_slot_image_scope_flags_or_objects_changed')
    archive_a, archive_b = (arm['image']['NPZ'] for arm in (a, b))
    for archive in (archive_a, archive_b):
        require(pin(archive['path']) == archive, 'pair_NPZ_original_changed_before_comparison')
    with SCORE.np.load(archive_a['path'], allow_pickle=False) as left, \
            SCORE.np.load(archive_b['path'], allow_pickle=False) as right:
        require(left.files == right.files and NECESSARY_ARRAYS | SLOT_MEMBERS <= set(left.files),
                'live_NPZ_member_layout_changed')
        same, slots = [], []
        for key in left.files:
            x, y = left[key], right[key]
            require(x.dtype == y.dtype and x.shape == y.shape, 'live_NPZ_member_shape_or_dtype_changed/' + key)
            if key in SLOT_MEMBERS:
                require(x.item() == scope_a[key] and y.item() == scope_b[key], 'cross_slot_NPZ_binding_wrong/' + key)
                slots.append(key)
            else:
                require(SCORE.np.array_equal(x, y), 'cross_slot_NPZ_pixels_or_sources_changed/' + key)
                same.append(key)
    return {**result, 'NPZ': {'same_members': same, 'verified_per_slot_members': slots,
                              'slots': {'A': scope_a, 'B': scope_b}}}


def verify_pair(a, b):
    result = bound_pair(a, b)
    require(result['normalizations'] == [1, 1], 'both_live_arms_must_keep_cross_region_shared_normalization')
    return result


def verify_legacy_originals():
    for path in retained_sources():
        raw = subprocess.check_output(['git', '-C', str(HERE.parents[1]), 'show',
                                       PRIOR_GIT + ':' + path.relative_to(HERE.parents[1]).as_posix()])
        require(path.read_bytes() == raw, 'prior_verifier_or_identity_changed/' + path.name)
    index_path = PRIOR_RUNTIME/'sealed/RAW_INDEX.json'
    index = read(index_path)
    manifest = read(PRIOR/'RESULT.json')
    archive = Path(index['archive']['path'])
    require(pin(archive) == index['archive'] == manifest['raw_evidence_local']
            and index['member_count'] == manifest['raw_member_count'] == len(index['members']) == 411,
            'prior_runtime_archive_unbound')
    for name, expected in index['members'].items():
        fit = pin(PRIOR_RUNTIME/name)
        require({key: value for key, value in fit.items() if key != 'path'} == expected,
                'prior_raw_member_changed/' + name)
    return [pin(index_path), pin(archive), *[pin(p) for p in retained_sources()]]


def require_reject(call, expected):
    try:
        call()
    except ValueError as error:
        require(str(error) == expected, 'unexpected_rejection/' + str(error))
    else:
        raise ValueError('expected_rejection_absent/' + expected)


def preflight(output):
    pins = verify_legacy_originals()
    score_file = PRIOR_RUNTIME/'SCORE.json'
    original = pin(score_file)
    scores = read(score_file)
    a, b = (PRIOR_RUNTIME/'slots'/label for label in 'AB')
    receipt_a = read(a/'SLOT_RESULT.json')
    require(original['sha256'] == PRIOR_SCORE_SHA and scores['passed'] is False
            and receipt_a['status'] == 'failed' and receipt_a['error'] == FROZEN_FAILURE
            and receipt_a['closure'] == read(a/'HOST_RECEIPT.json') and not receipt_a['closure']['errors']
            and scores['arms']['B']['passed'] is True, 'prior_failed_gate_or_physical_close_changed')
    require_reject(lambda: METER.summarize(a), FROZEN_FAILURE['message'])
    offline_a = amended(SCORE, 'verify_slot', {
        "result['status'] == published['status'] == 'completed'": "result['status'] == published['status'] == 'failed'",
    })(a, 'A')
    offline_b = SCORE.verify_slot(b, 'B')
    require_reject(lambda: SCORE.verify_pair(offline_a, offline_b), STRICT_NPZ_FAILURE)
    for folder, result in ((a, offline_a), (b, offline_b)):
        result['NPZ_scope'] = scope_evidence(folder, result, summarize(folder))
    old_pair = bound_pair(offline_a, offline_b)

    timing, *_ = summarize(a)['calls']
    host, owner = timing['host'], timing['native']['owner_execute_and_guards']
    exchange, transfer = (host[k] for k in ('tcp_exchange_including_outer_json', 'tcp_send_wait_receive_until_outer_json'))
    require(host['owner_overlap_with_connect_ns'] == 201_900 and captured_before_parse(owner, exchange, transfer),
            'prior_real_connect_overlap_not_reproduced')
    require(not captured_before_parse(METER._interval(exchange['started_ns']-1, owner['closed_ns']), exchange, transfer)
            and not captured_before_parse(METER._interval(owner['started_ns'], transfer['closed_ns']+1), exchange, transfer),
            'bad_native_clock_passed_new_gate')
    scope_swap = deepcopy(offline_a)
    scope_swap['NPZ_scope'] = offline_b['NPZ_scope']
    require_reject(lambda: bound_pair(scope_swap, offline_b), 'cross_slot_NPZ_binding_wrong/display_identity')
    require(pin(score_file) == original, 'prior_frozen_score_changed_by_preflight')
    receipt = {'passed': True, 'historical_original_score': original, 'input_pins': [*pins, original],
               'prior_rejections_reproduced': [FROZEN_FAILURE['message'], STRICT_NPZ_FAILURE],
               'retained_assessment_still_failed': True, 'same_raw_pair_now_satisfies_clock_and_scope_checks': old_pair,
               'extra_controls': ['owner_before_exchange', 'owner_after_outer_parse', 'cross_slot_NPZ_scope_swap'],
               'old_owner_connect_overlap_ns': host['owner_overlap_with_connect_ns'], 'new_Blender': 0}
    write(Path(output), receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', type=Path, required=True)
    preflight(parser.parse_args().preflight)
