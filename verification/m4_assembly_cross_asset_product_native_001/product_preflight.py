"""Verify the installed evidence endpoint against the archived assembly capture."""

import argparse
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
from runpy import run_path
import sys
import time
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
FOOT = run_path(str(V/'m1_yanyite_foot_region_image_evidence_consumption_001/product_preflight.py'))
CURVED, OLD, LOW = (FOOT[k] for k in ('CURVED','OLD','LOW'))
require, read, pin, git, write = (FOOT[k] for k in ('require','read','pin','git','write'))
PLAN = '18b864a64597f690172215f4045bb59bc9ec36ae:docs/M4_ASSEMBLY_CROSS_ASSET_PRODUCT_NATIVE_001_PLAN.md'
RUN = Path('D:/he_m4_assembly_cross_asset_product_native_001/preflight').resolve()
HISTORY = Path('D:/he_m4_cross_scale_assembly_transfer_001').resolve()
SLOT = HISTORY/'slots/P1'
REGISTER = '39fd39cdad162bbe7e5eb68243881d39bb67d285'
INDEX = V/'m4_cross_scale_assembly_transfer_001/RUNTIME_INDEX.json'
CATALOGUE = V/'m1_yanyite_foot_region_image_evidence_consumption_001/inputs/B1_EVIDENCE_TOOLS_SCHEMA.json'
ASSET = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
TERMINAL = 'd0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90'
BOXES = {
    'N19': ('N14', (.449,.135,.690), (.490,.174,.751), list(range(10,20)), .044500013813, 'TOP',161921,10),
    'N25': ('N07', (-.131,-.291,.295), (.011,-.250,.373), list(range(8)), .414366994068, 'SCENE',41395,4),
    'N12': ('N07', (-.512,.065,.619), (0,.154,.671), [0,1,8,9,16,17,24,25], .328100589892, 'SCENE',0,0),
}


def request(name, ident):
    target, minimum, maximum, *_ = BOXES[name]
    return {'jsonrpc':'2.0','method':'tools/call','id':ident,
            'params':{'name':'human_eye_scene_observe','arguments':{'include_image':True,'response_detail':'full',
                'query':{'mode':'source_region','region':{'object':{'name':name},
                    'world_box_m':{'min':list(minimum),'max':list(maximum)}},'reference':{'name':target},
                    'requested_facts':['surface_proximity']}}}}


def inputs():
    path, publication, product, source, wheel = FOOT['BINDINGS']['B']
    binding = read(path)
    require(path.read_bytes()==git('show',publication+':'+path.relative_to(V.parent).as_posix())
            and (binding['preparation_git'],binding['source_sha256'],binding['wheel_sha256'])==(product,source,wheel)
            and len(binding['source_manifest'])==143 and pin(binding['wheel_path'])['sha256']==wheel,
            'fixed_evidence_install_changed')
    require(INDEX.read_bytes()==git('show',REGISTER+':'+INDEX.relative_to(V.parent).as_posix()),
            'assembly_archive_index_changed')
    index = read(INDEX)
    bundle = HISTORY/'ORIGINAL_RUNTIME.zip'
    require(index['archive']==pin(bundle) and index['count']==len(index['files'])==789,'assembly_archive_changed')
    members = {item['path']:item for item in index['files']}
    pinned = [pin(p) for p in (Path(__file__),INDEX,bundle,path,binding['wheel_path'],CATALOGUE,
                              LOW['ORACLE'],V/'m1_yanyite_foot_region_image_evidence_consumption_001/product_preflight.py',
                              *CURVED['source_paths']())]
    with ZipFile(bundle) as archive:
        def take(filename):
            proof = pin(filename)
            key = filename.relative_to(HISTORY).as_posix()
            raw = filename.read_bytes()
            require(members[key]=={'path':key,'bytes':proof['bytes'],'sha256':proof['sha256']}
                    and archive.read(key)==raw,'historical_assembly_member_changed/'+key)
            pinned.append(proof)
            return raw

        asset = take(SLOT/'native/input.blend')
        terminal_bytes = take(SLOT/'TERMINAL_SOURCE.json')
        terminal = json.loads(terminal_bytes)
        score = json.loads(take(SLOT/'SLOT_RESULT.json'))
        require(sha256(asset).hexdigest()==terminal['source']['asset_sha256']==ASSET
                and sha256(terminal_bytes).hexdigest()==TERMINAL
                and score['status']=='completed' and score['closure_verification']['passed']
                and score['independent_before_after']['passed'],'original_assembly_source_unbound')
        close = json.loads(take(SLOT/'mcp/CLOSE.json'))
        require(close['confirmed'] and close['exit_code']==0,'historical_assembly_mcp_not_closed')
        wire_index = json.loads(take(SLOT/'native/WIRE/INDEX.json'))
        recorded = run_path(str(OLD['INPUTS']))['recorded_delta']
        full, first = recorded(SLOT,'002',28,wire_index,take)
        delta, second = recorded(SLOT,'003',0,wire_index,take)
        require(full['capture']==delta['capture'],'historical_assembly_capture_generation_changed')
    plan = [OLD['case'](request(name,'offline-'+name), delta if i else full,terminal,None,stage=name,box=True)
            for i,name in enumerate(BOXES)]
    return binding, {'terminal':terminal, 'capture_plan':[item['capture'] for item in plan],
                     'native_wire_receipts':[first,second],
                     'source_pins':list({p['path']:p for p in pinned}.values())}, plan


