"""Independent stdlib-only audit of the single recorded old/new native pair.

Uses the accepted audit's independent Newell/Gauss-Jordan/LBS/quaternion math,
not a producer or the fixture author's oracle.  Never invokes Blender, a model,
source capture, solver, or mutation.  All native runs must already be complete.
"""
import ast
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import subprocess
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE_COMMIT = 'a3a72b929f55c40f195ff5e1a9f64ceb303b6360'
HELPER = ROOT/'verification/arm_correction_execution_001/audit_execution.py'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == 'fe04059480b38dc870b636f612da53561c9f3d35331c7c2824b87be0dc857e68'
spec = importlib.util.spec_from_file_location('accepted_independent_geometry', HELPER)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
need, read, sha, digest = g.need, g.read, g.sha, g.digest
GATES, FIXED = g.GATES, g.FIXED
OUT = HERE/'INDEPENDENT_PAIR_AUDIT.json'


def ns(value, label):
    need(type(value) is int and value >= 0, 'finite nonnegative integer nanoseconds: '+label)
    return value


def source_manifest(root, identity):
    literals = {}
    for node in ast.parse((root/'human_eye_plugin/runtime_identity.py').read_bytes()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES'):
                    literals[target.id] = ast.literal_eval(node.value)
    names = set(literals['_ROOT_MODULES'])
    for package in ('human_eye_plugin', 'human_eye_module1_operators'):
        names.update(p.relative_to(root).as_posix() for p in (root/package).glob('*.py'))
    manifest = [{'path': name, 'sha256': sha(root/name)} for name in sorted(names)]
    need(len(manifest) == 137 and identity['source_files'] == manifest, 'complete runtime source enumeration')
    source_hash = digest({'base_version': literals['BASE_VERSION'], 'implementation_revision': literals['IMPLEMENTATION_REVISION'], 'files': manifest})
    need(identity['source_sha256'] == source_hash and identity['build_id'] == 'sha256:'+source_hash, 'canonical runtime identity')
    return source_hash


def audit_run(run, source_root, label):
    parent, freeze, state = (read(run/name) for name in ('RESULT.json', 'SOURCE_FREEZE.json', 'state.json'))
    need(parent['passed'] and parent['label'] == label and len(parent['cases']) == 8, label+' complete fixed result')
    need(Path(parent['source_root']).resolve() == source_root, label+' expected source root')
    need(freeze['native_gates'] == GATES and freeze['new_effect_assets'] == 0, label+' unchanged QA gates')
    identity = freeze['runtime_identity']; source_hash = source_manifest(source_root, identity)
    need(parent['source_before'] == parent['source_after'] == identity and parent['source_unchanged'], label+' frozen runtime before/after')
    for name, value in freeze['qa_scripts'].items():
        need(Path(name).is_absolute() and sha(name) == value, label+' absolute frozen QA script '+name)
    need(sha(freeze['blend_path']) == freeze['blend_sha256'] == parent['blend_sha256_before'] == parent['blend_sha256_after'], label+' original blend unchanged')
    fixture_file = run/'FIXTURE_INPUTS.json'; fixtures = read(fixture_file)['cases']
    need(sha(fixture_file) == freeze['fixture_input_sha256'] and len(fixtures) == 8, label+' fixture binding')
    tx = [json.loads(line) for line in (run/'RPC_TX.txt').read_text().splitlines() if line.strip()]
    prefix = 'HUMAN_EYE_RPC:'
    rx = [json.loads(line[len(prefix):]) for line in (run/'RPC_RX.txt').read_text().splitlines() if line.startswith(prefix)]
    need(len(tx) == len(rx) == 10 and [x['id'] for x in tx] == [x['id'] for x in rx] == list(range(1, 11)), label+' complete unique RPC transactions')
    need([x['command'] for x in tx] == ['capabilities']+['correct_arm_axial']*8+['shutdown'], label+' no extra capture/observation RPC')
    need(all('result' in x and 'error' not in x for x in rx), label+' all RPC responses valid')
    cap = rx[0]['result']; pid = parent['process_exit']['pid']
    need(cap == parent['capabilities'] and cap['process_id'] == pid and cap['connection'] == 'owned_headless_process', label+' owned capability identity')
    need(cap['generic_code_execution'] is False and cap['attaches_to_open_window'] is False and cap['arm_axial_execution_protocol'] == 'owned-arm-axial-execution-v1', label+' fixed finite worker')
    need(cap['native_observation_capabilities']['host_source_sha256'] == sha(source_root/'human_eye_plugin/blender_host.py'), label+' actual worker host bytes')
    records = state['arm_axial_events']['records']
    need(state['inflight'] is None and len(records) == 8 and state['config_fingerprint'] == digest(read(run/'config.json')), label+' complete durable state/config')
    summaries, raw_cases, costs = [], [], []
    totals = Counter(); source_work = Counter()
    for index, (expected, entry, fixture) in enumerate(zip(FIXED, parent['cases'], fixtures), 1):
        case_id, status, theta, initial_u = expected
        path = run/('case_'+str(index).zfill(2)+'.json'); raw = read(path); raw_cases.append(raw)
        audit, before, after = raw['product_audit'], raw['native_before'], raw['native_after']
        task, receipt = audit['task'], raw['receipt']; positive = status == 'satisfied'; count = 2 if positive else 0
        need(raw['case_id'] == entry['case_id'] == fixture['case_id'] == case_id, label+' fixed case order')
        need(raw['passed'] and raw['product_error'] is None and receipt == audit['receipt'] == rx[index]['result'], label+' actual host/RPC receipt')
        need(tx[index]['params'] == {'task': task} and task['event_id'] == entry['event_id'] == raw['event_id'], label+' one typed task')
        need('fixed_end_pose_matrices' not in task and 'candidate' not in task, label+' no caller candidate/end matrices')
        need((receipt['status'], receipt['setter_attempts'], receipt['setter_returns'], receipt['executed'], receipt['task_succeeded']) == (status, count, count, positive, status in ('satisfied', 'no_op')), label+' exact status/action counts')
        for key, value in receipt.items():
            need(entry['result'][key] == value, label+' entry bound to host receipt '+key)
        capture, static, patch, resolved = (audit[key] for key in ('before_capture', 'static_patch', 'input_patch', 'resolved_task'))
        need(capture['static_patch'] is None and patch['current_vertices'] == capture['current_vertices'] == before['current_vertices'], label+' actual consumed before points')
        need(capture['pose_matrices'] == before['poses'] == [b['pose_matrix'] for b in patch['bone_chain']], label+' actual consumed before pose')
        need(resolved['fixed_end_pose_matrices'] == [before['poses'][i] for i in (0, 2)], label+' endpoints resolved inside first capture')
        for key in ('u_interval_deg', 'max_section_area_loss', 'protected_vertex_ids', 'angle_tolerance_deg', 'position_tolerance_m', 'area_tolerance'):
            need(resolved[key] == task[key] == fixture[key], label+' unchanged task field '+key)
        need(task['max_section_area_loss'] == .4 and task['area_tolerance'] == 1e-6, label+' actual product success gates')
        for key in ('rest_vertices', 'weights', 'triangles', 'vertex_ids', 'sections'):
            need(static[key] == patch[key], label+' same static consumed field '+key)
        need(static['vertex_ids'] == list(range(402)) and len(static['rest_vertices']) == len(before['current_vertices']) == len(after['current_vertices']) == len(static['weights']) == 402, label+' complete vertex arrays')
        need(len(static['sections']) == 25 and static['sections'] == task['selection']['sections'], label+' complete selected sections')
        need(sorted(g.cyclic(t) for t in static['triangles']) == sorted(g.cyclic(t) for t in before['static']['triangles']), label+' oriented native topology')
        need(static['rest_vertices'] == before['static']['rest_vertices'] and before['static'] == after['static'] and before['sentinel'] == after['sentinel'], label+' complete raw static/sentinel preservation')
        need(before['static']['unit_scale_m'] == 1., label+' native fixture units')
        rests = [b['rest_matrix'] for b in before['static']['bones']]
        need(rests == [b['rest_matrix'] for b in static['bone_chain']] and len(rests) == len(before['poses']) == len(after['poses']) == 3, label+' native three-bone binding')
        for native, effective in zip(before['static']['raw_weights'], static['weights']):
            need(len(native) == len(effective) == 3 and abs(sum(native)-1.) <= 1e-6, label+' raw effective-weight domain')
            need([v/sum(native) for v in native] == effective, label+' production-normalized weights')
        source = capture['source']
        need(source == receipt['before_source'] and source['selected_vertices'] == 402 and source['selected_bones'] == task['selection']['bone_names'] and source['tracking'] == 'scene_residency' and source['unit'] == 'm', label+' current source identity')
        preview = audit['preview']; work = receipt['work']
        need(preview['status'] == ('candidate' if positive else status), label+' precise preview status')
        need(work['preview_calls'] == 1 and work['model_calls'] == 0 and work['source_captures'] == work['source_capture_attempts'] == work['source']['captures'] == (2 if positive else 1), label+' one solve/shared after source')
        need(work['source']['preparations'] == (1 if label == 'baseline' else 0), label+' actual preparation count')
        need(work['source']['static_reads'] == work['source']['topology_reads'] == work['source_captures'], label+' native static/topology accounting preserved')
        source_work.update(work['source']); totals.update(mutation_rpc=1, setter_attempts=count, setter_returns=count, preview_calls=1, source_captures=work['source_captures'])
        sections = static['sections']; area_before, j_before = g.objective(static['rest_vertices'], before['current_vertices'], sections); area_after, j_after = g.objective(static['rest_vertices'], after['current_vertices'], sections)
        need(g.maximum(area_before, raw['actual_before']['section_area_ratios']) < 1e-12 and g.maximum(area_after, raw['actual_after']['section_area_ratios']) < 1e-12, label+' independent Newell areas')
        ids = task['protected_vertex_ids']; need(len(ids) == 194, label+' protected region size')
        need(raw['protected_points_before'] == [before['current_vertices'][i] for i in ids] and raw['protected_points_after'] == [after['current_vertices'][i] for i in ids], label+' raw protected arrays')
        protected = g.distance(raw['protected_points_before'], raw['protected_points_after'])
        centers = g.distance([g.center([before['current_vertices'][i] for i in row]) for row in sections], [g.center([after['current_vertices'][i] for i in row]) for row in sections])
        head_tail = max(g.distance(before['heads'], after['heads']), g.distance(before['tails'], after['tails']))
        end_angle = max(g.angle(before['world_poses'][i], after['world_poses'][i]) for i in (0, 2))
        translation = g.distance([[before['world_poses'][i][k][3] for k in range(3)] for i in (0, 2)], [[after['world_poses'][i][k][3] for k in range(3)] for i in (0, 2)])
        lbs = max(g.distance(g.skin(static['rest_vertices'], static['weights'], rests, before['poses']), before['current_vertices']), g.distance(g.skin(static['rest_vertices'], static['weights'], rests, after['poses']), after['current_vertices']))
        need(max(protected, centers, head_tail, translation, lbs) <= GATES['position_m'] and end_angle <= GATES['angle_deg'], label+' independent LBS and preservation')
        for side, native in ((audit['side_before'], before), *(([(audit['side_after'], after)] if positive else []))):
            need(side['poses_m'] == native['poses'] and side['heads_m'] == native['heads'] and side['tails_m'] == native['tails'], label+' native small-read feedback binding')
        if positive:
            after_capture = audit['after_capture']; need(after_capture['source'] == receipt['after_source'] and after_capture['current_vertices'] == after['current_vertices'] and after_capture['pose_matrices'] == after['poses'], label+' actual after shared feedback')
            need(after_capture['static_patch'] is None and audit['after_static_patch'] == static, label+' static identity after pose')
            for key in source:
                if key not in ('revision', 'max_lbs_readback_error_m'):
                    need(source[key] == after_capture['source'][key], label+' held source field '+key)
            need(after_capture['source']['revision'] > source['revision'], label+' mutation revision advanced')
            need(j_after <= task['max_section_area_loss']+task['area_tolerance'] and abs(receipt['feedback']['max_section_area_loss']-j_after) < 1e-12 and receipt['feedback']['source'] == 'actual_after_capture', label+' actual target, not predicted result')
            candidate = preview['candidate']
            need(candidate['pose_matrices'][0] == before['poses'][0] and candidate['pose_matrices'][2] == before['poses'][2], label+' fixed complete endpoint matrices')
            need([c['name'] for c in candidate['bone_changes']] == task['selection']['bone_names'][1:], label+' only middle/last declared')
            need(before['basis'][0] == after['basis'][0], label+' no first-bone setter')
            for bone, change in zip((1, 2), candidate['bone_changes']):
                need(g.maximum(change['basis_matrix'], after['basis'][bone]) <= GATES['position_m'], label+' actual absolute basis')
            need(g.distance(candidate['current_vertices'], after['current_vertices']) <= GATES['position_m'], label+' candidate vs actual point gate')
        else:
            need(before == after and preview['candidate'] is None and receipt['after_source'] is None and 'after_capture' not in audit, label+' zero-write whole native state')
            need(receipt['reason'] == {'no_op':'area_target_already_met', 'unreachable':'best_allowed_u_exceeds_area_target', 'not_applicable':'non_axial_or_ambiguous_pose'}[status], label+' precise refusal/no-op reason')
        if theta is not None:
            u = theta/2 if positive else initial_u
            for row, actual in zip(sections, area_after):
                weights = static['weights'][row[0]]; angles = (0., u, theta)
                determinant = math.fsum(w*math.cos(math.radians(a)) for w, a in zip(weights, angles))**2 + math.fsum(w*math.sin(math.radians(a)) for w, a in zip(weights, angles))**2
                need(abs(actual-determinant) <= GATES['area_error'], label+' independent analytic axial section')
        record = records[task['event_id']]
        need(record['state'] == 'complete' and record['request'] == task and record['request_fingerprint'] == digest(task), label+' durable event binding')
        for key, value in receipt.items():
            need(record['result'][key] == value, label+' durable actual result '+key)
        step_costs = raw['qa_source_costs']; costs.extend(step_costs)
        need(Counter(x['phase'] for x in step_costs) == ({'_parse_patch':1, 'prepare_patch':1} if label == 'baseline' else {'_parse_patch':1}), label+' exact source function work')
        for item in step_costs:
            need(item['error'] is None and Path(item['original_filename']).resolve() == source_root/'human_eye_plugin/arm_twist_expert.py', label+' timed original function origin')
            need(len(item['original_code_sha256']) == 64 and all(c in '0123456789abcdef' for c in item['original_code_sha256']), label+' recorded original code SHA')
            ns(item['elapsed_ns'], label+' source '+item['phase'])
            need(item['elapsed_ns'] <= receipt['timings_ns']['source_before'], label+' source timing nested inside before')
        if label == 'baseline':
            need(step_costs[0]['phase'] == '_parse_patch' and step_costs[1]['phase'] == 'prepare_patch' and step_costs[1]['elapsed_ns'] >= step_costs[0]['elapsed_ns'], label+' parser is nested within original prepare')
        timings = receipt['timings_ns']; entry_times = entry['result']['entry_timings_ns']
        for name, value in timings.items(): ns(value, label+' host '+name)
        for name, value in entry_times.items(): ns(value, label+' entry '+name)
        need(entry['entry_ns'] >= entry_times['entry'] >= timings['host_total'] and entry_times['mutation_rpc'] >= raw['pure_product_method_ns'] >= timings['host_total'], label+' complete nested entry/RPC/host costs')
        for key in ('qa_before_read_ns', 'qa_after_read_ns'): ns(raw[key], label+' '+key)
        summaries.append({'case_id':case_id, 'status':status, 'before_j':j_before, 'actual_after_j':j_after, 'protected_max_m':protected, 'ring_centers_max_m':centers, 'heads_tails_max_m':head_tail, 'endpoint_angle_deg':end_angle, 'endpoint_translation_m':translation, 'LBS_max_m':lbs, 'raw_sha256':sha(path), 'entry_ns':entry['entry_ns'], 'source_preparations':work['source']['preparations']})
    need(dict(totals) == parent['product_work'] == {'mutation_rpc':8, 'setter_attempts':8, 'setter_returns':8, 'preview_calls':8, 'source_captures':12}, label+' fixed actual work')
    need(dict(source_work) == parent['source_work_totals'], label+' full source work totals')
    need(costs == parent['source_costs'] and dict(Counter(x['phase'] for x in costs)) == parent['source_cost_counts'], label+' complete recorded source costs')
    for phase in ('prepare_patch', '_parse_patch'):
        hashes = {x['original_code_sha256'] for x in costs if x['phase'] == phase}
        need(len(hashes) == (1 if phase == '_parse_patch' or label == 'baseline' else 0), label+' stable original function code identity')
    replay = parent['replay']
    need(replay['rpc_delta'] == replay['cost_delta'] == 0 and replay['result']['historical_receipt'] and replay['result']['replayed'] and replay['result']['new_setter_count'] == 0 and replay['result']['executed_this_call'] is False, label+' zero-action replay')
    cleanup, ready = read(run/'CHILD_CLEANUP.json'), read(run/'OBSERVER_READY.json')
    need(cleanup == parent['child_cleanup'] and cleanup['pid'] == ready['pid'] == pid, label+' one child identity')
    need(all(cleanup[k] for k in ('profile_none','host_residency_closed','owned_objects_removed','owned_meshes_removed','owned_rigs_removed','all_handlers_removed','file_unsaved')), label+' cleanup and no-save')
    need(cleanup['work'] == {'fixtures':8,'initial_basis_assignments':24,'candidate_assignments':0,'product_calls':8,'native_reads':16}, label+' QA init only, actual product writes')
    need(parent['process_exit'] == {'pid':pid,'returncode':0,'closed':True}, label+' process reaped')
    need(ready['profile_none'] and ready['product_method_source_sha256'] == sha(source_root/'human_eye_plugin/blender_host.py'), label+' actual method source witness')
    host_class = next(n for n in ast.parse((source_root/'human_eye_plugin/blender_host.py').read_bytes()).body if isinstance(n,ast.ClassDef) and n.name == 'BlenderSceneHost')
    method = next(n for n in host_class.body if isinstance(n,ast.FunctionDef) and n.name == 'correct_arm_axial')
    need(ready['product_method_firstlineno'] == method.lineno and Path(ready['product_method_filename']).resolve() == source_root/'human_eye_plugin/blender_host.py', label+' original host method origin')
    setters = [n for n in ast.walk(method) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr == 'matrix_basis' for t in n.targets)]
    need(len(setters) == 1, label+' finite product pair setter site')
    command = read(run/'COMMAND.json'); actual = command['actual']; position = actual.index('--python-expr')
    need(actual[:position]+actual[position+2:] == command['original'] and command['verified_expression_unchanged'] and '--disable-autoexec' in actual and '--background' in actual, label+' unchanged verified worker expression with QA prefix')
    events = [json.loads(line) for line in (run/'OBSERVER_EVENTS.jsonl').read_text().splitlines()]
    need(len(events) == 8 and all(x['passed'] for x in events) and [x['event_id'] for x in events] == [x['event_id'] for x in parent['cases']], label+' finite QA observer records')
    for event in events: ns(event['evidence_write_ns'], label+' QA evidence archive')
    need(dict(Counter(x['phase'] for x in parent['costs'])) == parent['cost_counts'], label+' complete state cost work')
    need(parent['cost_counts']['arm_ledger_validation'] == (16 if label == 'baseline' else 8), label+' separate ledger work count')
    for item in parent['costs']: ns(item['elapsed_ns'], label+' state '+item['phase'])
    for name in ('startup_ns','close_ns','total_controller_ns'): ns(parent[name], label+' '+name)
    need(parent['total_controller_ns'] >= parent['startup_ns']+parent['close_ns']+sum(x['entry_ns'] for x in parent['cases']), label+' full controller includes startup/entry/exit')
    need(parent['model_calls'] == parent['qa_candidate_assignments'] == 0, label+' zero model/QA candidate calls')
    timing = {'startup_ns':parent['startup_ns'], 'fixture_build_ns':ready['fixture_build_ns'], 'close_ns':parent['close_ns'], 'total_controller_ns':parent['total_controller_ns'], 'entry_ns':[x['entry_ns'] for x in parent['cases']], 'source_cost_ns':{phase:sum(x['elapsed_ns'] for x in costs if x['phase'] == phase) for phase in ('prepare_patch','_parse_patch')}, 'state_cost_ns':{phase:sum(x['elapsed_ns'] for x in parent['costs'] if x['phase'] == phase) for phase in parent['cost_counts']}, 'host_phase_ns':{phase:sum(x['receipt']['timings_ns'].get(phase,0) for x in raw_cases) for phase in ('scope','source_before','source_after','solve','assignment','feedback','host_total')}, 'entry_phase_ns':{phase:sum(x['result']['entry_timings_ns'][phase] for x in parent['cases']) for phase in ('state_lock_restore','pending_save','mutation_rpc','completion_save','entry')}, 'qa_archive_ns':[x['evidence_write_ns'] for x in events], 'qa_native_reads_ns':sum(x['qa_before_read_ns']+x['qa_after_read_ns'] for x in raw_cases)}
    return {'label':label,'runtime_source_sha256':source_hash,'process_exit':parent['process_exit'],'cases':summaries,'product_work':dict(totals),'source_work':dict(source_work),'ledger_validation_calls':parent['cost_counts']['arm_ledger_validation'],'timing':timing}, raw_cases


