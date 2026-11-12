"""The frozen five paired cold calls; run only after root candidate-freeze GO."""

import argparse
import ast
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
import traceback
import types


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
QUAL = ROOT/'verification/spatial_task_qualification_001'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')


def source(root,expected):
    tree = ast.parse((root/'human_eye_plugin/runtime_identity.py').read_bytes())
    constants = {node.targets[0].id:ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
        and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('_ROOT_MODULES','BASE_VERSION','IMPLEMENTATION_REVISION')}
    names = set(constants['_ROOT_MODULES']) | {p.relative_to(root).as_posix() for package in
        ('human_eye_plugin','human_eye_module1_operators') for p in (root/package).glob('*.py')}
    blobs = {name:(root/name).read_bytes() for name in sorted(names)}
    manifest = [{'path':name,'sha256':sha(raw)} for name,raw in blobs.items()]
    canonical = sha(json.dumps({'base_version':constants['BASE_VERSION'],'implementation_revision':constants['IMPLEMENTATION_REVISION'],
        'files':manifest},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
    assert len(blobs)==137 and canonical==expected
    return blobs,manifest


def load_kernel(role,root,blobs):
    package = types.ModuleType('_m3_'+role+'_kernel')
    package.__path__ = []
    sys.modules[package.__name__] = package
    for name in ('surface_proximity','surface_geometry'):
        module = types.ModuleType(package.__name__+'.'+name)
        module.__package__ = package.__name__
        module.__file__ = str(root/'human_eye_plugin'/(name+'.py'))
        sys.modules[module.__name__] = module
        setattr(package,name,module)
        exec(compile(blobs['human_eye_plugin/'+name+'.py'],module.__file__,'exec',dont_inherit=True),module.__dict__)
    return package.surface_proximity,package.surface_geometry


class ReferenceDeadline(RuntimeError):
    pass


@contextmanager
def work_spy(exact,closed):
    phase = {'name':'closed'}
    counts = {'closed':{},'surface':{}}
    originals = []
    for module,name in ((exact,'_admit'),(exact,'_integer_frame'),(exact,'_intersection'),
        (exact,'_point_faces'),(exact,'_point_edges'),(exact,'_edge_edges'),(closed,'_bvh')):
        original = getattr(module,name)
        label = module.__name__.split('.')[-1]+'.'+name
        def counted(*args,_original=original,_label=label,**kwargs):
            bucket = counts[phase['name']]
            bucket[_label] = bucket.get(_label,0)+1
            return _original(*args,**kwargs)
        originals.append((module,name,original))
        setattr(module,name,counted)
    try:
        yield phase,counts
    finally:
        for module,name,original in originals:
            setattr(module,name,original)


def mesh(row):
    return types.SimpleNamespace(vertices=[tuple(point) for point in row['vertices_world']],
        faces=[tuple(face) for face in row['triangles']])


def call(role,modules,left_raw,right_raw):
    exact,closed = modules
    left,right = mesh(left_raw),mesh(right_raw)
    closed_work,surface_work,holder,checkpoints = {},{},{},{}
    row = {'role':role,'closed':None,'surface':None,'exception':None}
    with work_spy(exact,closed) as (phase,calls):
        started = time.perf_counter_ns()
        deadline = started+30_000_000_000
        def checkpoint(stage):
            checkpoints[stage] = checkpoints.get(stage,0)+1
            if time.perf_counter_ns() >= deadline:
                raise ReferenceDeadline('frozen_30s_pair_deadline')
        try:
            before = time.perf_counter_ns()
            row['closed'] = closed.classify_closed_solids(left,right,checkpoint,diagnostics=closed_work,prepared_holder=holder)
            middle = time.perf_counter_ns()
            phase['name'] = 'surface'
            options = {'diagnostics':surface_work,'retain_exact_rank':True,
                '_prepared_pair':holder.get('pair'),'_boundary_contact':holder.get('boundary_contact')}
            if role=='candidate':
                options['_prepared_trees'] = holder.get('trees')
            row['surface'] = exact.measure_surface_proximity(left,right,checkpoint,**options)
            ended = time.perf_counter_ns()
            checkpoint('m3_pair_complete')
            row.update(closed_ns=middle-before,surface_ns=ended-middle)
        except BaseException as exception:
            row['exception'] = {'type':type(exception).__name__,'message':str(exception),'traceback':traceback.format_exc()}
        row.update(complete_ns=time.perf_counter_ns()-started,deadline_ns=deadline,
            closed_work=closed_work,surface_work=surface_work,actual_function_entries=calls,
            checkpoint_counts=checkpoints,holder_has_pair='pair' in holder,holder_has_trees='trees' in holder)
    row['complete_facts'] = bool(row['closed'] and row['closed'].get('measurement_valid')
        and row['surface'] and row['surface'].get('measurement_valid') and row['exception'] is None)
    return row


def verify(row,certifier,left,right,truth):
    value = row['surface']
    surface_valid = bool(value and value.get('measurement_valid'))
    relation_valid = bool(row['closed'] and row['closed'].get('measurement_valid')
        and row['closed'].get('relation')=='separated')
    proof = None
    surface_passed = False
    if surface_valid and value.get('witness_status')=='measured':
        proof = certifier.certify_pair(value['point_a_world'],value['point_b_world'],value['distance_m'],left,right,
            position_tolerance_m=1e-9,distance_tolerance_m=1e-6)
        surface_passed = proof['passed'] and truth[0]-1e-6<=value['distance_m']<=truth[1]+1e-6
    return {'passed':surface_passed and relation_valid,'surface_passed':surface_passed,'closed_passed':relation_valid,
        'surface_membership':proof,'independent_interval_m':truth,
        'scope':'independent verification after timed window; closed unknown never suppresses the separate surface check'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root',required=True,type=Path)
    parser.add_argument('--candidate-source-sha256',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    output = HERE/args.output
    assert output.resolve().parent==HERE.resolve()
    output.mkdir(exist_ok=False)
    frozen = json.loads((HERE/'FROZEN.json').read_bytes())
    designed = json.loads((HERE/'DESIGNED_CASES.json').read_bytes())
    assert sha((HERE/'DESIGNED_CASES.json').read_bytes())==frozen['designed_cases_sha256']
    for relative,expected in designed['source_files'].items():
        assert sha((ROOT/relative).read_bytes())==expected
    roots = {'reference':HERE/'baseline/product','candidate':args.candidate_root.resolve()}
    data,manifests,modules = {},{},{}
    for role,root in roots.items():
        expected = frozen['source_sha256'] if role=='reference' else args.candidate_source_sha256
        data[role],manifests[role] = source(root,expected)
        modules[role] = load_kernel(role,root,data[role])
    reference_exact,reference_closed = modules['reference']
    for qualified,change in frozen['reference']['overrides'].items():
        name,key = qualified.split('.')
        module = reference_exact if name=='surface_proximity' else reference_closed
        assert getattr(module,key)==change['from']
        setattr(module,key,change['to'])
    witness_source = HERE/'witness_oracle.py'
    spec = importlib.util.spec_from_file_location('_m3_independent_witness_oracle',witness_source)
    oracle = importlib.util.module_from_spec(spec)
    exec(compile(witness_source.read_bytes(),str(witness_source),'exec',dont_inherit=True),oracle.__dict__)
    snapshot = json.loads((ROOT/designed['g508']['snapshot']).read_bytes())
    objects = {row['name']:row for row in snapshot['objects']}
    certificate = json.loads((ROOT/designed['g508']['truth']).read_bytes())
    truths = {row['candidate_name']:[row['distance_lower_m'],row['distance_upper_m']] for row in certificate['pairs']}
    cases = [(name,objects['Target'],objects[name],truths[name]) for name in designed['g508']['candidates']]
    cases.append(('cube12/control',objects['Control_A'],objects['Control_B'],[1.,1.]))
    save(output/'INPUT_BINDINGS.json',{'frozen':frozen,'manifests':manifests,
        'runner_sha256':sha(Path(__file__).read_bytes()),'candidate_source_sha256':args.candidate_source_sha256,
        'witness_oracle_sha256':sha(witness_source.read_bytes()),
        'scope':'isolated manifest-bound kernel modules, diagnostic reference quantity overrides only; no installed service'})
    samples = []
    for name,left,right,truth in cases:
        for repetition in frozen['timing']['fixed_order']:
            for role in repetition['order']:
                row = call(role,modules[role],left,right)
                row.update(case=name,iteration=repetition['iteration'])
                row['independent_verification'] = verify(row,oracle,left,right,truth)
                row['peer_denominator_matches'] = (row['surface_work'].get('intersection_tests')==18791
                    if role=='reference' and name=='Peer_000' and row['surface'] and row['surface'].get('measurement_valid') else None)
                samples.append(row)
                filename = name.replace('/','_')+'_'+str(repetition['iteration'])+'_'+role+'.json'
                save(output/filename,row)
    unchanged = all((roots[role]/name).read_bytes()==raw for role,blobs in data.items() for name,raw in blobs.items())
    summaries = []
    for name,left,right,truth in cases:
        lanes = {}
        for role in roots:
            rows = [row for row in samples if row['case']==name and row['role']==role]
            values = [row['complete_ns'] for row in rows]
            lanes[role] = {'values_ns':values,'median_ns':statistics.median(values),'range_ns':[min(values),max(values)],
                'complete_facts':sum(row['complete_facts'] for row in rows),'independent_verified':sum(row['independent_verification']['passed'] for row in rows),
                'surface_verified':sum(row['independent_verification']['surface_passed'] for row in rows)}
        summaries.append({'case':name,'lanes':lanes})
    save(output/'RESULTS.json',{'samples':samples,'summaries':summaries,'source_files_unchanged':unchanged,
        'planned_samples':40,'actual_samples':len(samples),'retries':0,'models':0,'Blender_sessions':0,
        'scope':'finite paired cold kernel timing; admission decided separately by root, incomplete reference never supplies a speed ratio'})
    return 0 if unchanged and len(samples)==40 else 1


if __name__=='__main__':
    raise SystemExit(main())
