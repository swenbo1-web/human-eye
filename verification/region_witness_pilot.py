"""Finite cycle006 controller; no production edits or external provider.

The registration is immutable. Private qualification is never model input.
Native reports recompute public facts from fresh trusted captures.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'verification/fixes/20261103_review_cycle006'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from verification.deformation_anchor_oracle import verify_catalog, resolve_task, expected_box, selection as anchor_selection
from verification.deformation_context_oracle import policy, selection as core_selection
from verification.deformation_region_oracle import matching_indices, all_facts
from verification.rigged_source_qualification import independent_matrices, dependency_checks, animation_metrics, gltf_witness, GRAM_ATOL, MATRIX_ATOL, POSITION_ATOL
from verification.model_trial.b3e_native import validate_shared_capture


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def reg():
    value = load(OUT / 'PREREGISTERED.json')
    assert sha(OUT / 'PREREGISTERED.json') == '50df877c584042586887f7a2906a948fc6aa6ca8e3583b4af5d25e8e7acc1534'
    entry = Path(value['entry'])
    assert sha(entry) == value['entry_sha256']
    assert sha(entry.with_name('target_runtime_entry.py')) == value['target_entry_sha256']
    assert sha(ROOT / 'verification/pilot_profile_entry.py') == value['profile_wrapper_sha256']
    binding = load(entry.with_name('RUNTIME_BINDING.json'))
    assert sha(entry.with_name('RUNTIME_BINDING.json')) == value['binding_sha256']
    assert binding['identity']['source_sha256'] == value['runtime_source_sha256']
    assert len(binding['source_files']) == 125
    for row in binding['source_files']:
        assert sha(ROOT / row['path']) == sha(Path(binding['site_packages']) / row['path']) == row['sha256']
    for frame in value['frames']:
        assert sha(frame['original_file']) == frame['original_sha256']
    return value, binding


def invoke(folder, profile, *options):
    value, binding = reg()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    command = [binding['dependency_python'], '-I', '-B', str(ROOT / 'verification/pilot_profile_entry.py'),
               value['entry'], str(folder / 'SPANS.json'), '--operator-profile', str(profile), '--output', str(folder / 'readback'), *map(str, options)]
    start = time.perf_counter_ns()
    unix = time.time_ns()
    try:
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
        failure = None
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, code, failure = exc.stdout or b'', exc.stderr or b'', None, 'controller_timeout'
    elapsed = time.perf_counter_ns() - start
    for name, blob in [('STDOUT.bin', stdout), ('STDERR.bin', stderr)]:
        with (folder / name).open('xb') as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
    receipt = dict(command=command, started_unix_ns=unix, complete_subprocess_wall_ns=elapsed,
                   exit_code=code, failure=failure, stdout_bytes=len(stdout), stderr_bytes=len(stderr),
                   stdout_sha256=sha(folder / 'STDOUT.bin'), profile_sha256=sha(profile),
                   runtime_source_sha256=value['runtime_source_sha256'],
                   entry_sha256=value['entry_sha256'], measured_with_same_QA_profile=True)
    save(folder / 'EXECUTION.json', receipt)
    if code != 0:
        raise RuntimeError('product invocation failed; retained ' + str(folder))
    snapshots = load(folder / 'readback/SNAPSHOTS.json')
    cap = snapshots['capabilities']
    assert cap['geometry_setters'] == 0 and cap['saves_file'] is False and cap['sets_frame'] is False
    assert cap['runtime_source_sha256'] == value['runtime_source_sha256']
    assert cap['max_requests'] == 16 and cap['byte_limit'] == 524288
    report = load(folder / 'readback/REPORT.json')
    spans = load(folder / 'SPANS.json')['spans']
    assert any(k.endswith(':close') for k in spans), 'close stage not observed'
    assert any(k.endswith(':_inspect') and v['calls'] == 2 for k, v in spans.items()), 'double capture not observed'
    assert sha(load(profile)['scene_file']) == load(profile)['scene_sha256']
    return report, snapshots['second'], receipt


def reference_policy(catalog, anchor_id):
    return policy(catalog, anchor_id, dict(core=[.5]*3, primary=[.5]*3, candidates=[], max_surplus_members=0))


def native_region(packet, catalog, anchor_id, indices=None):
    """Public independent arithmetic, with no access to private qualification."""
    started = time.perf_counter_ns()
    verify_catalog(catalog, packet)
    anchor = next(a for a in catalog['anchors'] if a['anchor_id'] == anchor_id)
    region = expected_box(anchor, [.5]*3)
    members = matching_indices(packet, region['bounds'])
    facts = all_facts(packet, list(range(len(packet['inputs']['mesh']['triangles']))))
    global_counts = {state: sum(row['state'] == state for row in facts.values()) for state in ('measured', 'collapsed', 'unknown')}
    rows = [dict(facts[i], in_required_core=i in members) for i in (members if indices is None else indices)]
    public = dict(schema='independent-native-region-witness-v1', source_ref=catalog['source_ref'],
                  source_observation_sha256=packet['source_sha256'], catalog_sha256=catalog['catalog_sha256'],
                  anchor_id=anchor_id, core_region=region, complete_core_member_indices=members,
                  global_states=global_counts, global_status='partial' if global_counts['unknown'] else 'observed',
                  core_states={state: sum(facts[i]['state'] == state for i in members) for state in global_counts},
                  triangles=rows, scope='common trusted acquisition plus independent exact SAT and QR/SVD; whole intersecting original triangles; no damage/timeline/volume judgement',
                  execution_authority=False, geometry_setters=0, original_file_saved=False)
    blob = json.dumps(public, ensure_ascii=False, allow_nan=False).encode()
    assert len(blob) <= 524288
    return public, dict(independent_compute_and_public_serialization_ns=time.perf_counter_ns()-started,
                        public_bytes=len(blob), public_sha256=hashlib.sha256(blob).hexdigest())


def qualification():
    value, binding = reg()
    start = time.perf_counter_ns()
    originals = []
    truth = []
    sources = []
    for frame in value['frames']:
        folder = OUT / 'qualification' / frame['label']
        folder.mkdir(parents=True, exist_ok=True)
        copy_path = folder / 'fixture.blend'
        if not copy_path.exists():
            shutil.copyfile(frame['original_file'], copy_path)
        assert sha(copy_path) == frame['original_sha256']
        profile = copy.deepcopy(frame['profile'])
        profile['scene_file'] = str(copy_path)
        if not (folder/'PROFILE.json').exists():
            save(folder / 'PROFILE.json', profile)
        assert load(folder/'PROFILE.json') == profile
        if (folder/'catalog/EXECUTION.json').exists():
            receipt=load(folder/'catalog/EXECUTION.json'); assert receipt['exit_code']==0
            catalog=load(folder/'catalog/readback/REPORT.json')
            packet=load(folder/'catalog/readback/SNAPSHOTS.json')['second']
        else:
            catalog, packet, receipt = invoke(folder / 'catalog', folder / 'PROFILE.json', '--anchors-only')
        if not (folder/'CATALOG.json').exists():
            save(folder / 'CATALOG.json', catalog)
        verify_catalog(catalog, packet)
        target = resolve_task(catalog, 'unique_nonroot_head')
        assert target['state'] == 'selected', target
        anchor = next(a for a in catalog['anchors'] if a['anchor_id'] == target['anchor_id'])
        deadline = time.perf_counter_ns() + 30_000_000_000
        validate_shared_capture(packet)
        replay=independent_matrices(packet['inputs'],packet['evaluated'],deadline)
        assert replay['maximum_gram_residual']<=GRAM_ATOL
        assert max(replay[k] for k in ('maximum_object_matrix_error','maximum_object_channel_basis_error','maximum_FK_error','maximum_channel_basis_error'))<=MATRIX_ATOL
        assert replay['LBS_maximum_error']<=POSITION_ATOL
        dependency_checks(packet['inputs'])
        animation=animation_metrics(packet['inputs'],deadline)
        source=dict(status='qualified_finite_recorded_product_source', original_schema=packet['schema'],
                    numerical_replay=replay, animation_evaluation=animation,
                    external_product_admission_receipt=str(folder/'catalog/EXECUTION.json'),
                    scope='independent arithmetic over actual fixed product source; no packet schema conversion or general importer certification')
        scene = packet['inputs']['scene']
        glb = ROOT / 'verification/fixes/20261102_m4_task_qualification/external_assets/RiggedSimple/RiggedSimple.glb'
        witness = gltf_witness(packet, glb.read_bytes(), fps=scene['fps'], fps_base=scene['fps_base'], deadline_ns=deadline)
        region = expected_box(anchor, [.5]*3)
        members = matching_indices(packet, region['bounds'])
        facts = all_facts(packet, list(range(len(packet['inputs']['mesh']['triangles']))))
        acceptable = [i for i in members if facts[i]['state'] == 'measured' and facts[i]['principal_stretches'][0] >= 1.1 and facts[i]['principal_stretches'][1] <= .9]
        truth.append(dict(label=frame['label'], source_ref=catalog['source_ref'], anchor=anchor, region=region,
                          members=members, facts=facts, acceptable_witnesses=acceptable,
                          global_states={state: sum(r['state']==state for r in facts.values()) for state in ('measured','collapsed','unknown')}))
        originals.append((packet['inputs']['mesh']['vertices'], packet['inputs']['mesh']['triangles']))
        sources.append(dict(label=frame['label'], independent_source=source, direct_GLB=witness,
                            profile_sha256=sha(folder/'PROFILE.json'), catalog_sha256=sha(folder/'CATALOG.json'),
                            fresh_runtime_source_sha256=value['runtime_source_sha256'], capture_wall_ns=receipt['complete_subprocess_wall_ns']))
    assert originals[0] == originals[1], 'not same original triangles across static files'
    answerable = any(t['acceptable_witnesses'] for t in truth)
    save(OUT / 'qualification/PRIVATE_TRUTH.json', dict(frames=truth, original_topology_sha256=digest(originals[0])))
    save(OUT / 'qualification/RESULT.json', dict(answerable=answerable, source_contract_passed=True,
         same_original_mesh_and_triangles=True, sources=sources, total_preparation_wall_ns=time.perf_counter_ns()-start,
         complete_C_cost_channel=True, fine_stage_separation='inclusive profile spans plus external complete subprocess; threaded transport and OS flush remain unseparated',
         frozen_question_unchanged=True, model_run_allowed=answerable))
    print(json.dumps(dict(answerable=answerable, source_contract=True, acceptable_counts=[len(t['acceptable_witnesses']) for t in truth])))


def prepare_models():
    value, _ = reg()
    assert load(OUT/'qualification/RESULT.json')['model_run_allowed']
    started = time.perf_counter_ns()
    modes = ['A', 'B', 'C']
    random.Random(2026110306).shuffle(modes)
    mapping = dict(zip(['condition_amber', 'condition_jade', 'condition_violet'], modes))
    save(OUT/'PRIVATE_MAPPING.json', mapping)
    for anonymous, mode in mapping.items():
        base = OUT/'models'/anonymous
        base.mkdir(parents=True)
        directories = []
        for frame in value['frames']:
            folder = base/frame['label']
            folder.mkdir()
            profile = copy.deepcopy(frame['profile'])
            profile['scene_file'] = str(OUT/'qualification'/frame['label']/'fixture.blend')
            save(folder/'PROFILE.json', profile)
            catalog, packet, receipt = invoke(folder/'directory', folder/'PROFILE.json', '--anchors-only')
            save(folder/'CATALOG.json', catalog)
            verify_catalog(catalog, packet)
            directories.append(dict(label=frame['label'], file_sha256=frame['original_sha256'], catalog=catalog))
        task = dict(schema='whole-task-region-witness-v1', task_id='RW-'+anonymous,
                    question=value['question'], frames=[dict(label=f['label'], file_sha256=f['original_sha256'], saved_frame=f['profile']['expected_frame']) for f in value['frames']],
                    mesh='Cylinder', rig='Armature', half_extents_m=[.5]*3, threshold_high=1.1, threshold_low=.9)
        save(base/'TASK.json', task)
        save(base/'BUDGET.json', dict(directories=2, facts=0, native_supplements=0, stages=0))
        save(base/'PHASE1_INPUT.json', dict(task=task, task_sha256=digest(task), directories=directories,
             region_report_form={'A':'ordinary anchor report with bounded per-face details','B':'complete fixed-core facts with extrema witnesses','C':'common trusted capture and independent native region facts'}[mode],
             stage=1, request_schema=dict(task_sha256='copy exact value', anchors={'author_frame1':'selected anchor_id','author_frame25':'selected anchor_id'}, native_supplement='boolean; optional joint independent full-core facts, charged with two fresh captures; available equally, stage1 only'),
             instructions='Select the unique nonroot bone HEAD independently in each fresh directory. Do not give final facts before queries. Both regional queries are attempted exactly as selected; wrong targets are not corrected. Optional common native supplement is not free. No supplied anchor ID or truth.'))
    save(OUT/'MODEL_PREPARATION.json', dict(complete_fresh_directory_preparation_ns=time.perf_counter_ns()-started,
         condition_count=3, directory_calls=6, profile_wrapper_sha256=sha(ROOT/'verification/pilot_profile_entry.py'),
         human_halfwidth_selection_cost=None, tokens=None, usd=None))
    print('prepared 3 anonymous conditions; six fresh directory calls charged')


def fact_call(base, label, mode, anchor_id, indices=None, suffix='fact'):
    frame = base/label
    catalog = load(frame/'CATALOG.json')
    target = next((a for a in catalog['anchors'] if a['anchor_id']==anchor_id), None)
    if target is None:
        return dict(status='invalid_model_anchor', requested_anchor_id=anchor_id)
    folder = frame/suffix
    if mode == 'C':
        fresh, packet, receipt = invoke(folder, frame/'PROFILE.json', '--anchors-only')
        public, timing = native_region(packet, fresh, anchor_id, indices)
        save(folder/'NATIVE_PUBLIC.json', public)
        save(folder/'NATIVE_COST.json', timing)
        return public
    if indices is not None:
        selection = dict(schema='surface-deformation-selection-v1', source_ref=catalog['source_ref'], triangle_indices=indices)
        path = frame/(suffix+'_SELECTION.json'); save(path, selection)
        report, _, _ = invoke(folder, frame/'PROFILE.json', '--triangle-query', path)
    elif mode == 'A':
        path = frame/(suffix+'_SELECTION.json');save(path, anchor_selection(catalog, anchor_id, [.5]*3))
        report, _, _ = invoke(folder, frame/'PROFILE.json', '--anchor-query', path)
    else:
        policy_value = reference_policy(catalog, anchor_id)
        pp = frame/(suffix+'_POLICY.json'); save(pp, policy_value)
        sp = frame/(suffix+'_SELECTION.json'); save(sp, core_selection(catalog, anchor_id, sha(pp)))
        report, _, _ = invoke(folder, frame/'PROFILE.json', '--core-query', sp, '--context-policy', pp, '--context-policy-sha256', sha(pp))
    return report


def execute_phase(number):
    value, _ = reg()
    mapping = load(OUT/'PRIVATE_MAPPING.json')
    for anonymous, mode in mapping.items():
        base = OUT/'models'/anonymous
        response_path = base/('PHASE%d_RESPONSE.json'%number)
        response = load(response_path)
        save(base/('PHASE%d_FROZEN.json'%number), response)
        task = load(base/'TASK.json')
        budget = load(base/('BUDGET.json' if number == 1 else 'BUDGET_AFTER1.json'))
        assert response['task_sha256'] == digest(task)
        assert time.time_ns()-load(OUT/'MODEL_STARTED.json')['unix_ns'] <= 600_000_000_000, '600s task wall reached'
        outputs = []
        if number == 1:
            assert set(response)=={'task_sha256','anchors','native_supplement'} and type(response['native_supplement']) is bool
            assert set(response['anchors'])=={f['label'] for f in value['frames']}
            for label, anchor_id in response['anchors'].items():
                budget['facts'] += 1
                try: result = fact_call(base,label,mode,anchor_id)
                except Exception as exc: result = dict(status='failed', reason=str(exc))
                outputs.append(dict(label=label, result=result))
            supplement=[]
            if response['native_supplement']:
                budget['native_supplements'] += 1
                for label, anchor_id in response['anchors'].items():
                    try: result=fact_call(base,label,'C',anchor_id,suffix='common_native')
                    except Exception as exc: result=dict(status='failed',reason=str(exc))
                    supplement.append(dict(label=label,result=result))
            save(base/'PHASE2_INPUT.json',dict(stage=2,task=task,task_sha256=digest(task),actual_regional_results=outputs,
                 actual_common_native_supplement=supplement,selection_was_not_corrected=response,
                 request_schema=dict(task_sha256='copy exact value',triangle_indices='one identical list of 1..4 original triangle indices for both files'),
                 instructions='Select original triangle IDs from your actual evidence. The same list is queried in both static files. Distinct extrema cannot be combined as one witness. Do not invent missing facts.'))
        else:
            assert set(response)=={'task_sha256','triangle_indices'}
            ids=response['triangle_indices']; assert type(ids) is list and len(ids)<=4 and all(type(i) is int for i in ids) and len(set(ids))==len(ids)
            first=load(base/'PHASE1_FROZEN.json')
            for frame in value['frames']:
                label=frame['label'];budget['facts']+=1
                try: result=fact_call(base,label,mode,first['anchors'][label],indices=ids,suffix='targeted')
                except Exception as exc: result=dict(status='failed',reason=str(exc))
                outputs.append(dict(label=label,result=result))
            save(base/'PHASE3_INPUT.json',dict(stage=3,task=task,task_sha256=digest(task),actual_targeted_results=outputs,
                 selected_triangle_indices=ids,instructions='Final answer only from the accumulated public evidence. Preserve full reported numeric precision. Local measured positive does not remove global unknowns. No timeline/damage/volume proof.',
                 answer_schema=dict(task_sha256='copy exact value',selected_triangle='one integer or null',frames=[dict(label='author_frame1 or author_frame25',file_sha256='exact',principal_stretches='two full precision numbers or null',area_ratio='number or null',state='measured/collapsed/unknown',reason='exact reported reason or null',in_core='boolean',has_confirmed_mixed_witness='boolean or null')],interpretation='explain whole-triangle/core/global partial/unknown and static-time limitations; say if evidence is insufficient')))
        budget['stages']=number
        assert budget['facts']<=4 and budget['native_supplements']<=1
        save(base/('BUDGET_AFTER%d.json'%number),budget)
    print('executed actual frozen phase',number)


if __name__=='__main__':
    {'qualify':qualification,'prepare':prepare_models,'phase1':lambda:execute_phase(1),'phase2':lambda:execute_phase(2)}[sys.argv[1]]()