def point_on_triangle(point, vertices):
    a,b,c = vertices
    u,v,w = ([q[i]-a[i] for i in range(3)] for q in (b,c,point))
    uu, uv, vv = math.fsum(i*j for i,j in zip(u,u)), math.fsum(i*j for i,j in zip(u,v)), math.fsum(i*j for i,j in zip(v,v))
    wu, wv = math.fsum(i*j for i,j in zip(w,u)), math.fsum(i*j for i,j in zip(w,v))
    determinant = uu*vv-uv*uv
    if determinant <= 0:
        return False
    s,t = (wu*vv-wv*uv)/determinant,(wv*uu-wu*uv)/determinant
    return (s>=-1e-10 and t>=-1e-10 and s+t<=1+1e-10
            and math.dist(point,[a[i]+s*u[i]+t*v[i] for i in range(3)])<=1e-12)


def truth_for(fixture,capture):
    terminal = fixture['terminal']
    meshes = capture['meshes']
    verify = run_path(str(V/'m4_source_region_nonplanar_short_circuit_001/harness/inputs.py'))['verify_geometry']
    verify(capture,terminal)
    require([len(meshes),sum(len(m['vertices']) for m in meshes),sum(len(m['faces']) for m in meshes)]==[28,416,744],
            'original_assembly_geometry_totals_changed')
    native = {item['object_id']:item for item in terminal['objects']}
    display = capture['display_snapshot']
    require(display['view_layer']['instance_id']==terminal['source']['view_layer_id']
            and display['view_layer']['name']==terminal['source']['view_layer']
            and len(display['objects'])==len(native),'actual_assembly_view_layer_changed')
    for row in display['objects']:
        node = native[row['host_id']]
        require(row['instance_id']==node['instance_id'] and row['visible_get'] is node['visible_get']
                and all(row[k] is node['display'][k] for k in ('hide_get','hide_viewport','hide_render')),
                'actual_assembly_display_state_changed')
    by_name = {m['name']:m for m in meshes}
    truth = {}
    for name,(reference,minimum,maximum,required,distance,*_) in BOXES.items():
        m,r = by_name[name],by_name[reference]
        selected = [i for i,face in enumerate(m['faces'])
                    if all(all(a<=x<=b for a,x,b in zip(minimum,m['vertices'][v],maximum,strict=True)) for v in face)]
        require(selected==required,'frozen_closed_box_row_count_changed/'+name)
        vertices = sorted({v for i in selected for v in m['faces'][i]})
        a,b = [[tuple(map(Fraction,m[x][v])) for v in ids] for m,x,ids in (
               (m,'vertices',vertices),(r,'vertices',sorted({v for f in r['faces'] for v in f})))]
        left,right = (list(zip(*p,strict=True)) for p in (a,b))
        gap = [min(y)-max(x) if min(y)>max(x) else max(y)-min(x) if min(x)>max(y) else Fraction()
               for x,y in zip(left,right,strict=True)]
        square = sum(q*q for q in gap)
        lower_bound = math.sqrt(square)
        require(math.isclose(lower_bound,distance,abs_tol=1e-12,rel_tol=0),'frozen_independent_distance_changed/'+name)
        truth[name] = {'triangle_ids':selected,'vertex_ids':vertices,'distance_m':lower_bound,
                       'direction_world':[float(x)/lower_bound for x in gap],
                       'mesh':m,'reference':r}
    return truth


