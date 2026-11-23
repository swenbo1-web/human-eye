"""Grade original assembly answers against frozen geometry and same-slot PNGs."""

import argparse
from fractions import Fraction
from math import dist, isfinite, sqrt
from pathlib import Path
import re
from runpy import run_path
from types import SimpleNamespace
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
OPPOSITE_PATH = V/'m4_yanyite_opposite_direction_product_native_001/score.py'
OPPOSITE = SimpleNamespace(**run_path(str(OPPOSITE_PATH)))
FOOT, LOW, OLD, ORACLE = (getattr(OPPOSITE,k) for k in ('FOOT','LOW','OLD','ORACLE'))
QUALIFY = FOOT.QUALIFY
load, pin, require, write = LOW.load, LOW.pin, LOW.require, LOW.write
ROOT = Path('D:/he_m4_assembly_cross_asset_product_native_001')
HISTORY = Path('D:/he_m4_cross_scale_assembly_transfer_001')
HISTORY_INDEX = V/'m4_cross_scale_assembly_transfer_001/RUNTIME_INDEX.json'
TERMINAL_MEMBER = 'slots/P1/TERMINAL_SOURCE.json'
TERMINAL_SHA = 'd0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90'
ASSET_MEMBER = 'slots/P1/native/input.blend'
ASSET = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
PRODUCT_SOURCE = 'eb6590279920f3c9c4ca07330c0636d6d9bd99860bbed02abaa6e0976321381e'
PRODUCT_SOURCES = {'N1':None,'P1':PRODUCT_SOURCE}
THRESHOLD = Fraction(7,20)
BOXES = {'N19':((.449,.135,.690),(.490,.174,.751)),
         'N25':((-.131,-.291,.295),(.011,-.250,.373))}
REFERENCES = {'N19':'N14','N25':'N07','N12':'N07'}
CONTROL_BOX = ((-.512,.065,.619),(0,.154,.671))
EXPECTED = {'N19':(list(range(10,20)),.044500013813),
            'N25':(list(range(8)),.414366994068),
            'N12':([0,1,8,9,16,17,24,25],.328100589892)}
REQUIRED = tuple(f'{region}.{item}' for region in BOXES for item in OLD.REGIONAL_ITEMS)+('nearer',)
SCENE_FIELDS = ('display_object_mask','source_face_offsets','layer_collections','scene_cameras')
TOLERANCE = 1e-6


def extrema(points):
    return [(min(axis),max(axis)) for axis in zip(*points,strict=True)]


def on_exact_surface(point,vertices,triangles):
    return [index for index,face in triangles
            if ORACLE.triangle_contains(point,[vertices[v] for v in face])]


def attaining_pair(source,selected,target,reference,gap):
    # A separating-box gap is a lower bound. Project each extremal vertex
    # in both directions, then certify both endpoints on the original faces.
    indices = sorted({v for _,face in selected for v in face})
    for from_source, vertices in ((True,[source[i] for i in indices]),(False,target)):
        for vertex in vertices:
            delta = gap if from_source else tuple(-x for x in gap)
            projected = tuple(a+b for a,b in zip(vertex,delta,strict=True))
            a,b = (vertex,projected) if from_source else (projected,vertex)
            source_rows = on_exact_surface(a,source,selected)
            target_rows = on_exact_surface(b,target,reference) if source_rows else []
            if target_rows:
                return a,b,source_rows,target_rows
    raise ValueError('independent_box_lower_bound_not_attained_by_both_surfaces')


