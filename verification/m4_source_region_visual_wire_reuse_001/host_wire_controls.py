"""Exercise the installed visual capture host on pinned archived RNA, with no raster."""
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
from time import perf_counter_ns
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'m4_source_region_selective_visual_capture_001'
ROOT = Path('D:/he_m4_source_region_visual_wire_reuse_001').resolve()
BINDING = ROOT/'candidate_install/PRODUCT_RUN_BINDING.json'
QUALIFICATION = Path('D:/he_m4_source_region_live_bounds_qualification_001/REQUESTS.json')
RAW = ROOT/'preflight_host_wire'
CAP = 64*1024*1024
SOURCE_LIMITS = (
    'resident_before', 'resident_after', 'to_mesh', 'triangulations', 'expanded_vertices', 'expanded_triangles',
    'sent_vertices', 'sent_triangles', 'verified_resource_hits', 'mesh_wire_references',
    'metadata_wire_reference', 'residency_fallback', 'wire_known_state',
)


def need(value, reason):
    if not value:
        raise ValueError(reason)


def raw(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False,
                      separators=(',', ':')).encode('utf8')+b'\n'


def pin(path):
    data = path.read_bytes()
    return {'path':str(path),'bytes':len(data),'sha256':sha256(data).hexdigest()}


def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw(value))
    return pin(path)


def request(query):
    return {'target':query['region']['object'],'reference':query['reference'],
            'world_box_m':query['region']['world_box_m']}