def check_measurement(name,body,value,capture,expected):
    task,public = value['task_result'],body['task_result']
    fact = task['facts']['surface_proximity']
    point = fact['value']['nearest_witness']
    a,b = point['a'],point['b']
    mesh,ref = (expected[k] for k in ('mesh','reference'))
    src,vertices = (expected[k] for k in ('triangle_ids','vertex_ids'))
    scope = value['region_ref']
    region = value['facts']['region']
    mapping = value['source_mapping']
    wanted_faces = [mesh['faces'][i] for i in src]
    require(value['read_only'] is body['read_only'] is True
            and value['execution_authority'] is body['execution_authority'] is False
            and value['binding']['capture_state']==task['binding']['capture_state']==capture['capture_state']
            and scope['capture_generation']=={k:capture['capture_state'][k] for k in ('instance_id','epoch','revision')}
            and body['region_ref']==task['region_ref']==scope
            and scope['source_triangle_indices']==region['source_triangle_indices']==mapping['submesh_to_source_triangle_indices']==src
            and region['source_vertex_indices']==mapping['submesh_to_source_vertex_indices']==vertices
            and mapping['triangles_source_vertices']==wanted_faces
            and [[vertices[j] for j in row] for row in mapping['triangles_submesh_vertices']]==wanted_faces
            and task['measurement_scope']==public['measurement_scope']=='complete_selected_source_triangle_union_to_reference_triangle_surface'
            and task['reference']==public['reference'] and task['reference']['object_id']==ref['object_id']
            and fact==public['facts']['surface_proximity'] and fact['status']=='measured'
            and math.isclose(fact['value']['distance_m'],expected['distance_m'],abs_tol=1e-12,rel_tol=0)
            and math.isclose(math.dist(a,b),expected['distance_m'],abs_tol=1e-12,rel_tol=0)
            and math.dist(point['direction_a_to_b'],expected['direction_world'])<=1e-12,
            'actual_assembly_measurement_or_scope_changed/'+name)
    require(any(point_on_triangle(a,[mesh['vertices'][v] for v in face]) for face in wanted_faces)
            and any(point_on_triangle(b,[ref['vertices'][v] for v in face]) for face in ref['faces']),
            'actual_assembly_witness_not_on_current_surfaces/'+name)
    return fact


def control_rasters(binding,capture,np,truth):
    # Reuse the installed raster at the exact registered camera poses and
    # visibility mask. The control generates owner arrays only and writes
    # neither PNG nor NPZ, independent of actual public requests.
    saved = sys.path[:]
    sys.path[:0] = [binding['install_root'],binding['dependency_root']]
    try:
        from human_eye_plugin.attention_raster import rasterize_attention
        from human_eye_plugin.source_region import prepare_region
    finally:
        sys.path[:] = saved
    require(Path(sys.modules['human_eye_plugin.attention_raster'].__file__).resolve().is_relative_to(
            Path(binding['install_root']).resolve()),'in_memory_control_not_from_fixed_install')
    controls = {}
    for name in ('N19','N12'):
        query = {'region':{'object':{'name':name},'source_triangle_indices':truth[name]['triangle_ids']}}
        prepared = prepare_region(capture,query)
        sizes = [len(mesh.faces) for mesh in prepared.meshes]
        start = 0
        patches = []
        for count in sizes:
            patches.append(np.arange(start,start+count,dtype=np.int32))
            start += count
        offset = sum(sizes[:prepared.object_index])
        selected = np.asarray(truth[name]['triangle_ids'],dtype=np.int32)+offset
        tested = {}
        for pose in prepared.cameras['views']:
            view = pose['name']
            if name=='N19' and view!='SCENE':
                continue
            _,_,owner,triangle = rasterize_attention(prepared.meshes,np.asarray(pose['view_matrix'],dtype=np.float64),
                 np.asarray(pose['projection_matrix'],dtype=np.float64),512,return_owner=True,
                 return_patch_owner=True,face_patch_ids=patches,
                 object_mask=prepared.binding['image_scope']['participation_mask'])
            mask = (owner==prepared.object_index)&np.isin(triangle,selected)
            count = int(np.count_nonzero(mask))
            require(count==0,'in_memory_registered_view_not_zero/'+name+'/'+view)
            tested[view] = {'selected_pixels':count,'owners_sha256':sha256(owner.tobytes()).hexdigest(),
                            'triangle_ids_sha256':sha256(triangle.tobytes()).hexdigest()}
        controls[name] = tested
    require(len(controls['N12'])==6 and list(controls['N19'])==['SCENE'],'registered_zero_sample_control_missing')
    return controls


