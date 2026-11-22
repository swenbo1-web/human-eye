"""Check shared normalization through the installed read service without launching Blender."""

import argparse
from contextlib import contextmanager
from copy import deepcopy
import gc
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from weakref import ref
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
REPO = V.parent
EXTERNAL = Path('D:/he_m2_source_region_shared_normalization_001')
RETAINED = Path('D:/he_m2_source_region_normalization_triangle_list_001')
REFERENCE = V/'m2_source_region_normalization_triangle_list_001/RESULT.json'
REFERENCE_GIT = 'c5f987efafc5af3607497307baf0b6ccd30f23f5'
BASE = '31e9b46a68e5f791df9a75a1bad11caa8a6e8410'
SHARED = 'geometry_normalization_shared_hit'


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def digest(data):
    return {'bytes':len(data),'sha256':sha256(data).hexdigest()}


def pin(path):
    real=path.resolve(strict=True)
    return {'path':str(real),**digest(real.read_bytes())}


def stable(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,
                             allow_nan=False,default=str).encode()).hexdigest()


def freeze_inputs():
    raw=subprocess.check_output(['git','show',REFERENCE_GIT+':'+REFERENCE.relative_to(REPO).as_posix()],cwd=REPO)
    require(REFERENCE.read_bytes()==raw,'published_original_index_not_its_git_blob')
    index_path=RETAINED/'sealed/RAW_INDEX.json'
    archive_path=RETAINED/'sealed/ORIGINAL_RUNTIME.zip'
    expected=json.loads(raw)['raw_evidence_local']
    index=read(index_path)
    require(index['member_count']==expected['member_count'] and index['archive']==expected['archive']
            and digest(archive_path.read_bytes())=={key:expected['archive'][key] for key in ('bytes','sha256')},
            'original_archive_mismatch')
    pins=[pin(REFERENCE),pin(index_path),pin(archive_path)]
    with ZipFile(archive_path) as archive:
        def member(relative):
            local=RETAINED/relative
            data=archive.read('runtime/'+relative)
            require(digest(data)==index['members']['runtime/'+relative] and local.read_bytes()==data,
                    'old_member_bytes_changed/'+relative)
            pins.append(pin(local))
            return json.loads(data)
        captures={k:member('arms/'+k+'/CAPTURE_01.json') for k in ('DP','HP','RP')}
        second=member('arms/DP/CAPTURE_02.json')
        require(captures['DP']==second,'old_dual_not_same_exact_capture')
        inputs={k:[member(f'arms/{k}/mcp/rpc_{i+3:02d}/TX.bin')['params']['arguments']
                   for i in range(1,n+1)] for k,n in (('DP',2),('HP',1),('RP',1))}
        canonical=[member(f'arms/DP/product_full/call_{i:03d}/SERVICE_RESULT.json') for i in (1,2)]
    require([len(q['query']['region']['source_triangle_indices']) for q in inputs['DP']]==[311,331],
            'old_DP_two_distinct_selection_counts_changed')
    return captures,inputs,canonical,pins


class Host:
    def __init__(self):
        self.capture=None
        self.calls=0
        self.lock=None

    def capture_scene(self):
        require(self.lock._is_owned(),'capture_executed_without_read_context_lock')
        self.calls+=1
        return self.capture


