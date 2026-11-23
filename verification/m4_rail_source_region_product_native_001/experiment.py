"""Freeze the rail holdout and launch its two owned slots only after admission."""

import argparse
import inspect
import json
import os
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
V = HERE.parent
ROOT = V.parent
sys.path.insert(0, str(HERE))
import host


OLD = run_path(str(V/'m4_yanyite_bilateral_region_native_001/experiment.py'))
read, write, pin, git, require = (OLD[key] for key in ('read', 'write', 'pin', 'git', 'require'))
RUN, PLAN, PRODUCT = host.RUN, host.PLAN, host.PRODUCT
SLOTS, LIMITS = OLD['SLOTS'], OLD['LIMITS']
FROZEN, PROMPT = HERE/'FROZEN.json', host.PROMPT
PREFLIGHT = RUN/'preflight'
ENTRY = PREFLIGHT/'SCORE_GATE.json'
JOURNAL = RUN/'FORMAL_SEQUENCE.jsonl'
REPLAY = PREFLIGHT/'REPLAY.json'
REPLAY_BINDING = PREFLIGHT/'REPLAY_BINDING.json'
CONTROLS = PREFLIGHT/'controls/SUMMARY.json'
INGRESS = PREFLIGHT/'RUNTIME_PREFLIGHT.json'
TRUTH = PREFLIGHT/'RAIL_TRUTH_VERIFIED.json'
POSITIVES = PREFLIGHT/'score_positive_verified'
COLD = PREFLIGHT/'cold_start'
PRODUCT_PROOF = '6fee57dff92aed9270259368c3139118f016ae6f'
PRIOR_SCORE = 'fd10f824dc0fbde08985404c37d314b2d1a111ec'
SCORER = HERE/'score.py'
TRACE = HERE/'trace_entry.py'
MODEL = ['0.152.1','gpt-6.1-sol','medium','default']


def command(*args):
    return [sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), *args]


def trace_entry(script, receipt, *args):
    return [sys.executable, '-IB', '-X', 'utf8', str(TRACE), str(script), str(receipt), *map(str,args)]


def verify_pins(rows):
    for row in rows:
        require(pin(row['path']) == row, 'frozen_input_changed/'+row['path'])


def positive_scores():
    replay = read(REPLAY)
    require(replay['passed'] is True, 'ordinary_and_product_offline_replay_required')
    output = POSITIVES
    output.mkdir(exist_ok=False)
    for label in SLOTS:
        slot = PREFLIGHT/'score_replay/slots'/label
        claims = PREFLIGHT/f'{label}_CLAIMS.json'
        receipt = output/f'{label}_TRACE.json'
        verdict = output/f'{label}_RESULT.json'
        argv = trace_entry(SCORER, receipt, '--offline-fixture', '--slot', slot, '--claims', claims, '--output', verdict)
        start = time.perf_counter_ns()
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=75)
        write(output/f'{label}_PROCESS.json', {'argv':argv,'wall_ns':time.perf_counter_ns()-start,
              'exit_code':proc.returncode,'stderr':proc.stderr.decode('utf8',errors='replace')})
        require(proc.returncode == 0, 'actual_offline_scoring_entry_failed/'+label)