def verify_cli_evidence(reply, brief):
    # This assembly's brief contains a large shared display directory. Preserve
    # the exact task-bearing members and PNG through both real CLI budget paths,
    # and report separately which other members the middle crop cuts.
    cli = run_path(str(OLD['CLI_PATH']))['fixed_cli'](reply,require_all=False)
    helpers, limits = run_path(str(V/'m4_cross_scale_live_qualification_001/checks/delivery.py'))['budget_helpers']()
    raw = reply['result']['content'][0]['text']
    body = json.loads(raw)
    required = ('status','observation_status','task_result','visibility','images','region','region_ref',
                'read_only','execution_authority') if brief else ()
    encoded = raw.encode('utf-8')
    spans = {key:helpers['path_byte_span'](raw,(key,)) for key in body}
    for head,seconds in zip((33,34,35),('0.0000','10.0000','100.0000'),strict=True):
        items = helpers['model_items'](reply['result'],seconds)
        first = helpers['truncate_items'](items,limits['MCP_bytes'])
        second = helpers['truncate_items'](first,limits['history_approximate_tokens'],token_mode=True)
        for phase, delivered in (('MCP',first),('history',second)):
            retained = delivered[1]['text'].encode('utf-8')
            kept = [k for k,s in spans.items() if encoded[s['start']:s['end']] in retained]
            stage = next(row for row in cli['stages'] if row['head_bytes']==head and row['phase']==phase)
            stage.update(required_members=list(required), preserved_members=kept,
                         missing_members=[k for k in body if k not in kept])
            require(all(key in kept for key in required),'fixed_CLI_lost_task_evidence/'+str(stage))
    return cli


def preflight(root):
    binding,fixture,plan = inputs()
    binding_path = FOOT['BINDINGS']['B'][0]
    root.mkdir(parents=True,exist_ok=False)
    saved = sys.path[:]
    sys.path[:0] = [binding['dependency_root'],read(OLD['SEAL']/'SHARED_DEPENDENCY.json')['dependency_root'],
                   str(OLD['PRIOR']/'harness')]
    try:
        from runtime import ProductionStdioClient
    finally:
        sys.path[:] = saved
    ProductionStdioClient.finish.__globals__['SOURCE_SHA'] = binding['source_sha256']
    cmd = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--worker','--output',str(root)]
    started = time.perf_counter_ns()
    held = ProductionStdioClient(cmd,root,root/'mcp',started+120_000_000_000,worker_evidence=root/'mcp_io')
    replies = []
    invalid = request('N19','offline-inverted-box')
    invalid['params']['arguments']['query']['region']['world_box_m']['max'][0] = -1.0
    try:
        info = held.call(OLD['INIT'])['result']['_meta']['human_eye']
        held.call(OLD['NOTIFY'])
        tools = held.call(OLD['LIST'])['result']['tools']
        require(info['source_sha256']==binding['source_sha256'] and info['source_kind']=='installed_distribution'
                and tools==read(CATALOGUE),'actual_offline_product_install_or_tools_changed')
        rejected = held.call(invalid)
        require(rejected.get('result',{}).get('isError') is True and rejected['id']==invalid['id'],
                'bad_box_accepted_by_actual_product')
        for item in plan:
            reply = held.call(item['request'])
            require(reply.get('result',{}).get('isError') is False,
                    'new_assembly_product_request_failed/'+item['stage'])
            replies.append(reply)
        last = time.perf_counter_ns()
    finally:
        close = held.finish()
    closed = time.perf_counter_ns()
    score_packets(root,binding,fixture,plan,tools,rejected,replies,held.records[3:],close,started,last,closed)