def main():
    material = read(HERE/'BASELINE_MATERIALIZATION.json'); baseline_root = Path(material['source_root']).resolve()
    need(material['commit'] == BASE_COMMIT and material['runtime_sources'] == 137 and len(material['files']) == 138, 'baseline exact materialization declaration')
    for name, value in material['files'].items():
        blob = subprocess.check_output(['git','show',BASE_COMMIT+':'+name], cwd=ROOT)
        need(hashlib.sha256(blob).hexdigest() == value == sha(baseline_root/name), 'baseline exact Git bytes '+name)
    old, old_raw = audit_run(HERE/'baseline_01', baseline_root, 'baseline')
    new, new_raw = audit_run(HERE/'candidate_01', ROOT, 'candidate')
    need(old['runtime_source_sha256'] == 'e224f445a310c8b799b49d6f3f30184fa9b76b569cfa9ff1e79707c0291115b0', 'accepted baseline canonical identity')
    need(read(HERE/'baseline_01/SOURCE_FREEZE.json')['qa_scripts'] == read(HERE/'candidate_01/SOURCE_FREEZE.json')['qa_scripts'], 'identical pair QA instrumentation bytes')
    need((HERE/'baseline_01/FIXTURE_INPUTS.json').read_bytes() == (HERE/'candidate_01/FIXTURE_INPUTS.json').read_bytes(), 'identical pair initialization/task bytes')
    pair_cases = []
    for left, right in zip(old_raw, new_raw):
        need(left['case_id'] == right['case_id'] and left['product_audit']['task'] == right['product_audit']['task'], 'pair same explicit task')
        for key in ('native_before','native_after','protected_points_before','protected_points_after','actual_before','actual_after'):
            need(left[key] == right[key], 'pair complete geometry/native equality '+key)
        for key in ('static_patch','input_patch','resolved_task','preview'):
            need(left['product_audit'][key] == right['product_audit'][key], 'pair same consumed/preview geometry '+key)
        for key in ('status','reason','setter_attempts','setter_returns','executed','task_succeeded','feedback'):
            need(left['receipt'][key] == right['receipt'][key], 'pair same actual result '+key)
        pair_cases.append({'case_id':left['case_id'],'complete_native_before_after_equal':True,'consumed_patch_and_preview_equal':True,'actual_feedback_equal':True})
    cpu = read(HERE/'cpu_final_02/RESULT.json'); need(cpu['passed'] and cpu['tests'] == 62 and cpu['failures'] == cpu['errors'] == cpu['skips'] == 0 and cpu['before_sha256'] == cpu['after_sha256'], 'frozen CPU62 receipt (not rerun)')
    for name, value in cpu['after_sha256'].items(): need(sha(ROOT/name) == value, 'final CPU frozen source '+name)
    need(cpu['geometry_model_calls'] == cpu['paid_model_calls'] == cpu['blender_runs'] == 0 and cpu['diagnostic_prediction_calls'] == 14, 'diagnostic prediction calls separate from zero-call geometry')
    probe_counts = cpu['state_probe_counts']
    need(probe_counts['real_corrupt_load'] == {'validation_calls':1,'additional_mutation_rpcs':0}, 'persisted corrupt state rejected before dispatch')
    need(probe_counts['real_live_validation']['actual_lock_fresh_load'] == probe_counts['real_live_validation']['actual_lock_restart_load'] == 1, 'actual locked fresh/restart one arm validation each')
    need(probe_counts['pending_ack_loss'] == {'first_loads':1,'restart_loads':2,'mutation_rpcs':0}, 'pending confirmation loss/restart remains zero RPC')
    need(cpu['host_details']['returned_but_unchanged']['result']['status'] == 'feedback_failed' and cpu['host_details']['returned_but_unchanged']['result']['setter_returns'] == 2, 'ignored-write probe retains actual failure feedback')
    first = read(HERE/'cpu_final_01/RESULT.json')
    need(not first['passed'] and first['tests'] == 62 and first['failures'] == 1 and first['errors'] == 0, 'first fixture-count expectation failure retained')
    need(sha(HERE/'cpu_final_01/TEST_HOST.py') == first['before_sha256']['verification/arm_correction_execution_opt_001/test_host.py'], 'exact failed test source retained')
    initializer = HERE/'native_initializer.py'; tree = ast.parse(initializer.read_bytes())
    setters = [n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr == 'matrix_basis' for t in n.targets)]
    need(len(setters) == 1 and ast.unparse(setters[0].value) == 'Matrix(basis)', 'initializer only assigns starting bases')
    attached = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name == '_qa_attach')
    need(not any(isinstance(n,ast.Attribute) and n.attr == 'matrix_basis' for n in ast.walk(attached)), 'observer never assigns candidate')
    need(sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id == 'original' for n in ast.walk(attached)) == 1, 'observer delegates original host exactly once')
    need(sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id == 'original_loader' for n in ast.walk(attached)) == 1, 'same original lazy loader position')
    timed = next(n for n in ast.walk(attached) if isinstance(n,ast.FunctionDef) and n.name == 'timed')
    need(sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id == '_original' for n in ast.walk(timed)) == 1, 'timing wrapper delegates original function exactly once')
    comparison = read(HERE/'COST_COMPARISON.json')
    need(comparison['passed'] and comparison['ordered_runs'] == ['baseline_01','candidate_01'] and comparison['resamples'] == 0, 'one fixed ordered comparison declaration')
    for label, summary in (('baseline', old), ('candidate', new)):
        run = HERE/(label+'_01'); parent = read(run/'RESULT.json'); reported = comparison[label]
        need(reported['result_sha256'] == sha(run/'RESULT.json') and reported['source_sha256'] == summary['runtime_source_sha256'], 'cost summary binds result/source '+label)
        need(reported['product_work'] == parent['product_work'] and reported['source_work'] == parent['source_work_totals'] and reported['state_phase_counts'] == parent['cost_counts'] and reported['source_phase_counts'] == parent['source_cost_counts'], 'cost summary work counts '+label)
        for reported_key, actual in (('startup_ms',parent['startup_ns']/1e6),('close_ms',parent['close_ns']/1e6),('total_controller_ms',parent['total_controller_ns']/1e6),('entry_total_ms',sum(x['entry_ns'] for x in parent['cases'])/1e6),('hot_positive_entry_median_ms',statistics.median(x['entry_ns'] for x in parent['cases'][1:4])/1e6)):
            need(abs(reported[reported_key]-actual) < 1e-10, 'independent full cost '+label+' '+reported_key)
        for phase, actual in summary['timing']['state_cost_ns'].items():
            need(abs(reported['state_phase_total_ms'][phase]-actual/1e6) < 1e-10, 'independent state cost '+label+' '+phase)
        for phase, actual in summary['timing']['source_cost_ns'].items():
            need(abs(reported['source_phase_total_ms'].get(phase,0)-actual/1e6) < 1e-10, 'independent source cost '+label+' '+phase)
        events = [json.loads(line) for line in (run/'OBSERVER_EVENTS.jsonl').read_text().splitlines()]
        for case, entry, event in zip(reported['cases'], parent['cases'], events):
            raw = read(run/('case_'+str(events.index(event)+1).zfill(2)+'.json'))
            need(case['case_id'] == raw['case_id'] == entry['case_id'] and abs(case['entry_ms']-entry['entry_ns']/1e6) < 1e-10, 'independent per-case entry cost '+label)
            for phase, actual in raw['receipt']['timings_ns'].items():
                need(abs(case['host_ms'][phase]-actual/1e6) < 1e-10, 'independent per-case host cost '+label+' '+phase)
            for phase, actual in entry['result']['entry_timings_ns'].items():
                need(abs(case['entry_phase_ms'][phase]-actual/1e6) < 1e-10, 'independent per-case state/entry cost '+label+' '+phase)
            for reported_key, actual in (('qa_before_ms',raw['qa_before_read_ns']),('qa_after_ms',raw['qa_after_read_ns']),('qa_archive_ms',event['evidence_write_ns'])):
                need(abs(case[reported_key]-actual/1e6) < 1e-10, 'independent per-case QA cost '+label+' '+reported_key)
    old_prepare = old['timing']['source_cost_ns']['prepare_patch']; old_parse = old['timing']['source_cost_ns']['_parse_patch']; new_parse = new['timing']['source_cost_ns']['_parse_patch']
    for key, value in (('baseline_prepare_inclusive_ms',old_prepare),('baseline_parse_nested_inside_prepare_ms',old_parse),('baseline_prepare_excluding_parse_ms',old_prepare-old_parse),('candidate_retained_source_parse_ms',new_parse)):
        need(abs(comparison[key]-value/1e6) < 1e-10, 'exclusive vs retained parsing cost '+key)
    inputs = {str(path.relative_to(ROOT)):sha(path) for run in ('baseline_01','candidate_01') for path in (HERE/run).iterdir() if path.is_file()}
    inputs.update({str(HERE.relative_to(ROOT)/name):sha(HERE/name) for name in ('BASELINE_MATERIALIZATION.json','COST_COMPARISON.json','cpu_final_02/RESULT.json','cpu_final_02/TESTS.log','cpu_final_01/RESULT.json','cpu_final_01/TEST_HOST.py','native_controller.py','native_initializer.py')})
    return {'schema':'arm-correction-opt-independent-pair-audit-v1','passed':True,'checks':g.checks,'baseline':old,'candidate':new,'pair_cases':pair_cases,'cpu_methods_reported_passed_not_rerun':62,'diagnostic_prediction_calls_reported_not_rerun':14,'gates':GATES,'new_product_calls':0,'new_Blender_runs':0,'new_model_calls':0,'producer_imports':0,'helper_script_sha256':sha(HELPER),'script_sha256':sha(Path(__file__)),'input_sha256':inputs,'limitations':['Exactly one baseline and one candidate process; timings are not a distribution or a causal estimate of all latency changes.','Original function marshal hashes are recorded and stable within each interpreter/run; not independently reconstructed across Python versions.','Raw byte/native equality is checked apart from per-process source identities; this is controlled software evidence, not hardware attestation.','Only the eight fixed generated static three-bone tasks, not character animation, whole volume, or learned correction value.']}


if __name__ == '__main__':
    history = []
    if OUT.exists():
        prior = read(OUT); history = prior.get('audit_attempt_history', [])+[{k:v for k,v in prior.items() if k != 'audit_attempt_history'}]
    try:
        result = main()
    except BaseException as exc:
        result = {'schema':'arm-correction-opt-independent-pair-audit-v1','passed':False,'checks':g.checks,'failure':{'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()},'script_sha256':sha(Path(__file__)),'new_product_calls':0,'new_Blender_runs':0,'new_model_calls':0,'producer_imports':0}
    if history: result['audit_attempt_history'] = history
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({k:result[k] for k in ('passed','checks','new_product_calls','new_Blender_runs','new_model_calls')}))
    if not result['passed']: raise SystemExit(result['failure']['traceback'])
