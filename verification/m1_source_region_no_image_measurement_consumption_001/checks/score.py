"""Grade the original final model answer against independent source-triangle truth."""

import argparse
from fractions import Fraction as F
import json
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
V = NS.parent
T = run_path(str(NS/'checks/truth.py'))
FINAL = run_path(str(V/'m1_source_region_first_packet_consumption_001/checks/score.py'))
require,read,pin = (T[k] for k in ('require','read','pin'))
QUALITY_EXCEPTIONS = (ValueError,TypeError,KeyError,IndexError,ArithmeticError,OSError)


def quote(text, excerpt):
    require(type(excerpt) is str and excerpt.strip() and excerpt in text,'claim_not_quoted_from_original_final')
    return excerpt


def scoped_claim(scope, claim, text):
    exact_scope = 'selected_source_triangle_union' if scope=='selected' else 'whole_objects'
    statements = quote(text,claim['quotes']['scope'])
    require(claim['target']=='M15' and claim['reference']=='M14' and claim['scope']==exact_scope
            and claim['reference_scope']=='whole_object' and claim.get('selected_faces')==([6,7] if scope=='selected' else None)
            and 'M15' in statements and 'M14' in statements,
            'answer_scope_not_full_selected_faces_or_current_whole_order/'+scope)
    return {'target':claim['target'],'reference':claim['reference'],'scope':exact_scope,
            'selected_faces':claim.get('selected_faces'),'reference_scope':claim['reference_scope']}


def grade_claims(text, claims, current, *, read_only_proof):
    checks = {}

    def item(label, check):
        try:
            proof = check()
            require(bool(proof),'missing_independent_evidence')
        except QUALITY_EXCEPTIONS as err:
            checks[label] = {'passed':False,'reason':str(err)}
        else:
            checks[label] = {'passed':True,'verified':proof}

    rows = claims.get('measurements',{})
    item('ordered_selected_and_whole_scope',lambda: {s:scoped_claim(s,rows[s],text) for s in T['SELECTIONS']})
    for scope in T['SELECTIONS']:
        def distance():
            claim = rows[scope]
            scoped_claim(scope,claim,text)
            quote(text,claim['quotes']['distance_direction'])
            independent = T['establish'](current,scope)
            metres = float(F(claim['distance_m']))
            direction = T['vector'](claim['direction_a_to_b'])
            require(abs(metres-independent['distance_m'])<=float(T['REPORT_METRES'])
                    and all(abs(float(v)-expected)<=T['REPORT_DIRECTION']
                            for v,expected in zip(direction,independent['unit_direction_A_to_B'],strict=True)),
                    'asserted_distance_or_oriented_world_direction_is_incorrect/'+scope)
            return {'metres':metres,'direction_a_to_b':claim['direction_a_to_b'],
                    'independent_squared_metres':independent['distance_squared_m2']}

        def point_pair():
            claim = rows[scope]
            scoped_claim(scope,claim,text)
            quote(text,claim['quotes']['point_pair_and_faces'])
            # Point-pair grading uses the separately known length so an omitted
            # scalar or direction cannot change this item's geometric judgement.
            independent = T['establish'](current,scope)
            proof = T['check_measurement'](current,scope,{
                'distance_m':independent['distance_m'],'direction_a_to_b':independent['unit_direction_A_to_B'],
                'a':claim['a'],'b':claim['b'],'source_triangle_indices':claim['source_triangle_indices']})
            require(proof['actual_attaining_pair'] and proof['stated_source_triangle_membership_correct'],
                    'reported_points_or_attributed_source_faces_are_not_in_the_measured_surface/'+scope)
            return {'point_a':claim['a'],'point_b':claim['b'],'stated_source_triangle_indices':claim['source_triangle_indices'],
                    'independent_memberships':proof['reported_memberships'],'pair_distance_m':proof['pair_distance_m']}

        item(scope+'_distance_and_world_direction',distance)
        item(scope+'_actual_point_pair_and_triangle_membership',point_pair)

    def threshold():
        claim = claims['threshold']
        quote(text,claim['quote'])
        require(F(claim['metres'])==T['THRESHOLD'] and claim['selected_meets'] is True and claim['whole_meets'] is False
                and T['establish'](current,'selected')['meets_2m'] and not T['establish'](current,'whole')['meets_2m'],
                'original_two_metre_comparison_confuses_selected_and_whole')
        return {'threshold_m':2,'selected_meets':True,'whole_meets':False}

    def read_only():
        if claims.get('read_only_statement') is not None:
            quote(text,claims['read_only_statement'])
        require(read_only_proof and read_only_proof['scene_unchanged'] is True
                and read_only_proof['owned_close_verified'] is True,'actual_read_only_scene_and_close_not_verified')
        return read_only_proof

    item('two_metre_clearance_comparison',threshold)
    item('closed_read_only_completion',read_only)
    extra = claims.get('extra_unsupported_assertions',[])
    for excerpt in extra:
        quote(text,excerpt)
    passed = sum(row['passed'] for row in checks.values())
    return {'score':passed,'planned':len(checks),'all_quality_passed':passed==len(checks) and not extra,
            'checks':checks,'extra_unsupported_assertions':extra}


def score_slot(slot, claims):
    slot = Path(slot).resolve(strict=True)
    result_path = slot/'SLOT_RESULT.json'
    raw,pub = read(result_path),read(slot/'SLOT_PUBLICATION.json')
    require(raw['status']==pub['status']=='completed' and raw['model_consumers']==1
            and pub['result_sha256']==pin(result_path)['sha256'],'actual_formal_slot_unpublished_or_incomplete')
    first_file,last_file = (slot/path for path in ('initial_capture/TERMINAL_SOURCE.json','TERMINAL_SOURCE.json'))
    first,last = read(first_file),read(last_file)
    source_check = T['verify_source'](last,first)
    copy = pin(slot/'native/input.blend',T['ASSET_SHA'])
    require(raw['asset_sha256']==source_check['asset_sha256']==copy['sha256'],
            'same_formal_owned_blender_copy_not_frozen_asset')
    text, tools, final = FINAL['original_final'](slot)
    closed = raw['closure_verification']['passed'] and raw['independent_before_after']['passed']
    evidence = {'scene_unchanged':True,'owned_close_verified':closed,'initial_source':pin(first_file),
                'terminal_source':pin(last_file),'unchanged_read_only_asset':copy}
    return {'slot':slot.name,**grade_claims(text,claims,last,read_only_proof=evidence),
            'original_answer':final,'source':source_check,'reported_budget':raw['budget'],
            'actual_tool_events':len(tools)}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--slot',type=Path,required=True)
    cli.add_argument('--claims',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    args = cli.parse_args()
    report = score_slot(args.slot,read(args.claims))
    with args.output.open('x',encoding='utf-8',newline='\n') as output:
        output.write(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
