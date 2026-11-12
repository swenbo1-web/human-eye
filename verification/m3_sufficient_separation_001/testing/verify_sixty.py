"""Saved-only independent source, support, witness and frozen-cost validation."""

from fractions import Fraction as F
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    output = HERE/'saved_verification_01'
    output.mkdir(exist_ok=False)
    run = HERE/'sixty_01'
    actual = read(run/'RESULTS.json')
    bindings = read(run/'INPUT_BINDINGS.json')
    designed = read(HERE/'DESIGNED_CASES.json')
    sequence = read(HERE/'TIMING_SEQUENCE.json')['calls']
    checks = []

    def check(name,condition,detail=None):
        checks.append({'name':name,'passed':bool(condition),'detail':detail})

    source = ROOT/designed['g508']['snapshot']
    check('frozen_actual_source_sha',sha(source)==designed['g508']['snapshot_sha256'])
    objects = {row['name']:row for row in read(source)['objects']}
    truth_pairs = {row['candidate_name']:row for row in designed['g508']['truth_intervals']}
    cases = {'G508/'+name:(objects['Target'],objects[name],'separated',
        (truth_pairs[name]['distance_lower_m'],truth_pairs[name]['distance_upper_m'])) for name in designed['g508']['candidates']}
    cases['simple_control'] = (designed['simple_control']['left'],designed['simple_control']['right'],'separated',(1.,1.))
    for name in ('fallback_intersecting_bars','fallback_full_containment'):
        row = next(row for row in designed['analytic_pairs'] if row['id']==name)
        truth = row['independent_truth']
        cases[name] = row['left'],row['right'],truth['relation'],(truth['distance_m'],truth['distance_m'])
    witness_path = ROOT/'verification/m3_pair_scalability_001/testing/witness_oracle.py'
    check('independent_witness_source',sha(witness_path)=='5302157b0c1196d1be8a800253b54820b6da99901d321f7eb6986489d79ccbce')
    spec = importlib.util.spec_from_file_location('_saved_sixty_fraction_witness',witness_path)
    witness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(witness)
    check('sixty_exact_count',len(actual['samples'])==len(sequence)==60)
    check('no_retries',actual['retries']==0)
    check('source_unchanged_record',actual['source_files_unchanged'])
    check('preparation_unchanged_record',actual['preparation_files_unchanged'])
    for path,expected in bindings['source_files'].items():
        check('preparation_byte_pin:'+path,sha(Path(path))==expected)
    roots = {'reference':ROOT/'verification/m3_pair_scalability_001/testing/baseline/product',
        'candidate':HERE/'initial_candidate_01/product'}
    for arm,manifest in bindings['source_manifests'].items():
        check('manifest_count_'+arm,len(manifest)==137)
        for row in manifest:
            check('source_byte:'+arm+':'+row['path'],sha(roots[arm]/row['path'])==row['sha256'])
    sample_proofs = []
    all_correct = True
    for index,row in enumerate(actual['samples']):
        label = str(row['sequence']).zfill(2)+'_'+row['arm']
        check(label+':frozen_order',{key:row[key] for key in sequence[index]}==sequence[index])
        check(label+':raw_row_equal',read(run/(label+'.json'))==row)
        raw_payload = (run/(label+'.PAYLOAD.bin')).read_bytes()
        payload = json.loads(raw_payload)
        check(label+':payload_bytes',len(raw_payload)==row['payload_UTF8_bytes'] and sha(run/(label+'.PAYLOAD.bin'))==row['payload_sha256'])
        check(label+':payload_semantics',payload['result']==row['result'] and payload['diagnostics']==row['diagnostics'])
        expected_facts = ['closed_solid_relation','surface_proximity'] if row['arm']=='reference' else ['spatial_relation','surface_proximity']
        check(label+':explicit_demand',payload['requested_facts']==expected_facts)
        check(label+':no_error',row['error'] is None)
        check(label+':same_30s',row['original_deadline_ns']==row['started_ns']+30_000_000_000)
        check(label+':deadline',row['within_original_30s'] and row['ended_ns']<row['original_deadline_ns'])
        check(label+':full_time',row['complete_business_ns']==row['ended_ns']-row['started_ns'])
        check(label+':phase_partition',sum(row['timing_stages_ns'].values())+row['timing_residual_ns']==row['complete_business_ns']
            and row['timing_residual_ns']>=0 and all(value>=0 for value in row['timing_stages_ns'].values()))
        left,right,expected_relation,interval = cases[row['case']]
        surface = row['result']['surface']
        relation = row['result']['closed'] if row['arm']=='reference' else row['result']['spatial']
        valid = surface.get('measurement_valid') is True and relation.get('measurement_valid') is True and relation.get('relation')==expected_relation
        check(label+':common_facts',valid)
        all_correct = all_correct and valid
        distance = F(surface['distance_m'])
        check(label+':independent_distance',F(interval[0])-F(1e-6)<=distance<=F(interval[1])+F(1e-6))
        if interval[0]==interval[1]:
            check(label+':exact_analytic_distance',surface['distance_m']==interval[0])
        certificate = witness.certify_pair(surface['point_a_world'],surface['point_b_world'],surface['distance_m'],left,right,
            position_tolerance_m=1e-9,distance_tolerance_m=1e-6)
        check(label+':actual_triangle_witness',certificate['passed'])
        all_correct = all_correct and certificate['passed']
        if row['arm']=='candidate':
            diagnostics = row['diagnostics']
            check(label+':whole_bundle',row['result']['measurement_valid'] is True and row['result']['budget_stopped'] is False)
            if expected_relation=='separated':
                proof = relation['support_evidence']
                delta = [F(float(b))-F(float(a)) for a,b in zip(surface['point_a_world'],surface['point_b_world'])]
                denominator = max(value.denominator for value in delta)
                normal = [value.numerator*(denominator//value.denominator) for value in delta]
                divisor = math.gcd(*normal)
                normal = [value//divisor for value in normal]
                check(label+':unique_public_proposal',proof['primitive_direction']==normal and proof['proposal']=='first_public_nearest_points_difference')
                origin = [F(*value) for value in proof['origin']]
                factor = proof['factor']
                projections = []
                for raw in (left,right):
                    indices = sorted({i for tri in raw['triangles'] for i in tri})
                    projections.append({i:sum(n*(F(float(p))-o)*factor for n,p,o in zip(normal,raw['vertices_world'][i],origin)) for i in indices})
                maximum,minimum = max(projections[0].values()),min(projections[1].values())
                check(label+':all_referenced_support',minimum>maximum and proof['left_max']==maximum and proof['right_min']==minimum)
                check(label+':extremum_indices',projections[0][proof['left_vertex_index']]==maximum and projections[1][proof['right_vertex_index']]==minimum)
                counts = [len(values) for values in projections]
                check(label+':referenced_counts',proof['referenced_counts']==counts)
                support = diagnostics['support_work']
                check(label+':charged_2V3',support['support_source_vertices']==support['support_vertex_dots']==sum(counts)
                    and support['support_direction_components']==3 and support['work_units_after']-support['work_units_before']==2*sum(counts)+3)
                check(label+':closed_unexecuted',diagnostics['closed_solid_pair_count']==0 and diagnostics['closed_solid_work']=={} and row['result']['closed'] is None)
                check(label+':honest_scope',relation['geometry_scope']=='referenced_triangle_unions_and_their_vertex_convex_hulls')
            else:
                check(label+':one_closed_fallback',diagnostics['closed_solid_pair_count']==1 and row['result']['closed'] is not None)
                check(label+':prepared_reused',diagnostics['closed_solid_work']['prepared_pair_reused'])
        sample_proofs.append({'sequence':row['sequence'],'case':row['case'],'arm':row['arm'],'witness_certificate':certificate})
    medians = {case:{arm:statistics.median(row['complete_business_ns'] for row in actual['samples'] if row['case']==case and row['arm']==arm)
        for arm in ('reference','candidate')} for case in cases}
    old_sum = sum(medians['G508/'+name]['reference'] for name in designed['g508']['candidates'])
    new_sum = sum(medians['G508/'+name]['candidate'] for name in designed['g508']['candidates'])
    gates = {'common_business_facts':all_correct,
        'g508_sum_improvement_at_least_20_percent':new_sum*5<=old_sum*4,
        'g508_each_pair_no_regression':all(medians['G508/'+name]['candidate']<=medians['G508/'+name]['reference'] for name in designed['g508']['candidates'])}
    allowances = {}
    for case in ('simple_control','fallback_intersecting_bars','fallback_full_containment'):
        numerator,divisor = (1_000_000,20) if case=='simple_control' else (2_000_000,10)
        allowance = max(F(numerator),F(medians[case]['reference'],divisor))
        delta = medians[case]['candidate']-medians[case]['reference']
        gates[case+'_cost'] = delta<=allowance
        allowances[case] = {'delta_ns':delta,'maximum_delta_ns':float(allowance)}
    output_data = {'passed':all(row['passed'] for row in checks) and all(gates.values()),'checks':len(checks),
        'failed_checks':[row for row in checks if not row['passed']],'check_records':checks,'frozen_gates':gates,
        'complete_business_medians_ns':medians,'g508_sum_reference_ns':old_sum,'g508_sum_candidate_ns':new_sum,
        'g508_sum_reduction_fraction':{'numerator':old_sum-new_sum,'denominator':old_sum},
        'simple_and_fallback_allowances':allowances,'sample_proofs':sample_proofs,
        'input_results_sha256':sha(run/'RESULTS.json'),'analysis_source_sha256':sha(Path(__file__)),
        'candidate_commit':actual['candidate_commit'],'candidate_source_sha256':actual['candidate_source_sha256'],
        'scope':'saved-only independent Fraction facts and all frozen finite engineering gates; reference adds embedded-shell guarantee',
        'product_calls':0,'performance_calls':0,'Blender_sessions':0,'model_consumers':0}
    with (output/'RESULTS.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(output_data,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed':output_data['passed'],'checks':len(checks),'failed':len(output_data['failed_checks']),'gates':gates}))
    return 0 if output_data['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
