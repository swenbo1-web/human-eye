"""Count installed geometry work and verify exact source, instance and caller contracts."""

import argparse
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
REPO = NS.parents[1]
BASE = 'cca20c17401e75f564a9e881da977e5448bc3f94'
SOURCE_RUN = Path('D:/he_m4_source_region_nonplanar_short_circuit_001')
DEFAULT_RUN = Path('D:/he_m4_region_task_global_first_frame_001')
TARGET_RUN = Path('D:/he_m4_target_001')
SOURCE_COMMIT = 'a640d12814a5d0432f7b80ad690f2f1cc994a59a'
DEFAULT_COMMIT = '42ebf86d034fff9cc4bc788f815bd701b8e26eae'
TARGET_COMMIT = '03eb4e2971891dfe0160972cbcf974e3dcf1a21c'
SOURCE_SPEC = 'verification/m4_source_region_nonplanar_short_circuit_001/RESULT.json'
DEFAULT_SPEC = 'verification/m4_region_task_global_first_frame_001/RAW_INDEX.json'
TARGET_SPEC = 'verification/m4_target_acquisition_001/'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(data):
    return {'bytes':len(data),'sha256':sha256(data).hexdigest()}


def pin(path):
    return {'path':str(path.resolve(strict=True)),**digest(path.read_bytes())}


def read(path):
    return json.loads(path.read_bytes())


