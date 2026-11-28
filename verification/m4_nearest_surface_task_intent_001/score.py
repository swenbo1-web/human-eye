"""Check fixed intent-arm prompts, raw paths and first-image evidence."""
import argparse
import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PREV=HERE.parent/'m1_nearest_surface_entry_discovery_001/score.py'
spec=importlib.util.spec_from_file_location('entry_score',PREV)
entry=importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
nearest=entry.previous
intent=entry.intent
need,read,pin=intent.need,intent.read,intent.pin
BATCH='M4-NEAREST-SURFACE-TASK-INTENT-001'
ORDER=('A1','B1','B2','A2')


def scoped_prompts(frozen,slot,topic):
    selected=deepcopy(frozen)
    selected['fixture']['prompts']={topic:frozen['fixture']['prompts'][slot]}
    return selected


def passes_requirements(arm,common,distances):
    return bool(common and (arm=='A' or
        len(distances)==2 and {row['component'] for row in distances}=={0,1}
        and all(row['status']=='passed' for row in distances)))


def _wire_table(folder):
    return {row['ordinal']:row for row in intent.json_lines(folder/'wire/INDEX.jsonl')
            if row['method']=='tools/call'}


def _cached_measurement(folder,at):
    path=folder/'wire'/f'{at:03d}'/'PRODUCER.json'
    if not path.is_file():
        return None
    metrics=read(path).get('work',{}).get('task_query',{})
    return metrics.get('result_cache_hit')


def _cost(folder,trace):
    reply=read(intent.checked_pin(trace['rx']))
    native=[base64.b64decode(p['data'],validate=True) for p in reply.get('result',{}).get('content',[])
            if p.get('type')=='image']
    text=sum(len(p['text'].encode('utf8')) for p in reply.get('result',{}).get('content',[]) if p.get('type')=='text')
    return {'ordinal':trace['ordinal'],'business':trace['business'],'new_rasters':trace['rasters'],
            'round_trip_ns':trace['returned_ns']-trace['started_ns'],
            'tx_bytes':trace['tx']['bytes'],'rx_bytes':trace['rx']['bytes'],'text_bytes':text,
            'native_png_bytes':sum(map(len,native)),'native_png_blocks':len(native),
            'hot_measurement_reply':_cached_measurement(folder,trace['ordinal'])}


def _source_winning_region(piece):
    value=piece.get('winning_source_rows')
    if type(value) is dict:
        a=value.get('a',{})
        return a.get('source_triangle_indices')
    return value[:1] if isinstance(value,list) else None


def _confirmed_nearest_availability(values,near,expected_components):
    first={}
    for value in values:
        if value['kind']=='global_nearest_only':
            return {'ordinal':value['ordinal'],'basis':'product_global_witness','distance_m':value['distance_m'],
                    'source_rows':_source_winning_region(value)}
        first.setdefault(value['component'],value)
        if set(first)==expected_components:
            n=first[near]
            return {'ordinal':value['ordinal'],'basis':'compare_two_measured_components',
                    'distance_m':n['distance_m'],'source_rows':_source_winning_region(n)}
    return None


def _breakdown(folder,base,values,truth,topic):
    table=_wire_table(folder)
    near=truth['target_components'].index(truth['cases'][topic]['nearest_source_triangle_indices'])
    far=next((p for p in values if p['component']!=near),None)
    expected=set(range(len(truth['target_components'])))
    consumed={}
    repeated=[]
    for value in values:
        component=value['component']
        if component in consumed:
            repeated.append({'component':component,'kind':value['kind'],**_cost(folder,table[value['ordinal']])})
        else:
            consumed[component]=value['ordinal']
    location=base['first_geometry_localization']
    first_business=next(iter(table),None)
    used=[q for q in base['nearest_surface_routes'] if q['verified_nearest']]
    return {'first_business':first_business,'first_localization':location,
            'first_localization_cost':_cost(folder,table[location['ordinal']]) if location else None,
            'proof_of_global_nearest':_confirmed_nearest_availability(values,near,expected),
            'first_far_piece_measurement': None if far is None else {
                'component':far['component'],'kind':far['kind'],'source_rows':far['rows'],
                **_cost(folder,table[far['ordinal']])},
            'repeated_measured_fact_deliveries':repeated,
            'repeat_image_delivery_count':sum(len(image['delivery_ordinals'])-1
                                              for image in base['images'] if image['delivery_ordinals']),
            'additional_rasters_after_first':max(0,base['actual_rasters']-1),
            'early_nearest_accepted':any(q['before_geometry_localization'] for q in used),
            'only_late_nearest_accepted':bool(used and not any(q['before_geometry_localization'] for q in used)),
            'whole_business_by_request':[_cost(folder,row) for row in table.values()]}