def score_closed(root):
    binding,fixture,plan = inputs()
    raw = root/'mcp'
    read_reply = lambda i: read(raw/f'rpc_{i:02d}'/'RX.bin')
    start,close = (read(raw/name) for name in ('START.json','HELD_CLOSE.json'))
    identity = read_reply(1)['result']['_meta']['human_eye']
    tools = read_reply(3)['result']['tools']
    require(start['pid']==close['pid'] and identity['source_sha256']==binding['source_sha256']
            and tools==read(CATALOGUE),'closed_assembly_pipeline_identity_changed')
    proof = pin(root/'INITIAL_SCORER.py')
    worker = read(root/'REPLAY_CLOSE.json')
    original, = [row for row in worker['source_pins'] if row['path']==str(Path(__file__).resolve())]
    require(all(proof[k]==original[k] for k in ('bytes','sha256')),'closed_launch_script_not_original_bytes')
    fixture['source_pins'].extend((proof,pin(root/'INITIAL_SCORER_FAILURE.json')))
    receipts = [read(raw/f'rpc_{i:02d}'/'RECEIPT.json') for i in range(4,8)]
    score_packets(root,binding,fixture,plan,tools,read_reply(4),[read_reply(i) for i in range(5,8)],receipts,
                  close,start['started_ns'],receipts[-1]['closed_ns'],close['closed_ns'],
                  recounted_original_qualification=True)