def region_truth(source,target,box,name):
    va = [tuple(map(Fraction,p)) for p in source['vertices_world_m']]
    vb = [tuple(map(Fraction,p)) for p in target['vertices_world_m']]
    lo,hi = (tuple(map(Fraction,p)) for p in box)
    inside = [all(a<=x<=b for a,x,b in zip(lo,point,hi,strict=True)) for point in va]
    selected = [(i,face) for i,face in enumerate(source['triangles']) if all(inside[v] for v in face)]
    rows = [i for i,_ in selected]
    vertices = sorted({v for _,face in selected for v in face})
    require(rows==EXPECTED[name][0], 'frozen_world_box_source_rows_changed/'+name)
    interval_a,interval_b = extrema([va[i] for i in vertices]),extrema(vb)
    gap = tuple(c-b if b<c else d-a if d<a else Fraction(0)
                for (a,b),(c,d) in zip(interval_a,interval_b,strict=True))
    distance2 = sum(d*d for d in gap)
    distance = sqrt(distance2)
    require(abs(distance-EXPECTED[name][1])<5e-10, 'frozen_disjoint_box_gap_changed/'+name)
    reference = list(enumerate(target['triangles']))
    a,b,arows,brows = attaining_pair(va,selected,vb,reference,gap)
    return {'reference_name':REFERENCES[name],'world_box_m':{'min':list(box[0]),'max':list(box[1])},
            'triangle_ids':rows,'vertex_ids':vertices,'triangle_count':len(rows),'vertex_count':len(vertices),
            'distance_m':distance,'distance_squared_exact':[distance2.numerator,distance2.denominator],
            'direction_world':[float(d)/distance for d in gap],'at_least_0_35_m':distance2>=THRESHOLD*THRESHOLD,
            'box_gap_exact':[[d.numerator,d.denominator] for d in gap],
            'source_point_world_m':list(map(float,a)),'reference_point_world_m':list(map(float,b)),
            'source_witness_triangle_ids':arows,'reference_witness_triangle_ids':brows,
            'source_triangles_world_m':[[source['vertices_world_m'][v] for v in face] for _,face in selected],
            'reference_triangles_world_m':[[target['vertices_world_m'][v] for v in face] for _,face in reference]}


def scene_truth(terminal):
    context = terminal['source']
    require(context['asset_sha256']==ASSET and context['kind']=='actual_owned_Blender_evaluated_mesh'
            and context['scale_length']==1 and context['source_index_domain']==ORACLE.INDEX_DOMAIN,
            'unexpected_assembly_asset_or_source_domain')
    objects = terminal['objects']
    roster = {o['name']:o['evaluated'] for o in objects}
    offsets = [0]
    for o in objects:
        offsets.append(offsets[-1]+len(o['evaluated']['triangles']))
    require(len(objects)==len(roster)==28 and offsets[-1]==744 and offsets==terminal['source_face_offsets']
            and sum(len(o['vertices_world_m']) for o in roster.values())==416
            and [o['visible_get'] for o in objects]==terminal['display_object_mask'],
            'assembly_ordered_mesh_counts_or_display_changed')
    rows = {name:region_truth(roster[name],roster[REFERENCES[name]],box,name)
            for name,box in (*BOXES.items(),('N12',CONTROL_BOX))}
    control = rows.pop('N12')
    require(not rows['N19']['at_least_0_35_m'] and rows['N25']['at_least_0_35_m']
            and rows['N19']['distance_m']<rows['N25']['distance_m'],'assembly_threshold_or_order_changed')
    return {'source':context,'meshes':[{k:o[k] for k in ('name','object_id','instance_id','visible_get')}
                                      for o in objects],
            'source_face_offsets':offsets,'regions':rows,'offline_control':control,'nearer':'N19'}


def historical_truth():
    index = load(HISTORY_INDEX)
    bundle = HISTORY/'ORIGINAL_RUNTIME.zip'
    require(pin(bundle)==index['archive'] and len(index['files'])==index['count']==789,
            'frozen_assembly_archive_identity_changed')
    members = {r['path']:r for r in index['files']}
    sources = []
    with ZipFile(bundle) as zipped:
        for member,sha in ((ASSET_MEMBER,ASSET),(TERMINAL_MEMBER,TERMINAL_SHA)):
            path = HISTORY/member
            receipt = pin(path)
            require(receipt['sha256']==members[member]['sha256']==sha
                    and receipt['bytes']==members[member]['bytes'] and path.read_bytes()==zipped.read(member),
                    'frozen_assembly_member_changed/'+member)
            sources.append(receipt)
    terminal = load(HISTORY/TERMINAL_MEMBER)
    truth = scene_truth(terminal)
    pins = [*sources,pin(bundle),pin(HISTORY_INDEX),pin(Path(__file__)),pin(OPPOSITE_PATH),
            pin(Path(FOOT.__file__)),pin(Path(LOW.__file__)),pin(Path(OLD.__file__)),
            pin(Path(ORACLE.__file__)),pin(Path(QUALIFY.__file__))]
    proof = {**truth,'source':sources[1],'asset':sources[0],'asset_sha256':ASSET,'passed':True,
             'threshold_m':float(THRESHOLD),'coordinate_frame':'world','unit':'m',
             'actual_Blender_starts':0,'actual_models':0,'source_pins':pins}
    return terminal,proof


