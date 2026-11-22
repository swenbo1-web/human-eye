"""Continue the three unused slots after the closed P2 transport failure."""
from pathlib import Path
import runpy
import subprocess
import sys
import time

NS=Path(__file__).resolve().parent
sys.path[:0]=[str(NS/'harness'),str(NS/'qualification'),str(NS)]
import admission
from common import EXTERNAL, ORDER, ROOT, append, read, save, sha

FREEZE='ea8470e5be77195c07927425d2ebd3769eb4df6d57743dc27c6b44c0957a30b9'
FAILED='dda2f67a4cbb67fab671fd403fba3e4998f2e676978ac636ce168c706b25033a'
PREFIX=ORDER[:5]
REMAINING=ORDER[5:]
PREFLIGHT=EXTERNAL/'preflight'
JOURNAL=PREFLIGHT/'SEQUENCE.jsonl'
PROOF=PREFLIGHT/'P2_CLOSED_FAILURE_CONTINUATION.json'
ORIGINAL=PREFLIGHT/'SEQUENCE_BEFORE_P2_CONTINUATION.jsonl'
prior=admission.safe_to_continue


def qualification_boundary():
    result,publication=admission.publication('P2',FREEZE)
    slot=EXTERNAL/'slots/P2'
    runtime=read(slot/'RUNTIME_CLOSE.json')
    consumer=read(slot/'consumer/CONSUMER.json')
    close=result['closure_verification']
    owner=result['owner_close']
    ledger=result['budget']['counts']
    require=admission.require
    require(sha(slot/'SLOT_RESULT.json')==publication['result_sha256']==FAILED
            and result['status']==publication['status']=='failed' and publication['owned_budget_passed'] is True
            and result['model_consumers']==1 and result['paid_API_calls']==0
            and [item['stage'] for item in result['errors']]==['consumer']
            and all('Reconnecting... ' in item['event']['message']
                    for item in consumer['errors']) and len(consumer['errors'])==1
            and consumer['valid_completion'] is False and consumer['safe_to_continue'] is True
            and consumer['exit_code']==0 and consumer['process_reaped'] and consumer['readers_stopped']
            and consumer['runtime_exit']['confirmed'] and consumer['runtime_exit']['handle_closed']
            and consumer['deadline_timer_fired'] is False and not consumer['mutation_unknown'],
            'exact original P2 non-qualifying transport error is required')
    require(close['passed'] and close['status']=='ready_closed' and close['mcp_closure_required']
            and owner['confirmed'] and not owner['errors'] and not owner['transport_errors']
            and result['independent_before_after']['passed'] and runtime['Blender_close']['process_reaped']
            and runtime['Blender_exit']['confirmed'] and runtime['Blender_exit']['exit_code']==0
            and runtime['public_MCP_exit']['confirmed'] and runtime['public_MCP_exit']['exit_code']==0
            and runtime['public_MCP_close']['confirmed'] and runtime['public_MCP_close']['production_eof_and_exit_verified']
            and runtime['public_MCP_close']['process_handle_closed']
            and ledger['Blender_spawned_unknown']==ledger['pending_raster_reservations']==0,
            'the failed formal slot is not safe to schedule past')
    files=('SLOT_RESULT.json','SLOT_PUBLICATION.json','consumer/CONSUMER.json',
           'RUNTIME_CLOSE.json','TERMINAL_SOURCE.json','initial_capture/TERMINAL_SOURCE.json')
    return {'passed_for_scheduling_only':True,'freeze_sha256':FREEZE,'P2_original_status':'failed',
            'P2_result_sha256':FAILED,'continue_only':list(REMAINING),'replacement_allowed':False,
            'source_pins':{f:sha(slot/f) for f in files}}


def closed_for_admission(result,publication):
    if result['label']!='P2':
        return prior(result,publication)
    derived=qualification_boundary()
    admission.require(sha(ORIGINAL)==read(PROOF)['original_sequence_sha256']
                      and read(PROOF)=={**derived,'original_sequence_sha256':sha(ORIGINAL)},
                      'the derived scheduling-only receipt changed')
    return True


def child(label):
    admission.require(label in REMAINING and admission.verify_freeze()==FREEZE,
                      'no extra or replacement slot allowed')
    admission.safe_to_continue=closed_for_admission
    sys.argv=[str(NS/'harness/run_slot.py'),label]
    runpy.run_path(sys.argv[0],run_name='__main__')


def sequence():
    require=admission.require
    require(admission.verify_freeze()==FREEZE and tuple(REMAINING)==('N2','N3','P3'),
            'frozen trial roster changed')
    import json
    before=JOURNAL.read_bytes()
    events=[json.loads(line) for line in before.splitlines()]
    starts=[event['label'] for event in events if event['event']=='start']
    require(tuple(starts)==tuple(PREFIX) and events[-1]['event']=='blocked' and events[-1]['label']=='P2'
            and {p.name for p in (EXTERNAL/'slots').iterdir()}==set(PREFIX)
            and all(prior(*admission.publication(label,FREEZE)) for label in PREFIX[:-1]),
            'not the original interrupted sequence or slot already used')
    proof=qualification_boundary()
    with ORIGINAL.open('xb') as target:
        target.write(before)
    save(PROOF,{**proof,'original_sequence_sha256':sha(ORIGINAL)})
    append(JOURNAL,{'event':'continue_after_verified_owned_close','label':'P2','stamp_ns':time.perf_counter_ns(),
                    'proof_sha256':sha(PROOF),'original_sequence_sha256':sha(ORIGINAL),
                    'formal_outcome':'failed','remaining':list(REMAINING)})
    for label in REMAINING:
        append(JOURNAL,{'event':'start','label':label,'stamp_ns':time.perf_counter_ns(),'freeze_sha256':FREEZE})
        process=subprocess.run([sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),label],cwd=ROOT)
        try:
            result,receipt=admission.publication(label,FREEZE)
            safe=prior(result,receipt)
            append(JOURNAL,{'event':'publication','label':label,'exit_code':process.returncode,'status':receipt['status'],
                            'model_consumers':result['model_consumers'],'safe_to_continue':safe,
                            'result_sha256':receipt['result_sha256']})
            require(process.returncode==0 and safe,'actual_owned_slot_failed_or_unconfirmed')
        except Exception as error:
            append(JOURNAL,{'event':'blocked','label':label,'exit_code':process.returncode,
                            'type':type(error).__name__,'reason':str(error),
                            'remaining':list(REMAINING[REMAINING.index(label)+1:])})
            return 1
    return 0


if __name__=='__main__':
    admission.require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    if len(sys.argv)==2:
        child(sys.argv[1])
    else:
        raise SystemExit(sequence())
