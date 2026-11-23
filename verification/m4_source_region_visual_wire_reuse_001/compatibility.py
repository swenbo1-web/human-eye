"""Exercise the installed unflagged production endpoint and original image reference."""
from argparse import ArgumentParser
import json
from pathlib import Path
from runpy import run_path
import sys
from time import perf_counter_ns
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import experiment as trial
trial.stable = trial.shared['stable']

PRIOR = trial.PRIOR
DIRECTORIES = trial.ROOT/'preflight_compatibility'
LEGACY = trial.ROOT/'preflight_legacy_ref'
SLOT = LEGACY/'roundtrip/A'


def checked_tool_source(relative):
    path = PRIOR/relative
    tag = trial.PRIOR_COMMIT+':'+path.relative_to(HERE.parents[1]).as_posix()
    trial.need(path.read_bytes()==trial.git('show',tag),'prior_compatibility_source_changed')
    return path


def replay_worker(deadline):
    # Use the original standard exact-code replay logic on the current
    # candidate installation. No private visual command can reach it.
    old = run_path(str(PRIOR/'replay.py'))['run']
    namespace = old.__globals__
    installed_connector = namespace['installed_connector']

    def default_candidate(binding,label):
        trial.need(binding==trial.B_BINDING and label=='A','legacy_replay_wrong_arm')
        namespace['ROOT'] = trial.ROOT
        try:
            return installed_connector(binding,'B')
        finally:
            namespace['ROOT'] = LEGACY
    namespace.update(ROOT=LEGACY,installed_connector=default_candidate)
    old(SimpleNamespace(workspace=SLOT/'native',terminal=trial.shared['TERMINAL'],
        asset=trial.shared['FIXTURE'],asset_sha256=trial.ASSET,deadline_ns=deadline,
        label='A',binding=trial.B_BINDING))


def connect_catalogues(reference):
    old = run_path(str(checked_tool_source('compatibility.py')))['probe']
    standard = old.__globals__
    standard.update({k:trial.shared[k] for k in
                     ('HERE','ROOT','BASE_BINDING','B_BINDING','PYTHON','stable','load','save','reference_inputs','need')})
    a = old(trial.BASE_BINDING,DIRECTORIES/'A',reference)
    b = old(trial.B_BINDING,DIRECTORIES/'B-standard',reference)
    raw = [(DIRECTORIES/tag/'STDIO_RX.bin').read_bytes().splitlines()[1]
           for tag in ('A','B-standard')]
    trial.need(a==b and raw[0]==raw[1],'candidate_unflagged_tools_list_changed')
    return {'tools':len(a),'tools_list_response_bytes':len(raw[0]),
            'tools_list_exact_wire_equal':True,
            'raw_standard_stdio':{tag:{name:trial.pin(DIRECTORIES/tag/name)
                for name in ('STDIO_TX.bin','STDIO_RX.bin','STDIO_WORKER_EOF.json',
                             'LEGACY_REF_ADMISSION_STDOUT.bin')}
                for tag in ('A','B-standard')}}


def actual_legacy_roundtrip():
    old = run_path(str(checked_tool_source('supplement/legacy_ref.py')))['main']
    namespace = old.__globals__
    namespace.update(__file__=str(Path(__file__).resolve()),ROOT=LEGACY,SLOT=SLOT,
                     PREVIOUS=LEGACY/'unused',trial=SimpleNamespace(**trial.shared))
    old()
    row = trial.load(LEGACY/'RESULT.json')
    trial.need(row['passed'] and row['actual_Blender']==row['model_calls']==0
               and row['full_image_calls']==2 and row['software_raster_calls']==1
               and row['warm_ref_rasters']==0 and row['same_historical_original_png'],
               'candidate_legacy_reference_control_failed')
    return {'result':row,'receipt':trial.pin(LEGACY/'RESULT.json'),
            'archive':trial.pin(LEGACY/'ORIGINAL_RUNTIME.zip'),
            'closure':trial.pin(SLOT/'CLOSE.json')}


def main():
    start=perf_counter_ns()
    world = trial.reference_inputs()
    standard = connect_catalogues(world)
    legacy = actual_legacy_roundtrip()
    trial.save(trial.ROOT/'COMPATIBILITY.json',{
        'passed':True,'actual_Blender':0,'models':0,'formal_rasters':0,
        'standard':standard,'legacy_reference_roundtrip':legacy,'elapsed_ns':perf_counter_ns()-start,
        'scope':'separate archive-backed production stdio/TCP control',
    })


if __name__=='__main__':
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--worker',type=int)
    options=parser.parse_args()
    if options.worker is not None:
        replay_worker(options.worker)
    else:
        main()