def checked_scene(terminal,historical,expected=None):
    environment = ('asset_sha256','kind','source_index_domain','frame','subframe','scale_length',
                   'scene','view_layer','unit_settings')
    require(all(terminal['source'][k]==historical['source'][k] for k in environment),
            'slot_world_scene_context_changed')
    require(all(terminal[k]==historical[k] for k in SCENE_FIELDS),'slot_geometry_order_or_display_changed')
    for a,b in zip(terminal['objects'],historical['objects'],strict=True):
        require(a.keys()==b.keys() and all(a[k]==b[k] for k in a if k!='instance_id'),
                'slot_world_geometry_transform_or_source_measurement_changed/'+a['name'])
    current = scene_truth(terminal)
    require(expected is None or current['regions']==expected['regions'],'slot_selection_differs_from_frozen_truth')
    return current


verify_closed_source = OLD.with_replacements(ORACLE.verify_closed_source,
                                            verify_terminal=checked_scene,ASSET=ASSET)


def near_surface(point,triangles,tolerance):
    np = QUALIFY.np
    p = np.asarray(point,dtype=float)
    for face in triangles:
        vertices = np.asarray(face,dtype=float)
        a,b,c = vertices
        edges = (vertices[1:]-a).T
        parameters,_,rank,_ = np.linalg.lstsq(edges,p-a,rcond=None)
        if (rank==2 and min(parameters)>=0 and sum(parameters)<=1
                and np.linalg.norm(p-a-edges@parameters)<=tolerance):
            return True
        for v,w in ((a,b),(b,c),(c,a)):
            edge = w-v
            relative = p-v
            norm2 = float(edge@edge)
            weight = min(1,max(0,float(relative@edge)/norm2)) if norm2 else 0
            if np.linalg.norm(relative-weight*edge)<=tolerance:
                return True
    return False


def numeric_pair(distance,direction,a,b,truth,tolerance=TOLERANCE):
    require(type(distance) in (int,float) and abs(distance-truth['distance_m'])<=tolerance
            and QUALIFY.near_point(direction,truth['direction_world'],tolerance)
            and all(isinstance(p,(list,tuple)) and len(p)==3
                    and all(type(v) in (int,float) and isfinite(v) for v in p) for p in (a,b)),
            'incorrect_current_distance_direction_or_point_shape')
    require(abs(dist(a,b)-truth['distance_m'])<=tolerance
            and QUALIFY.near_point([v-u for u,v in zip(a,b,strict=True)],
                                   [float(Fraction(n,d)) for n,d in truth['box_gap_exact']],tolerance)
            and near_surface(a,truth['source_triangles_world_m'],tolerance)
            and near_surface(b,truth['reference_triangles_world_m'],tolerance),
            'points_not_an_attaining_pair_on_current_requested_surfaces')


def ordered_geometry(terminal):
    return QUALIFY.canonical_sha([{'host_id':o['object_id'],'instance_id':o['instance_id'],
                                  'vertices':o['evaluated']['vertices_world_m'],'faces':o['evaluated']['triangles']}
                                 for o in terminal['objects']])