class Controls:
    def __init__(self,live,sr,context,path,binding,candidate):
        self.live,self.sr,self.context=live,sr,context
        self.path,self.binding,self.candidate=path,binding,candidate
        self.measurements=[]

    def service(self,label):
        root=self.path/label
        root.mkdir(exist_ok=False)
        config=root/'CONFIG.json'
        with config.open('x',encoding='utf8') as out:
            json.dump({'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
                       'project_root':self.binding['install_root'],'state_file':str(root/'state.json'),
                       'audit_file':str(root/'audit.jsonl'),'request_budget_s':30,
                       'expected_identity':{'source_sha256':self.binding['source_sha256']}},out)
        host=Host()
        service=self.live.LiveSpatialService(config,host=host,production_mode=True)
        host.lock=service._read_context.lock
        return service,host

    @contextmanager
    def instrument(self,service):
        sr=self.sr
        original=(sr._validate_scene,sr.geometry,sr._observation_target_cameras)
        log={'scene_validation':0,'geometry':0,'camera':0}

        def instrument_call(fn,key):
            def call(*args,**kw):
                require(service._read_context.lock._is_owned(),'unlocked_preparation/'+key)
                log[key]+=1
                return fn(*args,**kw)
            return call

        sr._validate_scene,sr.geometry,sr._observation_target_cameras=(
            instrument_call(f,name) for f,name in zip(original,log,strict=True))
        try:
            yield log
        finally:
            sr._validate_scene,sr.geometry,sr._observation_target_cameras=original

    def execute(self,label,service,host,capture,query,expected,*,error=None):
        host.capture=capture
        before=host.calls
        with self.instrument(service) as work:
            try:
                result=service.observe(label,include_image=False,query=query)
            except ValueError as exc:
                if error is None or str(exc)!=error:
                    raise
                result=None
                reason=str(exc)
            else:
                require(error is None,'registered_bad_capture_or_query_accepted/'+label)
                reason=None
        require(host.calls==before+1,'eligible_request_did_not_capture_once/'+label)
        shared=expected=='shared' and self.candidate
        if expected in ('fresh','shared','hot'):
            required={'scene_validation':int(expected!='hot'),
                      'geometry':int(expected!='hot' and not shared),'camera':int(expected!='hot')}
        else:
            required=expected
        require(work==required,'actual_instrumented_prepare_work_changed/'+label+'/'+str(work))
        row={'label':label,'observed_calls':work,'error':reason}
        if result is not None:
            meter=result['work']
            require(meter['capture_calls']==1 and meter['ordered_geometry_identity_calls']==1
                    and meter['prepare_cache_hit']==(expected=='hot')
                    and meter['prepare_calls']==work['camera']
                    and meter['geometry_normalization_calls']==work['geometry']
                    and meter['camera_preparation_calls']==work['camera']
                    and meter['region_array_preparation_calls']==work['camera']
                    and meter['raster_attempts']==0 and result['frames']==[]
                    and result['execution_authority'] is False and result['read_only'] is True,
                    'recorded_work_or_read_contract_does_not_match_path/'+label)
            if self.candidate:
                require(meter[SHARED] is shared,'reported_shared_hit_does_not_match_real_calls/'+label)
                if expected!='hot':
                    prep=result['stages']['region_preparation']
                    require(prep['scene_validation']['elapsed_ns']>0,'complete_scene_validation_not_timed')
            row['work']={key:meter.get(key) for key in ('prepare_calls','prepare_cache_hit',
                                      'geometry_normalization_calls',SHARED)}
            row['semantic_sha256']=semantic(result)
        self.measurements.append(row)
        return result

    def registry(self,service):
        context=service._read_context
        with context.lock:
            value=context.current_prepared('source_regions')
            require(value is not None and set(value)=={'aliases','regions'},'unexpected_source_registry_shape')
            require(all(set(state['prepared'])<= {'source_regions'} and state['normalized'] is None
                        for state in context._selections.values()),'extra_prepare_resource_or_normalized_holder')
            return value

    def prepared(self,service,result):
        return self.registry(service)['regions'][result['region_ref']['region_id']]


def semantic(result):
    value={k:result[k] for k in ('status','facts','region_ref','source_mapping','frames','observation_status')}
    runtime=('runtime_source_sha256','source_status','source_check_scope','disk_status')
    binding={k:v for k,v in result['binding'].items() if k not in runtime}
    task=deepcopy(result['task_result'])
    for k in runtime:
        task['binding'].pop(k,None)
    return stable({**value,'binding':binding,'task_result':task})


def cases_from(capture,template):
    return [{**deepcopy(template),'region':{'object':{'name':'Obj_08'},'source_triangle_indices':[i]}}
            for i in range(12)]


def resign_display(capture):
    snap=capture['display_snapshot']
    snap.pop('sha256',None)
    snap['sha256']=stable(snap)


def arm_binding(suite,capture):
    bind=suite.sr.source_binding(capture)
    return bind,suite.sr.ordered_geometry_identity(capture,bind)


