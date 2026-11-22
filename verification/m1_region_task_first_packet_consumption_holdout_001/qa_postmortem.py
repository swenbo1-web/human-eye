"""Explain the closed QA failure using the exact frozen input and a memory-only lookup correction."""

from pathlib import Path
from runpy import run_path
import sys
import traceback


NS = Path(__file__).resolve().parent
sys.path[:0] = [str(NS/'harness'), str(NS/'qualification'), str(NS)]
import admission
from admission import require
from common import EXTERNAL, PRODUCT_BINDING, SEAL, read, save, sha


def review():
    token = admission.verify_freeze()
    slot = EXTERNAL/'slots/QA'
    require({item.name for item in slot.parent.iterdir()} == {'QA'}
            and not (EXTERNAL/'preflight/QA_CLOSED_GATE.json').exists(),
            'postmortem_requires_original_failed_gate_and_unrun_remaining_slots')
    sys.path[:0] = [read(PRODUCT_BINDING)['dependency_root'], read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root']]
    raw, publication = admission.publication('QA', token)
    verify = run_path(str(NS/'qualification/closed.py'))['verify']
    try:
        verify(slot, raw)
    except ValueError as error:
        stack = traceback.extract_tb(error.__traceback__)
        require(str(error) == 'not enough values to unpack (expected 1, got 0)'
                and stack[-1].name == 'verify_discovery' and 'observation, =' in stack[-1].line,
                'did_not_reproduce_frozen_lookup_failure')
        failure = {'exception':type(error).__name__,'message':str(error),
                   'line':stack[-1].lineno,'source':stack[-1].line}
    else:
        raise ValueError('frozen_failure_was_not_reproduced')
    script = NS/'checks/evidence.py'
    original = script.read_text(encoding='utf8')
    old = "observation, = [item for item in producer['facts']['observations']"
    new = ("scope, = [record for record in producer['scopes'] if record['scope_id']==witness['scope_id']]\n"
           "        observation, = [item for item in scope['facts']['observations']")
    require(original.count(old) == 1,'exact_single_lookup_to_diagnose_required')

    def altered_in_memory(path):
        if Path(path).resolve() != script:
            return run_path(path)
        scope = {'__file__':str(script),'__name__':'qa_diagnostic_only'}
        exec(compile(original.replace(old,new),str(script),'exec'),scope)
        return scope

    verify.__globals__['run_path'] = altered_in_memory
    observed = verify(slot,raw)
    proofs = observed['full_or_evidence']
    pixel = lambda row: {key:row[key] for key in ('selected_surface_pixels','contrasting_boundary_pixels',
                                                  'view','scope_id','frame_identity','ref')}
    receipt = {'scope':'post-close diagnosis only. Frozen admission remains failed and no admitted result is issued.',
               'freeze_sha256':token,'original_slot_result_sha256':publication['result_sha256'],
               'frozen_script_sha256':sha(script),'reproduced_failure':failure,
               'later_checks_after_in_memory_lookup_change':True,
               'actual_witnesses':{key:pixel(row) for key,row in proofs['witnesses'].items()},
               'actual_global_R':pixel(proofs['global_R_shortfall']),
               'actual_named_blockers':proofs['P_blockers'],'independent_RIGHT_depth_order':proofs['independent_RIGHT_depth_order'],
               'actual_image_readback':observed['readback'],'actual_measurement':observed['measurement'],
               'actual_CLI':observed['CLI'],'actual_wire':observed['outer_calls'],
               'observed_rasters':observed['rasters'],'new_Blender_starts':0,'new_model_starts':0}
    output = NS/'evidence'
    output.mkdir(exist_ok=True)
    save(output/'QA_READONLY_DIAGNOSIS.json',receipt)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'pinned_interpreter_I_B_required')
    review()
