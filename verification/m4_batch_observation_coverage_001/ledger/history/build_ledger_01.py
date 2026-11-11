"""Extract six sealed supplemental reads using stdlib parsing only.

Blender code is read as text and parsed as AST. It is never executed.
Only public tool records, frozen scoring rules and capture unit metadata are
read. Final answer files, model costs and production solvers are not opened.
"""
import ast
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
BATCH=HERE.parent
ROOT=BATCH.parents[1]
PREVIOUS=ROOT/'verification/m4_local_relation_consumption_001'
PUBLIC=PREVIOUS/'quality_handoff/handoff_01/public'
MECHANISM=Path('D:/hefe/verification/fixes/20261111_m4_local_consumption_cost_review/mechanism/MECHANISM.json')
CYCLE='M4-BATCH-OBSERVATION-COVERAGE-001'
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')


def put(path,raw):
    assert path.resolve().is_relative_to(HERE.resolve())
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)


def source(path):
    raw=path.read_bytes()
    return raw,{'path':str(path.resolve()),'sha256':sha(raw),'bytes':len(raw)}


def read_native(attempt,index):
    request=attempt['request']
    assert request['params']['name']=='execute_blender_code'
    code=request['params']['arguments']['code']
    ast.parse(code)
    assert len(attempt['responses'])==1 and attempt['responses'][0]['kind']=='RESPONSE.json'
    value=attempt['responses'][0]['value']['result']
    assert value['isError'] is False and len(value['content'])==1 and value['content'][0]['type']=='text'
    text=value['content'][0]['text'];native=json.loads(text)
    assert native['status']=='success' and native['result']['executed'] is True
    stdout=native['result']['result'];assert isinstance(stdout,str)
    pointer='/owner_attempts/'+str(index)
    return {'attempt_order':attempt['order'],'attempt_array_index':index,
      'request_pointer':pointer+'/request','code_pointer':pointer+'/request/params/arguments/code',
      'response_pointer':pointer+'/responses/0/value',
      'transport_text_pointer':pointer+'/responses/0/value/result/content/0/text',
      'stdout_pointer_in_decoded_transport_text':'/result/result',
      'code':code,'code_utf8_sha256':sha(code.encode('utf8')),
      'returned_transport_text':text,'returned_transport_text_utf8_sha256':sha(text.encode('utf8')),
      'stdout':stdout,'stdout_utf8_sha256':sha(stdout.encode('utf8')),
      'stdout_utf8_bytes':len(stdout.encode('utf8')),
      'original_request_files':attempt['source_files']}


def stage1_fields(stdout):
    rows={}
    for line in stdout.splitlines():
        if line.startswith(('{','[')):
            try:data=json.loads(line)
            except ValueError:continue
            if isinstance(data,dict):
                for name,value in data.items():
                    if isinstance(value,dict) and 'lo' in value:
                        rows[name]={'name':name,'data':value['data'],'bounds':{'min':value['lo'],'max':value['hi']},'center':value['center']}
            elif isinstance(data,list):
                for value in data:
                    if isinstance(value,dict) and {'name','mesh','min','max','center'}<=set(value):
                        rows[value['name']]={'name':value['name'],'data':value['mesh'],
                          'bounds':{'min':value['min'],'max':value['max']},'center':value['center']}
            continue
        match=re.fullmatch(r'(N\d{2})(?: mesh)? (G\d+) min (\[.*?\]) max (\[.*?\]) center (\[.*?\])',line)
        if match:
            name,data,low,high,center=match.groups()
            rows[name]={'name':name,'data':data,'bounds':{'min':ast.literal_eval(low),'max':ast.literal_eval(high)},'center':ast.literal_eval(center)}
    assert len(rows)==28,'Expected the complete delivered 28-mesh stage-1 spatial directory'
    return rows


def printed_geometry(stdout,kind):
    rows=[]
    for number,line in enumerate(stdout.splitlines(),1):
        if not re.match(r'N\d{2} ',line):continue
        if ('vertices' not in line and 'coordinate levels' not in line):continue
        name=line[:3];start=line.index('[')
        literal=ast.literal_eval(line[start:])
        rows.append({'object_name':name,'stdout_line_number':number,'line_utf8_sha256':sha(line.encode('utf8')),
          'field':kind,'returned_values':literal})
    return rows


def field_requirement(field,objects,disposition,required,explanation,source_pointer):
    return {'field':field,'fixture_objects':objects,'disposition':disposition,
      'frozen_scoring_requirement':required,'reason':explanation,'scoring_pointer':source_pointer}


