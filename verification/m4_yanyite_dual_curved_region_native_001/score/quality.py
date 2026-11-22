"""Score literal final-answer claims against the independently verified current slot."""

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0,str(Path(__file__).resolve().parent))
from oracle import history, load, pin, require, verify_closed_source, write
from qualify import actual_calls, frame_truth, numeric_pair, near_point


REQUIRED = tuple(f'{region}.{fact}' for region in ('lower','upper') for fact in
                 ('counts','distance','direction','nearest_pair','threshold'))+('nearer','upper_image','single_view_scope')
NUMERIC_REPORT_TOLERANCE_M = 5e-5


def verified_frames(slot, device, terminal, geometry):
    calls=actual_calls(slot)
    good,bad=[],[]
    for candidate in device['frames']:
        try:
            good.append(frame_truth(candidate,slot,terminal,device,geometry['regions']['upper'],calls))
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            bad.append({'ref':candidate.get('ref'),'error':str(error)})
    return good,bad


def exact_claim(claims, answer, name):
    row=claims.get(name)
    if row is None:
        return None
    quote=row['quote']
    require(isinstance(quote,str) and quote.strip() and quote in answer,'transcribed_quote_not_in_original_final/'+name)
    return row


def choose_image(row, frames):
    reference=row['final_image_literal']
    named=row['current_object_local_triangle']
    require(type(named) is int and isinstance(reference,str) and reference in row['quote'],
            'opening_reference_or_reported_local_triangle_missing')
    hits=[]
    for frame in frames:
        source=frame['PNG']['path']
        known={(source.replace('\\','/')),frame['ref']}
        if reference.replace('\\','/') not in known:
            continue
        if reference==frame['ref']:
            # A replay handle is not a post-close opening destination by itself.
            require(row.get('visible_original_path') in {source,source.replace('\\','/')}
                    and row['visible_original_path'] in row['quote'],'handle_without_openable_closed_png')
        if named in frame['upper_triangle_pixel_counts']:
            hits.append(frame)
    require(len(hits)==1,'final_image_or_source_face_not_unique_actual_delivered_upper_pixels')
    return {**hits[0],'named_triangle':named,
            'named_triangle_pixels':hits[0]['upper_triangle_pixel_counts'][named]}


def score_slot(slot, claim_path):
    snapshot,prior=history()
    geometry,terminal,device=verify_closed_source(slot,snapshot,prior)
    answer=slot/'consumer/PUBLIC_FINAL.txt'
    answer_pin=pin(answer)
    text=answer.read_text(encoding='utf8')
    table=load(claim_path)
    require(table['answer_sha256']==answer_pin['sha256'] and table['slot']==slot.name,
            'claim_transcription_not_bound_to_same_public_final')
    claims=table['claims']
    require(set(claims)<=set(REQUIRED),'claim_table_unknown_rubric_item')
    frames,unusable=verified_frames(slot,device,terminal,geometry)
    results={}
    for name in REQUIRED:
        claim=exact_claim(claims,text,name)
        if claim is None:
            results[name]={'status':'missing'}
            continue
        try:
            if name=='nearer':
                require(claim['value']=='upper','nearer_selection_not_correct')
            elif name=='upper_image':
                chosen=choose_image(claim,frames)
            elif name=='single_view_scope':
                require(claim['observable_scope']=='actual_samples_in_one_frame'
                        and claim['implies_complete_visibility'] is False
                        and claim['implies_all_unsampled_are_occluded'] is False,
                        'single_image_claim_overstates_scope')
            else:
                region,test=name.split('.')
                need=geometry['regions'][region]
                binary64=geometry['matrix64_regions'][region]
                if test=='counts':
                    require((claim['triangles'],claim['vertices'])==(need['triangle_count'],need['vertex_count']),
                            'wrong_current_selection_counts')
                elif test=='distance':
                    require(type(claim['distance_m']) in (int,float)
                            and abs(claim['distance_m']-need['distance_m'])<=NUMERIC_REPORT_TOLERANCE_M,
                            'wrong_shortest_surface_distance')
                elif test=='direction':
                    require(near_point(claim['world_unit_direction'],need['direction_world'],NUMERIC_REPORT_TOLERANCE_M),
                            'wrong_or_reversed_world_unit_direction')
                elif test=='nearest_pair':
                    # Match actual attaining features in a reported domain. Blender
                    # readback has two equal vertices per region, unlike binary64.
                    for domain in (need,binary64):
                        try:
                            numeric_pair(domain['distance_m'],domain['direction_world'],
                                         claim['selected_point_world_m'],claim['Cube_point_world_m'],
                                         domain,NUMERIC_REPORT_TOLERANCE_M)
                            break
                        except ValueError:
                            continue
                    else:
                        raise ValueError('no_attaining_same_slot_selected_and_Cube_surface_pair')
                elif test=='threshold':
                    require(claim['at_least_0_40_m'] is need['at_least_0_40_m'],'wrong_distance_threshold_classification')
            results[name]={'status':'pass','quote':claim['quote']}
        except (ValueError,KeyError,IndexError,TypeError) as exc:
            results[name]={'status':'failure','quote':claim['quote'],'reason':str(exc)}
    passed=sum(v['status']=='pass' for v in results.values())
    return {'slot':slot.name,'quality_complete':passed==len(REQUIRED),'passed_items':passed,
            'total_items':len(REQUIRED),'criteria':results,'answer':answer_pin,'claim_transcription':pin(claim_path),
            'verified_frames':frames,'unusable_frames':unusable,'chosen_image':locals().get('chosen'),
            'same_slot_geometry':geometry,
            'image_link_opening_scope':'closed-slot absolute PNG and exact original tool image block',
            'source_quantities':'current evaluated object-local triangles and selected surface to whole Cube surface'}


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--slot',type=Path,required=True)
    cli.add_argument('--claims',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    opt=cli.parse_args()
    try:
        result=score_slot(opt.slot.resolve(strict=True),opt.claims)
    except (OSError,ValueError,KeyError,TypeError,IndexError) as exc:
        result={'slot':opt.slot.name,'quality_complete':False,'passed_items':0,'total_items':len(REQUIRED),
                'unverified_items':list(REQUIRED),'error':str(exc)}
    write(opt.output,result)
    print(json.dumps({key:result[key] for key in ('slot','quality_complete','passed_items','total_items','error')
                      if key in result}),flush=True)
    raise SystemExit(0 if result['quality_complete'] else 1)