def frame_source_binding(frame,slot,terminal,device,truth,region):
    usual = OLD.with_replacements(QUALIFY.source_binding,TARGET=region,REFERENCE=REFERENCES[region])
    if frame['origin']!='product':
        return usual(frame,slot,terminal,device,truth)
    entry = frame['full_result']
    report = QUALIFY.receipt(slot,entry['path'],entry['sha256'])
    producer = load(report['path'])
    if producer['result_kind']=='source_region':
        return usual(frame,slot,terminal,device,truth)
    # Alternate product routes qualify if the actual frame is local, its
    # scope binds the same scene, and its saved pixels pass the same test.
    matches = [r for r in producer['frames'] if r['image_ref']==frame['ref']]
    scopes = [r for r in producer.get('scopes',()) if r['scope_id']==frame['scope_id']]
    require(producer['result_kind']=='active_observation' and producer['read_only'] is True
            and producer['execution_authority'] is False and matches==[frame['producer']] and len(scopes)==1,
            'alternate_product_frame_not_current_local_producer')
    scope = scopes[0]
    parent,local = producer['binding'],scope['binding']
    region_source = scope['scope']['source']
    target, = (o for o in terminal['objects'] if o['name']==region)
    evaluated = target['evaluated']
    mesh_digest = QUALIFY.canonical_sha({'vertices':evaluated['vertices_world_m'],'faces':evaluated['triangles']})
    require(scope['scope']['kind']=='same_capture_region' and frame['frame_identity'] in scope['frame_refs']
            and frame['producer']['frame_identity']==frame['frame_identity']
            and frame['producer']['image_sha256']==frame['PNG_sha256']
            and frame['producer']['arrays_sha256']==frame['NPZ_sha256']
            and frame['producer']['host_binding_sha256']==local['binding_sha256']
            and region_source['parent_binding_sha256']==parent['binding_sha256']
            and region_source['ordered_geometry_sha256']==mesh_digest
            and (region_source['host_id'],region_source['instance_id'])==(target['object_id'],target['instance_id']),
            'alternate_product_frame_not_current_bound_region')
    return {'scope_id':scope['scope_id'],'original_source':report}


def public_frame_binding(call,image,index):
    if call['name']=='read_images':
        return True
    packet = LOW.product_packet(call)
    if packet is not None:
        return LOW.matching_public_image(packet,image,index) is not None
    if call['name']!='human_eye_scene_observe':
        return False
    try:
        packet = load_public_active_observation(call)
        images = packet.get('images')
        if isinstance(images,dict):
            rows = [dict(zip(images['columns'],row,strict=True)) for row in images['rows']]
            return any(r.get('image_ref')==image['ref'] and r.get('image_sha256')==image['PNG']['sha256']
                       and r.get('native_content_block_index')==index for r in rows)
        frames = packet.get('frames')
        if isinstance(frames,dict):
            rows = [dict(zip(frames['columns'],row,strict=True)) for row in frames['rows']]
            return any(r.get('image_ref')==image['ref'] and r.get('image_sha256')==image['PNG']['sha256']
                       and r.get('frame_identity')==image['frame_identity']
                       and r.get('native_content_block_index')==index for r in rows)
        row = frames[index-1]
        return (row.get('image_ref')==image['ref'] and row.get('image_sha256')==image['PNG']['sha256']
                and row.get('frame_identity')==image['frame_identity'])
    except (KeyError,TypeError,ValueError,IndexError):
        return False


def load_public_active_observation(call):
    import json

    for text in call['text']:
        try:
            packet = json.loads(text)
        except ValueError:
            continue
        if isinstance(packet,dict) and packet.get('result_kind')=='active_observation':
            return packet
    raise ValueError('alternate_active_observation_packet_missing')


def qualify_frames(slot,terminal,device,geometry,cli_calls,calls):
    candidates, errors = {region:[] for region in BOXES},[]
    by_attempt = {row['attempt']:row for row in calls}
    for region,truth in geometry['regions'].items():
        def source_binding(frame,root,source,device_record,expected):
            return frame_source_binding(frame,root,source,device_record,expected,region)

        frame_truth = OLD.with_replacements(QUALIFY.frame_truth,TARGET=region,source_binding=source_binding)
        for record in device['frames']:
            try:
                image = frame_truth(record,slot,terminal,device,truth,calls)
                if record['origin']=='product':
                    image['public_delivery'] = [row for row in image['public_delivery']
                        if public_frame_binding(by_attempt[row['attempt']],image,row['public_block_index'])]
                image['CLI_delivery'] = OLD.consumer_delivery(record,image,calls,cli_calls)
                image['product_producer'] = OLD.check_product_frame(slot,record,calls)
                for name in ('triangle_pixel_counts','sampled_triangles','unsampled_triangles','selected_pixels'):
                    image['selected_triangle_counts' if name=='triangle_pixel_counts' else name] = image.pop('upper_'+name)
                image['target_object_row'] = record['object_names'].index(region)
                image['within_object_offset'] = record['source_face_offsets'][image['target_object_row']]
                candidates[region].append(image)
            except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
                errors.append({'region':region,'ref':record.get('ref'),'reason':str(error)})
    return candidates,errors