def main():
    mechanism_raw,mechanism_source=source(MECHANISM);mechanism=json.loads(mechanism_raw)
    index_raw,index_source=source(PUBLIC/'INDEX.json')
    assert sha(index_raw)==mechanism['public_index_sha256']
    scoring_raw,scoring_source=source(PREVIOUS/'scoring/SCORING_CONTRACT.json');scoring=json.loads(scoring_raw)
    unit_raw,unit_source=source(ROOT/'verification/m4_observation_baseline_001/preflight/SOURCE_SNAPSHOT.json')
    unit_capture=json.loads(unit_raw);assert unit_capture['unit_scale_m']==1.0
    shape_config={
      'answer_1acac64d24eaf8de':('vertices_world',['N16','N24','N12'],8,7),
      'answer_25b1ec4200384d46':('vertices_world',['N16','N12','N24','N04','N19'],8,7),
      'answer_3f87212b9e9cabc9':('vertices_world',['N16','N24','N12','N04','N19','N28'],9,None),
      'answer_84be72fecbf32dd2':('vertices_world',['N16','N13','N08','N28'],9,7),
      'answer_9b56fad6b7eb11c5':('vertices_world',['N16','N13','N28','N24','N12'],9,None),
      'answer_a4b1331500dcff86':('world_coordinate_levels',['N16','N13','N28','N04','N19'],8,7)}
    observed=[];source_hashes={}
    for row in mechanism['rows']:
        if row['anonymous_id'] not in shape_config:continue
        identity=row['anonymous_id'];path=PUBLIC/identity/'tool_evidence.json'
        raw,record_source=source(path);assert sha(raw)==row['evidence_sha256']
        evidence=json.loads(raw);attempts=evidence['owner_attempts']
        assert len(attempts)==3 and [attempt['request']['params']['name'] for attempt in attempts]==[
          'execute_blender_code','human_eye_spatial_relations','execute_blender_code']
        first=read_native(attempts[0],0);last=read_native(attempts[2],2)
        assert last['code']==row['last_native_code']
        shape,objects,precision,first_precision=shape_config[identity]
        geometry=printed_geometry(last['stdout'],shape)
        assert [item['object_name'] for item in geometry]==objects
        assert not any(isinstance(node,ast.Attribute) and node.attr in ('polygons','loop_triangles') for node in ast.walk(ast.parse(last['code'])))
        directory=stage1_fields(first['stdout'])
        relation_tool=attempts[1]['responses'][0]['value']['result']
        assert relation_tool['isError'] is False
        relation=json.loads(relation_tool['content'][0]['text'])
        assert relation['target']['name']=='N16'
        assert [item['name'] for item in relation['candidates']]==['N13','N08','N28']
        localized='local_evidence' in relation['candidates'][0]['closed_solid_relation']
        assert localized is row['crossing_evidence_present']
        completed_events=[item for item in evidence['public_tool_events'] if item['phase']=='item.completed']
        matching=[item for item in completed_events if item['event'].get('arguments',{}).get('code')==last['code']]
        assert len(matching)==1
        public_result=matching[0]['event']['result']
        assert public_result==attempts[2]['responses'][0]['value']['result']
        ref_geometry=[name for name in objects if name in ('N24','N12','N04','N19')]
        local_geometry=[name for name in objects if name not in ref_geometry]
        demands=[]
        for item in geometry:
            name=item['object_name']
            if name in ref_geometry:
                reason='Confirms reference-object shape or cross section. Target-position arithmetic needs only the already delivered bounds/centers.'
                required='optional_reference_shape_confirmation'
            else:
                reason='Adds selected coordinate-level shape information beyond a whole-object AABB. Its necessity depends on which sufficient local relation/material evidence is already available.'
                required='conditional_geometry_support_for_required_local_evidence_and_role'
            demands.append(field_requirement(shape,[name],'new_selected_geometry',required,reason,
              '/roles' if name!='N16' else '/target'))
        demands.extend([
          field_requirement('object_bounds_and_center',['N15','N16','N18','N25','N12','N24','N10','N04','N19'],
            'already_in_stage1','required_basis_for_target_position_explanations',
            'All these objects occur in the first read. A fresh full mesh traversal is unnecessary to recover bounds already delivered at its disclosed precision.','/target/three_conditions'),
          field_requirement('rail_center_Z_midpoint_beam_maxY_pipe_center_XY_midpoint',['N12','N24','N10','N04','N19'],
            'derived_arithmetic','required_equivalent_explanations_not_prescribed_numbers',
            'Midpoints and the beam rear bound follow directly from stage-1 bounds/centers. The exact unrounded last-read numbers require the same source precision.','/target/accepted_reasoning'),
          field_requirement('candidate_center_XY_distance_and_position_predicates',['N15','N16','N18','N25'],
            'derived_arithmetic','all_three_conditions_required',
            'Compute from candidate centers and the reference midpoints with task-provided comparisons. No closed-solid or surface-distance solver occurs in the last code.','/target/three_conditions'),
          field_requirement('closed_solid_relation_surface_gap_nearest_points',['N16','N13','N08','N28'],
            'already_in_relations','required_supported_three_pair_classifications',
            'The preceding relation response already provides three ordered pair classifications, unsigned surface measurements and witnesses.','/roles'),
          field_requirement('faces_or_triangles',local_geometry,'not_returned_in_this_read',
            'conditional_for_generic_material_or_opening_shape_proof',
            'No final native read returned connectivity. Vertex clouds or per-axis coordinate levels alone cannot determine a general surface, material boundary or hole. Current-capture topology is an explicit optional geometry field.','/evidence_policy/computed_from_observed_geometry')])
        relation_summary=[]
        contracts=relation['measurement_contracts']
        for candidate in relation['candidates']:
            relation_summary.append({'candidate_name':candidate['name'],
              'closed_solid_relation':{**contracts.get('closed_solid_relation',{}),**candidate['closed_solid_relation']},
              'surface_proximity':{**contracts.get('surface_proximity',{}),**candidate['surface_proximity']},
              'separation_gap':{**contracts.get('separation_gap',{}),**candidate['separation_gap']}})
        extraction={'source':record_source,'stage1':first,'last_native_read':last,
          'parsed_last_geometry':geometry,'stage1_directory':directory,
          'preceding_relation_response':relation,'preceding_relation_pointer':'/owner_attempts/1/responses/0/value/result/content/0/text',
          'completed_public_event_last_read_matches_owner':True,
          'public_event_source_hashes':{'source_sha256':matching[0]['source_sha256'],'source_line_sha256':matching[0]['source_line_sha256']}}
        extraction_path=HERE/'observations'/(identity+'.json');put(extraction_path,encoded(extraction))
        observed.append({'anonymous_id':identity,'tool_evidence_source':record_source,
          'extraction':'ledger/observations/'+extraction_path.name,'extraction_sha256':sha(extraction_path.read_bytes()),
          'last_attempt_order':3,'last_code_utf8_sha256':last['code_utf8_sha256'],
          'last_stdout_utf8_sha256':last['stdout_utf8_sha256'],
          'code_pointer':last['code_pointer'],'response_pointer':last['response_pointer'],
          'native_stdout_pointer':{'transport_text_pointer':last['transport_text_pointer'],'decoded_json_pointer':'/result/result'},
          'geometry_field':shape,'geometry_objects':objects,'optional_reference_geometry_objects':ref_geometry,
          'selected_local_geometry_objects':local_geometry,'topology_returned':False,
          'last_geometry_decimal_rounding':precision,'stage1_decimal_rounding':first_precision,
          'native_transform_policy':'Recorded Blender mathutils matrix_world @ raw data.vertices, followed by requested decimal rounding. No evaluated-mesh claim is inferred from this code.',
          'native_unit_scale_applied_in_code':False,'shared_capture_unit_scale_m':1.0,
          'local_crossing_evidence_already_present':localized,
          'existing_relations':relation_summary,'demand_items':demands,
          'remaining_precision_gap':'A seven-decimal delivered directory gives rounded-input arithmetic, not bit-identical reconstruction of later unrounded outputs. Standardize source and precision on both comparison paths.',
          'remaining_shape_gap':'Topology and semantic hole/material reconstruction were not acquired by these six reads. Current capture topology can support selected shape inspection, while generic semantic recognition remains outside this thin projection.'})
        source_hashes[str(path.resolve())]=sha(raw)
    assert len(observed)==6
    metadata={
      'cycle_id':CYCLE,'phase':'OFFLINE_DEMAND_ANALYSIS','observation_count':6,
      'sources':{'mechanism':mechanism_source,'public_index':index_source,'scoring_contract':scoring_source,
        'shared_capture_unit_metadata':unit_source},
      'source_policy':{'geometry_sources':'Owner tool responses and corresponding consumer-public event values only.',
        'Blender_code_execution':False,'final_answers_opened':False,'production_solver_imports':False,
        'mechanism_use':'Select the six recorded routes and cross-check exact last code. Its answer summaries are not geometry inputs.'},
      'generic_field_requirements':{
        'directory':['source_binding','unit','coordinate_frame','objects.id','objects.name','objects.world_bounds.min','objects.world_bounds.max'],
        'directory_center':'An optional explicit field derived from the same bounds; omit it on both paths if the simplified request derives it.',
        'selected_optional_geometry':['vertices_world','triangles OR polygons with an explicit topology encoding and capture-local vertex indices'],
        'selected_existing_relations':['ordered_pair_binding','closed_solid_relation','surface_proximity','nearest_witness','available_local_evidence'],
        'source_binding':'Same immutable capture, document/object instance binding and source revision. Separate captures need explicit identity/currentness checks.',
        'precision':'For the prospective comparison, both paths use the same finite binary64 capture coordinates and round-trip JSON encoding, or one identically declared quantization policy.'},
      'frozen_scoring_required':{
        'target':scoring['target'],'roles':scoring['roles'],'complete_correct':scoring['complete_correct'],
        'primary_fixed_denominators':scoring['primary_fixed_denominators'],
        'no_required_triangle_index_list':scoring['natural_language_policy']['no_required_triangle_index_list'],
        'no_forced_route':scoring['evidence_policy']['no_forced_route'],
        'initial_image_limit':scoring['evidence_policy']['initial_image_limit']},
      'optional_explanation_material':['Full upper/lower reference-rail vertices or wall thickness',
        'Full dual-pipe vertices or circular cross-section detail','An extra strict shared-interior point when another sufficient localized overlap certificate is present',
        'Numerical hole dimensions beyond the sufficient source-bound opening/material argument',
        'Repeated target-predicate arithmetic after its input bounds/centers are already available'],
      'coverage_counts':{'selected_full_world_vertex_reads':5,'coordinate_level_only_reads':1,'reads_returning_topology':0,
        'preceding_relations_with_crossing_local_evidence':3,'preceding_relations_without_crossing_local_evidence':3,
        'stage1_seven_decimal_directories':4,'stage1_without_additional_decimal_rounding':2},
      'fixture_only_baseline_request_recommendation':{
        'status':'Recommendation to freeze before measurement, not a product rule.',
        'stage1':{'selection':'all 28 meshes in the same capture','fields':['id','name','world_bounds.min','world_bounds.max'],
          'precision':'finite binary64 round-trip','optional_center':'derive from identical bounds on both paths'},
        'stage2':{'explicit_geometry_objects':['N16','N13','N08','N28'],'geometry_fields':['vertices_world','triangles'],
          'ordered_relation_pairs':[['N16','N13'],['N16','N08'],['N16','N28']],
          'relation_fields':'Exactly the same already recorded relation payload and source binding on both offline projections.',
          'precision':'same capture/world metres/finite binary64 round-trip, same current-capture index ordering',
          'reference_full_meshes':'Not requested by default. Stage-1 bounds support their task-position use.'},
        'simplification_candidate':'After proving coverage, inspect whether the separator/locator full meshes are redundant with the same recorded local/nearest relation evidence. Apply any selected-object reduction identically to both paths and preserve the before/after request.',
        'fair_native_baseline':'Allow a native caller the same two batched reads, same cached first capture, same explicit objects, same topology/precision and same already available relation facts. Geometry/relations absent from native data are an explicit acquisition/compute requirement, never free work.',
        'sampling_scope':'Identifiers and task thresholds occur only in this fixture recommendation. Generic code accepts selectors and fields.'},
      'observations':observed,'new_model_consumers':0,'new_product_processes':0,'new_Blender_sessions':0,'new_images':0}
    put(HERE/'DEMAND_LEDGER.json',encoded(metadata))
    intact=all(sha(Path(path).read_bytes())==digest for path,digest in source_hashes.items())
    assert intact
    put(HERE/'ANALYSIS_RECEIPT.json',encoded({'passed':True,'observation_count':6,
      'tool_evidence_sources_unchanged':intact,'script_sha256':sha(Path(__file__).read_bytes()),
      'ledger_sha256':sha((HERE/'DEMAND_LEDGER.json').read_bytes()),'source_code_read_as_text_only':True,
      'final_answers_opened':False,'model_consumers':0,'product_processes':0,'Blender_sessions':0,'new_images':0}))
    print(json.dumps({'passed':True,'observations':6,'ledger_sha256':sha((HERE/'DEMAND_LEDGER.json').read_bytes()),
      'model_consumers':0,'product_processes':0,'Blender_sessions':0,'new_images':0}))


if __name__=='__main__':main()
