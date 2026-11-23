"""Qualify selective transport on frozen production captures without Blender."""

import argparse
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import file_digest, sha256
from io import StringIO
import json
from math import inf, nextafter
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from time import perf_counter_ns
from types import SimpleNamespace
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
ROOT = V.parent
RUN = Path('D:/he_m2_source_region_cold_selective_transport_001').resolve()
BASE = V/'m1_source_region_image_evidence_001/install/PRODUCT_RUN_BINDING.json'
BASE_GIT = 'e800667077a6c390dbc1f49aa46ba9a01b153de5'
FIXTURES = {
    'assembly': ('m4_assembly_cross_asset_product_native_001','4bc6b7d6da32a4204f57465f4311723e0836faff',28),
    'yanyite': ('m4_yanyite_opposite_direction_product_native_001','75f75b920',2),
    'rail': ('m4_rail_source_region_product_native_001','a374e3dcde0334991a63c15d594604c068b0b614',21),
}
EXTRACTOR = V/'m1_source_region_world_box_001/inputs.py'
GEOMETRY = V/'m4_source_region_nonplanar_short_circuit_001/harness/inputs.py'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def stable(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as handle:
        return {'path':str(path),'bytes':path.stat().st_size,'sha256':file_digest(handle,'sha256').hexdigest()}


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8',newline='\n') as handle:
        json.dump(value,handle,ensure_ascii=False,allow_nan=False,sort_keys=True,indent=2)
        handle.write('\n')


def git_blob(revision,path):
    return subprocess.check_output(['git','-C',str(ROOT),'show',revision+':'+path.relative_to(ROOT).as_posix()])


def public_query(target,reference,box):
    minimum,maximum = box
    return {'mode':'source_region','region':{'object':{'name':target},
            'world_box_m':{'min':list(minimum),'max':list(maximum)}},
            'reference':{'name':reference},'requested_facts':['surface_proximity']}


def truth_for(name, terminal, capture, oracle):
    if name == 'yanyite':
        target,cube = ({row['name']:row for row in capture['meshes']}[n]
                       for n in (terminal['objects'][0]['name'],'Cube'))
        geometry = oracle['truth_regions'](target['vertices'],target['faces'],cube['vertices'],cube['faces'])
        require(terminal['display_object_mask'] == [True,False], 'hidden_reference_changed')
        queries = [public_query(target['name'],'Cube',box) for box in oracle['BOXES'].values()]
    else:
        geometry = oracle['scene_truth'](terminal)['regions']
        queries = [public_query(target,oracle['REFERENCES'][target],box) for target,box in oracle['BOXES'].items()]
    return queries,list(geometry.values())


def fixture(name, base_install_root):
    """Bind a closed actual slot and independently verify its request geometry."""
    namespace,commit,count = FIXTURES[name]
    home = Path('D:/he_'+namespace).resolve()
    slot = home/'slots/P1'
    metadata = V/namespace/'RESULT.json'
    raw_result = git_blob(commit,metadata)
    require(metadata.read_bytes()==raw_result,'frozen_original_result_changed/'+name)
    result = json.loads(raw_result)
    archive = home/'sealed/ORIGINAL_RUNTIME.zip'
    index_path = archive.with_name('RAW_INDEX.json')
    index = read(index_path)
    expected_archive = result['raw_local_archive'] if name=='rail' else result['raw_archive']['archive']
    actual_archive = pin(archive)
    require(index['archive']==actual_archive
            and all(actual_archive[k]==expected_archive[k] for k in actual_archive),
            'original_archive_digest_changed/'+name)
    pins = [pin(metadata),pin(index_path),actual_archive,pin(EXTRACTOR),pin(GEOMETRY)]
    sources_dir = V/namespace
    oracle_file = sources_dir/'score.py'
    oracle = run_path(str(oracle_file))
    pins.append(pin(oracle_file))

    with ZipFile(archive) as bundle:
        require(len(bundle.infolist())==len(index['members'])==index['member_count'],
                'original_archive_members_changed/'+name)

        def take(path):
            path = path.resolve(strict=True)
            require(path.is_relative_to(slot),'historical_fixture_path_outside_slot')
            relative = path.relative_to(home).as_posix()
            raw = path.read_bytes()
            digest = {'bytes':len(raw),'sha256':sha256(raw).hexdigest()}
            require(digest==index['members'][relative] and raw==bundle.read(relative),
                    'historical_fixture_member_changed/'+relative)
            pins.append({'path':str(path),**digest})
            return raw

        publication = json.loads(take(slot/'SLOT_PUBLICATION.json'))
        raw_slot = take(slot/'SLOT_RESULT.json')
        owned = json.loads(raw_slot)
        closed = json.loads(take(slot/'RUNTIME_CLOSE.json'))
        terminal_raw = take(slot/'TERMINAL_SOURCE.json')
        terminal = json.loads(terminal_raw)
        begin = json.loads(take(slot/'initial_capture/TERMINAL_SOURCE.json'))
        asset = take(slot/'native/input.blend')
        require(publication['result_sha256']==sha256(raw_slot).hexdigest()
                and publication['status']==owned['status']=='completed'
                and owned['terminal_source']['sha256']==sha256(terminal_raw).hexdigest()
                and owned['closure_verification']['passed'] is True
                and owned['independent_before_after']['passed'] is True
                and not closed['errors'] and closed['Blender_exit']['confirmed']
                and closed['public_MCP_close']['confirmed']
                and sha256(asset).hexdigest()==terminal['source']['asset_sha256']==owned['asset_sha256']
                and all(begin[k]==terminal[k] for k in ('source','objects','source_face_offsets','display_object_mask')),
                'original_owned_crop_or_closure_unbound/'+name)
        wire = json.loads(take(slot/'native/WIRE/INDEX.json'))
        delta,wire_record = run_path(str(EXTRACTOR))['recorded_delta'](slot,'002',count,wire,take)
        require(wire_record['resource_count']==count,'historical_capture_not_full/'+name)
        decoder_path = Path(base_install_root)/'human_eye_plugin/scene_residency.py'
        decoder = run_path(str(decoder_path))['SceneDeltaDecoder']
        pins.append(pin(decoder_path))
        capture = decoder().apply(delta)
        run_path(str(GEOMETRY))['verify_geometry'](capture,terminal)
        require([row['object_id'] for row in terminal['objects']]==[row['object_id'] for row in capture['meshes']]
                and terminal['display_object_mask']==[row['visible_get'] for row in capture['display_snapshot']['objects']],
                'historical_current_capture_order_or_display_changed/'+name)
        queries,truths = truth_for(name,terminal,capture,oracle)
        native_requests = [json.loads(take(path)) for path in sorted((slot/'owner').glob('tool_*/PRODUCT_REQUEST.json'))]
        require([row['params']['arguments']['query'] for row in native_requests]
                ==queries and all(row['params']['arguments']['include_image'] is True for row in native_requests),
                'historical_product_queries_differ_from_fixture/'+name)
        for n,truth in enumerate(truths,1):
            producer = json.loads(take(slot/f'product_full/call_{n:03d}/SERVICE_RESULT.json'))
            witness = producer['task_result']['facts']['surface_proximity']['value']
            pair = witness['nearest_witness']
            check = oracle['numeric_pair'] if name!='rail' else oracle['ASSEMBLY'].numeric_pair
            check(witness['distance_m'],pair['direction_a_to_b'],pair['a'],pair['b'],truth)
            require(producer['region_ref']['source_triangle_indices']==truth['triangle_ids']
                    and producer['binding']['capture_scope']=='complete_scene_meshes',
                    'historical_producer_selected_other_world_rows/'+name)
    return delta,capture,terminal,queries,truths,pins


def check_installed(binding_path):
    binding = read(binding_path)
    root = Path(binding['install_root']).resolve(strict=True)
    wheel = Path(binding['wheel_path']).resolve(strict=True)
    pins = [pin(binding_path),pin(wheel)]
    require(pins[-1]['sha256']==binding['wheel_sha256']
            and len(binding['source_manifest']) in (143,144), 'installed_wheel_changed')
    with ZipFile(wheel) as archive:
        for row in binding['source_manifest']:
            path = root/row['path']
            current = pin(path)
            require(current['sha256']==row['sha256'] and path.read_bytes()==archive.read(row['path']),
                    'installed_source_changed/'+row['path'])
            pins.append(current)
    return binding,root,pins


def fixture_only(base_path, output):
    binding,root,pins = check_installed(base_path)
    require(binding['preparation_git']==BASE_GIT,'fixed_baseline_install_required')
    fixtures = {}
    for name in FIXTURES:
        _,capture,terminal,queries,truths,source_pins = fixture(name,root)
        pins.extend(source_pins)
        fixtures[name] = {
            'asset_sha256':terminal['source']['asset_sha256'],
            'counts':[len(capture['meshes']),sum(len(row['vertices']) for row in capture['meshes']),
                      sum(len(row['faces']) for row in capture['meshes'])],
            'requests':[{'query':query,'include_image':False} for query in queries],
            'regions':[{'distance_m':truth['distance_m'],'direction':truth['direction_world'],
                        'source_triangle_indices':truth['triangle_ids'],
                        'source_vertex_indices':truth['vertex_ids'],
                        'nearest_source_world_m':truth['source_point_world_m'],
                        'nearest_reference_world_m':truth['reference_point_world_m']}
                       for truth in truths],
        }
    save(output,{'passed':True,'phase':'independent_historical_geometry','fixtures':fixtures,
                 'source_pins':list({row['path']:row for row in pins}.values()),
                 'actual_Blender':0,'actual_models':0,'actual_rasters':0})


class Replay:
    """Retain connector, generated resident code and host validation, replacing acquisition and socket only."""

    def __init__(self, root, original):
        from human_eye_plugin.blender_mcp_host import BlenderMCPHost

        self.delta,source,self.terminal,_,_,_ = original
        self.source = deepcopy(source)
        self.token = self.source.pop('capture_state')
        self.graph = object()
        rows = self.terminal['objects']
        self.objects = [SimpleNamespace(name=row['name'],name_full=row['name'],type='MESH',
                        session_uid=int(row['instance_id']),matrix_world=deepcopy(row['matrix_world'])) for row in rows]
        for obj in self.objects:
            obj.evaluated_get = lambda graph, obj=obj: obj
        details = self.terminal['source']
        self.scene = SimpleNamespace(objects=self.objects, frame_current=details['frame'],
            frame_subframe=details['subframe'], unit_settings=SimpleNamespace(scale_length=details['scale_length']))
        layer = SimpleNamespace(name=details['view_layer'],
            as_pointer=lambda: int(details['view_layer_id'].removeprefix('rna:')))
        self.scope = {'bpy':SimpleNamespace(context=SimpleNamespace(scene=self.scene,view_layer=layer),
                          app=SimpleNamespace(handlers=SimpleNamespace(depsgraph_update_post=[]))),
                      '_offline_attach_fixture':self.attach}
        self.connector = BlenderMCPHost(root,timeout_s=30)
        self.connector._exchange = self.exchange
        self.mutate_capture = self.mutate_response = None
        self.captures,self.wire = [],[]

    def attach(self, host):
        self.host = host
        host._capture,host._depsgraph = self.capture,lambda: self.graph
        host._identity_metadata = self.identity
        require([host.object_id(obj) for obj in self.objects] ==
                [row['object_id'] for row in self.terminal['objects']], 'replay_object_identifier_changed')
        state = host._residency
        state.instance_id,state.epoch,state.revision = (self.token[k] for k in ('instance_id','epoch','revision'))
        resources = {row['id']:{'resource_id':row['id'],'revision':row['revision'],
                    **{key:tuple(map(tuple,row[key])) for key in ('vertices_local','faces','edges')}}
                    for row in self.delta['resources']}
        for row in self.delta['capture']['meshes']:
            entry = row['_scene_resource']
            state.wire[row['object_id']] = (resources[entry['id']],deepcopy(entry['matrix']),entry['scale'])
        state.enabled = True

    def identity(self, objects, *, capture_scope):
        return {'schema_version':'1.0','document_epoch':self.source['host_identity']['document_epoch'],
                'object_instances':{self.host.object_id(obj):str(obj.session_uid) for obj in objects},
                'capture_scope':capture_scope}

    def capture(self, *, _acquisition_context=None, _acquisition_scope=None, _resident=False):
        require(self.host._lock._is_owned(),'actual_replay_capture_outside_host_read_lock')
        if _acquisition_context is None:
            require(_resident,'normal_capture_left_resident_path')
            self.captures.append('capture')
            return deepcopy(self.source)
        graph,scale,objects,evaluated,checkpoint = _acquisition_context
        require(graph is self.graph and scale==self.scene.unit_settings.scale_length and not _resident
                and _acquisition_scope=='selected_source_region_and_reference'
                and set(evaluated)=={self.host.object_id(obj) for obj in objects}
                and len(objects)==2,'selective_dispatch_did_not_expand_exactly_the_bound_pair')
        self.captures.append('selective')
        meshes = {row['object_id']:row for row in self.source['meshes']}
        checkpoint()
        result = {'meshes':[deepcopy(meshes[self.host.object_id(obj)]) for obj in objects]}
        if self.mutate_capture is not None:
            self.mutate_capture()
        return result

    def exchange(self, request, *, deadline_ns=None, max_response_bytes=None):
        packet = json.loads(request)
        require(packet['type']=='execute_code','connector_did_not_use_actual_fixed_bridge')
        code = packet['params']['code']
        if not self.connector._resident_ready:
            anchor = '    _host = _module._mcp_resident_host\n'
            require(code.count(anchor)==1,'resident_bootstrap_changed')
            code = code.replace(anchor,anchor+'    _offline_attach_fixture(_host)\n')
        self.scope.pop('_result',None)
        with redirect_stdout(StringIO()) as output:
            exec(compile(code,'<installed-fixed-local-dispatch>','exec'),self.scope)
        result = self.scope.get('_result')
        raw = output.getvalue()
        prefix = 'HUMAN_EYE_BLENDER_MCP:'
        require(raw.startswith(prefix) and raw.endswith('\n'),'host_bridge_envelope_changed')
        envelope = json.loads(raw[len(prefix):])
        command = self.scope['_request']
        if command['command']=='capture_source_region_pair':
            require(command['params']['deadline_ns']==deadline_ns and
                    command['params']['max_response_bytes']==max_response_bytes,
                    'private_connector_did_not_preserve_wire_deadline_or_response_budget')
        if self.mutate_response is not None and 'result' in envelope:
            self.mutate_response(envelope['result'])
            raw = prefix+json.dumps(envelope,ensure_ascii=True,allow_nan=False,separators=(',',':'))+'\n'
        reply = {'status':'success','result':{'executed':True,'result':raw}}
        self.wire.append({'command':command['command'],'TX_simulated':len(request),
                          'RX_simulated':len(stable(reply)),'response':result})
        return reply

    def close(self):
        self.connector.close()
        if hasattr(self,'host'):
            self.host.close_residency()
        sys.modules.pop(self.connector._resident_slot,None)


def normalize_result(value):
    product = value.get('task_result',value)
    source = product['source_mapping']
    return {'facts':product['facts'],'region':source['region'],'nearest':source['nearest_witness']}


def prove_transmitted(invoice, terminal, full, query, truth):
    region, reference = invoice['region'],invoice['reference']
    box = query['region']['world_box_m']
    target_name = query['region']['object']['name']
    ref_name = query['reference']['name']
    a,b = ({m['name']:m for m in full['meshes']}[name] for name in (target_name,ref_name))
    authored = {row['name']:row for row in terminal['objects']}
    indices = truth['vertex_ids']
    rows = truth['triangle_ids']
    faces = [a['faces'][i] for i in rows]
    binding = invoice['binding']
    require(binding['capture_scope']=='selected_source_region_and_reference'
            and binding['world_box_m']==box
            and binding['document_epoch']==full['host_identity']['document_epoch']
            and binding['target']['instance_id']==authored[target_name]['instance_id']
            and binding['reference']['instance_id']==authored[ref_name]['instance_id']
            and binding['world_matrices']=={'target':authored[target_name]['matrix_world'],
                                            'reference':authored[ref_name]['matrix_world']}
            and region['source_triangle_indices']==rows and region['source_vertex_indices']==indices
            and region['vertices']==[a['vertices'][i] for i in indices]
            and region['source_triangle_vertices']==faces
            and [[indices[local] for local in face] for face in region['faces']]==faces
            and reference=={key:b[key] for key in ('vertices','faces')},
            'private_capture_compaction_or_whole_reference_disagrees_with_actual_source')
    work = invoice['work']
    require(work['candidate_objects']==len(full['meshes'])
            and work['expanded_vertices']==len(a['vertices'])+len(b['vertices'])
            and work['expanded_triangles']==len(a['faces'])+len(b['faces'])
            and work['transmitted_vertices']==len(indices)+len(b['vertices'])
            and work['transmitted_triangles']==len(rows)+len(b['faces'])
            and work['private_cache_retained_objects']==0
            and 'ordered_geometry_sha256' not in binding and 'region_ref' not in invoice,
            'private_capture_claims_full_state_or_false_saved_expansion')


def expected_reject(action,reason):
    try:
        action()
    except (ValueError,RuntimeError) as error:
        require(reason in str(error),'unexpected_negative_diagnostic/'+str(error))
        return str(error)
    raise ValueError('wrong_capture_not_rejected/'+reason)


def build_service(root, bench, output):
    from human_eye_plugin.live_service import LiveSpatialService

    config = {'schema_version':'1.0','enabled':True,'project_root':str(root),
              'state_file':str(output/'view.json'),'audit_file':str(output/'audit.jsonl'),
              'observe_on_prompt':False,'request_budget_s':30}
    config_path = output/'config.json'
    save(config_path,config)
    return LiveSpatialService(config_path,host=bench.connector)


def worker(arm,base_path,candidate_path,output):
    binding,root,pins = check_installed(base_path if arm=='A' else candidate_path)
    base,base_root,base_pins = check_installed(base_path)
    require(base['preparation_git']==BASE_GIT,'unexpected_retained_baseline')
    pins.extend(base_pins)
    sys.path[:0] = [str(root),str(binding['dependency_root'])]
    import human_eye_plugin.blender_mcp_host as connector
    import human_eye_plugin.live_service as service
    import human_eye_plugin.source_region as source

    for module in (connector,service,source):
        require(Path(module.__file__).resolve().is_relative_to(root),'offline_worker_loaded_unbound_product')
    report,negative = {},{}
    for name in FIXTURES:
        original = fixture(name,base_root)
        _,full,terminal,queries,truths,fixture_pins = original
        pins.extend(fixture_pins)
        bench = Replay(root,original)
        scope = output.parent/(output.stem+'_'+name)
        local_service = build_service(root,bench,scope)
        reference_legacy = []
        private = []
        for index,(query,truth) in enumerate(zip(queries,truths,strict=True)):
            if arm == 'B':
                before = bench.connector._scene_decoder.baseline()
                selective = local_service._measure_selective_source_region('fixture',query,include_image=False)
                require(bench.connector._scene_decoder.baseline()==before,'private_capture_updated_full_scene_decoder')
                record = bench.wire[-1]
                prove_transmitted(record['response'],terminal,full,query,truth)
                require(selective['status']=='complete' and selective['frames']==[]
                        and selective['work']['raster_attempts']==0
                        and 'region_ref' not in selective
                        and selective['binding']['capture_scope']=='selected_source_region_and_reference',
                        'private_result_masquerades_as_full_scope_or_has_image')
                private.append({'result':normalize_result(selective),'payload_sha256':selective['payload_sha256'],
                                'host_work':record['response']['work'],
                                'wire':{key:value for key,value in record.items() if key!='response'}})
                if index==0:
                    again = local_service._measure_selective_source_region('fixture',query,include_image=False)
                    require(normalize_result(again)==private[-1]['result']
                            and again['payload_sha256']==private[-1]['payload_sha256'],
                            'private_unchanged_read_changes_binding_or_original_measurement')
            legacy = local_service.observe('fixture',query=query,include_image=False)
            require(legacy['binding']['capture_scope']=='complete_scene_meshes' and legacy['frames']==[]
                    and legacy['region_ref']['source_triangle_indices']==truth['triangle_ids'],
                    'public_scope_or_order_changed')
            reference_legacy.append(normalize_result(legacy))
            if arm=='B':
                require(reference_legacy[-1]==private[-1]['result'],'private_measurement_and_original_witness_differ/'+name)
                by_ref = {key:value for key,value in query.items() if key!='region'}
                by_ref['region_ref'] = legacy['region_ref']
                using_ref = local_service.observe('fixture',query=by_ref,include_image=False)
                require(normalize_result(using_ref)==reference_legacy[-1],'existing_public_region_ref_no_longer_replays')
        report[name] = {'legacy':reference_legacy,'selective':private,'host_dispatches':bench.captures,
                        'truth_rows':[truth['triangle_ids'] for truth in truths]}
        if arm=='B' and name=='rail':
            negative = protocol_controls(bench,local_service,queries[0],full,terminal)
        bench.close()
    save(output,{'passed':True,'arm':arm,'cases':report,'negative':negative,
                 'source_pins':list({row['path']:row for row in pins}.values()),
                 'actual_Blender':0,'actual_models':0,'actual_rasters':0})


def protocol_controls(bench, service, query, full, terminal):
    qualified = {}

    def request(box, target=query['region']['object'], reference=query['reference'], bytes_=64*1024*1024):
        return bench.connector.capture_source_region_pair(target,reference,box,perf_counter_ns()+5_000_000_000,bytes_)

    box = query['region']['world_box_m']
    qualified['empty_box'] = expected_reject(lambda:request({'min':[100.,100.,100.],'max':[101.,101.,101.]}),
                                              'source_region_pair_empty_world_box')
    qualified['same_object'] = expected_reject(lambda:request(box,reference=query['region']['object']),
                                                'source_region_pair_selectors_resolve_to_same_object')
    qualified['unknown_name'] = expected_reject(lambda:request(box,target={'name':'absent-qualified-mesh'}),
                                                 'source_region_pair_object_not_found')
    qualified['response_budget'] = expected_reject(lambda:request(box,bytes_=1),
                                                     'source_region_pair_document_budget_exceeded')
    qualified['expired'] = expected_reject(lambda:bench.connector.capture_source_region_pair(
        query['region']['object'],query['reference'],box,perf_counter_ns()-1,1), 'selective_source_region_deadline')
    good = request(box)
    qualified['id_selectors'] = request(box,{'id':good['binding']['target']['object_id']},
                                         {'id':good['binding']['reference']['object_id']})['region']==good['region']
    require(qualified['id_selectors'],'explicit_id_selection_does_not_match_unique_name')
    selected = good['region']['vertices']
    exact = {'min':[min(row[axis] for row in selected) for axis in range(3)],
             'max':[max(row[axis] for row in selected) for axis in range(3)]}
    exact_reply = request(exact)
    require(exact_reply['region']==good['region'],'closed_boundary_dropped_exact_extreme_face')
    target = next(row for row in full['meshes'] if row['name']==query['region']['object']['name'])
    inset = deepcopy(exact)
    inset['min'][0] = nextafter(inset['min'][0],inf)
    chosen = [i for i,face in enumerate(target['faces']) if all(
        all(a<=coordinate<=b for a,coordinate,b in zip(inset['min'],target['vertices'][v],inset['max']))
        for v in face)]
    require(chosen != good['region']['source_triangle_indices'],'nextafter_control_does_not_change_selection')
    if chosen:
        require(request(inset)['region']['source_triangle_indices']==chosen,'nextafter_box_kept_outside_vertex')
    else:
        expected_reject(lambda:request(inset),'source_region_pair_empty_world_box')
    qualified['boundary_and_nextafter'] = {'closed':good['region']['source_triangle_indices'],'inset':chosen}

    duplicate = SimpleNamespace(name=query['region']['object']['name'],name_full='duplicate-fixture-id',type='MESH')
    bench.objects.append(duplicate)
    try:
        qualified['duplicate_name'] = expected_reject(lambda:request(box),'source_region_pair_object_name_ambiguous')
    finally:
        bench.objects.pop()

    start_frame = bench.scene.frame_current
    bench.mutate_capture = lambda: setattr(bench.scene,'frame_current',start_frame+1)
    try:
        qualified['frame_changes_during_read'] = expected_reject(lambda:request(box),'source_region_pair_source_changed')
    finally:
        bench.mutate_capture = None
        bench.scene.frame_current = start_frame
    item = next(obj for obj in bench.objects if obj.name==query['region']['object']['name'])
    uid = item.session_uid
    bench.mutate_capture = lambda: setattr(item,'session_uid',uid+100_000)
    try:
        qualified['instance_changes_during_read'] = expected_reject(lambda:request(box),'source_region_pair_source_changed')
    finally:
        bench.mutate_capture = None
        item.session_uid = uid
    prior = deepcopy(item.matrix_world)
    bench.mutate_capture = lambda: item.matrix_world[0].__setitem__(3,item.matrix_world[0][3]+1.)
    try:
        qualified['transform_changes_during_read'] = expected_reject(lambda:request(box),'source_region_pair_source_changed')
    finally:
        bench.mutate_capture = None
        item.matrix_world = prior

    bench.scene.frame_current+=1
    newer = request(box)
    bench.scene.frame_current = start_frame
    require(newer['payload_sha256']!=good['payload_sha256'],'new_frame_kept_stale_private_payload')
    qualified['new_frame'] = {'previous':good['payload_sha256'],'current':newer['payload_sha256']}
    measure = lambda: service._measure_selective_source_region('fixture',query,include_image=False)
    mutations = (
        ('wrong_object',lambda value: value['binding']['target'].__setitem__('name','other'),
         'selective_source_region_object_binding'),
        ('wrong_scope',lambda value: value['binding'].__setitem__('capture_scope','complete_scene_meshes'),
         'selective_source_region_capture_binding'),
        ('wrong_original_index',lambda value: value['region']['source_triangle_indices'].__setitem__(0,
              value['region']['source_triangle_count']),'selective_source_region_source_order_or_range'),
        ('wrong_original_vertex',lambda value: value['region']['source_triangle_vertices'][0].__setitem__(0,1000),
         'selective_source_region_source_vertices_mismatch'),
        ('altered_payload',lambda value: value.__setitem__('payload_sha256','0'*64),
         'selective_source_region_payload_digest_mismatch'),
    )
    for name,mutation,reason in mutations:
        bench.mutate_response = mutation
        try:
            qualified[name] = expected_reject(measure,reason)
        finally:
            bench.mutate_response = None
    ordinary = service.observe('fixture',query=query,include_image=False)
    stale = {key:value for key,value in query.items() if key!='region'}
    stale['region_ref'] = ordinary['region_ref']
    qualified['legacy_region_ref_private'] = expected_reject(lambda:service._measure_selective_source_region(
        'fixture',stale,include_image=False),'selective_source_region')
    qualified['images_private'] = expected_reject(lambda: service._measure_selective_source_region(
        'fixture',query,include_image=True),'selective_source_region')
    recovered = measure()
    require(normalize_result(recovered)==normalize_result(ordinary),'private_error_poisoned_current_public_or_selective')
    qualified['after_rejections'] = {'published':True,'same_measurement':True}
    bench.mutate_response = lambda value: value['binding'].__setitem__('host_source_sha256','0'*64)
    try:
        qualified['wrong_host_digest'] = expected_reject(measure,'selective_source_region_host_binding')
    finally:
        bench.mutate_response = None
    require(not bench.connector.is_alive,'corrupt_connector_binding_not_invalidated')
    return qualified


def integrated(base,candidate,output):
    reports = {}
    for arm in ('A','B'):
        path = output.with_name(output.stem+'_'+arm+'.json')
        argv = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),str(base),
                '--candidate',str(candidate),'--worker',arm,'--output',str(path)]
        subprocess.run(argv,cwd=ROOT,check=True,timeout=180)
        reports[arm] = read(path)
    a,b = (reports[arm] for arm in ('A','B'))
    require(a['passed'] and b['passed'] and all(
        a['cases'][name]['legacy']==b['cases'][name]['legacy'] for name in FIXTURES),
        'frozen_standard_public_behavior_changed')
    pins = {row['path']:row for arm in reports.values() for row in arm['source_pins']}
    save(output,{'passed':True,'phase':'actual_installed_dispatch_offline',
                 'source_pins':list(pins.values()),'arms':reports,'actual_Blender':0,'actual_models':0,'actual_rasters':0})


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--worker',choices=('A','B'))
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode and
            args.output.resolve().is_relative_to(RUN/'preflight'),'private_isolated_controls_output_required')
    if args.worker:
        worker(args.worker,args.baseline,args.candidate,args.output.resolve())
    elif args.candidate:
        integrated(args.baseline,args.candidate,args.output.resolve())
    else:
        fixture_only(args.baseline,args.output.resolve())
