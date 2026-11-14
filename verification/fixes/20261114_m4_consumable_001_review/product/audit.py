"""Independent saved-data/AST review; never import or execute product code."""
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

R = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
H = R/'verification/m4_consumable_observation_001'
O = Path(__file__).parent
INPUTS = {}
CHECKS = []

def read(path):
    path = Path(path); data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return data
def load(path): return json.loads(read(path))
def ck(name, ok): CHECKS.append({'name': name, 'passed': bool(ok)})
def rows(table): return [dict(zip(table['columns'], row)) for row in table['rows']]

full = load('D:/he_consume_001/formal/P1/o/product_call_01/SERVICE_RESULT.json')
response = load('D:/he_consume_001/formal/P1/o/tool_01/RESPONSE.json')
brief = json.loads(response['result']['content'][0]['text'])
index = load('D:/he_anchor_001/run/acceptance_01/server/INDEX_01.json')
facts = full['facts']; observations = facts['observations']
ck('same_saved_geometry_and_camera_identity', index['scene_identity'] == facts['scene_identity']
   and index['candidate_identity'] == facts['candidate_identity'])
ck('current_schema_v4', brief['schema'] == 'active-observation-brief-v4')
regions = facts['regions']; compact = rows(brief['regions']); pixels = rows(brief['pixels'])
images = rows(brief['images']); groups = rows(brief['unobserved_view_groups'])
ids = [row['roi_id'] for row in regions]
ck('138_regions_unique', len(ids) == len(set(ids)) == len(compact) == 138)
ck('source_region_order_same', ids == [row['roi_id'] for row in index['regions']])
view_order = index['view_order']; observed_order = [x['view_name'] for x in observations]
lookup = {x['view_name']: {p['roi_id']: (i, p) for i, p in enumerate(x['pixel_rows'])} for x in observations}
ck('pixel_rows414', len(pixels) == 414)
ck('coverage_scope', facts['inspection']['scope'] == 'registered finite camera pool')
reason_counts = Counter(); covered = set(); pending = set(); impossible = set(); insufficient = set()
for region_index, (region, out, evidence) in enumerate(zip(regions, compact, facts['region_evidence'])):
    rid = region['roi_id']
    geometric = {view for view in view_order if index['classifications'][view][rid]['complete']}
    ck('mask_matches_classes:'+rid, all(bool(index['view_masks'][view] & (1 << region_index))
       == (view in geometric) for view in view_order))
    valid = []
    for view in observed_order:
        position, p = lookup[view][rid]
        if (view in geometric and p['front_facing'] is True and p['readable'] is True
                and p['visible_surface_pixels'] >= p['minimum_surface_pixels']
                and p['contrasting_boundary_pixels'] >= p['minimum_boundary_pixels']):
            valid.append((view, position))
    ck('same_region_public_fields:'+rid, all(out[k] == region[k] for k in
       ['roi_id','object_index','status','reason','center_world_m','half_edge_u_world_m',
        'half_edge_v_world_m','front_direction_world']))
    ck('actual_coverage_definition:'+rid, (region['status'] == 'covered') == bool(valid))
    if valid:
        covered.add(rid)
        v, i = valid[0]
        ck('deterministic_first_complete_witness:'+rid,
           evidence['complete_witness'] == {'view_name': v, 'pixel_row_index': i})
        p = pixels[out['complete_witness_pixel_index']]
        original = lookup[v][rid][1]
        ck('public_witness_exact_reference:'+rid, p['region_index'] == region_index
           and images[p['image_index']]['view_name'] == v
           and all(p[k] == original[k] for k in ('front_facing','readable','visible_surface_pixels',
                   'contrasting_boundary_pixels','visible_pixel_anchor','visible_pixel_bounds')))
        ck('covered_no_unknown_reason:'+rid, out['unobserved_reason'] is None and not out['unobserved_view_group_indices'])
    else:
        classes = {view:index['classifications'][view][rid]['status'] for view in view_order}
        if not geometric:
            impossible.add(rid)
            statuses = set(classes.values())
            if all(x in ('back_facing','edge_on') for x in statuses): reason = 'no_front_facing_candidate'
            elif all(x in ('back_facing','edge_on','positive_area_occlusion') for x in statuses): reason = 'positive_area_occlusion_all_front_views'
            else: reason = 'no_complete_geometric_candidate'
        elif geometric - set(observed_order):
            pending.add(rid); reason = 'unobserved_geometric_candidates'
        else:
            insufficient.add(rid); reason = 'pixel_evidence_insufficient'
        ck('unobserved_reason:'+rid, reason == evidence['unobserved_reason'] == out['unobserved_reason'])
        expected = {view: ('pixel_evidence_insufficient' if view in observed_order else 'unobserved_geometric_candidate')
                    if view in geometric else classes[view] for view in view_order}
        actual = {}
        for group_index in out['unobserved_view_group_indices']:
            group = groups[group_index]
            for view_index in group['view_indices']:
                name = brief['inspection']['view_names'][view_index]
                ck('group_no_duplicate_view:'+rid+':'+name, name not in actual)
                actual[name] = group['reason']
        ck('all_view_reasons_exact:'+rid, actual == expected)
        ck('unobserved_null_witness:'+rid, out['complete_witness_pixel_index'] is None and evidence['complete_witness'] is None)
        reason_counts[reason] += 1
