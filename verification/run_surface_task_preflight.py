"""Frozen installed surface protocol on the separately built owned B1 assets.

No user GUI, action tool, saved source edit or paid model. Fixture IDs are
supplied by the owner, not evidence of a natural language automatic selector.
"""
import argparse,copy,hashlib,importlib.util,json,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def main(args):
    args.output.mkdir(exist_ok=False)
    spec=importlib.util.spec_from_file_location('_surface_installed_entry',args.entry);entry=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=entry;spec.loader.exec_module(entry);proof=entry.validate_binding(expected_python=sys.executable)
    sys.path.insert(0,proof['module_root']);identity,_=entry.verify_imported_runtime(proof)
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    from human_eye_plugin import structure_task_control as control,mesh_structure as raw
    from human_eye_plugin.surface_reference import ReferenceRegistry,ReferenceIntent
    from human_eye_plugin.surface_task_service import consume_packet
    rows=[]
    for asset in json.loads((args.assets/'ASSETS.json').read_text(encoding='utf8'))['rows']:
        scene=Path(asset['scene']).resolve();assert scene.parent.parent==args.assets.resolve()
        source_sha=hashlib.sha256(scene.read_bytes()).hexdigest();assert source_sha==asset['scene_sha256']
        folder=args.output/asset['case']['id'];folder.mkdir(exist_ok=False);config=folder/'CONFIG.json'
        pins={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id','source_kind')};pins.update(protocol_version='2025-03-26',mode='live')
        save(config,dict(schema_version='1.0',enabled=True,project_root=proof['module_root'],expected_identity=pins,state_file='STATE.json',audit_file='AUDIT.jsonl',
            structure_task_file='TASK.json',structure_task_control_file='CONTROL.json',surface_diagnostics_enabled=True,quad_size=384,max_sessions=4))
        host=BlenderProcessHost(args.blender,scene);registry=ReferenceRegistry();start=time.perf_counter_ns()
        try:
            service=LiveSpatialService(config,host=host,surface_references=registry);server=LiveSpatialMCPServer(service)
            save(folder/'INITIALIZE.json',server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=1,method='initialize',params=dict(protocolVersion='2025-03-26',capabilities={}))))
            for target in asset['targets']:
                registration=control.begin(config,'surface:'+str(target['index']),target['object_id']);task_ref=registration['task_ref'];records=[]
                def call(operation,request,**fields):
                    query=dict(mode='mesh_surface',operation=operation,request_id=request,task_ref=task_ref);query.update(fields)
                    began=time.perf_counter_ns()
                    reply=server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=request,method='tools/call',params=dict(name='human_eye_scene_observe',
                        arguments=dict(session_id='surface-preflight',focal_id=target['object_id'],include_image=False,query=query,response_detail='full'))))
                    wire=json.dumps(reply,allow_nan=False).encode();elapsed=time.perf_counter_ns()-began
                    save(folder/('%d_%s.json'%(target['index'],request)),reply)
                    metadata=json.loads(next(x['text'] for x in reply['result']['content'] if x['type']=='text'))
                    record=dict(operation=operation,request=request,elapsed_ns=elapsed,wire_bytes=len(wire),isError=reply['result']['isError'],
                        status=metadata['status'],reason=metadata.get('reason',metadata.get('error')),diagnostic=metadata.get('diagnostic'),task_budget=metadata.get('task_budget'))
                    records.append(record);return metadata
                first=call('diagnose','first')
                for index in range(2):call('diagnose','repeat'+str(index))
                registration_source_ns=None;reference_kind=None
                if first.get('diagnostic'):
                    began=time.perf_counter_ns();current,packet,_=consume_packet(host,target['object_id'],time.perf_counter_ns()+30_000_000_000,0,geometry=False)
                    reference=copy.deepcopy(current);reference_kind='explicit_owner_intent_unchanged_copy'
                    if asset['case']['id']=='dented_sheet':
                        value=copy.deepcopy(current['raw'])
                        for vertex in value['vertices']:vertex[2]=0.
                        metadata={k:current['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')}
                        metadata['object_id']='owned-analytic-flat-reference'
                        reference=raw.prepare_raw(value,metadata);reference_kind='registered_analytic_flat_source_index_correspondence'
                    ref=registry.bind(reference,current,packet['triangles'],packet['triangle_polygons'],intent=ReferenceIntent(reference_kind,'owner registered intended surface','same_index_from_owned_copy'))
                    registration_source_ns=time.perf_counter_ns()-began
                    deviation=call('reference','reference',reference_ref=ref)
                    if asset['case']['id']=='dented_sheet':assert deviation['diagnostic']['changed_count']>0
                    else:assert deviation['diagnostic']['changed_count']==0
                    preview=call('restore_preview','preview',reference_ref=ref,indices=[0])
                    assert preview['diagnostic']['status']=='preview_only' and not preview['diagnostic']['execution_authority']
                    registry.revoke(ref);revoked=call('reference','revoked',reference_ref=ref)
                    assert 'revoked' in revoked['reason']
                control.close(config,task_ref)
                rows.append(dict(case=asset['case']['id'],target=target['name'],provenance=asset['case']['provenance'],records=records,
                    registration_source_ns=registration_source_ns,registration_extra_typed_capture=1 if registration_source_ns is not None else 0,
                    reference_kind=reference_kind,source_file_sha256=source_sha))
                print(json.dumps(dict(case=asset['case']['id'],target=target['name'],status=first['status'],reason=first.get('reason'),
                    found=first.get('diagnostic',{}).get('found'),complete=first.get('diagnostic',{}).get('scan_complete'))),flush=True)
        finally:host.close()
        assert host._process.poll()==0 and hashlib.sha256(scene.read_bytes()).hexdigest()==source_sha
        save(folder/'LIFECYCLE.json',dict(child_exit_code=0,source_file_unchanged=True,elapsed_ns=time.perf_counter_ns()-start))
    save(args.output/'RESULT.json',dict(runtime_source=identity['source_sha256'],rows=rows,all_protocol_assertions_passed=True,
        mathematical_oracle='separate_exact_edge_plane_test_suite',no_geometry_mutation_commands_sent=True,formal_model_calls=0,actual_Codex_consumption=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--entry',type=Path,required=True);p.add_argument('--blender',type=Path,required=True);main(p.parse_args())