def score_packets(root,binding,fixture,plan,tools,rejected,replies,receipts,close,started,last,closed,
                  recounted_original_qualification=False):
    require(close['confirmed'] and close['production_eof_and_exit_verified'] and close['process_handle_closed']
            and close['exit_code']==0,'actual_offline_product_close_missing')
    worker = read(root/'REPLAY_CLOSE.json')
    require(worker['old_sources_unchanged'] and worker['actual_Blender_starts']==worker['actual_models']==0,
            'new_assembly_preflight_acted_outside_sealed_source')
    wire = [r for line in (root/'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()
            if (r:=json.loads(line))['method']=='tools/call']
    require(len(wire)==4 and wire[0]['raster_actual']==0 and len(worker['calls'])==3,
            'rejected_box_touched_capture_or_raster')
    bound = OLD['retained_workers']()[1]['bound_wire']
    invalid = request('N19','offline-inverted-box')
    invalid['params']['arguments']['query']['region']['world_box_m']['max'][0] = -1.0
    require(rejected.get('result',{}).get('isError') is True,'closed_bad_box_not_rejected')
    reject_proof = {'wire':bound(root,invalid,receipts[0],wire[0]),'actual_rasters':0,
                    'content':rejected['result']['content']}
    first_capture = read(root/'CAPTURE_01.json')
    truth = truth_for(fixture,first_capture)
    np = CURVED['np_module'](binding)
    checks = []
    for i,(item,reply,receipt,meter,host) in enumerate(zip(plan,replies,receipts[1:],wire[1:],worker['calls'],strict=True),1):
        name = item['stage']
        _,_,_,_,_,view,pixels,rows = BOXES[name]
        cap_path = root/f'CAPTURE_{i:02d}.json'
        captured = read(cap_path)
        require(captured==first_capture and host['capture_state']==captured['capture_state']
                and host['resource_count']==(28 if i==1 else 0),'actual_assembly_replay_capture_changed/'+name)
        body = json.loads(reply['result']['content'][0]['text'])
        producer = root/'product_full'/f'call_{i:03d}'/'SERVICE_RESULT.json'
        value = read(producer)
        measured = check_measurement(name,body,value,captured,truth[name])
        frames,paths = OLD['selected_image_paths'](root,body,value,reply['result']['content'])
        frame, = frames
        visibility = value['facts']['visibility']
        work = value['work']
        probe = value['stages'][CURVED['SELECTION_STAGE']]
        brief = name!='N12'
        require(frame['view']==probe['chosen_view']==view and work['raster_attempts']==meter['raster_actual']==1
                and work['capture_calls']==1 and work['frame_array_decodes']==0
                and work['sparse_view_probe_views']==(1 if name=='N25' else 6)==len(probe['votes'])
                and (probe['votes']['SCENE']>0)==(name=='N25'),
                'actual_assembly_registered_fallback_or_raster_changed/'+name)
        if brief:
            image, = body['images']
            path, = paths
            require(body['schema']=='source-region-brief-v2' and path==Path(frame['png']['path']).as_posix(),
                    'proved_image_not_delivered_in_compact_first_packet/'+name)
        else:
            require(body['schema']=='human-eye-source-region-observation-v1' and not paths and not any(probe['votes'].values())
                    and 'sampled_pixel' not in body['facts']['visibility'] and 'images' not in body
                    and visibility['status']=='unknown' and 'complete_surface_visibility' in visibility['unknown'],
                    'N12_zero_samples_did_not_retain_explicit_full')
            image,path = {**value['frames'][0],'image_block_index':1},None
        observed = CURVED['verify_arrays'](np,frame,visibility,value,image,value['frames'][0],witness_required=brief)
        require(observed==(pixels,rows),'actual_assembly_png_ownership_changed/'+name)
        cli = verify_cli_evidence(reply,brief)
        require(cli['passed'] and len(cli['stages'])==6 and all(row['original_images_exact'] for row in cli['stages']),
                'assembly_fixed_cli_delivery_changed/'+name)
        checks.append({'stage':name,'detail':'full','projection':'brief' if brief else 'full',
                       'wire':bound(root,item['request'],receipt,meter),'producer':pin(producer),'capture':pin(cap_path),
                       'measurement':measured,'independent_source':{k:v for k,v in truth[name].items()
                                              if k not in ('mesh','reference')},'frame':frame,
                       'sampled_pixel':image.get('sampled_pixel'),'local_image_path':path,'selected_pixels':pixels,
                       'sampled_source_rows':rows,'actual_rasters':1,'work':work,'probe':probe,'cli':cli})
    controls = control_rasters(binding,first_capture,np,truth)
    write(root/'SUMMARY.json',{'passed':True,'role':'offline_product_assembly_qualification','plan':PLAN,
          'product_git':binding['preparation_git'],'source_sha256':binding['source_sha256'],
          'wheel_sha256':binding['wheel_sha256'],'actual_tools':tools,'requests':checks,'rejection':reject_proof,
          'actual_MCP_business':len(wire),'actual_rasters':sum(row['actual_rasters'] for row in checks),
          'separate_in_memory_rasters':sum(len(group) for group in controls.values()),'registered_zero_sample_controls':controls,
          'actual_Blender_starts':0,'actual_models':0,'held_close':pin(root/'mcp/HELD_CLOSE.json'),
          'source_pins':fixture['source_pins'],'historical_native_wire':fixture['native_wire_receipts'],
          'recounted_original_qualification':recounted_original_qualification,
          'host_capture_reencoded':False,'window_ns':closed-started,'through_last_response_ns':last-started})
    print(root/'SUMMARY.json',flush=True)


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and pin(sys.executable)['sha256']==OLD['PYTHON_SHA'],
            'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=RUN/'product')
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--score-closed',action='store_true')
    args = parser.parse_args()
    root = args.output.resolve()
    require(root.parent==RUN and root.name in ('product','product_recovery'),'current_assembly_qualification_root_required')
    if args.worker:
        require(root.is_dir() and not (root/'REPLAY_CLOSE.json').exists(),'current_assembly_worker_root_required')
        _,fixture,_ = inputs()
        raise SystemExit(OLD['retained_workers']()[0]['worker'](
            root,FOOT['BINDINGS']['B'][0],'assembly_cross_asset_qualification',False,source=fixture))
    if args.score_closed:
        score_closed(root)
    else:
        preflight(root)
