"""The frozen sixty unprofiled calls; root final Git-freeze GO is required."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import time
import traceback
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREVIOUS = ROOT/'verification/m3_pair_scalability_001/testing'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path,name):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def frozen_cases(designed):
    source = ROOT/designed['g508']['snapshot']
    assert sha(source)==designed['g508']['snapshot_sha256']
    objects = {row['name']:row for row in json.loads(source.read_bytes())['objects']}
    result = {'G508/'+name:(objects['Target'],objects[name]) for name in designed['g508']['candidates']}
    result['simple_control'] = (designed['simple_control']['left'],designed['simple_control']['right'])
    for name in ('fallback_intersecting_bars','fallback_full_containment'):
        row = next(row for row in designed['analytic_pairs'] if row['id']==name)
        result[name] = row['left'],row['right']
    return result


def run_call(arm,modules,left_raw,right_raw):
    # Earliest input allocation starts both the complete clock and original
    # deadline. The callback records no dictionary or auxiliary visit count.
    started = time.perf_counter_ns()
    deadline = started+30_000_000_000
    times = {}
    payload = None
    result = None
    diagnostics = {}
    error = None
    last = started

    def checkpoint(stage):
        if time.perf_counter_ns()>=deadline:
            raise TimeoutError('original_30s_complete_business_deadline')

    try:
        left,right = [types.SimpleNamespace(vertices=[tuple(point) for point in raw['vertices_world']],
            faces=[tuple(face) for face in raw['triangles']]) for raw in (left_raw,right_raw)]
        now = time.perf_counter_ns()
        times['input_preparation_ns'] = now-last
        checkpoint('after_input_preparation')
        last = now
        holder = {}
        facts = ['closed_solid_relation','surface_proximity'] if arm=='reference' else ['spatial_relation','surface_proximity']
        surface_work,closed_work = {},{}
        options = {'retain_exact_rank':True}
        now = time.perf_counter_ns()
        times['query_preparation_ns'] = now-last
        checkpoint('before_solving')
        last = now
        exact,closed = modules
        if arm=='reference':
            relation = closed.classify_closed_solids(left,right,checkpoint,diagnostics=closed_work,prepared_holder=holder)
            surface = exact.measure_surface_proximity(left,right,checkpoint,diagnostics=surface_work,
                _prepared_pair=holder.get('pair'),_boundary_contact=holder.get('boundary_contact'),**options)
            result = {'closed':relation,'surface':surface}
            diagnostics = {'closed_solid_pair_count':1,'surface_pair_count':1,
                'closed_solid_work':closed_work,'surface_work':surface_work}
        else:
            result = exact.measure_spatial_relation(left,right,checkpoint,diagnostics=diagnostics,
                prepared_holder=holder,**options)
        now = time.perf_counter_ns()
        times['solving_ns'] = now-last
        checkpoint('after_solving')
        last = now
        # Preserve each arm's full actual result and all product counters.
        payload = json.dumps({'requested_facts':facts,'result':result,'diagnostics':diagnostics},
            ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')
        now = time.perf_counter_ns()
        times['serialization_ns'] = now-last
        checkpoint('after_serialization')
    except BaseException as exception:
        error = {'type':type(exception).__name__,'message':str(exception),'traceback':traceback.format_exc()}
        now = time.perf_counter_ns()
    ended = time.perf_counter_ns()
    return {'arm':arm,'started_ns':started,'ended_ns':ended,'original_deadline_ns':deadline,
        'complete_business_ns':ended-started,'timing_stages_ns':times,
        'timing_residual_ns':ended-started-sum(times.values()),
        'within_original_30s':ended<deadline,'result':result,'diagnostics':diagnostics,'error':error,
        'payload_UTF8_bytes':None if payload is None else len(payload),
        'payload_sha256':None if payload is None else hashlib.sha256(payload).hexdigest()},payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root',required=True,type=Path)
    parser.add_argument('--candidate-source-sha256',required=True)
    parser.add_argument('--candidate-commit',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    batch_started = time.perf_counter_ns()
    assert len(args.candidate_commit)==40 and all(c in '0123456789abcdef' for c in args.candidate_commit)
    output = HERE/args.output
    assert output.resolve().parent==HERE.resolve()
    output.mkdir(exist_ok=False)
    frozen = json.loads((HERE/'FROZEN.json').read_bytes())
    designed = json.loads((HERE/'DESIGNED_CASES.json').read_bytes())
    sequence = json.loads((HERE/'TIMING_SEQUENCE.json').read_bytes())
    assert sha(HERE/'DESIGNED_CASES.json')==frozen['designed_cases_sha256']
    assert sha(HERE/'TIMING_SEQUENCE.json')==frozen['sequence_sha256']
    assert len(sequence['calls'])==60
    assert not (HERE/'TIMING_STARTED.json').exists(), 'one_frozen_timing_already_reserved'
    loading_started = time.perf_counter_ns()
    loader_path = PREVIOUS/'run_paired_kernel.py'
    assert sha(loader_path)=='668e56d8e887bc07ab24a888b004f3956e01299bc2d06c881f80fcf0fbcd68a7'
    loader = load(loader_path,'_prior_same_byte_kernel_loader')
    roots = {'reference':PREVIOUS/'baseline/product','candidate':args.candidate_root.resolve()}
    sources,manifests,modules,loading = {},{},{},{}
    for arm,root in roots.items():
        mark = time.perf_counter_ns()
        expected = '6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb' if arm=='reference' else args.candidate_source_sha256
        sources[arm],manifests[arm] = loader.source(root,expected)
        modules[arm] = loader.load_kernel('sufficient_timing_'+arm,root,sources[arm])
        loading[arm+'_source_load_ns'] = time.perf_counter_ns()-mark
    exact,closed = modules['reference']
    for qualified,change in frozen['reference_quantity_overrides'].items():
        name,key = qualified.split('.')
        module = exact if name=='surface_proximity' else closed
        assert getattr(module,key)==change['from']
        setattr(module,key,change['to'])
    cases = frozen_cases(designed)
    loading['total_loading_and_fixed_input_binding_ns'] = time.perf_counter_ns()-loading_started
    pins = {str(path):sha(path) for path in (Path(__file__),HERE/'FROZEN.json',HERE/'DESIGNED_CASES.json',
        HERE/'TIMING_SEQUENCE.json',HERE/'SOURCE_PINS.json',loader_path,
        ROOT/designed['g508']['snapshot'],ROOT/designed['g508']['truth'])}
    save(output/'INPUT_BINDINGS.json',{'frozen':frozen,'source_manifests':manifests,'source_files':pins,
        'candidate_commit':args.candidate_commit,'candidate_source_sha256':args.candidate_source_sha256,
        'loading_windows_ns':loading,'additional_spies':False,'per_checkpoint_dictionary':False,
        'scope':'common business facts with explicit reference/candidate additional-guarantee differences'})
    save(HERE/'TIMING_STARTED.json',{'output':str(output.resolve()),'calls':60,'candidate_commit':args.candidate_commit,
        'candidate_source_sha256':args.candidate_source_sha256,'input_bindings_sha256':sha(output/'INPUT_BINDINGS.json')})
    rows = []
    evidence_publication = []
    for slot in sequence['calls']:
        left,right = cases[slot['case']]
        row,payload = run_call(slot['arm'],modules[slot['arm']],left,right)
        row.update(slot)
        publication_started = time.perf_counter_ns()
        stem = str(slot['sequence']).zfill(2)+'_'+slot['arm']
        if payload is not None:
            (output/(stem+'.PAYLOAD.bin')).write_bytes(payload)
        save(output/(stem+'.json'),row)
        evidence_publication.append({'sequence':slot['sequence'],
            'elapsed_ns':time.perf_counter_ns()-publication_started})
        rows.append(row)
    source_unchanged = all((roots[arm]/name).read_bytes()==raw for arm,blobs in sources.items() for name,raw in blobs.items())
    preparation_unchanged = all(sha(Path(path))==expected for path,expected in pins.items())
    summaries = []
    for case in cases:
        arms = {}
        for arm in ('reference','candidate'):
            selected = [row for row in rows if row['case']==case and row['arm']==arm]
            values = [row['complete_business_ns'] for row in selected]
            arms[arm] = {'values_ns':values,'median_ns':statistics.median(values),'range_ns':[min(values),max(values)],
                'errors':sum(row['error'] is not None for row in selected),'within_original_30s':all(row['within_original_30s'] for row in selected)}
        summaries.append({'case':case,'arms':arms})
    batch_ended = time.perf_counter_ns()
    save(output/'RESULTS.json',{'samples':rows,'evidence_publication':evidence_publication,
        'summaries':summaries,'actual_calls':len(rows),'fixed_calls':60,'retries':0,
        'candidate_commit':args.candidate_commit,'candidate_source_sha256':args.candidate_source_sha256,
        'source_files_unchanged':source_unchanged,'preparation_files_unchanged':preparation_unchanged,
        'loading_windows_ns':loading,'batch_started_ns':batch_started,'batch_ended_ns':batch_ended,
        'batch_wall_ns':batch_ended-batch_started,
        'batch_timing_scope':'loading, fixed input binding, sixty calls and per-sample evidence publication, excludes this final summary publication',
        'Blender_sessions':0,'real_product_processes':0,'model_consumers':0,'performance_samples':60,
        'admission':'pending saved-only independent facts and all frozen performance checks'})
    return 0 if len(rows)==60 and source_unchanged and preparation_unchanged else 1


if __name__=='__main__':
    raise SystemExit(main())
