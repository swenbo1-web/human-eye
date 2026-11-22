"""Apply the frozen seven quality items to unchanged actual answers and images."""

import argparse
from fractions import Fraction as F
import json
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
E = run_path(str(V/'m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py'))
require,read = E['require'],E['read']


def quote(answer,row):
    phrase = row['quote']
    require(type(phrase) is str and bool(phrase.strip()) and phrase in answer,
            'claimed_evidence_not_quoted_from_actual_original')


def claimed_indices(claim,roi):
    fields = {'source_triangle_indices','source_triangle_index_ranges','source_roi_id'} & claim.keys()
    require(len(fields)==1,'no_unique_current_source_reference')
    key, = fields
    if key=='source_roi_id':
        return roi[claim[key]]
    if key=='source_triangle_indices':
        rows = claim[key]
    else:
        ranges = claim[key]
        require(all(type(lo) is int and type(hi) is int and 0<=lo<=hi<6160 for lo,hi in ranges),
                'wrong_current_source_range')
        rows = [n for lo,hi in ranges for n in range(lo,hi+1)]
    require(all(type(i) is int and i>=0 for i in rows) and len(rows)==len(set(rows)),
            'source_rows_invalid_or_duplicated')
    return sorted(rows)


def used_witness(item,answer,claims,role):
    require(claims,'original_answer_did_not_identify_a_readable_image_for/'+role)
    verified = []
    for row in claims:
        quote(answer,row)
        ref = row.get('image_ref')
        address = row.get('local_path')
        if ref:
            require(ref in row['quote'],'image_ref_not_in_original_answer_quote')
            frame = item['available_frames'].get(ref)
        else:
            require(address and address in row['quote'],'file_path_not_in_original_answer_quote')
            matches = [f for f in item['available_frames'].values()
                       if Path(f['post_close_png']['path']).resolve()==Path(address).resolve()]
            frame = item['link_frames'].get(address) or (matches[0] if len(matches)==1 else None)
        require(frame and frame['by_role'][role]['complete'], 'cited_original_lacks_current_complete_witness/'+role)
        proof = frame['by_role'][role]
        if row.get('view') is not None:
            require(row['view']==proof['view'],'quoted_image_points_to_wrong_registered_view/'+role)
        if row.get('scope_id') is not None:
            require(row['scope_id']==proof['scope_id'],'quoted_image_points_to_wrong_current_scope/'+role)
        verified.append({'reference_spelling':ref or address,'proof':proof,
                         'actual_image_deliveries':frame['actual_deliveries']})
    return verified


def occlusion(item,row,answer):
    quote(answer,row)
    truth = item['truth']
    p = truth['roles']['P']
    require(row['object_name']==p and row['all_six'] is True and row['full_visibility_unknown_in_pool'] is True
            and row.get('asserts_all_pixels_invisible') is not True,'does_not_bound_unknown_to_the_six_actual_directions')
    region = truth['regions'][p]
    independent = region['directions']
    require(all(not r['whole_region_clear'] and r['positive_area_occluders'] for r in independent.values()),
            'all_six_current_positive_area_shadows_unproved')
    stated = row.get('blockers_by_view',{})
    if not stated:
        named = row.get('blocker_object_names',[])
        require(named and len(named)==len(set(named)),'does_not_name_an_actual_blocker')
        mapping = {view:[i for i in entry['positive_area_occluders'] if i['object_name'] in named]
                   for view,entry in independent.items()}
        require(all(mapping.values()) and {i['object_name'] for rows in mapping.values() for i in rows}==set(named),
                'named_obstructors_do_not_account_for_six_finite_directions')
        return {'named_positive_blockers_by_view':mapping,'whole_region_is_unknown_within_only_fixed_views':True}
    require(stated.keys()==independent.keys(),'named_shadow_clips_missing_some_actual_directions')
    checked = {}
    for view,claim in stated.items():
        name = claim['object_name']
        require(name in row['quote'],'blocker_name_not_present_in_original_quote')
        index = claim.get('source_triangle_index')
        accepted = [actual for actual in independent[view]['positive_area_occluders']
                    if actual['object_name']==name and (index is None or actual['source_triangle_index']==index)]
        require(accepted,'named_geometry_has_no_positive_shaded_area/'+view)
        if claim.get('nearest'):
            require(view=='RIGHT' and name==truth['right_blocker_order']['first_blocker_over_interior'],
                    'nearest_blocker_not_independently_verified/'+view)
        checked[view] = accepted
    return {'named_positive_blockers_by_view':checked,'whole_region_is_unknown_within_only_fixed_views':True}