def verify_product_measurements(slot,calls,geometry,terminal):
    if slot.name!='P1':
        return {}
    ordered = ordered_geometry(terminal)
    objects = {o['name']:o for o in geometry['meshes']}
    evidence = {}
    for call in calls:
        packet = LOW.product_packet(call)
        if packet is None:
            continue
        attempt = call['attempt']
        try:
            args,raw,wire = LOW.product_wire(slot,call)
            ref,task,binding = raw['region_ref'],raw['task_result'],raw['binding']
            query = args['query']
            region, = (k for k,truth in geometry['regions'].items()
                       if ref['host_id']==objects[k]['object_id'] and ref['instance_id']==objects[k]['instance_id']
                       and ref['source_triangle_indices']==truth['triangle_ids'])
            reference = objects[REFERENCES[region]]
            require(query['mode']==raw['result_kind']=='source_region'
                    and raw['read_only'] is True and raw['execution_authority'] is False
                    and packet['region_ref']==task['region_ref']==ref and task['binding']==binding
                    and binding['capture_scope']=='complete_scene_meshes' and binding['unit']=='m'
                    and binding['coordinate_frame']=='world' and binding['document_epoch']==ref['document_epoch']
                    and binding['ordered_geometry_sha256']==ref['ordered_geometry_sha256']==ordered
                    and binding['runtime_source_sha256']==PRODUCT_SOURCE
                    and binding['image_scope']['participation_mask']==terminal['display_object_mask']
                    and all(binding['capture_state'][k]==ref['capture_generation'][k]
                            for k in ('instance_id','revision','epoch'))
                    and all(task['reference'][k]==reference[k] for k in ('name','object_id','instance_id')),
                    'two_product_surfaces_not_bound_to_current_assembly')
            public = packet['task_result']
            fact = public['facts']['surface_proximity']
            require(public['reference']==task['reference'] and public['measurement_scope']==task['measurement_scope']
                    =='complete_selected_source_triangle_union_to_reference_triangle_surface'
                    and fact==task['facts']['surface_proximity'] and fact['status']=='measured',
                    'public_measurement_is_not_original_whole_reference_fact')
            value,truth = fact['value'],geometry['regions'][region]
            pair = value['nearest_witness']
            numeric_pair(value['distance_m'],pair['direction_a_to_b'],pair['a'],pair['b'],truth)
            if 'region' in packet:
                require((packet['region']['source_triangle_count'],packet['region']['source_vertex_count'])==
                        (truth['triangle_count'],truth['vertex_count']),'product_source_counts_changed')
            world_box = (query.get('region') or {}).get('world_box_m')
            evidence[attempt] = {'attempt':attempt,'region':region,'status':'verified',
                'exact_requested_world_box':world_box==truth['world_box_m'],'distance_m':value['distance_m'],
                'nearest_pair':pair,'includes_image':args.get('include_image',True) is True,
                'response_detail':args.get('response_detail','omitted'),'images_delivered':len(call['images']),
                'visibility':packet.get('visibility'),'body':packet.get('images',[]),**wire}
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            evidence[attempt] = {'attempt':attempt,'status':'unverified','reason':str(error)}
    return evidence


def requested_region(query,geometry):
    selection = query.get('region')
    ref = query.get('region_ref')
    objects = {o['name']:o for o in geometry['meshes']}
    for region,truth in geometry['regions'].items():
        obj = objects[region]
        if isinstance(selection,dict) and isinstance(selected:=selection.get('object'),dict):
            if selected.get('name')==region or selected.get('id')==obj['object_id']:
                if (selection.get('world_box_m')==truth['world_box_m'] or
                        selection.get('source_triangle_indices')==truth['triangle_ids']):
                    return region
        if isinstance(ref,dict) and (ref.get('host_id'),ref.get('instance_id'))==(obj['object_id'],obj['instance_id']):
            if ref.get('source_triangle_indices')==truth['triangle_ids']:
                return region
    return None