def slot_score(folder,frozen,geometry,truth,slot,claim):
    topic='K' if slot.endswith('1') else 'T'
    initial=nearest.score_case(folder,scoped_prompts(frozen,slot,topic),geometry,truth,topic,claim)
    if initial['status']!='observed':
        return initial
    readings,ordinary=entry.distance_packets(folder,initial,geometry,truth,topic)
    distances=entry.score_distances(folder,claim or {},truth,topic,readings,ordinary)
    physical=initial['first_actual_raster']
    first_visible=bool(physical and physical['true_piece_visible'])
    common=bool(initial['quality_passed'] and first_visible and initial['same_first_frame_in_final'])
    qualified=passes_requirements(slot[0],common,distances)
    attributable=_breakdown(folder,initial,readings,truth,topic)
    return {**initial,'single_image_common_quality':common,'quality_passed':qualified,
            'mechanism_passed':bool(initial['mechanism_passed'] and qualified),
            'late_nearest_adoption':attributable['only_late_nearest_accepted'],
            'first_physical_true_piece_visible':first_visible,'piece_gap_reports':distances,
            'voluntary_A_gap_count':sum(q['status']=='passed' for q in distances) if slot.startswith('A') else None,
            'distance_packets':readings,'attribution':attributable,'payload':entry.actual_payload(folder)}


def evaluate(root,annotations):
    frozen=read(root/'preflight/FROZEN_EXECUTION.json')
    need(frozen['batch']==BATCH and frozen['order']==list(ORDER),'wrong-frozen-intent-batch')
    fixture=frozen['fixture']
    geom=read(intent.checked_pin(fixture['source']))
    truth=read(intent.checked_pin(fixture['truth']))
    need(geom['asset_sha256']==truth['asset_sha256']==fixture['blend']['sha256']
         and truth['evaluated_source_sha256']==fixture['source']['sha256'],'current-truth-not-frozen')
    out={}
    for slot in ORDER:
        try:
            out[slot]=slot_score(root/'slots'/slot,frozen,geom,truth,slot,annotations.get(slot))
        except (ValueError,KeyError,IndexError,TypeError,OSError) as error:
            out[slot]={'status':'unverified','reason':str(error)}
    counts={}
    for arm in 'AB':
        rows=[out[arm+'1'],out[arm+'2']]
        counts[arm]={'registered':2,'observed':sum(x['status']=='observed' for x in rows),
                     'unrun':sum(x['status']=='unrun' for x in rows)}
        for label,key in [('quality','quality_passed'),('early','route_first_nearest'),('late','late_nearest_adoption'),
                          ('any','nearest_surface_adopted'),('mechanism','mechanism_passed'),
                          ('first_physical_correct','first_physical_true_piece_visible'),('final_is_first','same_first_frame_in_final')]:
            counts[arm][label]=sum(x.get(key) is True for x in rows)
    favor=[i for i in '12' if out['A'+i].get('route_first_nearest') and not out['B'+i].get('route_first_nearest')]
    reverse=[i for i in '12' if out['B'+i].get('route_first_nearest') and not out['A'+i].get('route_first_nearest')]
    effect=all(v['observed']==2 for v in counts.values()) and counts['A']['mechanism']==2 and bool(favor)
    return {'batch':BATCH,'cases':out,'counts':counts,
            'A_only_early_topics':favor,'B_only_early_topics':reverse,'task_intent_mechanism_supported':effect}


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda p:Path(p).resolve(strict=True))
    cli.add_argument('annotations',type=Path)
    cli.add_argument('output',type=Path)
    args=cli.parse_args()
    intent.save(args.output,evaluate(args.root,read(args.annotations)))

