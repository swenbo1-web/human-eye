"""Audit both piece distances and natural entry adoption in the frozen A/B order."""
import argparse
import importlib.util
import math
from fractions import Fraction
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'m4_nearest_surface_natural_holdout_001/score.py'
spec=importlib.util.spec_from_file_location('nearest_natural_score',PREVIOUS)
previous=importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
intent=previous.intent
need,read,pin=intent.need,intent.read,intent.pin
BATCH='M1-NEAREST-SURFACE-ENTRY-DISCOVERY-001'
ORDER=('A1','B1','B2','A2')


def _topic(slot):
    return 'K' if slot[-1]=='1' else 'T'


def _same_current_region(ref,domain,target):
    state=domain['capture']['capture_state']
    return (ref['host_id']==target['object_id'] and
            ref['instance_id']==domain['instances'][target['object_id']] and
            ref['document_epoch']==domain['capture']['host_identity']['document_epoch'] and
            ref['capture_generation']=={k:state[k] for k in ('instance_id','epoch','revision')} and
            ref['ordered_geometry_sha256']==domain['geometry_sha'] and
            ref['region_id']=='source-region:'+intent.old.fingerprint({k:v for k,v in ref.items() if k!='region_id'}))


def distance_packets(folder,audited,geometry,truth,topic):
    source=read(folder/'post_capture.json')
    domain=intent.bind_geometry(source,geometry)
    scene={mesh['name']:mesh for mesh in source['meshes']}
    target=scene[truth['target_name']]
    ref=scene[truth['cases'][topic]['reference_name']]
    components=truth['target_components']
    by_role={tuple(c):i for i,c in enumerate(components)}
    measured,seen=[],{}
    for trace in intent.json_lines(folder/'wire/INDEX.jsonl'):
        if trace['method']!='tools/call':
            continue
        ordinal=trace['ordinal']
        tx=read(intent.checked_pin(trace['tx']))
        rx=read(intent.checked_pin(trace['rx']))
        if 'error' in rx or rx.get('result',{}).get('isError'):
            continue
        p=tx['params']
        bodies=list(previous._body(rx))
        if p['name']=='human_eye_scene_observe' and p['arguments'].get('query',{}).get('mode')=='source_region':
            for b in bodies:
                task=b.get('task_result',{})
                region=b.get('region_ref') or task.get('region_ref')
                fact=task.get('facts',{}).get('surface_proximity',{})
                other=task.get('reference',{})
                if not (region and fact.get('status')=='measured' and other.get('object_id')==ref['object_id']):
                    continue
                need(_same_current_region(region,domain,target) and
                     other['instance_id']==domain['instances'][ref['object_id']],
                     'piece_distance_not_from_current_ordered_objects')
                rows=region['source_triangle_indices']
                component=by_role.get(tuple(rows))
                if component is not None:
                    val=fact['value']
                    point_source=task.get('source_mapping',{}).get('nearest_witness',{})
                    measured.append({'ordinal':ordinal,'kind':'piece_surface',
                                     'component':component,'rows':rows,'distance_m':val['distance_m'],
                                     'winning_source_rows':point_source})
        elif p['name']=='read_scene':
            for b in bodies:
                actual=b.get('objects',[])
                if all(any(row.get('object_id')==m['object_id'] and row.get('vertices')==m['vertices']
                           and row.get('faces')==m['faces'] for row in actual) for m in (target,ref)):
                    seen[ordinal]={'kind':'ordinary_source_geometry','tool':'read_scene'}
        elif p['name']=='execute_python':
            text='\n'.join(str(b.get('stdout','')) for b in bodies)
            seen[ordinal]={'kind':'ordinary_calculation','tool':'execute_python','stdout':text}
    nearest=truth['cases'][topic]['nearest_source_triangle_indices']
    component=by_role[tuple(nearest)]
    for route in audited['nearest_surface_routes']:
        if route['verified_nearest']:
            measured.append({'ordinal':route['ordinal'],'kind':'global_nearest_only','component':component,
                             'rows':nearest,'distance_m':route['witness']['distance_m'],
                             'winning_source_rows':route['witness']['source_rows']})
    measured.sort(key=lambda m:m['ordinal'])
    return measured,seen


def _numbers(text):
    return [float(m) for m in re.findall(r'(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?',text)]


def _matches_value(a,b,reported=False):
    if type(a) not in (int,float) or not math.isfinite(a):
        return False
    return math.isclose(a,b,rel_tol=(1e-5 if reported else 5e-12),
                        abs_tol=(0.001 if reported else 5e-12))


def score_distances(folder,claims,truth,topic,observations,ordinary):
    final=(folder/'consumer/final.txt').read_bytes().decode('utf8')
    expected=[math.sqrt(float(Fraction(v))) for v in truth['cases'][topic]['distances_squared_m2']]
    claims=claims.get('distances',[])
    scored=[]
    for i,valid in enumerate(expected):
        matching=[p for p in claims if p.get('component')==i]
        if len(matching)!=1:
            scored.append({'component':i,'status':'missing_or_ambiguous','truth_distance_m':valid})
            continue
        q=matching[0]
        value=q.get('value_m')
        valid_report=q.get('quote') in final and _matches_value(value,valid,reported=True)
        index=q.get('ordinal')
        facts=[p for p in observations if p['component']==i and p['ordinal']==index
               and _matches_value(p['distance_m'],valid)]
        origin=facts[0]['kind'] if facts else None
        if origin is None and index in ordinary:
            ordinary_fact=ordinary[index]
            if ordinary_fact['kind']=='ordinary_calculation':
                # The unchanged final identifies the piece and its independent value.
                if any(_matches_value(x,valid,reported=True) for x in _numbers(ordinary_fact['stdout'])):
                    origin=ordinary_fact['kind']
            elif q.get('ordinary_derivation_quote') and q['ordinary_derivation_quote'] in final:
                origin=ordinary_fact['kind']
        scored.append({'component':i,'status':'passed' if valid_report and origin else 'unverified',
                       'truth_distance_m':valid,'reported_m':value,'source_ordinal':index,'kind':origin})
    return scored