def main():
    need(sys.flags.isolated and sys.dont_write_bytecode,'isolated_host_control_interpreter_required')
    binding = json.loads(BINDING.read_bytes())
    install = Path(binding['install_root']).resolve(strict=True)
    need(install==ROOT/'candidate_install/product','installed_candidate_path_changed')
    product = {row['path']:row['sha256'] for row in binding['source_manifest']}
    need(len(product)==144 and all(sha256((install/k).read_bytes()).hexdigest()==digest
                                   for k,digest in product.items()),'installed_candidate_source_manifest_mismatch')
    sys.path[:0] = [str(install),str(Path(binding['dependency_root']).resolve(strict=True)),str(HERE)]
    from human_eye_plugin import blender_host as module
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost
    need(Path(module.__file__).resolve()==install/'human_eye_plugin/blender_host.py',
         'actual_host_module_path_changed')
    module._READONLY_LOADED_HOST_SHA256 = product['human_eye_plugin/blender_host.py']
    connector = BlenderMCPHost(install)
    need(connector._readonly_host_source_sha256 == module._READONLY_LOADED_HOST_SHA256,
         'actual_connector_host_source_sha_changed')

    prior = run_path(str(PRIOR/'replay.py'))
    need(pin(QUALIFICATION)['sha256']==prior['PRIOR_SHA'],'prior_qualification_register_changed')
    records = json.loads(QUALIFICATION.read_bytes())['cases']
    rail = records['RAIL']
    source, colors, queries = prior['frozen_inputs'](SimpleNamespace(
        terminal=Path(rail['terminal']['path']).resolve(),asset=Path(rail['asset']['path']).resolve(),
        asset_sha256=rail['asset']['sha256']))
    origin = {row['label']:row for row in rail['closed_cases']}
    controls = {}

    def fixture():
        bpy = prior['replay_bpy'](source,colors)
        return bpy,module.BlenderSceneHost(bpy,identity_metadata=True,execution_metadata=True)

    def live(bpy, name='M11'):
        obj, = (row for row in bpy.context.scene.objects if row.name==name)
        return obj

    def invoke(host, query, ack, *, cap=CAP, expired=False):
        return host.capture_source_region_visual(query,perf_counter_ns()+(-1 if expired else 10**10),cap,
                                                 known=ack)

    def ack(wire):
        proof = wire['proof']
        return {'generation':proof['generation'],'receipt_sha256':module._digest([proof])}

    def save_wire(stage, wire, bpy, query, known):
        return {'wire':write(RAW/f'{stage}.json',wire),
                'request':write(RAW/f'{stage}_REQUEST.json',{'query':query,'known':known}),
                'work':{key:wire['capture']['work'][key] for key in SOURCE_LIMITS},
                'fixture_mesh_calls':{obj.name:dict(obj.replay_evaluated_calls) for obj in bpy.context.scene.objects
                                      if obj.replay_evaluated_calls['to_mesh']}}

    def read_one(stage, host, bpy, i, known):
        wire = invoke(host,queries[i],known)
        controls[stage] = save_wire(stage,wire,bpy,queries[i],known)
        return wire

    def cold(bpy, host):
        return invoke(host,queries[0],{})

    def mesh(wire, name='M11'):
        row, = (item for item in wire['capture']['meshes'] if type(item) is dict and item['name']==name)
        return row

    def reject(stage, call, error):
        try:
            call()
        except module.BlenderHostError as refusal:
            reason = str(refusal)
            need(reason.startswith(error),'unexpected_control_refusal/'+stage+'/'+reason)
        else:
            raise ValueError('control_did_not_refuse/'+stage)
        controls[stage] = {'reason':reason,'receipt':write(RAW/f'{stage}.json',{'reason':reason})}

    def mutate_same_bounds(bpy):
        obj = live(bpy)
        graph = bpy.context.view_layer.depsgraph
        vertices = obj.evaluated_get(graph).data.vertices
        before = module._source_region_visual_extrema([list(v.co) for v in vertices])
        point = list(vertices[0].co)
        delta = (before[1][0]-before[0][0])*.125
        point[0] += delta if point[0]==before[0][0] else -delta
        need(point!=list(vertices[0].co),'fixture_same_bounds_edit_required')
        vertices[0].co = tuple(point)
        need(module._source_region_visual_extrema([list(v.co) for v in vertices])==before,
             'fixture_same_bounds_edit_changed_extrema')
        graph.updates = [SimpleNamespace(is_updated_geometry=True,id=obj)]
        try:
            for callback in bpy.app.handlers.depsgraph_update_post:
                callback(bpy.context.scene,graph)
        finally:
            graph.updates = []

    bpy,host = fixture()
    previous = None
    for stage,i,label,expected in (('cold_M21',0,'M21',0),('exchange_M19',1,'M19',2),('repeat_M19',1,'M19',9)):
        known = {} if previous is None else {'generation':previous[0]['generation'],
                                             'receipt_sha256':module._digest([previous[0]])}
        data = read_one(stage,host,bpy,i,known)
        hydrated,previous,cost = connector._materialize_visual_capture(
            data,queries[i],perf_counter_ns()+10**10,CAP,previous)
        need(previous is not None and cost['mesh_references']==expected and
             cost['metadata_reused']==(stage!='cold_M21') and
             hydrated['retained_ordinals']==origin[label]['original_kept_ordinals'] and
             hydrated['source_triangle_indices']==origin[label]['source_triangle_indices'] and
             module._digest([hydrated['camera_plan']])==module._digest([origin[label]['old_camera_specification']]),
             'roundtrip_did_not_preserve_prior_views_and_selection/'+stage)
        stats = hydrated['work']
        need(stats['to_mesh']=={'cold_M21':4,'exchange_M19':7,'repeat_M19':0}[stage],
             'roundtrip_actual_mesh_work_changed/'+stage)
        controls[stage]['connector'] = cost
        controls[stage]['hydrated'] = write(RAW/f'{stage}_HYDRATED.json',hydrated)
    reject('wrong_same_generation_receipt',lambda:invoke(host,queries[1],
           {**ack(data),'receipt_sha256':'1'*64}),'source_region_visual_ack_mismatch')
    reject('malformed_receipt',lambda:invoke(host,queries[1],
           {'generation':123,'receipt_sha256':'1'*64}),'source_region_visual_invalid_ack')
    repair = read_one('receipt_recovery',host,bpy,1,ack(data))
    need(repair['capture']['work']['mesh_wire_references']==9,'valid_receipt_not_recovered')

    bpy,host = fixture()
    first = cold(bpy,host)
    mutate_same_bounds(bpy)
    changed = read_one('same_bounds_geometry_invalidated',host,bpy,1,ack(first))
    need(changed['proof']['metadata_sha256']==first['proof']['metadata_sha256']
         and changed['proof']['generation']!=first['proof']['generation']
         and changed['capture']['work']['mesh_wire_references']==0
         and changed['capture']['work']['to_mesh']==8 and mesh(changed)!=mesh(first),
         'same_bounds_geometry_reused')
    controls['same_bounds_geometry_invalidated']['predecessor'] = write(
        RAW/'same_bounds_geometry_invalidated_BEFORE.json',first)

    bpy,host = fixture()
    first = cold(bpy,host)
    key = host._residency_module.identity(live(bpy))
    host._residency.resources.pop(key)
    evicted = read_one('resource_evicted',host,bpy,1,ack(first))
    need(evicted['capture']['work']['mesh_wire_references']==1 and evicted['capture']['work']['to_mesh']==8,
         'evicted_grid_was_not_rebuilt')
    controls['resource_evicted']['predecessor'] = write(RAW/'resource_evicted_BEFORE.json',first)

    bpy,host = fixture()
    first = cold(bpy,host)
    original = live(bpy)
    original.session_uid += 10_000
    replacement = read_one('same_name_different_instance',host,bpy,1,ack(first))
    need(replacement['proof']['generation']!=first['proof']['generation']
         and replacement['capture']['work']['mesh_wire_references']==0
         and replacement['capture']['work']['to_mesh']==8 and
         next(row['instance_id'] for row in replacement['capture']['directory'] if row['name']=='M11')!=
         next(row['instance_id'] for row in first['capture']['directory'] if row['name']=='M11'),
         'prior_instance_was_reused_by_name')
    controls['same_name_different_instance']['predecessor'] = write(RAW/'same_name_different_instance_BEFORE.json',first)

    bpy,host = fixture()
    first = cold(bpy,host)
    visible = live(bpy)
    old = visible.visible_get(view_layer=bpy.context.view_layer)
    visible.visible_get = lambda *, view_layer: not old
    visibility = read_one('metadata_stale_same_generation',host,bpy,1,ack(first))
    need(visibility['proof']['generation']==first['proof']['generation']
         and visibility['proof']['metadata_sha256']!=first['proof']['metadata_sha256']
         and not visibility['capture']['work']['metadata_wire_reference']
         and visibility['capture']['work']['mesh_wire_references']==0
         and not next(row['visible_get'] for row in visibility['capture']['display_snapshot']['objects']
                      if row['host_id']==host.object_id(visible))==old,
         'stale_metadata_reference_admitted')
    controls['metadata_stale_same_generation']['predecessor'] = write(RAW/'metadata_stale_same_generation_BEFORE.json',first)

    bpy,host = fixture()
    first = cold(bpy,host)
    active_callbacks = bpy.app.handlers.depsgraph_update_post
    saved_callbacks = list(active_callbacks)
    active_callbacks.clear()
    mutate_same_bounds(bpy)
    uncached = read_one('missing_invalidation_callback',host,bpy,1,ack(first))
    need(uncached['proof']['generation'] is None and uncached['capture']['work']['resident_after']==0
         and uncached['capture']['work']['to_mesh']==9 and mesh(uncached)!=mesh(first),
         'unproven_invalidation_kept_stale_state')
    active_callbacks.extend(saved_callbacks)
    rebuilt = read_one('recovered_invalidation_callback',host,bpy,1,ack(first))
    need(rebuilt['proof']['generation']!=first['proof']['generation'] and rebuilt['capture']['work']['to_mesh']==9
         and mesh(rebuilt)==mesh(uncached),'reattached_listener_reused_unobserved_geometry')
    controls['missing_invalidation_callback']['predecessor'] = write(RAW/'missing_invalidation_callback_BEFORE.json',first)

    new_bpy,new_host = fixture()
    reopened = read_one('reconnect_previous_host_receipt',new_host,new_bpy,1,ack(first))
    need(reopened['proof']['generation']!=first['proof']['generation'] and
         reopened['capture']['work']['to_mesh']==9 and reopened['capture']['work']['mesh_wire_references']==0,
         'cross_host_receipt_admitted')
    reject('original_budget_reject',lambda:invoke(new_host,queries[1],{},cap=128),
           'source_region_visual_document_budget_exceeded')
    reject('absolute_deadline_reject',lambda:invoke(new_host,queries[1],{},expired=True),
           'source_region_visual_deadline_exceeded')

    assembly = records['ASSEMBLY']
    target = Path(assembly['terminal']['path']).resolve(strict=True)
    need(pin(target)['sha256']==assembly['terminal']['sha256'],'actual_assembly_terminal_source_changed')
    assembly_source = prior['load_module']('_host_wire_assembly',prior['SOURCE_SNAPSHOT'])
    bpy = assembly_source.archive_as_bpy(json.loads(target.read_bytes()))
    host = module.BlenderSceneHost(bpy,identity_metadata=True,execution_metadata=True)
    source_attempts = []
    for obj in bpy.context.scene.objects:
        ev = obj.evaluated_get(bpy.context.view_layer.depsgraph)
        def counted(operation, name):
            def call():
                source_attempts.append(name)
                return operation()
            return call
        ev.to_mesh = counted(ev.to_mesh,obj.name)
    for case in assembly['closed_cases']:
        reject('assembly_static_'+case['label'],
               lambda:invoke(host,request(case['query']),{}),'source_region_visual_unsupported_static_source:')
    need(not source_attempts,'out_of_domain_mesh_expanded')
    for case in assembly['closed_cases']:
        controls['assembly_static_'+case['label']]['mesh_expansions'] = 0
    summary = {'passed':True,'scope':'installed direct host and connector with custody-bound archived RNA',
               'controls':controls,'actual_Blender':0,'software_rasters':0,'model_calls':0,
               'host_source_sha256':product['human_eye_plugin/blender_host.py'],
               'installed_source_sha256':binding['source_sha256'],'install_binding':pin(BINDING),
               'qualification_register':pin(QUALIFICATION),'original_assembly':pin(target)}
    print(write(ROOT/'HOST_WIRE_CONTROLS.json',summary))


if __name__=='__main__':
    main()

