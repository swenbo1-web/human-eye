"""Validate finished formal slot originals and extract current-source facts."""

import base64
from functools import lru_cache
from hashlib import file_digest, sha256
import json
from pathlib import Path
from runpy import run_path
import sys
from types import SimpleNamespace
from urllib.parse import unquote


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
OLD = V / 'perf050_dense_micro_surface_holdout_001'
TRUTH = OLD / 'fixture/TRUTH.json'
BINDING = V / 'm4_source_region_blocker_frame_list_001/install/PRODUCT_RUN_BINDING.json'
LABELS = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
WIRE = V / 'm4_cross_scale_live_task_formal_001/checks/review_actual_tools.py'
ASSET = 'b0b55b6a508b1ef05f8362a7af1a27566827319de882fd4f30b06f16d0d2043f'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('xb') as out:
        out.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf8'))


def digest(path):
    with Path(path).open('rb') as raw:
        return file_digest(raw, 'sha256').hexdigest()


def exact(path, slot):
    path = Path(path).resolve(strict=True)
    require(path.is_relative_to(slot.resolve()), 'archived_path_outside_owned_slot')
    return {'path': path.as_posix(), 'sha256': digest(path), 'bytes': path.stat().st_size}


@lru_cache(maxsize=None)
def retained(path):
    return run_path(str(path))


