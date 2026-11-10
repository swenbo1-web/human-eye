"""One owned N/P preflight on the original M4 asset; no consumer or image."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import types

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
ROOT=BATCH.parents[1]
SHARED=Path('D:/hefe/verification/fixes/20261103_spatial_perception_qual002/shared')
CANONICAL='7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
TRUTH_SHA='2bb917d6d96bfec4b8dffbdbc437f70185f532877e9bcb45855ea2d988e6a1b2'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
read=lambda path:json.loads(Path(path).read_bytes())


def save(path,value):
    with Path(path).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')


def load_bytes(name,path):
    raw=path.read_bytes()
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),module.__dict__)
    return module,raw


def body(reply):
    blocks=reply['result']['content']
    assert len(blocks)==1 and blocks[0]['type']=='text'
    return json.loads(blocks[0]['text'])


def compare_task_relations(value,truth):
    assert value['status']=='observed' and value['execution_authority'] is False
    assert value['target']['name']==truth['target_id']
    assert value['context']['runtime_source_sha256']==CANONICAL
    assert value['context']['unit']=='m' and value['context']['coordinate_frame']=='world'
    expected={row['neighbor_id']:row for row in truth['relations']}
    rows=[]
    for candidate in value['candidates']:
        reference=expected[candidate['name']]
        relation=candidate['closed_solid_relation']
        assert relation['status']=='measured'
        gap=candidate['separation_gap']
        if relation['value']=='penetrating':
            classification='solid_overlap'
            assert gap['status']=='not_applicable' and gap['value'] is None
        else:
            assert relation['value'] in ('separated','touching')
            assert gap['status']=='measured'
            distance=gap['value']
            classification='within_contact_tolerance' if distance<=.00025 else 'separated'
            assert abs(distance-reference['minimum_distance_mm']/1000)<=1e-6
        assert classification==reference['classification']
        rows.append(dict(name=candidate['name'],classification=classification,original_pair=candidate))
    assert set(row['name'] for row in rows)==set(expected)
    return rows


def main():
    started=time.perf_counter_ns()
    out=HERE/'run_02';out.mkdir(exist_ok=False)
    assert not (BATCH/'GO.json').exists(), 'preparation cannot start a model GO'
    ready=read(BATCH/'installation/READY.json')
    assert ready['source_sha256']==CANONICAL and ready['installed_identity_passed']
    truth_raw=(BATCH/'scoring/TRUTH.json').read_bytes();assert sha(truth_raw)==TRUTH_SHA
    truth=json.loads(truth_raw)
    before={str(path):sha(path.read_bytes()) for path in SHARED.iterdir() if path.is_file()}
    plan=read(BATCH/'PLAN.json')
    source_copy=BATCH/plan['inputs']['scene']
    assert before[str(SHARED/'scene.blend')]==sha(source_copy.read_bytes())==truth['source_scene_sha256']
    before.update({str(path):sha(path.read_bytes()) for path in (BATCH/'input').iterdir() if path.is_file()})
    driver,driver_raw=load_bytes('_m4_owned_preflight_driver',BATCH/'runtime/driver.py')
    probe_path=ROOT/'verification/m1_task_entry_001_eval/preflight_client.py'
    client,probe_raw=load_bytes('_m4_original_verified_thin_probe',probe_path)
    actor_raw=(BATCH/'runtime/actor.py').read_bytes()
    save(out/'FROZEN_PREFLIGHT.json',dict(product_commit='107641ec19919d56aa843c1949261590fc338148',
        source_sha256=CANONICAL,source_count=137,actor_sha256=sha(actor_raw),driver_sha256=sha(driver_raw),
        reused_probe_path=str(probe_path),reused_probe_sha256=sha(probe_raw),
        protected_original_inputs=before,private_truth_sha256=TRUTH_SHA,
        query_policy='neutral first two sorted meshes plus one independently certified target/three-neighbor query; no query or role reaches a consumer',
        nearest_policy='preserve expected acquisition_invalid_triangle_structure refusal on original raw quads/ngons; do not triangulate or edit copies',
        model_calls=0,new_geometry=0,new_images=0))
    results=[];baseline=common=None
    for group in ('N','P'):
        folder=process=None;cell_started=time.perf_counter_ns()
        result=dict(group=group,errors=[],started_ns=cell_started,entry_results={},finish=None)
        try:
            folder,process,_=driver.prepare({'task':'T1','group':group},output=out/group,cell_started_ns=cell_started)
            initial=read(folder/'owner/INITIAL.json')
            assert len(initial['objects'])==28
            if baseline is None:
                baseline=initial
                with (HERE/'SOURCE_SNAPSHOT.json').open('xb') as stream:
                    stream.write((folder/'owner/INITIAL.json').read_bytes())
                save(HERE/'SOURCE_SNAPSHOT_BINDING.json',dict(path='preflight/SOURCE_SNAPSHOT.json',
                    sha256=sha((HERE/'SOURCE_SNAPSHOT.json').read_bytes()),source_asset_sha256=truth['source_scene_sha256'],
                    purpose='complete native local geometry/transform/unit source binding only; not independent relation truth',
                    mesh_objects=28,oracle_path='scoring/TRUTH.json',oracle_sha256=TRUTH_SHA))
            else:driver.snapshot_binding(initial,baseline)
            names=sorted(row['name'] for row in initial['objects'])
            code="import json\nprint(json.dumps({'unit_scale_m':bpy.context.scene.unit_settings.scale_length,'scene_objects':len(bpy.context.scene.objects),'mesh_names':sorted(o.name for o in bpy.context.scene.objects if o.type=='MESH'),'mesh_objects':sum(o.type=='MESH' for o in bpy.context.scene.objects)}))"
            messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'m4-no-model-preflight','version':'001'}}},
                {'jsonrpc':'2.0','method':'notifications/initialized'},
                {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'execute_blender_code','arguments':{'code':code}}}]
            if group=='P':
                messages += [
                    {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'human_eye_spatial_relations','arguments':{'target':{'name':names[0]},'candidates':[{'name':names[1]}]}}},
                    {'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'human_eye_surface_nearest','arguments':{'target':{'name':names[0]}}}},
                    {'jsonrpc':'2.0','id':6,'method':'tools/call','params':{'name':'human_eye_spatial_relations','arguments':{'target':{'name':truth['target_id']},'candidates':[{'name':row['neighbor_id']} for row in truth['relations']]}}}]
            probe=client.probe(ready['dependency_python'],folder/'ENDPOINT.json',folder/'thin_probe',messages)
            assert probe['confirmed'], 'original thin probe lifecycle not confirmed'
            replies={reply['id']:reply for reply in probe['responses']}
            tools=replies[2]['result']['tools']
            if common is None:
                assert len(tools)==1 and tools[0]['name']=='execute_blender_code'
                common=tools[0];save(HERE/'COMMON_NATIVE.json',common)
            else:assert tools==[common]+read(HERE/'P/PUBLIC_TOOLS.json')
            save(folder/'ACTUAL_PUBLIC_TOOLS.json',tools)
            assert replies[3]['result']['isError'] is False
            native=body(replies[3]);assert native['status']=='success'
            counts=json.loads(native['result']['result'])
            assert counts['scene_objects']==32 and counts['mesh_objects']==28 and counts['mesh_names']==names
            assert counts['unit_scale_m']==initial['unit_scale_m']
            result['native_counts']=counts
            if group=='P':
                assert replies[4]['result']['isError'] is False
                neutral=body(replies[4]);assert neutral['context']['runtime_source_sha256']==CANONICAL
                result['entry_results']['neutral_relations']=neutral
                nearest=body(replies[5])
                if replies[5]['result']['isError']:
                    assert 'acquisition_invalid_triangle_structure' in json.dumps(nearest)
                    result['entry_results']['nearest']={'admitted':False,'source_domain_refusal':nearest,
                        'scope':'tool reachable, original quad/ngon source outside current nearest acquisition; no geometry mutation or retry'}
                else:
                    assert nearest['binding']['runtime_source_sha256']==CANONICAL
                    result['entry_results']['nearest']={'admitted':True,'original_result':nearest}
                assert replies[6]['result']['isError'] is False
                actual=body(replies[6]);result['entry_results']['task_relations']=actual
                result['task_relations_against_independent_truth']=compare_task_relations(actual,truth)
                identity=read(folder/'owner/PLUGIN_INITIALIZE.json')['result']['_meta']['human_eye']
                assert identity['source_kind']=='installed_distribution' and identity['source_sha256']==CANONICAL
                result['installed_identity']=identity
            result['thin_exit_confirmed']=probe['client_exit_confirmed']
        except BaseException as exc:
            result['errors'].append(dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc()))
        finally:
            if process is not None:
                try:
                    result['finish']=driver.finish(folder,process)
                    assert result['finish']['confirmed']
                    close=result['finish']['close']
                    assert close['geometry_unchanged'] and close['asset_unchanged'] and close['zero_new_images_budget_met']
                    assert close['native_close']['source_file_unchanged'] and close['native_close']['protected_files_unchanged']
                    assert close['worker_closed']['initial_geometry_fingerprint']==close['worker_closed']['final_geometry_fingerprint']
                    driver.snapshot_binding(read(folder/'owner/INITIAL.json'),read(folder/'owner/FINAL.json'))
                except BaseException as exc:
                    result['errors'].append(dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc()))
            result['ended_ns']=time.perf_counter_ns()
            result['passed']=not result['errors'] and bool(result['finish'] and result['finish']['confirmed'])
            if folder is not None:save(folder/'PREFLIGHT_RESULT.json',result)
            results.append(result)
        if not result['passed']:break
    after={name:sha(Path(name).read_bytes()) for name in before}
    unchanged=before==after
    source_unchanged=(BATCH/'runtime/actor.py').read_bytes()==actor_raw and (BATCH/'runtime/driver.py').read_bytes()==driver_raw
    value=dict(passed=len(results)==2 and all(row['passed'] for row in results) and unchanged and source_unchanged,
        cases=results,original_inputs_sha256_before=before,original_inputs_sha256_after=after,
        original_inputs_unchanged=unchanged,runtime_source_unchanged=source_unchanged,
        elapsed_ns=time.perf_counter_ns()-started,model_calls=0,constructed_geometry=0,new_images=0,
        qualification='Actual installed/native entry, independent three-pair geometry and readonly close preflight only; nearest source refusal is a retained capability gap, not a successful nearest measurement.')
    save(out/'RESULTS.json',value)
    print(json.dumps({'passed':value['passed'],'cases':len(results),'errors':[e['message'] for row in results for e in row['errors']],
        'nearest_admission':next((row['entry_results'].get('nearest',{}).get('admitted') for row in results if row['group']=='P'),None)}))
    raise SystemExit(0 if value['passed'] else 1)


if __name__=='__main__':main()