def qualify_scores():
    source_pins = {}
    for proof in (REPLAY, REPLAY_BINDING, CONTROLS, INGRESS, TRUTH):
        receipt = read(proof)
        require(receipt['passed'] is True, 'required_offline_preflight_failed/'+proof.name)
        for row in receipt.get('source_pins', []):
            require(source_pins.setdefault(row['path'],row) == row,
                    'conflicting_preflight_source_identity/'+row['path'])
    replay,ingress = read(REPLAY),read(INGRESS)
    require(replay['offline_fixture'] is True and replay['product_git'] == PRODUCT['commit']
            and replay['actual_Blender_starts'] == replay['actual_models'] == ingress['Blender'] == ingress['models'] == 0,
            'same_installed_product_and_isolated_offline_proofs_required')
    for receipt in (replay,ingress):
        catalogue = {key:value['tools'] for key,value in receipt['arms'].items()}
        require(set(catalogue) == set(SLOTS) and
                [row for row in catalogue['P1'] if row['name'] != 'human_eye_scene_observe'] == catalogue['N1']
                and len(catalogue['P1']) == len(catalogue['N1'])+1, 'ordinary_tool_catalogue_parity_failed')
    controls = read(CONTROLS)
    required_cases = ('wrong-direction','wrong-image','wrong-pixel','wrong-range',
                      'cross-slot-same-png','wrong-sha','missing-claim','wrong-close')
    require(set(controls['cases']) == set(required_cases), 'incomplete_offline_rejection_matrix')
    actual = {}
    for label in SLOTS:
        prefix = POSITIVES
        trace = read(prefix/f'{label}_TRACE.json')
        result = read(prefix/f'{label}_RESULT.json')
        process = read(prefix/f'{label}_PROCESS.json')
        require(result['quality_complete'] is True and result['passed_items'] == result['total_items'] == 17
                and result['slot'] == label and process['exit_code'] == trace['entry_return_code'] == 0
                and trace['entry'] == str(SCORER) and trace['entry_exception'] is None
                and trace['new_Blender'] == trace['new_models'] == trace['new_rasters'] == 0
                and trace['argv'] == [process['argv'][5],*process['argv'][7:]]
                and str(V/'m4_source_region_score_admission_001/score.py') in
                    {row['path'] for row in trace['source_pins']},
                'actual_same_scoring_entry_not_qualified/'+label)
        actual[label] = {'result':pin(prefix/f'{label}_RESULT.json'), 'trace':pin(prefix/f'{label}_TRACE.json'),
                         'process':pin(prefix/f'{label}_PROCESS.json')}
        for row in trace['source_pins']:
            require(source_pins.setdefault(row['path'],row) == row,
                    'conflicting_scoring_dependency_identity/'+row['path'])
    verify_pins(source_pins.values())
    record = {'passed':True,'kind':'offline_closed_replay_only','replay':pin(REPLAY),'controls':pin(CONTROLS),
              'replay_binding':pin(REPLAY_BINDING),
              'truth':pin(TRUTH),'ingress':pin(INGRESS),'case_receipts':actual,
              'score_entry':pin(SCORER),'source_pins':list(source_pins.values())}
    return record