expected_counts = {'supported':len(ids),'covered':len(covered),'unobserved':len(ids)-len(covered),
                   'pending_geometric_candidate':len(pending),'no_geometric_complete_candidate':len(impossible),
                   'pixel_insufficient':len(insufficient),'covered_without_witness':0}
ck('inspection_counts_independently_derived', facts['inspection']['counts'] == brief['inspection']['counts'] == expected_counts)
ck('115_23_partition', len(covered)==115 and len(impossible)==23 and not pending and not insufficient)
ck('no_further_geometric_candidate_not_all_observed', brief['inspection']['state']=='finite_pool_exhausted'
   and brief['inspection']['stop_reason']=='no_unobserved_geometric_candidates' and len(covered)<len(ids))
ck('22_back_1_occluded', reason_counts=={'no_front_facing_candidate':22,'positive_area_occlusion_all_front_views':1})
ck('finite_pool_lists_correct', set(facts['coverage']['covered_roi_ids'])==covered
   and set(facts['coverage']['candidate_pool_uncovered_roi_ids'])==impossible
   and set(facts['coverage']['unresolved_roi_ids'])==set(ids)-covered)
ck('same_inspection_projection', brief['inspection']==facts['inspection'])
ck('unsupported48', brief['scope']['patch_support']['unsupported_components']['rows'][0][-1]==[[48,48]])

core_path=R/'human_eye_plugin/active_observation.py'; mcp_path=R/'human_eye_plugin/live_spatial_mcp.py'
core = ast.parse(read(core_path).decode('utf-8')); mcp = ast.parse(read(mcp_path).decode('utf-8'))
short = next(x for x in ast.walk(core) if isinstance(x,ast.FunctionDef) and x.name=='short_facts')
helper = next(x for x in ast.walk(mcp) if isinstance(x,ast.FunctionDef) and x.name=='_project_active_inspection')
calls = sorted({ast.unparse(x.func) for x in ast.walk(short) if isinstance(x,ast.Call)})
ck('short_facts_single_summary_call',sum(isinstance(x,ast.Call) and ast.unparse(x.func)=='self.summary' for x in ast.walk(short))==1)
ck('no_geometry_render_call_in_new_short_facts',not any(any(w in call for w in ['prepare_scene','raster','build_index','project','triangle_shadow','geometry']) for call in calls))
ck('helper_no_geometry_render_call',not any(isinstance(x,ast.Call) and any(w in ast.unparse(x.func) for w in ['raster','build_index','triangle_shadow','geometry']) for x in ast.walk(helper)))

authors={}
required = {'readable_does_not_establish_complete','unobserved_candidate_not_pool_exhausted',
            'prediction_only_no_evidence','actual_pixels_insufficient','scene_identity_invalidates_receipts',
            'candidate_identity_invalidates_receipts','patch_mapping_rebind_invalidates','old_patch_receipt_rejected',
            'patch_mapping_explicit_invalidate','historical_v3_fields_preserved_exactly',
            'full_debug_preserves_complete_facts','count_conflict_retains_full_fallback',
            'wrong_witness_retains_full_fallback','false_pool_stop_retains_full_fallback'}
for file in ['offline/REPO_RESULT_FINAL.json','offline/INSTALLED_RESULT_01.json']:
    x=load(H/file);names={item['name'] for item in x['checks']}
    ck('author_check_record:'+file,x['passed'] and len(x['checks'])==171 and all(item['passed'] for item in x['checks'])
       and not x['forbidden_calls'] and required<=names)
    ck('author_legacy_record:'+file,x['legacy_zero_raster_tests']['run']==19
       and not x['legacy_zero_raster_tests']['failures'] and not x['legacy_zero_raster_tests']['errors'])
    authors[file]={'checks':len(x['checks']),'legacy':x['legacy_zero_raster_tests'], 'required_named_cases_present':sorted(required & names)}
read(H/'offline/check_product.py');read(H/'offline/REPORT.md');read(H/'DESIGN_PRODUCT.md')
legacy_sources=['verification/test_active_observation_brief.py','verification/test_active_observation_patch_delivery.py','verification/test_active_observation_region_delivery.py']
for file in legacy_sources: read(R/file)
result={'passed':all(c['passed'] for c in CHECKS),'checks':len(CHECKS),'failures':[c for c in CHECKS if not c['passed']],
        'independently_derived_counts':expected_counts,'reason_counts':dict(reason_counts),'short_facts_call_targets':calls,
        'authors_execution_records_not_rerun':authors,'inputs':INPUTS,
        'new_product_model_Blender_raster_benchmark_calls':0,
        'scope':'saved current facts and same-identity previously captured index; static source review; no new geometry solve'}
O.mkdir(parents=True,exist_ok=True)
(O/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(O/'CHECKS.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ['inputs','authors_execution_records_not_rerun']},ensure_ascii=False))