def score_answer(item,claims):
    answer = item['answer']['text']
    truth = item['truth']
    rows = claims.get('regions',[])
    names = [row['object_name'] for row in rows]
    expected = truth['regions']
    flags = {}

    def score(name,check):
        try:
            result = check()
            require(bool(result),'missing_or_incorrect_answer_proof')
            flags[name] = {'passed':True,'verified':result}
        except (ValueError,KeyError,TypeError,IndexError,ZeroDivisionError,OSError) as error:
            flags[name] = {'passed':False,'reason':str(error)}

    def roster():
        require(len(names)==len(expected) and set(names)==set(expected),'actual_source_rectangle_set_incomplete_or_extra')
        for row in rows:
            quote(answer,row)
            wanted = expected[row['object_name']]
            if 'area_m2' in row:
                require(abs(F(str(row['area_m2']))-F(wanted['area_m2_exact']))<=E['EPS'],
                        'incorrect_area_in_original_answer/'+row['object_name'])
            if 'unit_normal_world' in row:
                require(E['nearby'](row['unit_normal_world'],wanted['unit_normal_world_exact']),
                        'incorrect_oriented_normal_in_original_answer/'+row['object_name'])
        return names

    def sources():
        require(len(names)==len(expected) and set(names)==set(expected),'incorrect_current_source_candidate_set')
        sources = {}
        for row in rows:
            quote(answer,row)
            name = row['object_name']
            source = claimed_indices(row,item['roi_aliases'].get(name,{}))
            require(source==expected[name]['source_triangle_indices']
                    and E['nearby'](row['center_world_m'],expected[name]['center_world_m_exact']),
                    'source_rows_or_world_center_not_current/'+name)
            sources[name] = {'indices':source,'center_world_m':row['center_world_m']}
        return sources

    def distance():
        claim = claims['measurement']
        quote(answer,claim)
        return E['measured'](claim,item['source'],truth)

    def final_links():
        resolved = {}
        for role in ('R','Q'):
            rows = claims.get('images',{}).get(role,[])
            for row in rows:
                quote(answer,row)
                address = row.get('local_path')
                if not address:
                    continue
                frame = item['link_frames'].get(address)
                if frame and frame['by_role'][role]['complete']:
                    require(address in row['quote'],'actual_final_link_not_in_original_quote')
                    resolved[role] = frame['post_close_png']
                    break
        require(set(resolved)=={'R','Q'},'same_slot_operable_original_links_for_both_required')
        return resolved

    score('all_scene_candidates',roster)
    score('current_source_faces_and_centers',sources)
    score('original_image_R',lambda: used_witness(item,answer,claims.get('images',{}).get('R'), 'R'))
    score('original_image_Q',lambda: used_witness(item,answer,claims.get('images',{}).get('Q'), 'Q'))
    score('occluded_target_six_direction_unknown',lambda: occlusion(item,claims['occlusion'],answer))
    score('exact_surface_distance_direction_and_points',distance)
    score('both_final_links_reopened',final_links)
    total = sum(row['passed'] for row in flags.values())
    unsupported = claims.get('extra_unsupported_assertions',[])
    for row in unsupported:
        quote(answer,row)
    return {'slot':item['slot'],'score':total,'planned':len(flags),'all_quality_passed':total==7 and not unsupported,
            'checks':flags,'extra_unsupported_assertions':unsupported,
            'final_original':{key:value for key,value in item['answer'].items() if key!='text'},
            'closure':item['closed_source'],'first_matching_task':item['first_matching_task'],
            'successful_matching_task_count':len(item['matching_task_requests']),
            'actual_budget':item['budget'],'host_render_and_user_click':None}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--slot',type=Path,required=True)
    p.add_argument('--claims',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--truth',type=Path)
    a = p.parse_args()
    load_slot = run_path(str(HERE/'formal.py'))['load_slot']
    scored = score_answer(load_slot(a.slot,a.truth),read(a.claims))
    with a.output.open('x',encoding='utf8',newline='\n') as out:
        out.write(json.dumps(scored,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

