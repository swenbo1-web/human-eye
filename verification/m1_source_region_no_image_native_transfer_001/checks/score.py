"""Grade each unchanged final answer on the same seven geometry and closure items."""

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


def scoped_claim(case, scope, claim, text):
    _,config = T['scenario'](case)
    names = (config['target'],config['reference'])
    wanted = 'selected_source_triangle_union' if scope=='selected' else 'whole_objects'
    stated = quote(text,claim['quotes']['scope'])
    require((claim['target'],claim['reference'])==names and claim['scope']==wanted
            and claim['reference_scope']=='whole_object'
            and claim.get('selected_faces')==(config['selected'] if scope=='selected' else None)
            and all(name in stated for name in names),'answer_confuses_selected_faces_or_whole_object_order/'+scope)
    return {'scope':wanted,'target':names[0],'reference':names[1],'reference_scope':'whole_object',
            'source_faces':claim.get('selected_faces')}


def grade_claims(case,text,claims,source,*,read_only_proof):
    case,config = T['scenario'](case)
    rows = claims.get('measurements',{})
    checks = {}

    def item(label,verify):
        try:
            proof = verify()
            require(bool(proof),'independent_truth_or_answer_missing')
        except QUALITY_EXCEPTIONS as error:
            checks[label] = {'passed':False,'reason':str(error)}
        else:
            checks[label] = {'passed':True,'verified':proof}

    def units():
        value = claims['units']
        quote(text,value['quote'])
        require(value['distance_unit']=='m' and value['point_coordinate_frame']=='world',
                'answer_does_not_supply_world_metres')

    item('ordered_selected_and_whole_scope',lambda:{s:scoped_claim(case,s,rows[s],text) for s in T['SCOPES']})
    for scope in T['SCOPES']:
        def distance():
            claim = rows[scope]
            scoped_claim(case,scope,claim,text)
            quote(text,claim['quotes']['distance_direction'])
            units()
            independent = T['establish'](source,case,scope)
            metres = float(F(claim['distance_m']))
            direction = T['vector'](claim['direction_a_to_b'])
            require(abs(metres-independent['distance_m'])<=float(T['REPORT_METRES'])
                    and all(abs(float(x)-y)<=T['REPORT_DIRECTION']
                            for x,y in zip(direction,independent['direction_a_to_b'],strict=True)),
                    'reported_distance_or_world_direction_is_not_the_case_solution/'+scope)
            return {'metres':metres,'direction_a_to_b':claim['direction_a_to_b'],
                    'independent_squared_metres':independent['distance_squared_m2']}

        def point_pair():
            claim = rows[scope]
            scoped_claim(case,scope,claim,text)
            quote(text,claim['quotes']['point_pair_and_faces'])
            units()
            independent = T['establish'](source,case,scope)
            proof = T['measured'](source,case,scope,{
                'distance_m':independent['distance_m'],'direction_a_to_b':independent['direction_a_to_b'],
                'a':claim['a'],'b':claim['b'],'source_triangle_indices':claim['source_triangle_indices']})
            require(proof['pair_attains'] and proof['stated_source_memberships_correct'],
                    'reported_world_points_or_source_triangles_do_not_attain_the_current_surfaces/'+scope)
            return {'point_a':claim['a'],'point_b':claim['b'],'stated_source_triangle_indices':claim['source_triangle_indices'],
                    'independent_memberships':proof['actual_memberships'],'pair_distance_m':proof['pair_distance_m']}

        item(scope+'_distance_and_world_direction',distance)
        item(scope+'_actual_point_pair_and_triangle_membership',point_pair)

    def threshold():
        claim = claims['threshold']
        quote(text,claim['quote'])
        require(F(claim['metres'])==F(config['threshold_m']) and claim['selected_meets'] is True
                and claim['whole_meets'] is False and T['establish'](source,case,'selected')['meets_threshold']
                and not T['establish'](source,case,'whole')['meets_threshold'],'wrong_frozen_case_threshold_comparison')
        return {'threshold_m':float(F(config['threshold_m'])),'selected_meets':True,'whole_meets':False}

    def readonly():
        if claims.get('read_only_statement') is not None:
            quote(text,claims['read_only_statement'])
        require(read_only_proof and read_only_proof['scene_unchanged'] is True
                and read_only_proof['owned_close_verified'] is True,'actual_read_only_scene_and_close_not_verified')
        return read_only_proof

    item('case_clearance_threshold_comparison',threshold)
    item('closed_read_only_completion',readonly)
    unsupported = claims.get('extra_unsupported_assertions',[])
    for exact in unsupported:
        quote(text,exact)
    passed = sum(row['passed'] for row in checks.values())
    return {'case':case,'score':passed,'planned':len(checks),'all_quality_passed':passed==len(checks) and not unsupported,
            'checks':checks,'extra_unsupported_assertions':unsupported}


def score_slot(slot, claims):
    slot = Path(slot).resolve(strict=True)
    case,_ = T['scenario'](slot.name)
    slot_result = slot/'SLOT_RESULT.json'
    raw,publication = read(slot_result),read(slot/'SLOT_PUBLICATION.json')
    require(raw['status']==publication['status']=='completed' and raw['model_consumers']==1
            and publication['result_sha256']==pin(slot_result)['sha256'],
            'original_actual_formal_slot_not_completed_or_published')
    initial,terminal = (slot/path for path in ('initial_capture/TERMINAL_SOURCE.json','TERMINAL_SOURCE.json'))
    first,last = read(initial),read(terminal)
    source = T['verify_source'](last,first)
    copy = pin(slot/'native/input.blend',T['ASSET_SHA'])
    require(raw['asset_sha256']==copy['sha256']==source['asset_sha256'],'actual_formal_blender_copy_not_frozen_asset')
    text,tools,final = FINAL['original_final'](slot)
    close = raw['closure_verification']['passed'] and raw['independent_before_after']['passed']
    readonly = {'scene_unchanged':True,'owned_close_verified':close,
                'initial_source':pin(initial),'terminal_source':pin(terminal),'unchanged_read_only_asset':copy}
    return {'slot':slot.name,**grade_claims(case,text,claims,last,read_only_proof=readonly),
            'original_answer':final,'source':source,'reported_budget':raw['budget'],'actual_tool_events':len(tools)}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--slot',type=Path,required=True)
    cli.add_argument('--claims',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    args = cli.parse_args()
    report = score_slot(args.slot,read(args.claims))
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        stream.write(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
