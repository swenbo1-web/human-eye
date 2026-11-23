"""Preflight the real score CLI and freeze its four complete offline results."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from inputs import ASSETS, PRODUCT, RUN, manifest, pin, read, require, verify_manifest


V = HERE.parent
OLD = run_path(str(V/'m2_source_region_shared_normalization_live_001/experiment.py'))
git = OLD['git']
PLAN = '823bc1d538fdf00a1031f5463ef026065a7c058c:docs/M4_SOURCE_REGION_SCORE_ADMISSION_001_PLAN.md'
PYTHON = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
FIRST_REPORT = RUN/'preflight/QUALIFICATION.json'
SECOND_REPORT = RUN/'preflight_verified/QUALIFICATION.json'
PRE = RUN/'preflight_qualified'
PRE_REPORT = PRE/'QUALIFICATION.json'
MANIFEST = PRE/'INPUT_MANIFEST.json'
FROZEN = HERE/'FROZEN.json'
CONTROLS = ('wrong-direction','wrong-path','wrong-pixel','cross-slot-same-png','wrong-capture','wrong-sha',
            'duplicate-claim','missing-claim','unexpected-claim')
SCORE_KEYS = ('criteria','chosen_images','same_slot_geometry','adoption','CLI_stdout','answer','actual_final_item')


def write(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')


def planned(custody):
    for asset, data in custody['assets'].items():
        for label,slot in data['slots'].items():
            common = ('--slot',slot['slot_path'],'--claims',slot['claims_path'])
            if asset == 'assembly':
                yield f'baseline_{label}', 'baseline.py', common, 1
            yield f'{asset}_{label}', 'score.py', ('--asset',asset,*common), 0
    for case in CONTROLS:
        yield case,'controls.py',('--case',case),0


def launch(name,entry,arguments):
    folder = PRE/'jobs'/name
    folder.mkdir(parents=True,exist_ok=False)
    output, receipt = folder/'RESULT.json', folder/'TRACE.json'
    argv = [sys.executable,'-IB','-X','utf8',str(HERE/'trace_entry.py'),str(HERE/entry),str(receipt),
            *arguments,'--output',str(output)]
    begin = time.perf_counter_ns()
    child = subprocess.Popen(argv,cwd=V.parent,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        stdout,stderr = child.communicate(timeout=75)
    except subprocess.TimeoutExpired:
        child.kill()
        stdout,stderr = child.communicate()
    closed = time.perf_counter_ns()
    (folder/'STDOUT.bin').write_bytes(stdout)
    (folder/'STDERR.bin').write_bytes(stderr)
    write(folder/'PROCESS.json', {'name':name,'pid':child.pid,'return_code':child.returncode,
          'argv':argv,'begin_ns':begin,'closed_ns':closed,'wall_ns':closed-begin,
          'stdout':pin(folder/'STDOUT.bin'),'stderr':pin(folder/'STDERR.bin'),
          'trace':pin(receipt) if receipt.is_file() else None,'result':pin(output) if output.is_file() else None})


def public_boundary():
    """A malformed nonpublic line must not be handed to the JSON decoder."""
    approved = run_path(str(HERE/'score.py'))['public_events']
    boundary = PRE/'PUBLIC_READER_INPUT.jsonl'
    accepted_rows = [
        {'type':'item.completed','item':{'id':'item_1','type':'mcp_tool_call','result':{'content':[]}}},
        {'type':'item.completed','item':{'id':'item_2','type':'agent_message','text':'public final'}},
        {'type':'turn.completed','usage':{'input_tokens':6,'cached_input_tokens':3,'output_tokens':2,'private_stat':999}},
    ]
    with boundary.open('xb') as stream:
        stream.write(b'{"perf_ns":1,"event":{"type":"item.completed","item":{"id":"item_0","type":"reasoning",!\n')
        for i,event in enumerate(accepted_rows,2):
            stream.write(json.dumps({'perf_ns':i,'event':event},separators=(',',':')).encode()+b'\n')
    actual = list(approved(boundary))
    accepted_rows[-1]['usage'].pop('private_stat')
    require(actual == accepted_rows,'head_first_public_boundary_failed')
    write(PRE/'PUBLIC_READER.json',{'passed':True,'input':pin(boundary),'accepted_events':3,
          'malformed_nonpublic_event_skipped':True,'usage_keys':sorted(actual[-1]['usage'])})


def compare(name,entry,record,custody):
    if entry == 'baseline.py':
        original = read(custody['assets']['assembly']['slots'][record['slot']]['original_score_path'])
        require(record['adaptation']=='approved public event reader only'
                and record['confirmed_original_baseline_exit']==1,'old_baseline_reader_scope_changed/'+name)
        if name.endswith('N1'):
            verdict = record['score']
            require(verdict['passed_items']==original['passed_items']==7
                    and verdict['total_items']==original['total_items']==17
                    and verdict['criteria']==original['criteria'],'legacy_native_score_not_reproduced')
        else:
            require(record['score'] is None
                    and record['exception']=={'type':original['error_type'],'message':original['error']},
                    'legacy_plugin_path_error_not_reproduced')
        return
    if entry == 'score.py':
        asset,label = name.split('_')
        original = read(custody['assets'][asset]['slots'][label]['expected_score_path'])
        require(record['asset']==asset and record['slot']==label and record['quality_complete']
                and record['passed_items']==record['total_items']==17
                and all(record[k]==original[k] for k in SCORE_KEYS),
                'candidate_did_not_preserve_all_original_verified_outcomes/'+name)
        return
    require(record['case']==name and record['passed'] is True and record['candidate_exit_code'] != 0
            and record['candidate_entry']==pin(HERE/'score.py') and
            record['candidate_receipt']==pin(record['candidate_receipt']['path'])
            and read(record['candidate_receipt']['path'])['quality_complete'] is False,
            'candidate_control_did_not_reject/'+name)


def evidence(custody):
    checked, pins = [], {}
    for name,entry,args,expected_code in planned(custody):
        folder = PRE/'jobs'/name
        process = read(folder/'PROCESS.json')
        require(process['name']==name and process['return_code']==expected_code and process['trace'] and process['result'],
                'cold_preflight_failed/'+name)
        trace = read(process['trace']['path'])
        require(trace['entry']==str(HERE/entry) and trace['argv']==[str(HERE/entry),*args,'--output',str(folder/'RESULT.json')]
                and trace['pid']==process['pid'] and trace['entry_return_code']==expected_code
                and trace['entry_exception'] is None
                and process['begin_ns']<=trace['started_ns']<=trace['closed_ns']<=process['closed_ns']
                and trace['new_Blender']==trace['new_models']==trace['new_rasters']==0,
                'cold_preflight_entry_exit_or_budget_changed/'+name)
        for row in (process['trace'],process['result'],process['stdout'],process['stderr'],
                    pin(folder/'PROCESS.json'),*trace['source_pins']):
            require(pin(row['path'])==row and pins.setdefault(row['path'],row)==row,
                    'preflight_executed_input_or_result_changed/'+row['path'])
        actual_deps = {Path(p['path']).resolve() for p in trace['source_pins']}
        require({HERE/'score.py',V/'m4_assembly_evidence_consumption_001/consumer_contract.py',
                 V/'m4_assembly_cross_asset_product_native_001/score.py',
                 V/'m4_yanyite_opposite_direction_product_native_001/score.py'}.issubset(actual_deps),
                'critical_transitive_scoring_code_was_not_observed/'+name)
        compare(name,entry,read(process['result']['path']),custody)
        checked.append({'name':name,'passed':True,'process':pin(folder/'PROCESS.json'),
                        'trace':process['trace'],'result':process['result']})
    return checked,pins


def preflight():
    require((HERE/'PLAN.md').read_bytes()==git('show',PLAN) and pin(sys.executable)['sha256']==PYTHON,
            'fixed_plan_and_interpreter_required')
    PRE.mkdir(parents=True,exist_ok=False)
    custody = manifest()
    write(MANIFEST,custody)
    public_boundary()
    for name,entry,args,_ in planned(custody):
        launch(name,entry,args)
    verify_manifest(custody)
    try:
        checked,pins = evidence(custody)
    except (OSError,ValueError,KeyError,TypeError) as error:
        write(PRE_REPORT,{'passed':False,'reason':str(error),'manifest':pin(MANIFEST)})
        raise
    write(PRE_REPORT,{'passed':True,'manifest':pin(MANIFEST),'public_boundary':pin(PRE/'PUBLIC_READER.json'),
          'cases':checked,'source_pins':sorted(pins.values(),key=lambda r:r['path'])})
    print('Qualified',len(checked),'cold scoring entries',flush=True)


def gate(report,custody):
    require(report.get('passed') is True,'full_scoring_preflight_did_not_pass')
    require(report.get('manifest')==pin(MANIFEST) and report.get('public_boundary')==pin(PRE/'PUBLIC_READER.json'),
            'preflight_manifest_or_event_boundary_changed')
    require(read(PRE/'PUBLIC_READER.json')['passed'] is True,'public_event_boundary_failed')
    require([r['name'] for r in report.get('cases',[])]==[j[0] for j in planned(custody)]
            and all(row['passed'] is True for row in report['cases']),'full_scoring_preflight_incomplete')
    actual,pins = evidence(custody)
    require(actual==report['cases'] and list(sorted(pins.values(),key=lambda r:r['path']))==report['source_pins'],
            'preflight_result_or_executed_dependency_binding_changed')


def freeze():
    require(not FROZEN.exists(),'single_score_admission_freeze')
    custody,report = read(MANIFEST),read(PRE_REPORT)
    verify_manifest(custody)
    gate(report,custody)
    rejected = {}
    for name,value in [('actual_read_guard_failed_preflight',read(FIRST_REPORT)),
                       ('actual_claim_matcher_failed_preflight',read(SECOND_REPORT)),
                       ('failed_preflight',{**report,'passed':False}),
                       ('missing_full_case',{**report,'cases':report['cases'][:-1]})]:
        try:
            gate(value,custody)
        except ValueError as error:
            rejected[name] = str(error)
        else:
            raise ValueError('freeze_admitted_bad_preflight/'+name)
    changed = deepcopy(report)
    changed['cases'][0]['result']['sha256'] = '0'*64
    try:
        gate(changed,custody)
    except ValueError as error:
        rejected['altered_result_binding'] = str(error)
    else:
        raise ValueError('freeze_admitted_altered_result_binding')
    write(PRE/'GATE_CONTROLS.json',{'passed':True,'rejected':rejected})
    files = [*custody['source_pins'],*report['source_pins'],pin(PRE_REPORT),pin(MANIFEST),
             pin(PRE/'PUBLIC_READER.json'),pin(PRE/'PUBLIC_READER_INPUT.jsonl'),pin(PRE/'GATE_CONTROLS.json'),
             pin(HERE/'PLAN.md'),pin(HERE/'experiment.py'),pin(HERE/'inputs.py'),pin(FIRST_REPORT),pin(SECOND_REPORT)]
    unique = {row['path']:row for row in files}
    write(FROZEN, {'plan':PLAN,'installed_product':PRODUCT,'historical_assets':list(ASSETS),
          'qualified_cases':len(report['cases']),'qualification':pin(PRE_REPORT),
          'manifest':pin(MANIFEST),'gate_controls':pin(PRE/'GATE_CONTROLS.json'),
          'inputs':sorted(unique.values(),key=lambda r:r['path'])})
    print('Frozen',verify_freeze(),'with',len(unique),'inputs',flush=True)


def verify_freeze():
    frozen = read(FROZEN)
    require(frozen['plan']==PLAN and frozen['installed_product']==PRODUCT
            and frozen['qualification']==pin(PRE_REPORT) and frozen['manifest']==pin(MANIFEST)
            and all(pin(row['path'])==row for row in frozen['inputs']),'frozen_score_admission_inputs_changed')
    return pin(FROZEN)['sha256']


def archive():
    verify_freeze()
    seal = OLD['archive']
    seal.__globals__['RUN'] = RUN
    seal()


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode,'fixed_isolated_interpreter_required')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('phase',choices=('preflight','freeze','archive'))
    globals()[cli.parse_args().phase]()