def independent_alias(first,second,share):
    require((first.objects is second.objects) is share and (first.meshes is second.meshes) is share
            and first.objects==second.objects and first.binding['geometry_identity']==second.binding['geometry_identity'],
            'mathematical_scene_or_shared_tuple_identity_changed')
    buffers=0
    for f,s in zip(first.meshes,second.meshes,strict=True):
        require((f is s) is share and f.object_id==s.object_id and f.name==s.name,
                'wrong_shared_mesh_object')
        for kind in ('vertices','faces','edges'):
            fp,sp=getattr(f,kind),getattr(s,kind)
            require((fp is sp) is share and fp.tobytes()==sp.tobytes()
                    and (not share or not fp.flags.writeable and not sp.flags.writeable),
                    'accessibility_or_mutability_contract_changed/'+kind)
            buffers+=1
    require(first.region_mesh is not second.region_mesh and first.source_mapping is not second.source_mapping
            and first.binding is not second.binding and first.cameras is not second.cameras
            and first.region_ref!=second.region_ref and first.binding['camera_identity']!=second.binding['camera_identity'],
            'selection_owned_camera_or_compact_array_was_not_independent')
    return buffers


def positive(s,captures,requests,original,queries):
    service,host=s.service('dual_real')
    capture=captures['DP']
    first=s.execute('real_upper',service,host,capture,requests['DP'][0]['query'],'fresh')
    second=s.execute('real_lower',service,host,capture,requests['DP'][1]['query'],'shared')
    for old,new in zip(original,(first,second),strict=True):
        require(semantic(old)==semantic(new),'actual_dual_result_differs_from_original_truth')
    buffers=independent_alias(s.prepared(service,first),s.prepared(service,second),s.candidate)
    as_ref={k:v for k,v in requests['DP'][1]['query'].items() if k!='region'}
    as_ref['region_ref']=second['region_ref']
    repeated=s.execute('same_region_by_current_ref',service,host,capture,as_ref,'hot')
    require(semantic(repeated)==semantic(second),'hot_reference_changed_actual_result')
    small,h=s.service('reverse_reference')
    second=s.execute('reverse_seed',small,h,captures['HP'],queries[8],'fresh')
    discovered=s.sr.prepare_region(captures['HP'],queries[0]).region_ref
    reverse={k:v for k,v in queries[0].items() if k!='region'}
    reverse['region_ref']=discovered
    first=s.execute('reverse_fresh_ref',small,h,captures['HP'],reverse,'shared')
    independent_alias(s.prepared(small,second),s.prepared(small,first),s.candidate)
    return {'equal_to_original_dual':True,'identical_readonly_buffer_objects':buffers if s.candidate else 0,
            'tested_buffers':buffers,'fresh_valid_region_ref_and_reverse_order':True}


def invalidated(s,capture,queries):
    changes={}
    for field in ('epoch','revision','selection_key','instance_id'):
        v=deepcopy(capture)
        state=v['capture_state']
        old=state[field]
        state[field]=old+1 if type(old) is int else old+'-control'
        changes[field]=v
    v=deepcopy(capture)
    v.pop('capture_state')
    changes['no_version']=v
    v=deepcopy(capture)
    v['revision']+='-changed-host-revision'
    changes['scene_revision']=v
    v=deepcopy(capture)
    v['meshes'].reverse()
    changes['ordered_objects']=v
    v=deepcopy(capture)
    v['meshes'][0]['faces'].reverse()
    changes['ordered_unselected_faces']=v
    v=deepcopy(capture)
    v['meshes'][0]['vertices'][0][0]+=0.125
    changes['unselected_vertex_geometry']=v
    v=deepcopy(capture)
    v['meshes'][0]['name']+='-renamed'
    changes['unselected_name']=v
    v=deepcopy(capture)
    host_id=v['meshes'][0]['object_id']
    v['host_identity']['object_instances'][host_id]+='-distinct'
    for row in v['display_snapshot']['objects']:
        if row['host_id']==host_id:
            row['instance_id']=v['host_identity']['object_instances'][host_id]
    resign_display(v)
    changes['equal_geometry_different_host_instance']=v
    v=deepcopy(capture)
    v['display_snapshot']['objects'][0]['visible_get']=not v['display_snapshot']['objects'][0]['visible_get']
    resign_display(v)
    changes['display_changed']=v
    v=deepcopy(capture)
    v.pop('display_snapshot')
    changes['display_missing']=v
    for label,value in changes.items():
        service,host=s.service('invalidation_'+label)
        old=s.execute(label+'_seed',service,host,capture,queries[0],'fresh')
        first=s.prepared(service,old)
        fresh=s.execute(label+'_changed',service,host,value,queries[8],'fresh')
        second=s.prepared(service,fresh)
        require(first.objects is not second.objects and first.meshes is not second.meshes,
                'borrowed_across_new_strict_capture_state/'+label)
        if label=='no_version':
            s.execute('second_unversioned_capture',service,host,value,queries[0],'fresh')
    return list(changes)