def dependency_paths():
    binding = read(BINDING)
    shared = read(V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    for path in (binding['dependency_root'], shared['dependency_root']):
        if path not in sys.path:
            sys.path.insert(0, path)


def publication(slot):
    raw, pub = read(slot/'SLOT_RESULT.json'), read(slot/'SLOT_PUBLICATION.json')
    require(raw['label'] == pub['label'] == slot.name and pub['result_sha256'] == digest(slot/'SLOT_RESULT.json'),
            'actual_result_and_publication_do_not_match')
    return raw, pub


def closed_source(slot, raw):
    source = retained(V / 'm4_cross_scale_live_task_formal_001/scoring/formal.py')
    require(raw.get('closure_verification', {}).get('passed') is True
            and raw.get('independent_before_after', {}).get('passed') is True and raw['asset_sha256'] == ASSET,
            'owned_scene_not_closed_or_verified')
    copy = (slot / 'native/input.blend').resolve(strict=True)
    expected = Path(read(TRUTH)['asset']['path']).resolve(strict=True)
    start, ready, close = source['generic_process'](slot, expected, copy, ASSET, raw['owned_deadline_ns'])
    files = (slot/'initial_capture/TERMINAL_SOURCE.json', slot/'TERMINAL_SOURCE.json')
    first, last = (source['read_capture'](slot, file, raw.get(key), start['pid'], ASSET)
                   for file, key in zip(files, ('initial_source','terminal_source'), strict=True))
    require(start['created_after_ns'] <= first['started_ns'] < raw['ready_ns'] <= raw['cleanup_started_ns']
            <= last['started_ns'] <= close['closed_ns'] < raw['owned_deadline_ns'], 'current_capture_spans_changed')
    fields = ('source','objects','source_face_offsets','display_object_mask','display_scope','layer_collections','scene_cameras')
    require(all(first[key] == last[key] for key in fields), 'geometry_or_display_changed_in_owned_slot')
    frozen = read(TRUTH)['reopened_source']
    require(digest(frozen['path']) == frozen['sha256'], 'frozen_geometry_source_changed')
    fixture = {obj['name']: obj for obj in read(frozen['path'])['objects']}
    owned = {obj['name']: obj for obj in last['objects']}
    require(fixture.keys() == owned.keys() and len(owned) == len(last['objects']) == 21,
            'same_slot_object_roster_not_current_fixture')
    for name, obj in owned.items():
        reference = fixture[name]
        require(all(obj[stage]['triangles'] == reference[stage]['triangles'] and
                    obj[stage]['vertices_world_m'] == reference[stage].get('vertices_world_m',reference[stage].get('vertices_world'))
                    for stage in ('native','evaluated')), 'same_slot_geometry_changed/' + name)
    return last, {'first': exact(files[0],slot), 'last': exact(files[1],slot),
                  'closed_pid':start['pid'],'unchanged_fingerprint':ready['initial_fingerprint']}


def closed_answer(slot, raw):
    """Require the published UTF-8 original to match the real completed CLI agent item."""
    if raw.get('answer') is None:
        return None
    path = slot / 'consumer/PUBLIC_FINAL.txt'
    result = raw['answer']
    original = exact(path, slot)
    require(Path(result['path']).resolve() == path.resolve()
            and (result['sha256'], result['bytes']) == (original['sha256'], original['bytes']), 'answer_original_hash_changed')
    cli = slot/'consumer/stdout.raw.bin'
    cli_exact = exact(cli, slot)
    messages = [event['item'] for line in cli.read_bytes().splitlines() if line.strip()
                if (event := json.loads(line)).get('type') == 'item.completed'
                and event.get('item',{}).get('type') == 'agent_message']
    body = path.read_bytes()
    require(messages and messages[-1]['text'].encode('utf8') == body, 'answer_final_CLI_event_mismatch')
    return {**original,'raw_cli':cli_exact,'agent_message_item':messages[-1]['id'],'text':body.decode('utf8')}


def producer_delivery(slot, owner, request, response):
    """Bind the installed inner tool response without interpreting task-specific clocks."""
    request_path, receipt_path = (owner/f for f in ('PRODUCT_REQUEST.json','PRODUCT_RECEIPT.json'))
    if not request_path.is_file() and not receipt_path.is_file():
        return None
    require(request_path.is_file() and receipt_path.is_file(), 'incomplete_installed_product_forwarding_paths')
    live, audit = read(request_path), read(receipt_path)
    entry, = [row for line in (slot/'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()
              if (row:=json.loads(line)).get('request')==live]
    business = {key:value for key,value in request['params'].items() if key!='_meta'}
    require(live['params']==business and audit.get('receipt')==entry.get('receipt')
            and audit.get('producer_archive')==entry.get('producer_archive'), 'actual_installed_RPC_correlation_failed')
    inner=owner/'PRODUCT_RESPONSE.json'
    if inner.is_file():
        original=read(inner)
        require(original==entry['response'] and ('result' not in original or original['result']==response.get('result')),
                'installed_product_delivery_not_forwarded_original')
    archive=entry.get('producer_archive')
    if archive is not None:
        original=exact(archive['path'],slot)
        require(original['sha256']==archive['sha256'], 'installed_original_producer_archive_changed')
    return {'request':exact(request_path,slot),'receipt':exact(receipt_path,slot),'arguments':live['params']['arguments'],
            'response':exact(inner,slot) if inner.is_file() else None,
            'producer_delivery':{'path':original} if archive is not None else None}


def formal_wires(slot, pub):
    review = retained(WIRE)
    original_audit = review['audit_slot']
    previous = dict(original_audit.__globals__)
    try:
        original_audit.__globals__.update(NS=NS, RUNTIME=slot.parent.parent, product_evidence=producer_delivery)
        seal = {'slot':slot.name,'status':pub['status'],'slot_result_sha256':pub['result_sha256'],
                'path':None,'sha256':None}
        tools,_ = original_audit(seal)
    finally:
        original_audit.__globals__.update(previous)
    attempts=tools['attempts']
    require([r['attempt'] for r in attempts] == list(range(1,len(attempts)+1)), 'formal_attempt_order_changed')
    policy,limits = retained(V/'m4_cross_scale_live_qualification_001/checks/delivery.py')['budget_helpers']()
    for row in attempts:
        wire = read(row['RX']['path'])
        request = read(row['TX']['path'])
        row['response_detail'] = request['params']['arguments'].get('response_detail')
        results = wire.get('result')
        row['fixed_history_text'] = []
        if results is not None and row['model_visible_as_public_CLI_tool_result']:
            items = policy['model_items'](results,'100.0000')
            first = policy['truncate_items'](items,limits['MCP_bytes'])
            history = policy['truncate_items'](first,limits['history_approximate_tokens'],token_mode=True)
            row['fixed_history_text'] = [item['text'] for item in history[1:] if item['type']=='input_text']
            row['fixed_history_whole'] = history == items
    return tools


def frame_declarations(result):
    """Read ordered original native captions and public product frame tables."""
    found = []
    blocks = result.get('content', [])
    for index, block in enumerate(blocks):
        if block.get('type') != 'text':
            continue
        label, separator, details = block['text'].partition('\n')
        if separator and label.startswith(('active-host-image:','native-image:','source-region-image:')) and label.endswith('image/png)'):
            row=json.loads(details)
            found.append((label.split()[0],index+1,row['image_sha256'],row.get('local_image_path')))
            continue
        try:
            body=json.loads(block['text'])
        except json.JSONDecodeError:
            continue
        if not isinstance(body,dict):
            continue
        for key in ('frames','images'):
            entries=body.get(key)
            if isinstance(entries,dict):
                entries=[dict(zip(entries['columns'],entry,strict=True)) for entry in entries['rows']]
            if not isinstance(entries,list):
                continue
            for position, row in enumerate(entries,1):
                if type(row) is not dict or not isinstance(row.get('image_ref'),str):
                    continue
                ordinal=row.get('native_content_block_index',row.get('image_block_index',position))
                if type(ordinal) is int and row.get('image_sha256'):
                    found.append((row['image_ref'],ordinal,row['image_sha256'],row.get('local_image_path',row.get('image_path'))))
    return found


def frame_deliveries(slot, frames, tools):
    by_ref={row['ref']:row for row in frames}
    require(len(by_ref)==len(frames),'duplicate_active_slot_frame_reference')
    result={ref:[] for ref in by_ref}
    for attempt in tools['attempts']:
        if not attempt['model_visible_as_public_CLI_tool_result'] or attempt['is_error']:
            continue
        wire=read(attempt['RX']['path'])['result']
        for ref, position, sha, declaration in frame_declarations(wire):
            frame=by_ref.get(ref)
            content=wire['content']
            if frame is None or not 0 <= position < len(content) or sha != frame['PNG_sha256']:
                continue
            block=content[position]
            if block.get('type')!='image' or block.get('mimeType')!='image/png':
                continue
            png=exact(frame['PNG'],slot)
            raw=base64.b64decode(block['data'],validate=True)
            require(sha256(raw).hexdigest()==sha==png['sha256'] and Path(png['path']).read_bytes()==raw,
                    'CLI_native_image_bytes_differ_from_original')
            if declaration is not None:
                require(Path(declaration).is_absolute() and Path(declaration).resolve(strict=True)==Path(png['path']),
                        'declared_CLI_original_image_path_not_current')
            result[ref].append({'attempt':attempt['attempt'],'block_index':position,'named_local_path':declaration is not None,
                                'route':attempt['tool'],'RX':attempt['RX']})
    return result


def product_frame(slot,row,source,target,tools,geometry):
    captures = retained(V/'m4_cross_scale_discovery_001/oracle/check_saved.py')
    check = retained(NS/'qualification/frame.py')['prove_frame']
    capture_map,_ = captures['decode_captures'](slot,read(BINDING),captures['Audit']())
    for attempt in tools['attempts']:
        packet = (attempt.get('product') or {}).get('producer_delivery')
        if not packet:
            continue
        pinned = packet['path']
        original = exact(pinned['path'],slot)
        require(original['sha256']==pinned['sha256'] and original['bytes']==pinned['bytes'],
                'actual_producer_frame_archive_changed')
        body=read(original['path'])
        for frame in body.get('frames',[]):
            if frame['image_ref'] != row['ref']:
                continue
            parent=body['binding']
            scope=next((item['binding'] for item in body.get('scopes',[]) if item['scope_id']==row['scope_id']),parent)
            capture=captures['current_capture'](capture_map,parent,captures['Audit']())
            parent_binding=parent if scope.get('capture_scope')=='same_capture_region_view' else None
            return check(slot,row,frame,scope,capture,source,target,geometry=geometry,parent=parent_binding)
    raise ValueError('no_original_same_capture_and_frame_scope/' + row['ref'])


def score_frame(slot,row,source,target,tools,geometry):
    native=retained(OLD/'qualification/native.py')
    if row['origin']=='product':
        return product_frame(slot,row,source,target,tools,geometry)
    require(row['origin']=='common_native','unknown_owned_raster_origin')
    owner=SimpleNamespace(runtime=SimpleNamespace(device=SimpleNamespace(by_ref={row['ref']:row})))
    return native['prove_image'](slot,owner,row['ref'],target,source=source,geometry=geometry)


def product_facts(slot,source,tools,geometry):
    """Record only temporally bound, independently supported tool facts a grader may attribute."""
    aliases, proved = {}, []
    checks=retained(OLD/'qualification/product_qa.py')
    decode=retained(V/'m4_dense_region_brief_001/checks/brief_schema.py')['decode_body']
    for row in tools['attempts']:
        archive=(row.get('product') or {}).get('producer_delivery')
        if archive is None or not row.get('fixed_history_text') or row['is_error']:
            continue
        result=read(row['RX']['path'])['result']
        block=result['content'][0]
        if block['type']!='text' or block['text'] not in row['fixed_history_text']:
            continue
        try:
            body=json.loads(block['text'])
            if type(body) is not dict or body.get('read_only') is not True or body.get('execution_authority') is not False:
                continue
            producer=read(archive['path']['path'])
            host=checks['host_source'](slot,producer['binding'],source,require_full=False)
            if body.get('schema')=='active-observation-region-task-brief-v2':
                facts=decode(body,len(result['content']))['region_task']['rows']
                producer_task=producer['facts']['region_task']['rows']
                matches=[]
                for fact in facts:
                    name=fact['object_name']
                    expected=geometry['regions'].get(name)
                    if expected and any(raw['roi_id']==fact['roi_id'] and raw['source']==fact['source']
                        for raw in producer_task) and fact['source_triangle_indices']==expected['source_triangle_indices'] and (
                        fact['center_world_m']==expected['center_world_m']):
                        row_refs=aliases.setdefault(name,{}).setdefault(fact['roi_id'],[])
                        ids=fact['source_triangle_indices']
                        if ids not in row_refs:
                            row_refs.append(ids)
                        matches.append(name)
                if matches:
                    proved.append({'attempt':row['attempt'],'kind':'discovery','objects':matches,'wire':row['RX']})
                unknown=[fact for fact in facts if fact['object_name']=='S034']
                if len(unknown)==1 and unknown[0]['reason']=='positive_area_occlusion_all_front_views' and (
                        set(unknown[0]['view_reasons']['positive_area_occlusion'])==set(geometry['strict_covering']['S034'])):
                    names=checks['tables'](body['objects'],['object_index','host_id','instance_id','object_name'])
                    # When a named blocker is actually published, independently replay all its directions.
                    if 'blocker_evidence' in body:
                        checks['verify_blockers'](body,facts,names,host)
                    proved.append({'attempt':row['attempt'],'kind':'occlusion','objects':['S034'],'wire':row['RX']})
            elif body.get('schema')=='source-region-brief-v2':
                task=body['task_result']
                witness=task['facts']['surface_proximity']
                selected=body['region_ref']
                name=body['region']['object_name']
                tool_row=next(obj for obj in source['objects'] if obj['name']==name)
                if name=='S034' and selected==producer['region_ref'] and selected['source_triangle_indices']==[0,1] and (
                        selected['host_id']==tool_row['object_id'] and selected['instance_id']==tool_row['instance_id']) and (
                        selected['document_epoch']==producer['binding']['document_epoch'] and
                        all(selected['capture_generation'][key]==producer['binding']['capture_state'][key]
                            for key in ('instance_id','epoch','revision'))) and (
                        task['reference']['name']=='M4_Far_00' and
                        task['measurement_scope']=='complete_selected_source_triangle_union_to_reference_triangle_surface' and
                        witness['status']=='measured'):
                    nearest=witness['value']['nearest_witness']
                    proved.append({'attempt':row['attempt'],'kind':'measurement','objects':[name],'wire':row['RX'],
                                   'measurement':{'object_name':name,'reference':'M4_Far_00',
                                     'distance_m':witness['value']['distance_m'],'direction_world':nearest['direction_a_to_b'],
                                     'a':nearest['a'],'b':nearest['b']}})
        except (KeyError,IndexError,TypeError,OSError,ValueError,StopIteration):
            # A shape the evidence reader cannot bind is unavailable for optional adoption attribution.
            continue
    return aliases,proved


def evaluated_facts(slot,source,tools,link_paths):
    geometry=retained(OLD/'qualification/native.py')['certify_geometry'](source)
    local=read(slot/'DEVICE_EVIDENCE.json')
    require(local['asset_sha256']==ASSET and local['label']==slot.name,'original_device_wrong_asset_or_slot')
    frames=local['frames']
    deliveries=frame_deliveries(slot,frames,tools)
    by_link={}
    for link in link_paths:
        path=Path(unquote(link))
        if not path.is_absolute() or not path.is_file():
            continue
        matches=[row for row in frames if Path(row['PNG']).resolve()==path.resolve()]
        if len(matches)!=1:
            continue
        row,=matches
        actual=deliveries[row['ref']]
        if not actual:
            continue
        reviewed={}
        for name in ('S021','S055'):
            try:
                reviewed[name]=score_frame(slot,row,source,name,tools,geometry)
            except (OSError,KeyError,ValueError,TypeError,ImportError) as err:
                reviewed[name]={'complete':False,'issue':str(err)}
        by_link[link]={'targets':reviewed,'deliveries':actual}
    aliases,verified=product_facts(slot,source,tools,geometry)
    return {'geometry':geometry,'linked_originals':by_link,'attempts':tools['attempts'],
            'roi_aliases':aliases,'verified_product_text_facts':verified}
