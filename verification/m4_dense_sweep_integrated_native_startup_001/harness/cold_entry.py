"""Exercise frozen formal entry in two cold processes without reserving Blender."""

import argparse
import ast
from contextlib import ExitStack
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
NS = HERE.parent
REPO = NS.parents[1]
RUN = Path('D:/he_m4_dense_sweep_integrated_native_startup_001')
OLD = Path('D:/he_m4_dense_sweep_integrated_native_pilot_recovery_001/slots/N1')
FROZEN = NS/'FROZEN.json'
LABELS = ('N1','P1')
FRESH_MODULES = ('runtime','budget','bridge')
EXPECTED_LIMITS = {'Blender_start_attempts':2,'all_rasters':24,'consumer_tasks':2,
                   'tools_per_slot':12,'rasters_by_slot':{'N1':12,'P1':12}}


class OfflineBlenderBudgetBoundary(RuntimeError):
    """Stop before executing any real Blender reservation."""


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open('xb') as stream:
        stream.write((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())


def pin(path):
    raw = path.read_bytes()
    return {'path':str(path.resolve()),'bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def reject(action, expected):
    try:
        action()
    except ValueError as error:
        require(str(error)==expected,f'unexpected_control_rejection/{error}')
        return str(error)
    raise ValueError('unexpected_control_acceptance/'+expected)


def enforce_scratch_only(scratch):
    def contained(path):
        require(not isinstance(path,int) and Path(os.fsdecode(path)).resolve().is_relative_to(scratch),
                'cold_probe_write_outside_temporary_root/'+str(path))

    def audit(event, args):
        if event == 'open':
            pathname, mode, flags = args
            if (isinstance(mode,str) and any(flag in mode for flag in 'wax+')
                    or isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
                contained(pathname)
        elif event in ('os.mkdir','os.remove','os.rmdir','os.chmod','os.utime'):
            contained(args[0])
        elif event in ('os.rename','os.link','os.symlink'):
            contained(args[0])
            contained(args[1])
        elif event == 'subprocess.Popen':
            _, command, _, _ = args
            # The only process allowed during the actual cold entry is git
            # show, used by the unchanged sealed-evidence verifier.
            require((isinstance(command,(list,tuple)) and list(command[:2])==['git','show'])
                    or (isinstance(command,str) and command.startswith('git show ')),
                    'cold_probe_worker_process_forbidden')
        elif event in ('os.system','os.exec','os.spawn','os.posix_spawn'):
            raise ValueError('cold_probe_worker_process_forbidden')
    sys.addaudithook(audit)


def simulated_predecessor(admission, common, scratch, token):
    rejected_root = scratch/'old_failed_predecessor'
    failure = rejected_root/'slots/N1'
    failure.mkdir(parents=True)
    for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json','SLOT_STARTED.json'):
        (failure/name).write_bytes((OLD/name).read_bytes())
    old_raw, old_receipt = (read(failure/name) for name in ('SLOT_RESULT.json','SLOT_PUBLICATION.json'))
    require(old_receipt['result_sha256']==pin(failure/'SLOT_RESULT.json')['sha256']
            and old_raw['status']==old_receipt['status']=='failed' and old_raw['model_consumers']==0
            and not admission.safe_to_continue(old_raw,old_receipt),'old_failed_N1_not_sealed_or_not_failed')
    baseline = sys.path[:]
    with patch.object(admission,'EXTERNAL',rejected_root):
        reason = reject(lambda: admission.validate_admission('P1',FROZEN),
                        'new_formal_owned_publication_binding_changed/N1')
    require(sys.path==baseline and all(name not in sys.modules for name in FRESH_MODULES),
            'old_failed_predecessor_check_leaked_path_or_preloaded_runtime')
    slot = scratch/'formal/slots/N1'
    slot.mkdir(parents=True)
    fixture = {
        'offline_predecessor_simulation':True, 'label':'N1','group':'N','phase':'formal',
        'asset_sha256':common.ASSET_SHA256,'freeze_sha256':token,
        'product_binding_sha256':pin(common.PRODUCT_BINDING)['sha256'],'product_source_sha256':common.SOURCE_SHA,
        'status':'completed','model_consumers':1,'paid_API_calls':0,
        'closure_verification':{'passed':True,'status':'ready_closed','mcp_closure_required':False},
        'owner_close':{'confirmed':True,'errors':[],'transport_errors':[]},
        'independent_before_after':{'passed':True},'consumer':{'safe_to_continue':True},
        'budget':{'counts':{'Blender_spawned_unknown':0,'pending_raster_reservations':0}},
    }
    result_path = slot/'SLOT_RESULT.json'
    write(result_path,fixture)
    write(slot/'SLOT_PUBLICATION.json',{
        'offline_predecessor_simulation':True,'label':'N1','status':'completed','owned_budget_passed':True,
        'result_sha256':pin(result_path)['sha256'],
    })
    write(scratch/'OFFLINE_PREDECESSOR.json',{
        'simulation':True,'purpose':'exercise_P1_order_only','prior_actual_runs':0,
        'not_for_formal_ledger':True,'old_failed_predecessor_reason':reason,
    })
    return {'simulated':True,'old_failed_predecessor_rejected':True,
            'reason':reason,'old_result':pin(OLD/'SLOT_RESULT.json'),
            'old_publication':pin(OLD/'SLOT_PUBLICATION.json')}


def failed_receipt_path_restoration(admission,scratch):
    malformed = deepcopy(read(admission.DERIVED))
    malformed['evidence']['reused_qualification_rasters'] += 1
    path = scratch/'OFFLINE_REJECTED_DERIVED_RECEIPT.json'
    write(path,malformed)
    baseline = sys.path[:]
    reason = reject(lambda: admission.verify_derived(path),'derived_gate_does_not_match_original_closed_evidence')
    require(sys.path==baseline,'rejecting_full_derived_audit_leaked_import_path')
    return {'restored':True,'after_full_audit':True,'reason':reason}


def cold_arm(label,scratch):
    scratch = scratch.resolve(strict=True)
    require(not list(scratch.iterdir()) and not scratch.is_relative_to(RUN.resolve())
            and not scratch.is_relative_to(REPO.resolve()) and not scratch.is_relative_to(OLD.parents[1].resolve()),
            'cold_arm_requires_unique_empty_temporary_root')
    enforce_scratch_only(scratch)
    require(all(name not in sys.modules for name in FRESH_MODULES),'cold_modules_preloaded')
    entry = run_path(str(HERE/'run_slot.py'))
    run, admission = entry['run'], entry['admission']
    common = sys.modules['common']
    actual_admission = run.__globals__['validate_admission']
    require(actual_admission is admission.validate_admission and all(name not in sys.modules for name in FRESH_MODULES),
            'old_or_preloaded_formal_entry')
    token = admission.verify_freeze()
    controls = simulated_predecessor(admission,common,scratch,token) if label=='P1' else None
    root = scratch/'formal'
    definition = next(node for node in ast.parse(Path(run.__code__.co_filename).read_bytes()).body
                      if isinstance(node,ast.FunctionDef) and node.name=='run')
    before_import, = [node.lineno for node in ast.walk(definition)
                      if isinstance(node,ast.ImportFrom) and node.module=='runtime']
    before_constructor, = [node.lineno for node in ast.walk(definition)
                           if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='Runtime']
    checkpoints = {}
    reserve_code = None

    def admission_observed(candidate,path):
        baseline = sys.path[:]
        value = actual_admission(candidate,path)
        require(value['freeze_sha256']==token and sys.path==baseline
                and all(name not in sys.modules for name in FRESH_MODULES),'successful_admission_path_not_cold_or_restored')
        checkpoints['actual_admission'] = {'same_frozen_gate':True,'restored':True,'runtime_modules_absent':True}
        return value

    with ExitStack() as patches:
        patches.enter_context(patch.object(common,'EXTERNAL',root))
        patches.enter_context(patch.object(admission,'EXTERNAL',root))
        patches.enter_context(patch.dict(run.__globals__,{'EXTERNAL':root,'validate_admission':admission_observed}))

        def launcher_trace(frame,event,arg):
            nonlocal reserve_code
            if event=='line' and frame.f_lineno==before_import:
                require(checkpoints.get('actual_admission') and all(name not in sys.modules for name in FRESH_MODULES),
                        'formal_scope_was_not_cold_before_first_Runtime_import')
                checkpoints['first_import_after_derived_admission'] = True
            if event=='line' and frame.f_lineno==before_constructor:
                modules = {name:Path(sys.modules[name].__file__).resolve() for name in FRESH_MODULES}
                require(all(path==HERE/f'{name}.py' for name,path in modules.items()),'formal_module_import_origin_changed')
                runtime = frame.f_locals['Runtime']
                budget = sys.modules['budget']
                require(budget.LIMITS==EXPECTED_LIMITS,'formal_runtime_budget_limits_changed')
                scopes = [kind.__dict__['__init__'].__globals__ for kind in runtime.__mro__
                          if hasattr(kind.__dict__.get('__init__'),'__globals__')
                          and 'EXTERNAL' in kind.__dict__['__init__'].__globals__]
                bases = [scope for scope in scopes if Path(scope['__file__']).name=='owned_runtime.py']
                require(len(bases)==1 and bases[0]['Budget'] is budget.Budget,'base_owned_constructor_budget_not_bound')
                runtime_module = sys.modules['runtime']
                patches.enter_context(patch.object(runtime_module,'EXTERNAL',root))
                for scope in scopes:
                    patches.enter_context(patch.dict(scope,{'EXTERNAL':root}))
                require(all(scope['EXTERNAL']==root for scope in scopes) and common.EXTERNAL==admission.EXTERNAL==root
                        and frame.f_globals['EXTERNAL']==runtime_module.EXTERNAL==root,'split_temporary_runtime_root')
                checkpoints['imports'] = {name:pin(path) for name,path in modules.items()}
                checkpoints['base_owned_runtime'] = pin(Path(bases[0]['__file__']))
                checkpoints['base_external'] = str(bases[0]['EXTERNAL'])
                reserve_code = budget.Budget.reserve.__code__
            return launcher_trace

        def route_trace(frame,event,arg):
            if frame.f_code is run.__code__:
                return launcher_trace(frame,event,arg)
            if event=='call' and frame.f_code is reserve_code:
                budget = frame.f_locals['self']
                runtime = frame.f_back.f_locals['self']
                require(checkpoints.get('imports') and runtime.budget is budget
                        and frame.f_back.f_code is runtime.start.__code__
                        and budget.root==(root/'budget').resolve()
                        and runtime.folder==(root/'slots'/label).resolve()
                        and runtime.label==label and runtime.group==label[0] and runtime.phase=='formal'
                        and all(frame.f_locals[k]==v for k,v in
                                {'kind':'Blender_start','label':label,'phase':'formal','upper':1}.items()),
                        'actual_runtime_its_ledger_or_reservation_boundary_changed')
                snapshot = budget.snapshot()
                require(snapshot['limits']==EXPECTED_LIMITS and not snapshot['records'] and not snapshot['slots']
                        and all(count==0 for count in snapshot['counts'].values()),
                        'actual_constructor_budget_is_not_empty_and_bound')
                checkpoints['runtime_constructed'] = True
                checkpoints['budget'] = {'limits':snapshot['limits'],'root':str(budget.root),
                                         'counts_before_reserve':snapshot['counts']}
                checkpoints['reserve_call_before_body'] = {'kind':'Blender_start','label':label,'phase':'formal','upper':1}
                raise OfflineBlenderBudgetBoundary('offline_intentional_stop_before_Blender_start_claim')
            return None

        sys.settrace(route_trace)
        try:
            run_status = run(label)
        finally:
            sys.settrace(None)

    slot = root/'slots'/label
    result, publication, close = (read(slot/name) for name in
                                  ('SLOT_RESULT.json','SLOT_PUBLICATION.json','RUNTIME_CLOSE.json'))
    errors = [(item['stage'],item['type'],item['message']) for item in result['errors']]
    require(run_status==1 and result['status']==publication['status']=='failed'
            and result['freeze_sha256']==token
            and publication['result_sha256']==pin(slot/'SLOT_RESULT.json')['sha256']
            and errors==[('runtime_start','OfflineBlenderBudgetBoundary','offline_intentional_stop_before_Blender_start_claim')]
            and result['closure_verification']['status']=='startup_failed_clean'
            and result['closure_verification']['basis']=='not_entered_no_owned_process'
            and result['closure_verification']['passed'] and close['errors']==[]
            and result['actual_model_admitted'] is False and result['model_consumers']==result['paid_API_calls']==0
            and result['budget']['counts']==checkpoints['budget']['counts_before_reserve']
            and not result['budget']['records'] and not result['budget']['slots']
            and {p.name for p in slot.iterdir()}=={'RUNTIME_CLOSE.json','SLOT_STARTED.json','SLOT_RESULT.json','SLOT_PUBLICATION.json'},
            'offline_intentional_stop_and_cleanup_unconfirmed')
    require(all(not list((root/'budget'/part).iterdir()) for part in ('claims','settlements')),
            'cold_probe_wrote_actual_budget_claim')
    adverse = failed_receipt_path_restoration(admission,scratch) if label=='N1' else None
    return {'passed':True,'label':label,'freeze_sha256':token,'pid':os.getpid(),
            'started_ns':result['started_ns'],'ended_ns':result['closed_ns'],
            'actual_entry':pin(HERE/'run_slot.py'),'actual_retained_run':pin(Path(run.__code__.co_filename)),
            'temporary_root':str(scratch),'checks':checkpoints,'predecessor':controls,
            'rejecting_path_restoration':adverse,'clean_stop':result['closure_verification'],
            'actual_Blender_starts':0,'actual_model_starts':0,'actual_rasters':0}


def run_preflight():
    require(FROZEN.is_file() and not (RUN/'slots').exists() and not (RUN/'budget').exists(),
            'cold_preflight_requires_frozen_unstarted_formal_roster')
    token = pin(FROZEN)['sha256']
    output = RUN/'preflight/cold_entry'
    output.mkdir(parents=True,exist_ok=False)
    arms = {}
    for label in LABELS:
        folder = output/label
        folder.mkdir()
        started = time.perf_counter_ns()
        with TemporaryDirectory(prefix='m4-startup-cold-') as target:
            scratch = Path(target)
            command = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),'--arm',label,'--scratch',str(scratch)]
            try:
                child = subprocess.run(command,cwd=REPO,capture_output=True,timeout=120)
                stdout,stderr,code = child.stdout,child.stderr,child.returncode
            except subprocess.TimeoutExpired as error:
                stdout,stderr,code = error.stdout or b'',error.stderr or b'',None
            (folder/'stdout.bin').write_bytes(stdout)
            (folder/'stderr.bin').write_bytes(stderr)
            held = []
            for path in sorted(p for p in scratch.rglob('*') if p.is_file()):
                require(path.resolve().is_relative_to(scratch.resolve()),'cold_probe_artifact_scope_changed')
                copy = folder/'scratch'/path.relative_to(scratch)
                copy.parent.mkdir(parents=True,exist_ok=True)
                copy.write_bytes(path.read_bytes())
                held.append(pin(copy))
            child_proof, decode_error = None, None
            if code==0:
                try:
                    child_proof = json.loads(stdout.splitlines()[-1])
                except (ValueError,IndexError) as error:
                    decode_error = type(error).__name__
        passed = bool(child_proof and child_proof['passed'] and child_proof['label']==label
                      and child_proof['freeze_sha256']==token and child_proof['checks']['runtime_constructed']
                      and child_proof['actual_Blender_starts']==child_proof['actual_model_starts']==child_proof['actual_rasters']==0
                      and not scratch.exists())
        receipt = folder/'RECEIPT.json'
        write(receipt,{'passed':passed,'label':label,'freeze_sha256':token,'argv':command,'returncode':code,
                       'stdout_receipt_decode_error':decode_error,
                       'started_ns':started,'finished_ns':time.perf_counter_ns(),'removed_temporary_root':not scratch.exists(),
                       'stdout':pin(folder/'stdout.bin'),'stderr':pin(folder/'stderr.bin'),'held_files':held,'proof':child_proof})
        arms[label] = {'passed':passed,'receipt':pin(receipt)}
        if not passed:
            break
    passed = tuple(arms)==LABELS and all(arm['passed'] for arm in arms.values())
    actual_receipt = output.parent/'COLD_ENTRY.json'
    write(actual_receipt,{'schema':'m4-dense-native-startup-cold-entry-v1','passed':passed,
                          'freeze_sha256':token,'arms':arms,'unrun':[label for label in LABELS if label not in arms],
                          'program':pin(Path(__file__)),'formal_slots_created':False,'actual_Blender_starts':0,
                          'actual_model_starts':0,'actual_rasters':0})
    require(not (RUN/'slots').exists() and not (RUN/'budget').exists(),'cold_preflight_created_formal_output')
    print('Cold formal entry', 'passed' if passed else 'failed',pin(actual_receipt)['sha256'],flush=True)
    return 0 if passed else 1


if __name__=='__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_isolated_cold_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm',choices=LABELS)
    parser.add_argument('--scratch',type=Path)
    args = parser.parse_args()
    require((args.arm is None)==(args.scratch is None),'provide_arm_and_its_temporary_root')
    if args.arm is None:
        raise SystemExit(run_preflight())
    print(json.dumps(cold_arm(args.arm,args.scratch),ensure_ascii=False,separators=(',',':')))
