"""Score the natural holdout from original public events and same-slot geometry and frames."""
import argparse
import importlib.util
from hashlib import sha256
import json
import math
from pathlib import Path


HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'m4_nearest_surface_first_focus_001/score.py'
spec=importlib.util.spec_from_file_location('engineering_score',PREVIOUS)
engineering=importlib.util.module_from_spec(spec)
spec.loader.exec_module(engineering)
intent=engineering.intent
need,read,pin=intent.need,intent.read,intent.pin
BATCH='M4-NEAREST-SURFACE-NATURAL-HOLDOUT-001'
LABELS=('K','T')
THRESHOLD=16


def _frame_rows(folder,row):
    frame=Path(row['image_path'])
    arrays=Path(row['arrays_path'])
    for path in (frame,arrays):
        need(path.is_absolute() and path.resolve(strict=True) == path and path.is_relative_to(folder)
             and not path.is_symlink(), 'frame_not_from_own_current_slot')
    return frame,arrays


def _valid_review(final,claim,truth,by_path,folder,capture,target):
    need(isinstance(claim,dict) and claim.get('final_sha256')==sha256(final.encode('utf8')).hexdigest()
         and all(type(claim.get(k)) is bool for k in ('understood_target_reference','selected_correct_piece',
                                                     'qualifies_frame_scope'))
         and all(isinstance(q,str) and q and q in final for q in claim['quotations']),
         'manual_checks_not_bound_to_original_final')
    result={k:claim[k] for k in ('understood_target_reference','selected_correct_piece','qualifies_frame_scope')}
    raw=intent.json_lines(folder/'frames.jsonl') if (folder/'frames.jsonl').is_file() else []
    reference_links={}
    for frame in raw:
        path,_=_frame_rows(folder,frame)
        if path in by_path:
            ref=frame['image_ref']
            previous=reference_links.setdefault(ref,path)
            need(previous==path,'same_reference_had_multiple_frames')
    legitimate={p for p in intent.markdown_paths(final) if p in by_path}
    bare_or_ref=replacements_in_final(final,by_path,reference_links)
    legitimate.update(bare_or_ref)
    result.update(original_png_link=bool(legitimate),same_frame_pixel_in_nearest_piece=False,
                  has_16_nearest_pixels=False,
                  linked_original_paths=[p.relative_to(folder).as_posix() for p in sorted(legitimate)])
    claim_pixel=claim.get('pixel')
    if claim_pixel is None:
        return result
    try:
        if 'image_ref' in claim_pixel:
            need(claim_pixel['image_ref'] in reference_links,'claimed_ref_not_delivered')
            path=reference_links[claim_pixel['image_ref']]
        else:
            path=intent.file_in_slot(folder,claim_pixel['image_path'],'.png')
        need(path in legitimate,'claimed_pixel_frame_not_referenced_in_original_answer')
        frame=by_path[path]
        pixel=intent.prove_pixel(frame['arrays'],capture,target,claim_pixel['row'],claim_pixel['column'])
        pixel['reported_source_triangle_index']=claim_pixel['source_triangle_index']
        result['same_frame_pixel_in_nearest_piece']=(pixel['source_triangle_index']==claim_pixel['source_triangle_index']
            and pixel['source_triangle_index'] in truth['nearest_source_triangle_indices'])
        result.update(pixel=pixel,image_path=path.relative_to(folder).as_posix(),frame_request=frame['ordinal'],
                      image_sha256=frame['image_sha256'],
                      has_16_nearest_pixels=frame['pixels_of_nearest_piece']>=THRESHOLD,
                      nearest_pixels=frame['pixels_of_nearest_piece'])
    except (ValueError,KeyError,TypeError,OSError) as error:
        result['pixel_proof_error']=str(error)
    return result


def replacements_in_final(final,by_path,refs):
    import re
    result=set()
    for path in by_path:
        spellings=(str(path),path.as_posix(),'/'+path.as_posix())
        if any(re.search(r'(?<![\w/\\])'+re.escape(p)+r'(?![\w/\\.-])',final) for p in spellings):
            result.add(path)
    for ref,p in refs.items():
        if re.search(r'(?<![\w:])'+re.escape(ref)+r'(?![\w:])',final):
            result.add(p)
    return result