def freeze():
    require(not FROZEN.exists() and not JOURNAL.exists() and not (RUN/'slots').exists(),
            'one_freeze_before_formal_slots')
    require((HERE/'PLAN.md').read_bytes() == git('show', PLAN)
            and host.sha(sys.executable) == host.PYTHON_SHA and host.sha(host.CLI) == host.CLI_SHA,
            'fixed_plan_interpreter_or_CLI_changed')
    asset,digest = host.asset_identity()
    proof = qualify_scores()
    prior = V/'m4_source_region_score_admission_001'
    prior_files = tuple(prior/name for name in ('score.py','FROZEN.json','ADMISSION.json','trace_entry.py'))
    for path in prior_files:
        require(path.read_bytes() == git('show', PRIOR_SCORE+':'+path.relative_to(ROOT).as_posix()),
                'prior_score_path_changed/'+path.name)
    binding_path = host.PRODUCT_BINDING
    require(binding_path.read_bytes() == git('show', PRODUCT_PROOF+':'+binding_path.relative_to(ROOT).as_posix()),
            'accepted_product_binding_changed')
    binding = host.fixed_binding()
    wheel = Path(binding['wheel_path'])
    paths = {asset, wheel, binding_path, *prior_files, *host.retained_sources(),
             V/'m4_yanyite_bilateral_region_native_001/experiment.py',
             V/'m4_yanyite_bilateral_region_native_001/costs.py',
             V/'m4_yanyite_dual_curved_region_native_001/costs.py',
             V/'perf050_readonly_product_pilot_001/consumer/costs.py',
             *[Path(row['path']) for row in proof['source_pins']],
             *[p for p in PREFLIGHT.rglob('*') if p.is_file()],
             *[p for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.md','.json','.py','.txt')]}
    with ZipFile(wheel) as pack:
        for row in binding['source_manifest']:
            installed = Path(binding['install_root'])/row['path']
            require(host.sha(installed) == row['sha256'] and
                    installed.read_bytes() == pack.read(row['path']) == git('show',PRODUCT['commit']+':'+row['path']),
                    'fixed_product_file_changed/'+row['path'])
            paths.add(installed)
    inputs = {row['path']:row for row in map(pin,paths)}
    write(ENTRY, proof)
    inputs[str(ENTRY)] = pin(ENTRY)
    write(FROZEN,{'plan':PLAN,'product':PRODUCT,'asset_sha256':digest,'slots':list(SLOTS),'prompt':pin(PROMPT),
          'limits':LIMITS,'request_configuration':MODEL,'passed_offline_preflight':True,'gate':pin(ENTRY),
          'formal_entry':pin(Path(__file__)),'formal_commands':{label:command('slot',label) for label in SLOTS},
          'inputs':[inputs[path] for path in sorted(inputs)]})
    print('Frozen',verify_freeze(FROZEN),len(inputs),'inputs',flush=True)


def verify_freeze(path):
    require(Path(path).resolve(strict=True) == FROZEN, 'current_frozen_rail_batch_required')
    receipt = read(FROZEN)
    require(receipt['plan'] == PLAN and receipt['product'] == PRODUCT and receipt['asset_sha256'] == host.ASSET_SHA256
            and receipt['slots'] == list(SLOTS) and receipt['limits'] == LIMITS and receipt['prompt'] == pin(PROMPT)
            and receipt['request_configuration'] == MODEL and receipt['passed_offline_preflight'] is True
            and receipt['formal_entry'] == pin(Path(__file__)) and receipt['gate'] == pin(ENTRY)
            and receipt['formal_commands'] == {label:command('slot',label) for label in SLOTS},
            'frozen_launch_contract_changed')
    verify_pins(receipt['inputs'])
    return pin(FROZEN)['sha256']


def cold_child(label):
    """Exercise the actual immutable slot until just before reserving Blender."""
    root = COLD/label
    root.mkdir(parents=True,exist_ok=False)
    digest = verify_freeze(FROZEN)
    first = SLOTS[:SLOTS.index(label)]
    observed = {}
    for earlier in first:
        folder = root/'slots'/earlier
        folder.mkdir(parents=True)
        result = folder/'SLOT_RESULT.json'
        write(result, {'label':earlier,'freeze_sha256':digest,'status':'completed',
            'paid_API_calls':0,'actual_model_admitted':False,'consumer':None,
            'closure_verification':{'passed':True,'status':'ready_closed'},
            'independent_before_after':{'passed':True},'owner_close':{'confirmed':True},
            'budget':{'counts':{'Blender_spawned_unknown':0,'pending_raster_reservations':0}},
            'kind':'offline_simulated_order_prerequisite_only'})
        write(folder/'SLOT_PUBLICATION.json', {'label':earlier,'status':'completed',
              'owned_budget_passed':True,'result_sha256':host.sha(result),
              'kind':'offline_simulated_order_prerequisite_only'})
    journal = root/'FORMAL_SEQUENCE.jsonl'
    for key in (*first,label):
        OLD['append'](journal,{'event':'start','label':key,'freeze_sha256':digest,'offline_cold_start':True})
    namespace = OLD['admit'].__globals__
    namespace.update(RUN=root,JOURNAL=journal)
    try:
        common, module, _, _, _ = host.runtime_graph(root,label)
        original_start = module.Runtime.start
        original_budget = module.Runtime.__init__

        def init(worker,*args):
            original_budget(worker,*args)
            worker.budget = host.Gate(worker.budget,label)
            require(worker.budget.root.resolve() == root/'budget', 'cold_runtime_budget_root_mismatch')
            observed['runtime_class'] = inspect.getsourcefile(type(worker))

        def checked_start(worker):
            try:
                original_start(worker)
            except host.PreflightBoundary:
                require(worker.budget.reached and not worker.native_start_entered and worker.native is None
                        and worker.claim is None, 'cold_launch_crossed_reservation_boundary')
                observed.update(reached_before_Blender_reserve=True, counts=worker.budget.snapshot()['counts'],
                                start_implementation=inspect.getsourcefile(original_start))
                raise
            raise RuntimeError('real_slot_did_not_use_Blender_budget_boundary')

        runner = host.prepared_runner(common,OLD['admit'])
        require(runner.__globals__['EXTERNAL'] == root, 'cold_runner_output_root_changed')
        module.Runtime.start, module.Runtime.__init__ = checked_start, init
        try:
            exit_code = runner(label)
        finally:
            module.Runtime.start, module.Runtime.__init__ = original_start, original_budget
    finally:
        namespace.update(RUN=RUN,JOURNAL=JOURNAL)
    result_path = root/'slots'/label/'SLOT_RESULT.json'
    result = read(result_path)
    require(exit_code == 1 and result['freeze_sha256'] == digest and observed.get('reached_before_Blender_reserve')
            and result['qualification_gate_sha256'] == host.sha(ENTRY)
            and not result['actual_model_admitted'] and not (result_path.parent/'native').exists()
            and not any(observed['counts'][k] for k in ('Blender_start_attempts','consumer_admissions','all_raster_upper'))
            and any(row['type'] == 'PreflightBoundary' and row['stage'] == 'runtime_start' for row in result['errors']),
            'cold_real_slot_boundary_not_proven')
    files = {Path(path).resolve() for module in tuple(sys.modules.values())
             if isinstance(path:=getattr(module,'__file__',None),str) and Path(path).is_file()}
    write(root/'COLD_START.json',{'passed':True,'label':label,'pid':os.getpid(),'freeze_sha256':digest,
          'no_Blender_or_model':True,'same_formal_run_callable':True,'slot_receipt':pin(result_path),
          'offline_simulated_preceding_slots':list(first),'observed':observed,
          'imported_sources':[pin(path) for path in sorted(files)]})


def verify_cold(digest):
    rows = {label:read(COLD/label/'COLD_START.json') for label in SLOTS}
    require(len({row['pid'] for row in rows.values()}) == 2, 'cold_entries_did_not_use_distinct_processes')
    for label,row in rows.items():
        require(row['label'] == label and row['passed'] and row['freeze_sha256'] == digest
                and row['no_Blender_or_model'] and row['same_formal_run_callable']
                and row['observed']['reached_before_Blender_reserve']
                and row['slot_receipt'] == pin(row['slot_receipt']['path'])
                and row['offline_simulated_preceding_slots'] == list(SLOTS[:SLOTS.index(label)]),
                'cold_launch_admission_failed/'+label)
        verify_pins(row['imported_sources'])
    return rows


def cold():
    digest = verify_freeze(FROZEN)
    require(not JOURNAL.exists() and not (RUN/'slots').exists() and not COLD.exists(),
            'cold_validation_before_live_launch_only')
    for label in SLOTS:
        subprocess.run(command('cold_child',label),cwd=ROOT,check=True,timeout=150)
    rows = verify_cold(digest)
    print('Qualified cold startup',list(rows),flush=True)


def admit(label,path):
    verify_cold(host.sha(FROZEN))
    return OLD['admit'](label,path)


def formal():
    verify_cold(verify_freeze(FROZEN))
    OLD['formal']()


def archive():
    OLD['archive']()


OLD['formal'].__globals__.update(HERE=HERE,RUN=RUN,PLAN=PLAN,PRODUCT=PRODUCT,FROZEN=FROZEN,PROMPT=PROMPT,
    JOURNAL=JOURNAL,ENTRY=ENTRY,verify_freeze=verify_freeze,__file__=str(Path(__file__).resolve()))


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_rail_isolated_runtime_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('positive_scores','freeze','cold','cold_child','formal','slot','archive'))
    parser.add_argument('label',choices=SLOTS,nargs='?')
    args = parser.parse_args()
    require((args.phase in ('slot','cold_child')) == bool(args.label), 'current_label_required_for_slot_or_cold_child')
    if args.phase == 'slot':
        raise SystemExit(host.run_slot(args.label,admit))
    elif args.phase == 'cold_child':
        cold_child(args.label)
    else:
        globals()[args.phase]()
