"""One root-authorized six-case diagnostic pass, outside primary timing."""

import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import traceback
import types
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREVIOUS = ROOT/'verification/m3_pair_scalability_001/testing'


def load(path,name):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-root',required=True,type=Path)
    parser.add_argument('--source-sha256',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    output = HERE/args.output
    assert output.resolve().parent==HERE.resolve()
    output.mkdir(exist_ok=False)
    frozen = json.loads((HERE/'FROZEN.json').read_bytes())
    assert sha(HERE/'DESIGNED_CASES.json')==frozen['designed_cases_sha256']
    designed = json.loads((HERE/'DESIGNED_CASES.json').read_bytes())
    loader_path = PREVIOUS/'run_paired_kernel.py'
    assert sha(loader_path)=='668e56d8e887bc07ab24a888b004f3956e01299bc2d06c881f80fcf0fbcd68a7'
    loader = load(loader_path,'_prior_manifest_kernel_loader')
    engine = args.product_root.resolve()
    blobs,manifest = loader.source(engine,args.source_sha256)
    exact,closed = loader.load_kernel('sufficient_work_observation',engine,blobs)
    source_path = ROOT/designed['g508']['snapshot']
    assert sha(source_path)==designed['g508']['snapshot_sha256']
    objects = {row['name']:row for row in json.loads(source_path.read_bytes())['objects']}
    cases = [(name,objects['Target'],objects[name]) for name in designed['g508']['candidates']]
    cases.append(('simple_control',designed['simple_control']['left'],designed['simple_control']['right']))
    for name in ('fallback_intersecting_bars','fallback_full_containment'):
        row = next(row for row in designed['analytic_pairs'] if row['id']==name)
        cases.append((name,row['left'],row['right']))
    save(output/'INPUT_BINDINGS.json',{'manifest':manifest,'source_sha256':args.source_sha256,
        'loader_sha256':sha(loader_path),'script_sha256':sha(Path(__file__)),
        'frozen_sha256':sha(HERE/'FROZEN.json'),'case_order':[row[0] for row in cases],
        'scope':'one six-case function-work observation with spies; not a performance sample'})
    rows = []
    for name,left_raw,right_raw in cases:
        left,right = [types.SimpleNamespace(vertices=[tuple(point) for point in raw['vertices_world']],
            faces=[tuple(face) for face in raw['triangles']]) for raw in (left_raw,right_raw)]
        counts = {}
        functions = ((exact,'measure_surface_proximity'),(exact,'_admit'),(exact,'_integer_frame'),
            (exact,'_referenced_support_evidence'),(exact,'_public_support_direction'),
            (closed,'classify_closed_solids'),(closed,'_bvh'),(closed,'_closed_validate_embedded'),
            (closed,'_closed_candidate_trees'),(closed,'_closed_cone_metadata'))
        holder,diagnostics,result,error = {},{},None,None
        with ExitStack() as stack:
            for module,function in functions:
                original = getattr(module,function)
                key = module.__name__.split('.')[-1]+'.'+function
                counts[key] = 0
                def counted(*args,_key=key,_original=original,**kwargs):
                    counts[_key] += 1
                    return _original(*args,**kwargs)
                stack.enter_context(patch.object(module,function,counted))
            started = time.perf_counter_ns()
            deadline = started+30_000_000_000
            def checkpoint(stage):
                if time.perf_counter_ns()>=deadline:
                    raise TimeoutError('original_30s_pair_deadline')
            try:
                result = exact.measure_spatial_relation(left,right,checkpoint,diagnostics=diagnostics,
                    retain_exact_rank=True,prepared_holder=holder)
            except BaseException as exception:
                error = {'type':type(exception).__name__,'message':str(exception),'traceback':traceback.format_exc()}
            elapsed = time.perf_counter_ns()-started
        row = {'case':name,'result':result,'diagnostics':diagnostics,'actual_function_calls':counts,
            'holder_keys':sorted(holder),'error':error,'elapsed_ns':elapsed,
            'scope':'instrumented attribution only; never used for primary performance thresholds'}
        rows.append(row)
        save(output/(name+'.json'),row)
    unchanged = all((engine/name).read_bytes()==raw for name,raw in blobs.items())
    save(output/'RESULTS.json',{'cases':rows,'actual_calls':len(rows),'fixed_expected_calls':6,'retries':0,
        'source_sha256':args.source_sha256,'source_files_unchanged':unchanged,
        'Blender_sessions':0,'real_product_processes':0,'model_consumers':0,'performance_samples':0})
    return 0 if unchanged and len(rows)==6 and not any(row['error'] for row in rows) else 1


if __name__=='__main__':
    raise SystemExit(main())