def _body(response):
    for part in response.get('result',{}).get('content',[]):
        if part.get('type')=='text':
            try:
                yield json.loads(part['text'])
            except (ValueError,TypeError):
                continue


def _selector_matches(selector, target):
    return selector == {'name':target['name']} or selector == {'id':target['object_id']}


def _localizes(tool,params):
    if tool in ('read_scene','execute_python','render_view'):
        return True
    if tool!='human_eye_scene_observe':
        return False
    query=params.get('query',{})
    return query.get('mode') not in (None,'directory')


def _route(folder,audited,capture,geometry,truth,topic):
    case=truth['cases'][topic]
    meshes={m['name']:m for m in capture['meshes']}
    current_domain=intent.bind_geometry(capture,geometry)
    events=intent.public_cli(folder/'consumer/stdout.raw.bin')
    app=[(e['item']['tool'],e['item']['arguments']) for e in events
         if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
    calls=[]
    for entry in intent.json_lines(folder/'wire/INDEX.jsonl'):
        if entry['method']!='tools/call':
            continue
        path=folder/'wire'/f"{entry['ordinal']:03d}"
        tx,rx=read(path/'TX.bin'),read(path/'RX.bin')
        params=tx['params']
        calls.append((entry['ordinal'],params['name'],params['arguments'],rx,path))
    key=lambda pair:json.dumps(pair,ensure_ascii=False,sort_keys=True)
    need(sorted(map(key,app))==sorted(key((tool,args)) for _,tool,args,_,_ in calls),
         'public_CLI_events_do_not_match_received_tool_replies')
    selected=[]
    preceding=[]
    details=[]
    first_geometry=None
    for ordinal,tool,args,rx,path in calls:
        query=args.get('query',{})
        focus=query.get('focus',{})
        region=focus.get('task_region') if isinstance(focus,dict) else None
        nearest=(tool=='human_eye_scene_observe' and query.get('mode')=='active_observation'
                 and isinstance(region,dict) and region.get('relation')=='nearest_surface')
        exact_target=False
        if nearest:
            selectors=query.get('objects',[])
            exact_target=(len(selectors)==1 and _selector_matches(selectors[0],meshes[truth['target_name']])
                          and _selector_matches(region.get('reference'),meshes[case['reference_name']]))
            accepted=False
            witness=None
            if exact_target and (path/'PRODUCER.json').is_file() and not rx.get('result',{}).get('isError'):
                producer=read(path/'PRODUCER.json')
                f=producer.get('facts',{}).get('focus')
                if f and f['selection']==focus and f.get('nearest_surface',{}).get('status')=='measured':
                    current=capture['capture_state']
                    ref=f['region_ref']
                    binding=producer['binding']
                    objects=(f['object'],f['reference'])
                    need(tuple(o['object_name'] for o in objects)==(truth['target_name'],case['reference_name'])
                         and all(m['object_id']==o['host_id']
                             and current_domain['instances'][o['host_id']]==o['instance_id']
                             and 0<=o['object_index']<len(capture['meshes'])
                             and capture['meshes'][o['object_index']]['object_id']==o['host_id']
                             for o,m in zip(objects,(meshes[truth['target_name']],meshes[case['reference_name']]),strict=True))
                         and binding['capture_state']==current and binding['display_identity']==current_domain['display_sha']
                         and ref['ordered_geometry_sha256']==current_domain['geometry_sha']
                         and ref['capture_generation']=={k:current[k] for k in ('instance_id','epoch','revision')},
                         'nearest_focus_not_same_capture')
                    for body in _body(rx):
                        if (body.get('facts',{}).get('focus')==f or body.get('facts',{}).get('focus',{}).get(
                            'nearest_surface')==f['nearest_surface']):
                            accepted=True
                            break
                    if accepted:
                        witness=engineering.verify_exact_witness(f,current_domain,case)
            selected.append({'ordinal':ordinal,'right_objects':exact_target,'verified_nearest':accepted,
                             'sent_with_image':args.get('include_image',True),'before_geometry_localization':first_geometry is None,
                             'preceding_localization_ordinals':list(preceding),'witness':witness})
        localization=_localizes(tool,args)
        if localization and first_geometry is None:
            first_geometry={'ordinal':ordinal,'tool':tool,'query_mode':query.get('mode')}
        if localization and not nearest:
            preceding.append(ordinal)
        details.append(dict(ordinal=ordinal,tool=tool,query_mode=query.get('mode'),
                            is_error=bool(rx.get('error') or rx.get('result',{}).get('isError')),
                            nearest_requested=bool(nearest),right_objects=exact_target))
    return selected,first_geometry,details


def _physical_and_final(folder,audited,nearest):
    closed=read(folder/'closed.json')
    rasters=closed['transport']['rasters']
    built=intent.json_lines(folder/'physical_frames.jsonl') if (folder/'physical_frames.jsonl').is_file() else []
    need(len(rasters)==len(built)<=4 and all(i==x['construction_index'] and all(x[k]==y[k] for k in y)
         for i,(x,y) in enumerate(zip(built,rasters,strict=True),1)), 'physical_frame_meter_has_missing_attempts')
    rows=intent.json_lines(folder/'frames.jsonl') if (folder/'frames.jsonl').is_file() else []
    physical=None
    if rasters:
        first=min(built,key=lambda row:row['started_ns'])
        chosen=None
        if first['complete'] and first['frame_status']=='bound':
            frame=first['frame']
            png,arrays=(intent.checked_pin(frame[k]) for k in ('image','arrays'))
            recorded=[r for r in rows if r['frame_identity']==frame['frame_identity']
                      and r['image_ref']==frame['image_ref'] and r['request_ordinal']==first['ordinal']
                      and _frame_rows(folder,r)==(png,arrays)]
            same=[i for i in audited['images'] if i['ordinal']==first['ordinal']
                  and i['png']==png.relative_to(folder).as_posix() and i['npz']==arrays.relative_to(folder).as_posix()]
            need(bool(recorded) and len(same)==1,'first_actual_raster_has_no_same_slot_ownership')
            chosen=same[0]
        physical={'ordinal':first['ordinal'],'completed':bool(first['complete']),
                  'origin':first['origin'],'frame':chosen,
                  'true_piece_visible':bool(chosen and chosen['pixels_of_nearest_piece']>=THRESHOLD)}
    delivered=[(at,v) for v in audited['images'] for at in v['delivery_ordinals']]
    first_delivered=min(delivered,key=lambda row:row[0])[1] if delivered else None
    final=audited['answer'].get('image_path')
    matching=bool(physical and physical['frame'] and physical['frame']['png']==final)
    qualifies=[q for q in nearest if q['verified_nearest'] and q['before_geometry_localization']]
    direct=bool(qualifies and physical and physical['ordinal']==qualifies[0]['ordinal']
              and physical['origin']=='product')
    return {'first_actual_raster':physical,'first_actual_delivery':first_delivered,
            'same_first_frame_in_final':matching,'route_first_nearest':bool(qualifies),
            'first_raster_from_first_nearest':direct}



def _verify_close(folder):
    final=read(folder/'consumer/RESULT.json')
    closed=read(folder/'closed.json')
    owner=read(folder/'TRANSPORT_OWNER.json')
    delivery=final['delivery']
    need(closed['zero_geometry_preread'] is True and closed['safe_to_continue'] is True
         and closed['transport']==owner and owner['closed'] and owner['zero_in_flight']
         and isinstance(owner['Thin_process']['exit_code'],int) and owner['owner_thread_closed']
         and closed['cli_exit']==closed['blender_exit']==0
         and closed['worker_custody']['passed'] is True
         and intent.checked_pin(closed['initial_capture'])==folder/'initial_capture.json'
         and delivery['passed'] is True and delivery['zero_outstanding_cli']
         and intent.checked_pin(delivery['owner_close'])==folder/'TRANSPORT_OWNER.json',
         'unverified_formal_owner_or_last_delivery')
    left,right=(intent.json_lines(folder/name) for name in ('TRANSPORT_OWNER.jsonl','TRANSPORT_THIN.jsonl'))
    wire=intent.json_lines(folder/'wire/INDEX.jsonl')
    need(len(left)==len(right)==len(wire)==owner['paired_exchanges']==owner['requests'],
         'transport_indices_or_pair_count_differ')
    accepted=[]
    for entry,l,r in zip(wire,left,right,strict=True):
        msg=l['request']
        need(msg==r['request'] and msg['ordinal']==entry['ordinal']
             and msg['request_sha256']==entry['tx']['sha256'] and msg['response_sha256']==entry['rx']['sha256']
             and l['offer']==r['offer'] and l['ack']==r['ack'] and l['offer']['in_flight']==0
             and l['peer_eof'] and r['peer_eof'] and l['owner_eof_sent'] and r['thin_eof_sent'],
             'unpaired_or_unbound_owned_Thin_shutdown')
        if entry['method']=='tools/call':
            accepted.append(entry)
    need(len(accepted)==delivery['paired_public_calls']
         and delivery['actual_tools'][-1]==delivery['last_cli_delivery']
         and pair_last(delivery['last_cli_delivery'],accepted[-1])
         and all(pair_last(d,e) for d,e in zip(delivery['actual_tools'],accepted,strict=True)),
         'formal_last_or_intermediate_result_did_not_reach_real_CLI')
    return {'pairs':len(wire),'business_pair_closures':len(accepted),
            'thin_exit_code':owner['Thin_process']['exit_code'],'thin_termination':owner['Thin_termination'],
            'last_received':delivery['last_cli_delivery']['ordinal'],'safe':True}


def pair_last(d,e):
    return d['ordinal']==e['ordinal'] and d['rx']==e['rx'] and d['tool']==e['tool']


def score_case(folder,frozen,geometry,truth,topic,claim):
    if not (folder/'consumer/stdout.raw.bin').is_file():
        return {'status':'unrun'}
    verify=intent.verify_review
    intent.verify_review=_valid_review
    try:
        audited=intent.natural_case(folder,frozen,geometry,truth,topic,claim)
    finally:
        intent.verify_review=verify
    if audited['status']!='observed':
        return audited
    capture=read(folder/'post_capture.json')
    close=_verify_close(folder)
    selected,first_geometry,details=_route(folder,audited,capture,geometry,truth,topic)
    steps=_physical_and_final(folder,audited,selected)
    quality=audited['evidence_pass'] and audited['answer'].get('has_16_nearest_pixels',False)
    interop=bool(steps['route_first_nearest'] and steps['first_raster_from_first_nearest']
                 and steps['first_actual_raster']['true_piece_visible'] and steps['same_first_frame_in_final'] and quality)
    return {**audited,'strict_closure':close,'quality_passed':bool(quality),'nearest_surface_requested':len(selected),
            'nearest_surface_adopted':any(k['verified_nearest'] for k in selected),
            'nearest_surface_routes':selected,'first_geometry_localization':first_geometry,
            'tool_routes':details,'mechanism_passed':interop,**steps}


def evaluate(root,claims):
    frozen=read(root/'preflight/FROZEN_EXECUTION.json')
    need(frozen['batch']==BATCH,'audit_wrong_batch')
    fixture=frozen['fixture']
    geometry=read(intent.checked_pin(fixture['source']))
    truth=read(intent.checked_pin(fixture['truth']))
    need(fixture['blend']['sha256']==truth['asset_sha256']==geometry['asset_sha256']
         and truth['evaluated_source_sha256']==fixture['source']['sha256'],'audit_truth_not_frozen')
    out={}
    for topic in LABELS:
        try:
            out[topic]=score_case(root/'slots'/f'NATURAL_{topic}',frozen,geometry,truth,topic,claims.get(topic))
        except (ValueError,KeyError,IndexError,TypeError,OSError) as error:
            out[topic]={'status':'unverified','reason':str(error)}
    return {'batch':BATCH,'cases':out,'registered':2,
            'observed':sum(r['status']=='observed' for r in out.values()),
            'unrun':sum(r['status']=='unrun' for r in out.values()),
            'quality':sum(r.get('quality_passed') is True for r in out.values()),
            'natural_adoption':sum(r.get('nearest_surface_adopted') is True for r in out.values()),
            'early_natural_adoption':sum(r.get('route_first_nearest') is True for r in out.values()),
            'full_mechanism':sum(r.get('mechanism_passed') is True for r in out.values()),
            'passed':all(r.get('mechanism_passed') is True for r in out.values())}


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root',type=lambda value:Path(value).resolve(strict=True))
    cli.add_argument('annotations',type=Path)
    cli.add_argument('output',type=Path)
    args=cli.parse_args()
    intent.save(args.output,evaluate(args.root,read(args.annotations)))