def rejection(s,capture,queries):
    service,host=s.service('unhashed_validation')
    first=s.execute('bad_capture_seed',service,host,capture,queries[0],'fresh')
    before=s.prepared(service,first)
    membership=list(s.registry(service)['regions'])
    correct=arm_binding(s,capture)
    for label,field,value,reason in (
            ('unhashed_bad_edge','edges',[[0,10**6]],'invalid topology indices'),
            ('unhashed_bad_axes','local_axes',[[1,0,0],[0,1,0]],'invalid local_axes'),
            ('unhashed_bad_pivot','pivot_world',[0,0],'invalid pivot_world')):
        altered=deepcopy(capture)
        altered['meshes'][0][field]=value
        require(arm_binding(s,altered)==correct,'unhashed_negative_changed_binding/'+label)
        s.execute(label,service,host,altered,queries[8],{'scene_validation':1,'geometry':0,'camera':0},error=reason)
        require(list(s.registry(service)['regions'])==membership and s.prepared(service,first) is before,
                'invalid_new_prepare_registered_or_released_old_good_state/'+label)
    bad=deepcopy(queries[8])
    bad['region']['source_triangle_indices']=[10**6]
    s.execute('bad_selected_index',service,host,capture,bad,{'scene_validation':0,'geometry':0,'camera':0},
              error='source_region_unique_current_triangle_indices_required')
    original=s.sr._observation_target_cameras
    def refused(*args,**kw):
        raise ValueError('control_camera_factory_exception')
    s.sr._observation_target_cameras=refused
    try:
        s.execute('factory_failed_before_registration',service,host,capture,queries[8],
                  {'scene_validation':1,'geometry':int(not s.candidate),'camera':1},
                  error='control_camera_factory_exception')
    finally:
        s.sr._observation_target_cameras=original
    require(list(s.registry(service)['regions'])==membership,'factory_failure_registered_selection')
    recovered=s.execute('retry_valid_new_selection',service,host,capture,queries[8],'shared')
    independent_alias(before,s.prepared(service,recovered),s.candidate)
    stale={k:v for k,v in queries[8].items() if k!='region'}
    stale['region_ref']=recovered['region_ref']
    changed=deepcopy(capture)
    changed['capture_state']['revision']+=1
    s.execute('stale_ref_after_revision',service,host,changed,stale,{'scene_validation':0,'geometry':0,'camera':0},
              error='source_region_ref_capture_generation_changed')
    s.execute('valid_recovery_new_revision',service,host,changed,queries[8],'fresh')
    malformed=deepcopy(capture)
    malformed['meshes'][0]['vertices']=[[*row,0] for row in malformed['meshes'][0]['vertices']]
    s.execute('malformed_ordered_geometry_shape',service,host,malformed,queries[0],
              {'scene_validation':1,'geometry':0,'camera':0},error='invalid vertices shape')
    return {'same_digest_bad_edges_axes_pivot_rejected':True,'failed_factory_left_no_registered_region':True}


