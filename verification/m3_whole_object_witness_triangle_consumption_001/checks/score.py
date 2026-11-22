"""Grade each unchanged final answer on seven source-bound geometry and closure checks."""

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
ERRORS = (ValueError,TypeError,KeyError,IndexError,ArithmeticError,OSError)


def quote(text,excerpt):
    require(type(excerpt) is str and excerpt.strip() and excerpt in text,'claim_is_not_quoted_from_actual_raw_answer')
    return excerpt


def scope_of(text,reference,item):
    phrase = quote(text,item['quotes']['scope'])
    require(item['target']==T['TARGET'] and item['reference']==reference and item['scope']=='whole_objects'
            and T['TARGET'] in phrase and reference in phrase and item.get('selected_faces') is None,
            'reported_object_order_or_entire_triangle_surface_scope_changed/'+reference)
    return {'order':[T['TARGET'],reference],'scope':'whole_objects'}


def grade_claims(text,claims,source,*,read_only_proof):
    checks = {}
    references = T['REFERENCES']
    answers = claims.get('pairs',{})

    def test(label,verify):
        try:
            evidence = verify()
            require(bool(evidence),'answer_or_independent_evidence_not_present')
        except ERRORS as error:
            checks[label] = {'passed':False,'reason':str(error)}
        else:
            checks[label] = {'passed':True,'verified':evidence}

    def scopes():
        require(set(answers)==set(references),'original_answer_did_not_identify_both_exact_whole_object_pairs')
        return {reference:scope_of(text,reference,answers[reference]) for reference in references}

    def said_units():
        unit = claims['units']
        quote(text,unit['quote'])
        require(unit['distance_unit']=='m' and unit['point_coordinate_frame']=='world','original_answer_world_metres_required')

    test('ordered_whole_object_scopes',scopes)
    for ref in references:
        def distance():
            item = answers[ref]
            scope_of(text,ref,item)
            said_units()
            phrase = quote(text,item['quotes']['distance_direction'])
            expect = T['establish'](source,ref)
            metres = float(F(item['distance_m']))
            direction = T['vector'](item['direction_a_to_b'])
            require(abs(metres-expect['distance_m'])<=float(T['REPORT_METRES'])
                    and all(abs(float(a)-b)<=T['REPORT_DIRECTION']
                            for a,b in zip(direction,expect['direction_a_to_b'],strict=True)),
                    'original_distance_or_world_A_to_B_direction_incorrect/'+ref)
            return {'metres':metres,'direction_a_to_b':item['direction_a_to_b'],
                    'independent_squared_metres':expect['distance_squared_m2'],'distance_direction_quote':phrase}

        def points():
            item = answers[ref]
            scope_of(text,ref,item)
            said_units()
            phrase = quote(text,item['quotes']['point_pair_and_faces'])
            expect = T['establish'](source,ref)
            independent = T['measured'](source,ref,{**item,'distance_m':expect['distance_m'],
                                                    'direction_a_to_b':expect['direction_a_to_b']})
            require(independent['actual_attaining_pair'] and independent['claimed_source_triangle_indices_are_current'],
                    'original_pair_or_reported_object_local_triangles_do_not_contain_true_surface_points/'+ref)
            return {'point_a':item['a'],'point_b':item['b'],'stated_source_triangle_indices':item['source_triangle_indices'],
                    'independent_memberships':independent['memberships'],'pair_distance_m':independent['pair_distance_m'],
                    'point_pair_quote':phrase}

        test(ref+'_distance_and_world_direction',distance)
        test(ref+'_actual_point_pair_and_triangle_membership',points)

    def threshold():
        item = claims['threshold']
        quote(text,item['quote'])
        observations = {ref:T['establish'](source,ref) for ref in references}
        require(F(item['metres'])==T['THRESHOLD'] and item['M19_meets'] is observations['M19']['meets_threshold'] is False
                and item['M14_meets'] is observations['M14']['meets_threshold'] is True
                and item['closer_reference']=='M19'
                and observations['M19']['distance_m']<observations['M14']['distance_m'],
                'wrong_minimum_clearance_threshold_or_closer_reference')
        return {'threshold_m':2.5,'M19_meets':False,'M14_meets':True,'closer_reference':'M19'}

    def closed():
        if claims.get('read_only_statement') is not None:
            quote(text,claims['read_only_statement'])
        require(read_only_proof and read_only_proof['scene_unchanged'] is True
                and read_only_proof['owned_close_verified'] is True,'owned_read_only_completion_not_observed')
        return read_only_proof

    test('threshold_and_closer_whole_pair',threshold)
    test('closed_read_only_completion',closed)
    unsupported = claims.get('extra_unsupported_assertions',[])
    for item in unsupported:
        quote(text,item)
    passed = sum(row['passed'] for row in checks.values())
    return {'score':passed,'planned':len(checks),'all_quality_passed':passed==len(checks) and not unsupported,
            'checks':checks,'extra_unsupported_assertions':unsupported}


def score_slot(slot,claims):
    slot = Path(slot).resolve(strict=True)
    result = slot/'SLOT_RESULT.json'
    raw,published = read(result),read(slot/'SLOT_PUBLICATION.json')
    require(slot.name in ('A1','B1') and raw['status']==published['status']=='completed'
            and raw['model_consumers']==1 and published['result_sha256']==pin(result)['sha256'],
            'formal_original_slot_not_actual_completed_and_published')
    initial,terminal = (slot/path for path in ('initial_capture/TERMINAL_SOURCE.json','TERMINAL_SOURCE.json'))
    first,last = read(initial),read(terminal)
    geometry = T['verify_source'](last,first)
    filename = pin(slot/'native/input.blend',T['SOURCE']['ASSET_SHA'])
    require(raw['asset_sha256']==geometry['asset_sha256']==filename['sha256'],'formal_same_asset_origin_mismatch')
    text,tools,answer = FINAL['original_final'](slot)
    proof = {'scene_unchanged':True,'owned_close_verified':raw['closure_verification']['passed']
             and raw['independent_before_after']['passed'],'initial_source':pin(initial),
             'terminal_source':pin(terminal),'read_only_asset':filename}
    return {'slot':slot.name,**grade_claims(text,claims,last,read_only_proof=proof),
            'original_answer':answer,'source':geometry,'reported_budget':raw['budget'],'actual_tool_events':len(tools)}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--slot',type=Path,required=True)
    cli.add_argument('--claims',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    args = cli.parse_args()
    result = score_slot(args.slot,read(args.claims))
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