def stable(value):
    return sha256(json.dumps(value,default=str,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def git(commit, key):
    return subprocess.check_output(['git','show',f'{commit}:{key}'],cwd=REPO)


def committed(commit, key, pins):
    local = REPO/key
    data = git(commit,key)
    require(local.read_bytes()==data,'committed_evidence_on_disk_changed/'+key)
    pins.append(pin(local))
    return json.loads(data)


def indexed(archive, index, root, path, pins):
    source = root/path
    name = 'runtime/'+path
    data = archive.read(name)
    require(digest(data)==index['members'][name] and source.read_bytes()==data,'immutable_archive_member_changed/'+path)
    pins.append(pin(source))
    return json.loads(data)


def cases(pins):
    original = committed(SOURCE_COMMIT,SOURCE_SPEC,pins)['raw_evidence_local']
    idx_path = SOURCE_RUN/'sealed/RAW_INDEX.json'
    index = read(idx_path)
    zipped = SOURCE_RUN/'sealed/ORIGINAL_RUNTIME.zip'
    require(index['archive']==original['archive'] and index['member_count']==original['member_count']
            and digest(zipped.read_bytes())=={k:index['archive'][k] for k in ('sha256','bytes')},
            'source_region_archive_is_not_published_original')
    pins.extend((pin(idx_path),pin(zipped)))
    with ZipFile(zipped) as archive:
        for label,slot,num in (('yanyite_upper','P1',1),('yanyite_lower','P1',3),
                               ('obj08','HP',1),('n15','RP',1)):
            root = 'arms/'+slot
            case = lambda path: indexed(archive,index,SOURCE_RUN,root+'/'+path,pins)
            request = case(f'mcp/rpc_{num+3:02d}/TX.bin')['params']['arguments']
            yield label,case(f'CAPTURE_{num:02d}.json'),request,case(f'product_full/call_{num:03d}/SERVICE_RESULT.json')
    idx = committed(DEFAULT_COMMIT,DEFAULT_SPEC,pins)
    zipped = REPO/Path(DEFAULT_SPEC).with_name('ORIGINAL_RUNTIME.zip')
    require(digest(zipped.read_bytes())=={k:idx['archive'][k] for k in ('sha256','bytes')},'default_archive_changed')
    pins.append(pin(zipped))
    with ZipFile(zipped) as archive:
        for label,slot,num in (('ordinary','controls/OP',4),('region_task','arms/HP',1)):
            case = lambda path: indexed(archive,idx,DEFAULT_RUN,slot+'/'+path,pins)
            request = case(f'mcp/rpc_{num+3:02d}/TX.bin')['params']['arguments']
            yield label,case(f'CAPTURE_{num:02d}.json'),request,case(f'product_full/call_{num:03d}/SERVICE_RESULT.json')
    index = json.loads(git(TARGET_COMMIT,TARGET_SPEC+'RUNTIME_ARCHIVE.json'))
    subdir = 'qualification/A_peripheral_02/'
    rows = {row['relative_path']:row for row in index['files']}

    def retained(name):
        row = rows[subdir+name]
        data = git(TARGET_COMMIT,TARGET_SPEC+row['archive_path'])
        local = TARGET_RUN/subdir/name
        require(digest(data)=={k:row[k] for k in ('sha256','bytes')} and local.read_bytes()==data,
                'target_capture_or_request_changed/'+name)
        pins.append(pin(local))
        return json.loads(data)

    request = retained('REQUEST_01.json')['params']['arguments']
    yield 'target',retained('CAPTURE_01.json'),request,None


def exact_objects(scene):
    def independent_key(points):
        x,y,z = points
        return min((x,y,z),(y,z,x),(z,x,y))

    result, order = [],[]
    for obj,source in enumerate(scene['objects']):
        vertices = tuple(tuple(Fraction(value) for value in p) for p in source['vertices'])
        faces = tuple(tuple(face) for face in source['triangles'])
        keys = []
        for idx,face in enumerate(faces):
            points = tuple(vertices[v] for v in face)
            oriented = independent_key(points)
            keys.append(oriented)
            order.append((oriented,obj,idx,points))
        result.append((vertices,faces,(tuple(sorted(vertices)),tuple(sorted(keys))),str(source.get('name',''))))
    return tuple(result),sorted(order,key=lambda row:row[0])


@contextmanager
def count_geometry(ao):
    old_tri,old_canon,old_profile = ao.Triangle,ao.canonical_triangle,sys.getprofile()
    work = {'global_constructions':0,'canonical_face_calls':0,'global_sorts':0}
    code = ao.geometry.__code__

    def tri(*args,**kwargs):
        if sys._getframe(1).f_code is code:
            work['global_constructions'] += 1
        return old_tri(*args,**kwargs)

    def canonical(*args,**kwargs):
        # Object keys use a generator on older Python and a comprehension on newer Python.
        frame = sys._getframe(1)
        while frame is not None:
            if frame.f_code is code:
                work['canonical_face_calls'] += 1
                break
            frame = frame.f_back
        return old_canon(*args,**kwargs)

    def profile(frame,event,value):
        if (event=='c_call' and frame.f_code is code and value.__name__=='sort'
                and type(value.__self__) is list):
            work['global_sorts'] += 1

    ao.Triangle,ao.canonical_triangle = tri,canonical
    sys.setprofile(profile)
    try:
        yield work
    finally:
        sys.setprofile(old_profile)
        ao.Triangle,ao.canonical_triangle = old_tri,old_canon


def meter(ao, function):
    with count_geometry(ao) as work:
        value = function()
    return value,work


def equal_work(work, faces, emits):
    desired = {'global_constructions':faces if emits else 0,
               'canonical_face_calls':faces*(2 if emits else 1),'global_sorts':int(emits)}
    require(work==desired,'unexpected_normalization_work '+str(work)+' expected '+str(desired))


def geometry_result(value,expected,order,emits):
    objects,triangles,identity = value
    require(objects==expected and identity==stable(tuple(sorted(row[2] for row in objects))),
            'canonical_object_keys_source_rows_or_scene_identity_changed')
    require(type(triangles) is tuple and [(t.key,t.object_index,t.triangle_index,t.vertices) for t in triangles]
            == (order if emits else []),'global_triangles_changed_order_orientation_or_indices')


def mesh_bind(meshes):
    return [(m.object_id,m.name,{name:{'shape':arr.shape,'dtype':str(arr.dtype),**digest(arr.tobytes())}
                                for name,arr in ((k,getattr(m,k)) for k in ('vertices','faces','edges'))})
            for m in meshes]


def prepare_case(ao,sr,host,label,capture,request,producer,expected,order,candidate):
    query = request['query']
    prepared,work = meter(ao,lambda:sr.prepare_region(capture,query))
    equal_work(work,len(order),not candidate)
    require(tuple((a,b,key[0],name) for a,b,key,name in prepared.objects)==expected
            and tuple((key[1],key[2]) for _,_,key,_ in prepared.objects)==
            tuple((row['host_id'],row['instance_id']) for row in prepared.binding['objects']),
            'source_region_world_points_faces_or_current_instances_changed')
    for attr,key in (('region_ref','region_ref'),('source_mapping','source_mapping')):
        require(getattr(prepared,attr)==producer[key],'archived_current_reference_or_mapping_changed/'+label)
    require(prepared.region_facts==producer['facts']['region']
            and all(prepared.binding[key]==producer['binding'][key] for key in prepared.binding)
            and prepared.cameras==producer['binding']['camera_specification'],
            'archived_selection_identity_or_current_camera_changed/'+label)
    separate = None
    if label=='n15':
        region=sr._selected_rectangle(prepared)
        require(region is not None,'registered_rectangle_disappeared')
        triangles=sr._displayed_front_triangles(prepared,region,lambda _:None)
        require(bool(triangles) and all(isinstance(t,ao.Triangle) for t,_ in triangles),'local_occluder_triangle_path_disappeared')
        separate = {'local_occluder_triangles':len(triangles),'data_sha256':stable([
            (t.object_index,t.triangle_index,t.vertices,t.key,tie) for t,tie in triangles])}
    identity={k:getattr(prepared,k) for k in ('binding','region_ref','objects','source_triangle_indices',
        'source_vertex_indices','region_facts','source_mapping','cameras')}
    identity['mesh_arrays'] = mesh_bind((*prepared.meshes,prepared.region_mesh))
    return {'label':label,'normalization':work,'faces':len(order),'identity_sha256':stable(identity),
            'scene_identity':prepared.binding['geometry_identity'],'local':separate}


def default_case(ao,host,task,label,capture,request,producer,expected,order,candidate):
    module = task if label=='region_task' else host
    geometry = module.geometry
    seen = []

    def dispatch(scene,**kwargs):
        require(not kwargs,'default_caller_overrode_triangle_list/'+label)
        value = geometry(scene)
        geometry_result(value,expected,order,True)
        seen.append(True)
        return value

    module.geometry = dispatch
    def stop_raster(_):
        raise AssertionError('offline_default_control_raster_forbidden')
    try:
        value,work = meter(ao,lambda:host.observe_capture(capture,Path.cwd(),include_image=False,
                         construction_callback=stop_raster,region_task=request['query'].get('region_task')))
    finally:
        module.geometry = geometry
    equal_work(work,len(order),True)
    require(seen==[True] and not value['frames'] and value['work']['raster_attempts']==0
            and value['binding']['geometry_identity']==stable(tuple(sorted(row[2] for row in expected))),
            'default_observation_geometry_or_output_changed/'+label)
    if producer is not None:
        require(value['binding']['geometry_identity']==producer['binding']['geometry_identity'],
                'default_observation_no_longer_matches_archived_geometry/'+label)
    payload={k:v for k,v in value.items() if k not in ('stages','work')}
    return {'label':label,'normalization':work,'faces':len(order),'identity_sha256':stable(payload),
            'scene_identity':value['binding']['geometry_identity'],'call_reached_original_result':True,
            'observation_status':value['observation_status']}


def outcome(action):
    try:
        return {'status':'returned','sha256':stable(action())}
    except (ValueError,IndexError,KeyError,TypeError) as error:
        return {'status':'rejected','type':type(error).__name__,'message':str(error)}


def synthetic(ao,host,sr,candidate,small_capture,query):
    points = [(Fraction(1,3),0,0),(1,0,0),(0,1,0)]
    def obj(name,faces):
        return {'name':name,'vertices':points,'triangles':faces}
    records = []
    for label,scene in (
            ('empty_scene',{'objects':[]}),
            ('stable_equal_keys_and_reverse_winding',{'objects':[
                obj('same',[(1,2,0),(0,1,2),(0,2,1)]),obj('same',[(2,0,1)])]}),
            ('retain_degenerate_faces',{'objects':[obj('degenerate',[(0,0,1),(1,1,1)])]})):
        expected,order = exact_objects(scene)
        val,work = meter(ao,lambda:ao.geometry(scene))
        geometry_result(val,expected,order,True)
        equal_work(work,len(order),True)
        skipped = None
        if candidate:
            val,skipped = meter(ao,lambda:ao.geometry(scene,include_triangles=False))
            geometry_result(val,expected,order,False)
            equal_work(skipped,len(order),False)
        records.append({'label':label,'default':work,'skipped':skipped,'same_scene_sha256':val[2]})
    for label,faces in (('negative_index',[(0,1,-1)]),('too_large_index',[(0,1,3)]),
                        ('boolean_index',[(0,True,1)]),('invalid_face_length',[(0,1,2,0)])):
        scene={'objects':[obj('valid',[(0,1,2)]),obj('invalid',faces)]}
        default=outcome(lambda:ao.geometry(scene))
        require(default=={'status':'rejected','type':'ValueError','message':'invalid_triangle_indices'},
                'invalid_face_rejection_changed/'+label)
        if candidate:
            require(outcome(lambda:ao.geometry(scene,include_triangles=False))==default,'skip_bypassed_validation/'+label)
        records.append({'label':label,'default':default})
    versionless=deepcopy(small_capture)
    versionless.pop('capture_state',None)
    outcome_now=outcome(lambda:sr.prepare_region(versionless,query).region_ref)
    records.append({'label':'missing_version_keeps_previous_region_contract','default':outcome_now})
    empty={**small_capture,'meshes':[]}
    records.append({'label':'empty_capture_keeps_previous_region_rejection','default':outcome(lambda:sr.prepare_region(empty,query))})
    return records


def checked(path, baseline_path):
    binding=read(path)
    candidate=binding['preparation_git']!=BASE
    require(candidate==(baseline_path is not None),'baseline_proof_required_only_for_candidate')
    root=Path(binding['install_root']).resolve(strict=True)
    require(len(binding['source_manifest'])==143,'unexpected_source_manifest_roster')
    sys.path[:0]=[str(root),binding['dependency_root']]
    from human_eye_plugin import active_observation as ao, active_observation_host as host
    from human_eye_plugin import active_observation_region_task as task, source_region as sr
    pins=[pin(path),pin(Path(__file__))]
    sources={row['path']:row['sha256'] for row in binding['source_manifest']}
    for module in (ao,host,task,sr):
        path=Path(module.__file__).resolve(strict=True)
        receipt=pin(path)
        require(receipt['sha256']==sources[path.relative_to(root).as_posix()],'module_does_not_match_isolated_install')
        pins.append(receipt)
    real,versionless_capture = [],None
    for label,capture,request,producer in cases(pins):
        expected,order=exact_objects(host.scene_from_capture(capture))
        if request['query']['mode']=='source_region':
            if label=='obj08':
                versionless_capture=(capture,request['query'])
            case=prepare_case(ao,sr,host,label,capture,request,producer,expected,order,candidate)
        else:
            case=default_case(ao,host,task,label,capture,request,producer,expected,order,candidate)
        real.append(case)
    controls=synthetic(ao,host,sr,candidate,*versionless_capture)
    if candidate:
        prior=read(baseline_path)
        require(prior['binding_git']==BASE and prior['passed'] and
                [(row['label'],row['identity_sha256'],row.get('local')) for row in real]==
                [(row['label'],row['identity_sha256'],row.get('local')) for row in prior['real_cases']],
                'prepared_source_or_default_result_diverges_from_baseline')
        require([{k:v for k,v in item.items() if k!='skipped'} for item in controls]==
                [{k:v for k,v in item.items() if k!='skipped'} for item in prior['synthetic']],
                'synthetic_default_rejection_or_identity_changed')
        pins.append(pin(baseline_path))
    return {'passed':True,'installed':True,'binding_git':binding['preparation_git'],'source_sha256':binding['source_sha256'],
            'real_cases':real,'synthetic':controls,'source_pins':list({row['path']:row for row in pins}.values()),
            'new_models':0,'new_Blender':0,'new_rasters':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding',type=Path,required=True)
    parser.add_argument('--baseline-proof',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=checked(args.binding,args.baseline_proof)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
    print(json.dumps({key:result[key] for key in ('passed','binding_git')},ensure_ascii=False))
