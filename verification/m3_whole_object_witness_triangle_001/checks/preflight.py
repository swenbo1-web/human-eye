"""Preflight the independent checker using actual sealed inputs and labelled controls."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
D = run_path(str(NS/'checks/delivery.py'))
H = D['H']
require = D['require']


def fail(call,expected):
    try:
        call()
    except ValueError as issue:
        require(str(issue)==expected,'unexpected_independent_checker_rejection/'+str(issue))
        return expected
    raise ValueError('independent_checker_accepted_invalid_claim/'+expected)


def projection(retained,capture):
    _,_,original = D['E']['public'](retained['reply'])
    body = deepcopy(original)
    points = D['witnesses'](body)
    binding = body['binding']
    source = {'scope':D['PROOF_SCOPE'],'index_domain':D['DOMAIN'],
              'capture_state':deepcopy(capture['capture_state']),
              'document_epoch':capture['host_identity']['document_epoch']}
    for side,row in zip(D['SIDES'],binding['objects'],strict=True):
        source[side] = {'instance_id':capture['host_identity']['object_instances'][row['object_id']],
                        'source_triangle_index':retained['membership'][side][0]}
    points['source_triangles'] = source
    return body


def fake_reply(original,body):
    reply = deepcopy(original)
    reply['result']['content'][0]['text'] = D['wire_text'](body)
    return reply


def preflight():
    checked = {}
    for label in H['LABELS']:
        retained = D['historical'](label)
        capture = retained['capture']
        body = projection(retained,capture)
        projected = fake_reply(retained['reply'],body)
        positive = D['verify_delivery'](label,retained['reply'],projected,capture=capture,
                                       identity={'source_sha256':D['BASE_SHA']})
        standard = D['verify_delivery'](label,retained['reply'],retained['reply'],capture=capture,
                                       identity={'source_sha256':D['BASE_SHA']},require_source=False)
        stale = deepcopy(capture)
        stale['capture_state']['revision'] += 1
        stale_error = fail(lambda:D['verify_witness'](stale,body),
                           'triangle_source_reference_not_same_capture_generation_or_domain')
        impersonated = deepcopy(capture)
        changed = body['binding']['objects'][0]['object_id']
        impersonated['host_identity']['object_instances'][changed] += '-different-instance'
        wrong_object = fail(lambda:D['verify_witness'](impersonated,body),
                            'triangle_source_reference_not_same_current_ordered_object_instance/a')
        other = deepcopy(body)
        left = next(m for m in capture['meshes'] if m['object_id']==changed)
        outside = next(i for i in range(len(left['faces'])) if i not in retained['membership']['a'])
        D['witnesses'](other)['source_triangles']['a']['source_triangle_index'] = outside
        wrong_face = fail(lambda:D['verify_witness'](capture,other),
                          'reported_world_point_does_not_lie_on_claimed_current_triangle/a')
        switched = deepcopy(body)
        switched['binding']['objects'].reverse()
        wrong_order = fail(lambda:D['verify_witness'](capture,switched,expected_names=retained['names']),
                           'native_current_ordered_pair_capture_or_scope_mismatch')
        points = D['witnesses'](switched)
        points['a'],points['b'] = points['b'],points['a']
        points['direction_a_to_b'] = [-v for v in points['direction_a_to_b']]
        sides = points['source_triangles']
        sides['a'],sides['b'] = sides['b'],sides['a']
        reverse = D['verify_reverse'](projected,fake_reply(retained['reply'],switched),capture=capture)
        checked[label] = {'derived_projected_checker_passed':positive,'sealed_standard_checker_passed':standard,
                          'derived_valid_reverse_checker':reverse,'wrong_face':wrong_face,'wrong_order':wrong_order,
                          'wrong_generation':stale_error,'same_name_changed_instance':wrong_object}
    return {'passed':True,'actual_new_Blender':0,'actual_new_models':0,
            'source_binding':'sealed actual original; explicit synthetic projection and substitutions only for checker coverage',
            'controls':checked}


if __name__=='__main__':
    print(json.dumps(preflight(),ensure_ascii=False,allow_nan=False,indent=2))
