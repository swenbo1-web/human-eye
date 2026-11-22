"""Replay locked original paths, invalid bindings, and actual extra construction."""

from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import sys


G = run_path(str(Path(__file__).resolve().parent/'grade.py'))
E = G['E']
V, NS = (E[name] for name in ('V','NS'))
read, require, pin = (E[name] for name in ('read','require','pin'))
ORIGINAL = Path('D:/he_m1_region_task_first_packet_consumption_holdout_recovery_001/slots')
PROJECTION = Path('D:/he_m1_region_task_witness_image_path_001/qualification')
HISTORIC = Path('D:/he_m4_cross_scale_live_task_formal_001/slots/P1')


def reject(check, reason):
    try:
        check()
    except ValueError as error:
        require(str(error)==reason,'wrong_rejection/'+str(error))
    else:
        raise ValueError('unexpected_acceptance/'+reason)
    return reason


def compact(value):
    return json.dumps(value,separators=(',',':'),ensure_ascii=False)


def actual_replayed_formats():
    checks = []
    for label,number in (('A1',4),('B1',5)):
        slot = ORIGINAL/label
        projection = PROJECTION/(label+'_candidate')
        producer = read(projection/'worker/SERVICE_RESULT_01.json')
        first = read(projection/'COLD_RESPONSE.json')
        bound = E['verify_public_witnesses'](first,producer,slot=slot,require_paths=True)
        read_owner = slot/'owner'/f'tool_{number:02d}'
        req = read(read_owner/'REQUEST.json')
        require(req['params']['name']=='read_images','old_original_read_path_request_changed')
        ordinary = E['verify_read_images'](slot,read(read_owner/'RESPONSE.json'),producer,
                                           req['params']['arguments']['refs'])
        paths = {row['path']:row for row in bound['first_packet_path_originals']}
        legacy = {row['path']:row for row in ordinary}
        require(paths.keys()==legacy.keys() and all(paths[p]['ref']==legacy[p]['ref']
                and paths[p]['sha256']==legacy[p]['sha256'] for p in paths),'legal_routes_disagree_on_original_file')
        final = slot/'consumer/PUBLIC_FINAL.txt'
        body = final.read_bytes().decode('utf8')
        require(set(paths)<=set(G['markdown_paths'](body)),'old_genuine_final_answer_links_missing_original')
        via_first = [G['final_link'](slot,body,path,paths) for path in paths]
        via_read = [G['final_link'](slot,body,path,legacy) for path in paths]
        require([item['closed_reopen'] for item in via_first]==[item['closed_reopen'] for item in via_read],
                'legal_final_forms_must_reopen_same_file_independently')
        lookalike, = [row['path'] for row in bound['original_images'] if row['scope_id']=='global']
        wrong = reject(lambda: G['final_link'](slot,f'![wrong]({lookalike})',lookalike,paths),
                       'final_PNG_link_not_delivered_with_current_binding')
        raw = projection/'COLD_RESPONSE.json'
        payload = E['body'](first)
        cols = payload['witnesses']['columns']
        own, = [w for w in bound['public_witnesses'] if w['object_name']=='Component_582']
        require(own['view_name']=='SCENE' and own['frame_index']==1,'sealed_same_named_local_view_changed')
        row, = [row for row in payload['witnesses']['rows'] if row[cols.index('region_index')]==own['region_index']]
        altered = list(row)
        altered[cols.index('frame_index')] = 0
        base = raw.read_bytes()
        before,after = compact(row).encode(),compact(altered).encode()
        require(base.count(before)==1,'could_not_make_one_byte_view_substitution')
        mutated = base.replace(before,after)
        require(len(mutated)==len(base) and sum(a!=b for a,b in zip(base,mutated,strict=True))==1,
                'one_byte_view_substitution_modified_other_original_bytes')
        rejection = reject(lambda: E['verify_public_witnesses'](json.loads(mutated),producer,slot=slot,require_paths=True),
                           E['WRONG_WITNESS'])
        corrupt = deepcopy(first)
        first_json = E['body'](corrupt)
        first_json['witness_image_paths']['rows'][0][1] = lookalike
        corrupt['result']['content'][0]['text'] = compact(first_json)
        wrong_path = reject(lambda: E['verify_public_witnesses'](corrupt,producer,slot=slot,require_paths=True),
                            'path_not_canonical_spelling_of_this_current_frame')
        checks.append({'old_slot':label,'candidate_serialization_original':pin(raw),'original_answer':pin(final,slot),
                       'actual_read_request':pin(read_owner/'REQUEST.json',slot),
                       'actual_read_response':pin(read_owner/'RESPONSE.json',slot),
                       'original_first_packet_independent_paths':via_first,'original_read_images_paths':via_read,
                       'same_name_global_final_wrong_path_rejected':wrong,'one_byte_wrong_scope_frame_rejected':rejection,
                       'direct_table_to_wrong_disk_frame_rejected':wrong_path})
    return checks


def actual_construction_and_source():
    stored = HISTORIC/'product_full/call_001/SERVICE_RESULT.json'
    proven = HISTORIC/'TERMINAL_SOURCE.json'
    original_binding = V/'m4_live_assembly_relation_task_001/PRODUCT_RUN_BINDING.json'
    installed = read(V/'m1_region_task_witness_image_path_001/install/PRODUCT_RUN_BINDING.json')
    p = read(stored)
    source = read(proven)
    original_arguments = read(HISTORIC/'owner/tool_01/PRODUCT_REQUEST.json')['params']['arguments']
    sys.path.insert(0,installed['install_root'])
    from human_eye_plugin.live_spatial_mcp import _tool_result

    root = Path(p['frames'][0]['image_path']).parents[2]
    raw_candidate = _tool_result(p,is_error=False,response_detail='brief',
        observation_task_query=original_arguments['query'],region_task_observation_producer=lambda *_:(p,root))
    proof = E['verify_discovery'](HISTORIC,raw_candidate,p,source,binding=original_binding,require_paths=True,
                                  pinned_truth=read(NS/'fixture/TRUTH.json'))
    require(proof['constructed_count']==4 and proof['selected_count']==3
            and len(proof['constructed_not_delivered_indices'])==1 and len(proof['original_images'])==2,
            'four_constructed_three_delivered_not_preserved')
    return {'mode':'derived_display_projection_only_on_original_actual_source_frame_and_PNG',
            'source':pin(proven,HISTORIC),'producer':pin(stored,HISTORIC),
            'installed_candidate_sha256':installed['source_sha256'],'source_capture_still_historical':True,
            'proof':proof}


def main():
    old_routes = actual_replayed_formats()
    original_construction = actual_construction_and_source()
    print(json.dumps({'passed':True,'models':0,'Blender':0,'new_constructed_images':0,
                      'two_actual_old_final_paths_each_checked_by_both_routes':old_routes,
                      'original_construction_round_trip':original_construction},
                     ensure_ascii=False,allow_nan=False,indent=2))


if __name__=='__main__':
    main()
