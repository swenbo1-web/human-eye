"""Independent static and recorded-wire review. Does not import product code."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH=ROOT/'verification/m4_active_observation_host_bridge_001'
OUT=Path(__file__).resolve().parent
checks=[];inputs={}
def read(p):
    p=Path(p);b=p.read_bytes();inputs[str(p)]=hashlib.sha256(b).hexdigest();return b
def js(p):return json.loads(read(p))
def source(path, revision=None):
    return subprocess.check_output(['git','-C',str(ROOT),'show',revision+':'+path]).decode() if revision else read(ROOT/path).decode()
def ck(name, ok, detail=None):checks.append({'check':name,'passed':bool(ok),'detail':detail})
def funcs(text):return {n.name:n for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
def dump(n):return ast.dump(n,include_attributes=False)
def code(text,name):return ast.get_source_segment(text,funcs(text)[name])
def enc(v):return json.dumps(v,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')
paths=['active_observation.py','active_observation_images.py','active_observation_host.py','live_service.py','live_spatial_mcp.py','query_policy.py']
texts={p:source('human_eye_plugin/'+p) for p in paths}
oldcore=source('human_eye_plugin/active_observation.py','cd863183')
newcore=texts['active_observation.py']
for name, node in funcs(oldcore).items():
    if name!='prepare_scene':ck('unchanged_core:'+name,dump(node)==dump(funcs(newcore)[name]))
parsebody=code(newcore,'prepare_scene_from_parsed')
ck('parsed_prepare_no_geometry', 'geometry(' not in parsebody)
ck('public_prepare_one_parse', code(newcore,'prepare_scene').count('geometry(scene)')==1)
ck('public_prepare_routes_parsed', 'prepare_scene_from_parsed(objects, triangles, scene_identity, cameras' in code(newcore,'prepare_scene'))
oldimages=source('human_eye_plugin/active_observation_images.py','cd863183')
for name,node in funcs(oldimages).items():
    if name!='ActiveObservationImages':ck('unchanged_image_function:'+name,dump(node)==dump(funcs(texts['active_observation_images.py'])[name]))
host=texts['active_observation_host.py'];observe=code(host,'observe_capture')
ck('one_geometry_call',observe.count('geometry(scene)')==1)
ck('one_mesh_conversion',observe.count('_meshes_from_objects(objects)')==1)
ck('one_parsed_prepare',observe.count('prepare_scene_from_parsed(objects, triangles, scene_identity, cameras)')==1)
ck('shared_prepared_meshes','_prepared_meshes=(objects, meshes)' in observe)
ck('map_references_actual_vertices_faces',"'vertices': mesh['vertices'], 'triangles': mesh['faces']" in code(host,'scene_from_capture'))
calls=[n for n in ast.walk(ast.parse(observe+'\n'+code(host,'scene_from_capture'))) if isinstance(n,ast.Call)]
ck('no_coordinate_rounding',not any(isinstance(n.func,ast.Name) and n.func.id=='round' for n in calls)
   and "'vertices': mesh['vertices'], 'triangles': mesh['faces']" in code(host,'scene_from_capture'))
ck('zero_roi_gates_image_adapter','if include_image and session.regions:' in observe)
ck('no_roi_unknown','no_supported_regions' in observe and "'status': 'unknown' if not session.regions" in observe)
ck('no_image_predicted','prediction_only' in observe and "else 'predicted'" in observe)
ck('intent_before_raster',observe.index('construction_callback(name)')<observe.index('images.render_view(name)'))
ck('feedback_before_final_facts',observe.index('images.observe_frame(frame)')<observe.index('session.short_facts()'))
ck('non_roi_scope_all_objects',"if row['object_index'] not in supported" in observe and "'all_objects_participate_in_occlusion': True" in observe)
ck('host_bound_image_ref',"(binding['binding_sha256'], name, frame['image_sha256'])" in observe)
ck('no_model_consumption_claim',"'external_consumer_verified': False" in observe)
binding=code(host,'source_binding')
for token in ['document_epoch','scene_revision','capture_state','camera_policy','objects','unit','coordinate_frame','capture_scope','source_binding_sha256','binding_sha256']:
    ck('source_binding:'+token,token in binding)
for token in ['host_id','object_name','instance_id','object_index']:
    ck('ordered_mapping:'+token,token in binding)
ck('full_cold_camera_spec',"result['camera_specification'] = copy.deepcopy(cameras)" in binding)
ck('complete_scope_only',"identity.get('capture_scope') != 'complete_scene_meshes'" in binding)

# Existing camera fitting loop retained byte-for-byte modulo named constants,
# static directions, and converting tuple directions to the prior JSON lists.
oldcam=source('verification/m4_active_coverage_001/render/adapter.py','cd863183')
oldfn=funcs(oldcam)['freeze_cameras'];newfn=funcs(host)['freeze_cameras']
class CameraNames(ast.NodeTransformer):
    def visit_Name(self,n):
        return ast.copy_location(ast.Name(id={'ORDER':'CAMERA_ORDER','SIZE':'IMAGE_SIZE','directions':'CAMERA_DIRECTIONS'}.get(n.id,n.id),ctx=n.ctx),n)
    def visit_Call(self,n):
        n=self.generic_visit(n)
        if isinstance(n.func,ast.Name) and n.func.id=='list' and len(n.args)==1 and isinstance(n.args[0],ast.Subscript) and isinstance(n.args[0].value,ast.Name) and n.args[0].value.id=='CAMERA_DIRECTIONS':return n.args[0]
        return n
def normalized_statements(fn):
    start=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='vertices')
    return [dump(CameraNames().visit(copy.deepcopy(n))) for n in fn.body[start:]]
oldstat=normalized_statements(oldfn);newstat=normalized_statements(newfn)
ck('camera_numeric_loop_exact_ast',oldstat[:-1]==newstat[:-1])

service=code(texts['live_service.py'],'LiveSpatialService')
tree=funcs(texts['live_service.py'])['LiveSpatialService']
methods={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
entry=ast.get_source_segment(texts['live_service.py'],methods['_observe_active_observation'])
ck('service_one_actual_capture',entry.count('self.host.capture_scene()')==1)
ck('capture_before_cache',entry.index('self.host.capture_scene()')<entry.index('context.activate(')<entry.index('context.result('))
ck('binding_used_as_selection',"context.activate(captured, 'active_observation', binding)" in entry)
ck('include_image_part_of_result_key',"'include_image': include_image" in entry)
ck('hot_clears_current_work',"result['work'] = {key: 0 for key in generation_work}" in entry and "result['stages'] = {}" in entry)
ck('cold_calls_adapter_only_once',entry.count('observe_capture(captured, directory')==1)
ck('no_write_or_old_renderer',not any(w in entry for w in ('_locked(', 'render_scene_canvas(', '.transform(', 'goal_execution')))
context=source('human_eye_plugin/read_context.py')
ck('context_cache_deepcopies','return copy.deepcopy(cached), True' in context and 'return copy.deepcopy(value), False' in context)
ck('context_token_and_full_selection',"key = (entry, token, query_key(selection))" in context)
ck('context_missing_token_no_reuse','generation = token[:3] if token is not None else object()' in context)

mcp=texts['live_spatial_mcp.py'];content=code(mcp,'_active_observation_content');tool=funcs(mcp)['_tool_result']
ck('active_bundle_6_512',"len(frames) > 6" in content and "\\x00\\x00\\x02\\x00\\x00\\x00\\x02\\x00" in content)
ck('no_base64_in_metadata',"content.append({'type': 'image', 'mimeType': 'image/png', 'data': data})" in content)
ck('full_camera_metadata_excluded',"if key != 'camera_specification'" in content)
ck('content_consumer_unconfirmed',"'consumer_read_status': 'unconfirmed'" in content)
ck('legacy_tool_result_unchanged_except_active_branch', [dump(n) for n in funcs(source('human_eye_plugin/live_spatial_mcp.py','cd863183'))['_tool_result'].body]==[dump(n) for n in tool.body[:1]+tool.body[2:]])
early=tool.body[1]
ck('active_early_return_ignores_response_detail',isinstance(early,ast.If) and 'active_observation' in ast.unparse(early.test) and 'response_detail' not in ast.unparse(early))
ck('active_content_signature_no_detail',all(a.arg!='response_detail' for a in funcs(mcp)['_active_observation_content'].args.args+funcs(mcp)['_active_observation_content'].args.kwonlyargs))

summary=js(BATCH/'RESULT_SUMMARY.json')
for c in summary['cases']:
    tag=c['case'];hot=tag=='same_source_repeat'
    ck(tag+':one_capture',c['work']['capture_calls']==1)
    ck(tag+':parse_prepare',c['work']['geometry_parse_calls']==c['work']['prepare_calls']==(0 if hot else 1))
    ck(tag+':same_new_raster',c['work']['raster_attempts']==c['work']['raster_completed']==(0 if hot or tag=='nonplanar_source' else 2))

# Measure the actual serialized text, not estimates or author audit totals.
wire=[]
for row in js(BATCH/'EXTERNAL_ARCHIVE.json')['files']:
    if '/stdio/' not in row['original_relative_path'] or not row['original_relative_path'].endswith('/RX.bin'):continue
    p=ROOT/row['archive_path'];envelope=js(p)
    result=envelope.get('result',{})
    blocks=result.get('content',[]) if isinstance(result,dict) else []
    if not blocks or blocks[0].get('type')!='text':continue
    text=blocks[0]['text'];v=json.loads(text)
    if v.get('result_kind')!='active_observation':continue
    ck(row['original_relative_path']+':canonical_text',enc(v).decode()==text)
    fields={k:len(enc({k:value}))-2 for k,value in v.items()}
    ck(row['original_relative_path']+':field_partition',sum(fields.values())+len(fields)-1+2==len(text.encode()))
    reduced=copy.deepcopy(v)
    diagnostics=('work','generation_work','stages','generation_stages')
    for k in diagnostics:reduced.pop(k,None)
    for frame in reduced.get('frames',[]):
        for k in ('stages','feedback_stages'):frame.pop(k,None)
    reduced_bytes=len(enc(reduced))
    wire.append({'archive':row['archive_path'],'wire_text_bytes':len(text.encode()),'fields_bytes_excluding_outer_braces_commas':fields,
                 'diagnostics_top_level_fragment_bytes':sum(fields.get(k,0) for k in diagnostics),
                 'after_removing_only_work_and_all_timings_bytes':reduced_bytes,
                 'diagnostics_removed_bytes':len(text.encode())-reduced_bytes,
                 'remaining_facts_bytes':len(enc(v.get('facts'))),'remaining_binding_bytes':len(enc(v.get('binding'))),
                 'facts_subfields_bytes':{k:len(enc(value)) for k,value in v.get('facts',{}).items()},
                 'binding_subfields_bytes':{k:len(enc(value)) for k,value in v.get('binding',{}).items()},
                 'image_blocks':sum(b.get('type')=='image' for b in blocks),
                 'is_same_source_repeat':v.get('work',{}).get('result_cache_hit',False)})
ck('five_actual_active_texts',len(wire)==5)
ck('actual_active_text_total',sum(r['wire_text_bytes'] for r in wire)==101824)
out={'schema':'root-host-bridge-semantics-review-v1','commit':'32a1c6eb47cfa84133d92199387339d407a33cb5',
 'passed':all(c['passed'] for c in checks),'check_count':len(checks),'checks':checks,
 'review_decision':'Functional bridge acceptable; required short-fact delivery has a confirmed P2 gap and needs one bounded projection repair.',
 'findings':[{'severity':'P2','scope':'Default model-facing delivery projection','finding':'Active observation always publishes internal work/generation work, timing trees and per-frame diagnostic paths. response_detail=brief is ignored by its special early branch. No compact active projection exists.',
 'impact':'Functional host integration works, but required short-fact delivery is incomplete; measured payload and no hypothetical failure.'}],
 'wire_breakdown':wire,'wire_text_total_bytes':sum(r['wire_text_bytes'] for r in wire),
 'diagnostics_only_removable_bytes':sum(r['diagnostics_removed_bytes'] for r in wire),
 'limits':['No product imports or dynamic test reruns','No model quality or token measurement','Output reduction computed from existing recorded values; not a new product implementation or benchmark'],
 'audit_correction':{'first_result':'One false-positive no-coordinate-rounding check: substring 256 matched SHA256 identifiers.', 'fix':'Check actual AST round calls and exact direct vertices/faces mapping instead. First script and result preserved.', 'product_calls':0},
 'inputs_sha256':inputs}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'passed':out['passed'],'checks':len(checks),'failed':[c for c in checks if not c['passed']], 'wire':wire,'diagnostics_only_removable_bytes':out['diagnostics_only_removable_bytes']},ensure_ascii=False))
