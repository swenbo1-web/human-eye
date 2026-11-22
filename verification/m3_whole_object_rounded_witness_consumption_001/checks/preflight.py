"""Check scoring on the archived-current captures and the actual offline stdio deliveries."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path

NS = Path(__file__).resolve().parents[1]
V = NS.parent
E = run_path(str(NS / 'checks/evidence.py'))
S = run_path(str(NS / 'checks/score.py'))
T = E['T']
read, require, pin = (T[k] for k in ('read', 'require', 'pin'))
ROOT = Path('D:/he_m3_whole_object_rounded_witness_consumption_001/offline_runtime_02')
BINDINGS = {
    'QA': V / 'm3_whole_object_witness_triangle_001/install/PRODUCT_RUN_BINDING.json',
    'QB': V / 'm3_whole_object_rounded_witness_compat_001/install/PRODUCT_RUN_BINDING.json',
}


def rejects(callback, reason):
    try:
        callback()
    except ValueError as error:
        require(str(error).startswith(reason), 'wrong_preflight_rejection/' + str(error))
        return str(error)
    raise ValueError('preflight_accepted_' + reason)


def files(role, i):
    slot = ROOT / role
    return (slot / f'client/call_{i + 1:02d}/RESPONSE.json',
            slot / f'worker/product_full/call_{i:03d}/SERVICE_RESULT.json',
            slot / f'worker/CAPTURE_{i:02d}.json')


def claim_route(source, proofs, *, alternate_faces):
    basis = ('Recomputed closest features against the current world mesh.' if alternate_faces
             else 'Used the capture-bound exact rational triangle witness, with approximate display coordinates.')
    units = 'All distances are in metres and points are world coordinates.'
    threshold = 'At 0.20 m N04 falls short, N05 qualifies, and N02 to N04 is closer.'
    answer = [basis, units, threshold]
    claims = {'pairs': {}, 'units': {'distance_unit': 'm', 'point_coordinate_frame': 'world', 'quote': units},
              'threshold': {'metres': '0.20', 'N04_meets': False, 'N05_meets': True,
                            'closer_reference': 'N04', 'quote': threshold}}
    for ref in T['REFERENCES']:
        proof = proofs[ref]
        truth = T['establish'](source, ref)
        if alternate_faces:
            indices = {side: [row['exact_source_triangle_indices'][-1]] for side, row in
                       truth['attaining_point_pair']['memberships'].items()}
            require(list(ix[0] for ix in indices.values()) != proof['source_evidence']['indices'],
                    'no_independently_admissible_equivalent_face_choice')
        else:
            indices = {side: [idx] for side, idx in zip(('a', 'b'), proof['source_evidence']['indices'], strict=True)}
        scope = f'N02 whole surface to {ref} whole surface.'
        direction = f"{ref} distance {proof['distance_m']} with world direction {proof['direction_a_to_b']}."
        a, b = [[round(p, 6) for p in proof[side]] for side in ('a', 'b')]
        closest = f'{ref} approximate points {a}, {b}; current zero-based triangles {indices}.'
        answer.extend((scope, direction, closest))
        claims['pairs'][ref] = {'target': 'N02', 'reference': ref, 'scope': 'whole_objects',
            'distance_m': proof['distance_m'], 'direction_a_to_b': proof['direction_a_to_b'], 'a': a, 'b': b,
            'source_triangle_indices': indices, 'coordinates_claimed_exact': False,
            'source_basis_kind': 'independent_geometry' if alternate_faces else 'exact_bound_points',
            'quotes': {'scope': scope, 'distance_direction': direction, 'point_pair_and_faces': closest, 'source_basis': basis}}
    typed = '\n'.join(answer)
    closure = {'scene_unchanged': True, 'owned_close_verified': True}
    grade = S['grade_claims'](typed, claims, source, read_only_proof=closure)
    require(grade['all_quality_passed'] and grade['score'] == grade['planned'] == 7,
            'valid_equivalent_formal_source_route_preflight_failed')
    bad = {}
    for kind in ('wrong_face', 'rounded_as_exact', 'no_basis', 'wrong_object'):
        corrupted = deepcopy(claims)
        pair = corrupted['pairs']['N04']
        if kind == 'wrong_face':
            pair['source_triangle_indices']['a'] = [0]
        elif kind == 'rounded_as_exact':
            pair['coordinates_claimed_exact'] = True
            pair['source_basis_kind'] = 'exact_reported_coordinates'
        elif kind == 'no_basis':
            pair['source_basis_kind'] = 'display_coordinates_only'
        else:
            pair['target'] = 'N01'
        result = S['grade_claims'](typed, corrupted, source, read_only_proof=closure)
        row = result['checks']['N04_actual_point_pair_and_triangle_membership']
        require(not row['passed'], 'wrong_formal_claim_accepted/' + kind)
        bad[kind] = row['reason']
    return {'score': grade['score'], 'controls_rejected': bad}


def main():
    source = T['archive']()
    original = T['frozen_truth']()
    require(read(NS / 'fixture/TRUTH.json') == original, 'independent_frozen_truth_bytes_not_reproduced')
    proofs, paths = {}, {}
    for role, binding in BINDINGS.items():
        refs = {ref: files(role, i) for i, ref in enumerate(T['REFERENCES'], 1)}
        paths[role] = {ref: [pin(path) for path in args] for ref, args in refs.items()}
        proofs[role] = E['verify_qualification'](T['SLOT'],
            *({ref: read(args[i]) for ref, args in refs.items()} for i in range(3)),
            binding=binding, require_source=role == 'QB', source=source)

    reply, packet, capture = (read(path) for path in files('QB', 1))
    evidence = E['R']['EXACT']
    rejections = {}
    for control in ('wrong_order', 'wrong_instance', 'stale_generation', 'wrong_triangle', 'rounded_rational'):
        bad, response = deepcopy(packet), deepcopy(reply)
        closest = E['D']['witnesses'](bad)
        certificate = closest[evidence]
        if control == 'wrong_order':
            bad['binding']['objects'].reverse()
            reason = 'public_whole_pair_scope_order_or_producer_identity_changed'
        elif control == 'wrong_instance':
            certificate['b']['instance_id'] += '-mismatch'
            reason = 'exact_public_proof_current_instance_or_order_changed'
        elif control == 'stale_generation':
            certificate['capture_state']['revision'] += 1
            reason = 'exact_public_proof_does_not_bind_current_capture_generation'
        elif control == 'wrong_triangle':
            certificate['a']['source_triangle_index'] = 0
            reason = 'proof_point_not_exactly_on_current_source_triangle'
        else:
            certificate['a']['point_m'] = list(map(str, E['G']['vector'](closest['a'])))
            reason = 'proof_point_not_exactly_on_current_source_triangle'
        response['result']['content'][0]['text'] = E['G']['encode'](bad)
        rejections[control] = rejects(lambda: E['verify_pair']('N04', response, bad, capture,
                                      source, BINDINGS['QB'], require_source=True), reason)

    report = {'passed': True, 'qualification_shapes': proofs, 'pinned_offline_delivery_records': paths,
              'independent_truth': pin(NS / 'fixture/TRUTH.json'),
              'formal_grading_routes': {
                  'bound_precise_certificate': claim_route(source, proofs['QB']['pairs'], alternate_faces=False),
                  'independent_equivalent_faces': claim_route(source, proofs['QB']['pairs'], alternate_faces=True),
              }, 'packet_controls_rejected': rejections, 'scope': 'offline full stdio using archived Blender source',
              'actual_new_Blender': 0, 'actual_new_models': 0, 'actual_new_rasters': 0}
    with (NS / 'checks/SCORER_PREFLIGHT.json').open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    print(json.dumps({'passed': True, 'packet_controls': len(rejections), 'formal_routes': 2,
                      'qualification_body_lengths': {role: [row['actual_body_utf8_bytes'] for row in proof['pairs'].values()]
                                                     for role, proof in proofs.items()}}))


if __name__ == '__main__':
    main()
