"""Independently inspect the closed pair while retaining the failed frozen timing gate."""

import argparse
import ast
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import experiment
import meter
import score


FROZEN_FAILURE = {'type': 'ValueError', 'message': 'transport_and_decoder_boundaries_out_of_order'}
STRICT_NPZ_FAILURE = 'live_candidate_png_npz_or_source_pixel_mapping_changed'


def diagnostic_function(module, name, replacements):
    """Use a frozen function with only the explicitly recorded comparison changed."""
    path = Path(module.__file__)
    tree = ast.parse(path.read_bytes(), filename=str(path))
    fn, = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]

    class Replace(ast.NodeTransformer):
        def __init__(self):
            self.pending = {ast.dump(ast.parse(old, mode='eval').body): ast.parse(new, mode='eval').body
                            for old, new in replacements.items()}

        def visit(self, node):
            match = self.pending.pop(ast.dump(node), None) if isinstance(node, ast.expr) else None
            return ast.copy_location(match, node) if match is not None else super().visit(node)

    edit = Replace()
    function = edit.visit(fn)
    experiment.require(not edit.pending, 'frozen_diagnostic_comparison_no_longer_matches')
    isolated = dict(vars(module))
    program = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(program, str(path), 'exec'), isolated)
    return isolated[name]


def diagnose(output):
    freeze_sha = experiment.verify_freeze()
    run = experiment.RUN
    original_score = experiment.read(run/'SCORE.json')
    a, b = (run/'slots'/label for label in 'AB')
    failed = experiment.read(a/'SLOT_RESULT.json')
    proof = experiment.read(a/'HOST_RECEIPT.json')
    completed = experiment.read(b/'SLOT_RESULT.json')
    experiment.require(original_score['freeze_sha256'] == failed['freeze_sha256'] == completed['freeze_sha256']
                       == freeze_sha and original_score['passed'] is False
                       and failed['status'] == original_score['arms']['A']['actual_status'] == 'failed'
                       and failed['error'] == original_score['arms']['A']['error'] == FROZEN_FAILURE
                       and original_score['arms']['B']['passed'] is True
                       and proof == failed['closure'] and proof['status'] == 'completed'
                       and not proof['errors'] and len(failed['observations']) == 4,
                       'frozen_failure_or_independent_physical_close_differs')
    try:
        meter.summarize(a)
    except ValueError as exc:
        experiment.require(str(exc) == FROZEN_FAILURE['message'], 'frozen_timing_error_no_longer_reproduces')
    else:
        raise ValueError('frozen_timing_error_was_not_reproduced')

    score_with_original_failure = diagnostic_function(score, 'verify_slot', {
        "result['status'] == published['status'] == 'completed'":
            "result['status'] == published['status'] == 'failed'",
    })
    a_verified = score_with_original_failure(a, 'A')
    b_verified = score.verify_slot(b, 'B')
    try:
        score.verify_pair(a_verified, b_verified)
    except ValueError as exc:
        experiment.require(str(exc) == STRICT_NPZ_FAILURE, 'unexpected_strict_pair_rejection')
    else:
        raise ValueError('strict_cross_slot_NPZ_rejection_was_not_reproduced')

    # Each arm has already bound its NPZ identities to its own measured producer.
    # Prove the original arrays and all remaining metadata are identical.
    a_image, b_image = (arm['image'] for arm in (a_verified, b_verified))
    with score.np.load(a_image['NPZ']['path'], allow_pickle=False) as left, \
            score.np.load(b_image['NPZ']['path'], allow_pickle=False) as right:
        experiment.require(left.files == right.files, 'NPZ_member_layout_changed')
        same, changed = [], []
        for key in left.files:
            x, y = left[key], right[key]
            experiment.require(x.dtype == y.dtype and x.shape == y.shape, 'NPZ_member_type_or_shape_changed/' + key)
            (same if score.np.array_equal(x, y) else changed).append(key)
        experiment.require(set(changed) == {'display_identity', 'image_scope_identity'} and
                           {'triangle_ids', 'owners', 'depth', 'color', 'display_object_mask',
                            'face_patch_offsets'}.issubset(same), 'actual_NPZ_difference_exceeds_per_slot_identity')
    compare_bound_pair = diagnostic_function(score, 'verify_pair', {
        "all(prev[key]['sha256'] == cand[key]['sha256'] for key in ('PNG', 'NPZ'))":
            "prev['PNG']['sha256'] == cand['PNG']['sha256']",
    })
    pair = compare_bound_pair(a_verified, b_verified)

    # The existing requirement that the owner span is inside the inclusive TCP
    # exchange remains checked. Only the post-connect decomposition changes.
    split_mcp_clock = diagnostic_function(meter, 'summarize', {
        '_within(native_call["owner_execute_and_guards"], transfer)':
            '_overlap(native_call["owner_execute_and_guards"], transfer) > 0',
        'transfer["elapsed_ns"] - native_call["owner_execute_and_guards"]["elapsed_ns"]':
            'transfer["elapsed_ns"] - _overlap(transfer, native_call["owner_execute_and_guards"])',
    })
    clocks = {}
    divergences = []
    for label, path in (('A', a), ('B', b)):
        result = experiment.read(path/'SLOT_RESULT.json')
        t = split_mcp_clock(path, window=(result['window']['opened_ns'], result['closure']['closed_ns']))
        for call in t['calls']:
            native = call['native']['owner_execute_and_guards']
            host = call['host']
            transfer = host['tcp_send_wait_receive_until_outer_json']
            if not meter._within(native, transfer):
                connect = host['tcp_connect']
                record = {'label': label, 'call': call['index'],
                          'owner': native, 'connect': connect, 'post_connect_transfer': transfer,
                          'owner_starts_before_client_connect_returns_ns': connect['closed_ns']-native['started_ns'],
                          'owner_ends_before_outer_JSON_ns': transfer['closed_ns']-native['closed_ns'],
                          'owner_overlap_with_connect_ns': meter._overlap(connect, native)}
                divergences.append(record)
        clocks[label] = t
    divergence, = divergences
    experiment.require(divergence['label'] == 'A' and divergence['call'] == 1
                       and divergence['owner_starts_before_client_connect_returns_ns'] > 0
                       and divergence['owner_starts_before_client_connect_returns_ns']
                       == divergence['owner_overlap_with_connect_ns']
                       and divergence['owner_ends_before_outer_JSON_ns'] > 0,
                       'timing_failure_not_the_original_connect_overlap')
    experiment.write(output, {'frozen_result': experiment.pin(run/'SCORE.json'), 'frozen_passed': False,
                               'frozen_A_error': FROZEN_FAILURE, 'same_closed_pair_quality_verified': True,
                               'replacement_slots': 0, 'timing_overlap': divergence, 'pair': pair,
                               'NPZ': {'strict_cross_slot_rejection': STRICT_NPZ_FAILURE,
                                       'same_members': same, 'changed_members': changed,
                                       'both_current_slot_bindings_verified': True},
                               'verified_arms': {'A': a_verified, 'B': b_verified}, 'clocks': clocks})


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, required=True)
    diagnose(cli.parse_args().output)