def check_claim(item,row,answer,geometry,frames,claims):
    region,_,criterion = item.partition('.')
    if criterion not in ('threshold','distance','nearest_pair'):
        return OLD.check_claim(item,row,answer,geometry,frames,claims)
    quote = row['quote']
    truth = geometry['regions'][region]
    require(isinstance(quote,str) and quote.strip() and quote in answer,'claim_quote_absent_from_actual_final')
    if criterion=='threshold':
        require(row['at_least_0_35_m'] is truth['at_least_0_35_m'],'incorrect_threshold_classification')
    elif criterion=='distance':
        value,allowance = OPPOSITE.distance_in_metres(row)
        literal = re.escape(row['distance_literal'])
        require(re.search(r'(?<![\d.])'+literal+r'(?![\d.])',quote)
                and abs(value-truth['distance_m'])<=min(allowance,.000500001)
                and (value>=float(THRESHOLD)) is truth['at_least_0_35_m'],
                'distance_rounding_incorrect_or_does_not_resolve_threshold')
    else:
        a,b = (row[k] for k in ('selected_point_world_m','reference_point_world_m'))
        require({*a,*b} <= OLD.literal_numbers(quote),'nearest_point_coordinates_absent_from_original_claim')
        numeric_pair(truth['distance_m'],truth['direction_world'],a,b,truth)
    return None


def exposure_verifier():
    from inspect import getsource

    text = getsource(FOOT.score_exposure)
    replacements = (
        ("slot.name=='B1'", "slot.name=='P1'"),
        ("abs(float(claims[region+'.distance']['distance_literal'])-first_fact['distance_m'])<=OLD.POSITION_TOL",
         "rounded_distance_matches(claims[region+'.distance'],(first_fact['distance_m'],))"),
        ("cited['Cube_point_world_m']", "cited['reference_point_world_m']"))
    for old,new in replacements:
        require(text.count(old)==1,'retained_exposure_anchor_changed')
        text = text.replace(old,new)
    scope = dict(FOOT.score_exposure.__globals__,BOXES=BOXES,requested_region=requested_region,
                 rounded_distance_matches=OPPOSITE.rounded_distance_matches)
    exec(compile(text,str(FOOT.__file__),'exec'),scope)
    return scope['score_exposure']


score_slot = OLD.with_replacements(FOOT.score_slot,PRODUCT_SOURCES=PRODUCT_SOURCES,BOXES=BOXES,
                                   REQUIRED=REQUIRED,historical_truth=historical_truth,
                                   verify_closed_source=verify_closed_source,qualify_frames=qualify_frames,
                                   verify_product_measurements=verify_product_measurements,check_claim=check_claim,
                                   score_exposure=exposure_verifier())


def preflight(output):
    _,proof = historical_truth()
    for row in (*proof['regions'].values(),proof['offline_control']):
        numeric_pair(row['distance_m'],row['direction_world'],row['source_point_world_m'],row['reference_point_world_m'],row)
    write(output,proof)
    return proof


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight',type=Path)
    mode.add_argument('--slot',type=Path)
    parser.add_argument('--claims',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.preflight:
        preflight(args.preflight)
    else:
        require(args.output is not None,'score_output_required')
        try:
            verdict=score_slot(args.slot,args.claims)
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            verdict={'slot':args.slot.name,'quality_complete':False,'passed_items':0,'total_items':len(REQUIRED),
                     'unverified_items':list(REQUIRED),'error':str(error),'adoption':None}
        write(args.output,verdict)
        print({key:verdict[key] for key in ('slot','quality_complete','passed_items','total_items','error') if key in verdict})
        raise SystemExit(0 if verdict['quality_complete'] or args.claims is None and
                         verdict.get('awaits_literal_claim_transcription') is True else 1)