def lifetime(s,capture,queries):
    service,host=s.service('region_capacity')
    first=s.execute('capacity_first',service,host,capture,queries[0],'fresh')
    first_id=first['region_ref']['region_id']
    prepared=ref(s.prepared(service,first))
    for i in range(1,9):
        s.execute('capacity_fill_'+str(i),service,host,capture,queries[i],'shared')
    registry=s.registry(service)
    require(len(registry['regions'])==len(registry['aliases'])==8
            and first_id not in registry['regions'] and first_id not in registry['aliases'].values(),
            'existing_eight_region_fifo_boundary_changed')
    require(prepared() is None,'evicted_region_record_remained_reachable')
    replay={k:v for k,v in queries[0].items() if k!='region'}
    replay['region_ref']=first['region_ref']
    s.execute('evicted_ref_rebuilt_on_current_capture',service,host,capture,replay,'shared')
    del registry
    another,h=s.service('read_context_capacity')
    original=s.execute('selection_capacity_first',another,h,capture,queries[0],'fresh')
    buf=ref(s.prepared(another,original).meshes[0].vertices)  # unselected and unmeasured fixture mesh
    selection_ref=ref(s.prepared(another,original))
    for i in range(1,9):
        alt=deepcopy(capture)
        alt['capture_state']['selection_key']+='-lru-'+str(i)
        s.execute('capture_key_capacity_'+str(i),another,h,alt,queries[0],'fresh')
    gc.collect()
    require(len(another._read_context._selections)==8 and selection_ref() is None and buf() is None,
            'existing_lru_eviction_boundary_or_borrowed_buffer_reachability_changed')
    current=s.registry(service)
    item=next(iter(current['regions'].values()))
    active=ref(item)
    old_buf=ref(item.meshes[0].vertices)
    del current,item
    revised=deepcopy(capture)
    revised['capture_state']['revision']+=1
    s.execute('generation_reset_rebuild',service,host,revised,queries[8],'fresh')
    gc.collect()
    require(active() is None and old_buf() is None and len(service._read_context._selections)==1,
            'generation_reset_did_not_release_old_region_or_borrowed_buffer')
    return {'registry_limit':8,'capture_selection_limit':8,'dependent_buffer_released':True,
            'captured_and_prepared_under_read_lock':True}


def qualification(binding_path,prior_path,output):
    binding=read(binding_path)
    candidate=binding['preparation_git']!=BASE
    require(candidate is (prior_path is not None),'candidate_must_bind_baseline_proof')
    install=Path(binding['install_root']).resolve(strict=True)
    sys.path[:0]=[str(install),binding['dependency_root']]
    from human_eye_plugin import live_service,read_context,source_region
    manifest={row['path']:row['sha256'] for row in binding['source_manifest']}
    require(len(manifest)==143,'wrong_installed_package_roster')
    files=[pin(Path(module.__file__)) for module in (live_service,read_context,source_region)]
    require(all(row['sha256']==manifest[Path(row['path']).relative_to(install).as_posix()] for row in files),
            'actual_installed_sources_do_not_match_runtime_binding')
    captures,requests,original,pins=freeze_inputs()
    s=Controls(live_service,source_region,read_context,output.parent/(output.stem.lower()+'_scenarios'),binding,candidate)
    s.path.mkdir(parents=True,exist_ok=False)
    queries=cases_from(captures['HP'],requests['HP'][0]['query'])
    # The renderer callback is never permitted in a no-image proof.
    require(all(not item['include_image'] for item in requests['DP']),'unexpected_image_in_original_dual')
    pos=positive(s,captures,requests,original,queries)
    changed=invalidated(s,captures['HP'],queries)
    bad=rejection(s,captures['HP'],queries)
    retained=lifetime(s,captures['HP'],queries)
    if prior_path:
        prior=read(prior_path)
        def outputs(rows):
            return [(v['label'],v.get('semantic_sha256'),v.get('error')) for v in rows]
        require(prior['passed'] and prior['binding_git']==BASE
                and outputs(prior['requests'])==outputs(s.measurements),'signed_baseline_read_result_or_rejection_changed')
        pins.append(pin(prior_path))
    report={'passed':True,'installed':True,'binding_git':binding['preparation_git'],
            'source_sha256':binding['source_sha256'],'wheel_sha256':binding['wheel_sha256'],
            'new_Blender':0,'new_models':0,'new_rasters':0,'positive':pos,'invalidation':changed,
            'rejections':bad,'retention':retained,'requests':s.measurements,
            'source_pins':[pin(Path(__file__)),pin(binding_path),*files,*pins]}
    with output.open('x',encoding='utf8',newline='\n') as out:
        json.dump(report,out,ensure_ascii=False,indent=2,allow_nan=False)
        out.write('\n')
    print(json.dumps({'passed':True,'binding_git':report['binding_git'],'cases':len(s.measurements)}),flush=True)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--binding',type=Path,required=True)
    cli.add_argument('--baseline-proof',type=Path)
    cli.add_argument('--output',type=Path,required=True)
    a=cli.parse_args()
    require(a.output.resolve().is_relative_to(EXTERNAL.resolve()),'new_owned_control_directory_required')
    qualification(a.binding.resolve(strict=True),a.baseline_proof,a.output.resolve())