def actual_payload(folder):
    counts=dict(business_tx_bytes=0,business_rx_bytes=0,text_utf8_bytes=0,native_png_bytes=0,
                native_png_blocks=0,public_zero_business_bytes=0)
    for row in intent.json_lines(folder/'wire/INDEX.jsonl'):
        if row['method']!='tools/call':
            counts['public_zero_business_bytes']+=row['tx']['bytes']+row['rx']['bytes']
            continue
        counts['business_tx_bytes']+=row['tx']['bytes']
        counts['business_rx_bytes']+=row['rx']['bytes']
        rx=read(intent.checked_pin(row['rx']))
        import base64
        for part in rx.get('result',{}).get('content',[]):
            if part['type']=='text':
                counts['text_utf8_bytes']+=len(part['text'].encode('utf8'))
            if part['type']=='image':
                counts['native_png_blocks']+=1
                counts['native_png_bytes']+=len(base64.b64decode(part['data'],validate=True))
    return counts


def compare_slot(folder,frozen,geometry,truth,slot,claims):
    topic=_topic(slot)
    result=previous.score_case(folder,frozen,geometry,truth,topic,claims)
    if result.get('status')!='observed':
        return result
    observed,ordinary=distance_packets(folder,result,geometry,truth,topic)
    distances=score_distances(folder,claims or {},truth,topic,observed,ordinary)
    piece_fields=all(d['status']=='passed' for d in distances)
    quality=result['quality_passed'] and piece_fields
    near=truth['target_components'].index(truth['cases'][topic]['nearest_source_triangle_indices'])
    repeated=dict(near=max(0,sum(p['component']==near for p in observed)-1),
                  far=max(0,sum(p['component']!=near for p in observed)-1))
    picked=[p for p in observed if p['kind']=='global_nearest_only']
    extras=[p['ordinal'] for p in observed if p['kind']=='piece_surface' and p['component']!=near
            and picked and p['ordinal']>picked[0]['ordinal']]
    image_repeats=sum(max(0,len(i['delivery_ordinals'])-1) for i in result['images'])
    result.update(image_and_intent_passed=result['quality_passed'],
                  quality_passed=quality,mechanism_passed=result['mechanism_passed'] and quality,
                  distances=distances,distance_packets=observed,duplicate_distance_searches=repeated,
                  farther_piece_measurements_after_nearest=extras,repeat_delivery_same_frame=image_repeats,
                  public_payload=actual_payload(folder))
    return result


def evaluate(root,annotations):
    frozen=read(root/'preflight/FROZEN_EXECUTION.json')
    need(frozen['batch']==BATCH and frozen['order']==list(ORDER), 'wrong_frozen_trial_order')
    files=frozen['fixture']
    geometry=read(intent.checked_pin(files['source']))
    truth=read(intent.checked_pin(files['truth']))
    need(files['blend']['sha256']==truth['asset_sha256']==geometry['asset_sha256']
         and files['source']['sha256']==truth['evaluated_source_sha256'],'unbound_new_fixture_truth')
    data={}
    for slot in ORDER:
        try:
            data[slot]=compare_slot(root/'slots'/slot,frozen,geometry,truth,slot,annotations.get(slot))
        except (KeyError,ValueError,TypeError,IndexError,OSError) as err:
            data[slot]={'status':'unverified','error':str(err)}
    counts={}
    for arm in 'AB':
        rows=[data[arm+'1'],data[arm+'2']]
        counts[arm]={'registered':2,'observed':sum(r['status']=='observed' for r in rows),
                     'unrun':sum(r['status']=='unrun' for r in rows),
                     'quality':sum(r.get('quality_passed') is True for r in rows),
                     'early':sum(r.get('route_first_nearest') is True for r in rows),
                     'adopted':sum(r.get('nearest_surface_adopted') is True for r in rows),
                     'mechanism':sum(r.get('mechanism_passed') is True for r in rows)}
    early=lambda slot:data[slot].get('route_first_nearest') is True
    gained=[i for i in '12' if early('B'+i) and not early('A'+i)]
    no_retreat=all(not early('A'+i) or early('B'+i) for i in '12')
    effect=counts['A']['observed']==2 and counts['B']['mechanism']==2 and len(gained)>0 and no_retreat
    return {'batch':BATCH,'cases':data,'counts':counts,
            'early_gained_topics':gained,'no_early_adoption_retreat':no_retreat,'entry_benefit_passed':effect}


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda v:Path(v).resolve(strict=True))
    cli.add_argument('annotations',type=Path)
    cli.add_argument('output',type=Path)
    args=cli.parse_args()
    intent.save(args.output,evaluate(args.root,read(args.annotations)))

