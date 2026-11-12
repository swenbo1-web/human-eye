"""Independent standard-library audit of OPT1 source, all rows and surface facts."""
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INITIAL = ROOT/'verification/m4_surface_scan_001'
QUAL = INITIAL/'qualification'
RUN = HERE/'engineering/run_01'
SOURCES = {'A':'b3654f6f943c3fb6feff0011397c0a8c20872e41f35973e6baf53e3a5e277314',
           'B':'c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943'}
COMMITS = {'A':'c6355a01a4c6ee204a0d676cd9309f02428fe3ba',
           'B':'c1cb2da32034e056a270384e691a2cde8dddbc0d'}
TOL = F(1,10**10)


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()


def difference(a,b):
    return tuple(x-y for x,y in zip(a,b))


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def on_surface(point, mesh):
    point = tuple(map(F,point))
    vertices = [tuple(map(F,p)) for p in mesh['vertices_world']]
    for indices in mesh['triangles']:
        a,b,c = (vertices[index] for index in indices)
        u,v,w = difference(b,a),difference(c,a),difference(point,a)
        uu,uv,vv,wu,wv = dot(u,u),dot(u,v),dot(v,v),dot(w,u),dot(w,v)
        denominator = uu*vv-uv*uv
        assert denominator > 0
        second,third = (wu*vv-wv*uv)/denominator,(wv*uu-wu*uv)/denominator
        bary = (1-second-third,second,third)
        clipped = tuple(max(F(0),value) for value in bary)
        total = sum(clipped)
        candidate = tuple(sum(weight*p[k] for weight,p in zip(clipped,(a,b,c)))/total for k in range(3))
        offset = difference(point,candidate)
        if dot(offset,offset) <= TOL*TOL:
            return True
    return False


def main():
    binding = read(RUN/'INPUT_BINDINGS.json')
    assert binding['pair_orders'] == ['AB','BA','AB','BA','AB']
    assert binding['evaluation_consumers'] == binding['images'] == binding['automatic_retries'] == 0
    for name, expected in binding['files'].items():
        assert sha(Path(name)) == expected, name
    qualified = subprocess.check_output(['git','show',
        '96fce78b98cb749885792112e039a406744d282b:verification/m4_surface_scan_001/qualification/QUALIFICATION_READY.json'],cwd=ROOT)
    assert (QUAL/'QUALIFICATION_READY.json').read_bytes() == qualified
    promises = json.loads(qualified)
    for field,name in [('asset','assembly.blend'),('base_snapshot','BASE_SNAPSHOT.json'),
        ('edit_snapshot','EDIT_SNAPSHOT.json'),('base_truth','BASE_TRUTH.json'),
        ('edit_truth','EDIT_TRUTH.json'),('geometry_freeze','GEOMETRY_FREEZE.json'),
        ('control_certificates','CONTROL_CERTIFICATES.json')]:
        assert sha(QUAL/name) == promises[field+'_sha256']
    for version,ready in binding['readies'].items():
        assert ready['commit'] == COMMITS[version] and ready['source_sha256'] == SOURCES[version]
        manifest = read(Path(ready['fixed_inputs']))['manifest']
        assert len(manifest) == 138
        for item in manifest:
            assert sha(Path(ready['install_root'])/item['path']) == item['sha256']
        assert read(Path(ready['receipt']))['source_sha256'] == SOURCES[version]
    protected = read(HERE/'WORK_ORDER.json')['protected_before']
    assert all(sha(Path(name)) == expected for name,expected in protected.items())
    snapshots = {state:read(QUAL/(state.upper()+'_SNAPSHOT.json')) for state in ('base','edit')}
    meshes = {state:{obj['name']:obj for obj in snap['objects']} for state,snap in snapshots.items()}
    names = {'blender:'+hashlib.sha256(canonical(['',name])).hexdigest():name for name in meshes['base']}
    truth = {state:{tuple(sorted((row['object_a'],row['object_b']))):row
                    for row in read(QUAL/(state.upper()+'_TRUTH.json'))['pairs']} for state in snapshots}
    point_proofs = {}
    counts = Counter()
    inputs = {}

    def verify(row,version):
        state = 'edit' if row['state'] == 'edit' else 'base'
        body,work = row['body'],row['diagnostics']
        assert not row['errors'] and body['status'] == 'complete'
        assert body['result_kind'] == 'surface_scan' and body['threshold_m'] == .002
        assert body['binding']['runtime_source_sha256'] == SOURCES[version]
        assert body['coverage']['catalog_scope_confirmed'] and not body['scope_issues']
        assert not body['unsupported_objects'] and not body['unresolved']
        seen = set()
        partition = Counter()
        for part in work['dispositions']:
            pair = tuple(sorted(names[oid] for oid in part['object_ids']))
            assert pair not in seen and pair in truth[state]
            seen.add(pair)
            expected = truth[state][pair]
            status = part['status']
            assert status in ('bound_excluded','measured_match','measured_nonmatch')
            value = expected['exact_squared_distance_m2']
            exact = F(int(value['numerator']),int(value['denominator']))
            match = exact <= F(.002)**2
            assert expected['matches_threshold'] == match
            assert (status == 'measured_match') == match
            if status == 'bound_excluded':
                assert part['lower_bound_m'] > .002 and F(part['lower_bound_m'])**2 <= exact
            else:
                assert abs(part['distance_m']-math.sqrt(float(exact))) <= float(TOL)
            partition[status] += 1
        assert seen == set(truth[state]) and len(seen) == 276
        public = set()
        for match in body['matches']:
            pair = tuple(sorted(obj['name'] for obj in match['objects']))
            assert pair not in public and truth[state][pair]['matches_threshold']
            public.add(pair)
            value = truth[state][pair]['exact_squared_distance_m2']
            distance = math.sqrt(float(F(int(value['numerator']),int(value['denominator']))))
            assert abs(match['distance_m']-distance) <= float(TOL)
            assert match['witness_status'] == 'measured'
            assert abs(math.dist(match['point_a_world'],match['point_b_world'])-distance) <= float(TOL)
            for obj,point in zip(match['objects'],(match['point_a_world'],match['point_b_world'])):
                assert names[obj['id']] == obj['name']
                key = state,obj['name'],tuple(point)
                if key not in point_proofs:
                    point_proofs[key] = on_surface(point,meshes[state][obj['name']])
                assert point_proofs[key]
                counts['witness_occurrences'] += 1
            counts['public_distances'] += 1
        assert public == {pair for pair,value in truth[state].items() if value['matches_threshold']}
        coverage = body['coverage']
        assert coverage['objects'] == 24 and coverage['total_pairs'] == 276
        for label in ('bound_excluded','measured_match','measured_nonmatch','unknown','deferred'):
            assert coverage[label] == partition[label]
        assert body['delivery']['complete'] and body['delivery']['matches_total'] == len(public)
        assert body['execution_authority'] is False
        assert row['actual_host_RPC'] == 1
        counts['pair_dispositions'] += 276
        counts['observations'] += 1

    sequences = {}
    for index in range(1,6):
        for version in ('A','B'):
            folder = RUN/('pair_'+str(index).zfill(2))/version
            path = folder/'RESULTS.json'
            sequence = sequences[index,version] = read(path)
            inputs[str(path.relative_to(ROOT))] = sha(path)
            assert sequence['passed'] and not sequence['errors'] and sequence['source_files_unchanged']
            assert sequence['automatic_retries'] == 0 and sequence['metadata_zero_host_RPC']
            assert sequence['native_close']['process_reaped'] and sequence['native_close']['exit_code'] == 0
            assert sequence['runtime_exit']['confirmed'] and sequence['runtime_exit']['exit_code'] == 0
            assert [row['state'] for row in sequence['business']] == ['cold','repeat','edit']
            for state in ('base','edit'):
                actual = read(folder/(state+'_ACTUAL_SNAPSHOT.json'))
                strip = lambda value:{k:v for k,v in value.items() if k not in ('pid','blend_filepath')}
                assert strip(actual) == strip(snapshots[state])
            for row in sequence['business']:
                verify(row,version)
                assert {'mcp.wire_encode','mcp.stdio_write'} <= {span['name'] for span in row['span_timings_ns']}
                assert row['trace']['annotations']['mcp_native_image_block_count'] == 0
                if version == 'B':
                    work = row['diagnostics']
                    assert work['measurement_cache_max_measurements'] == 256
                    for label in ('measurement_cache_before','measurement_cache_after'):
                        assert work[label]['max_bytes'] == 2097152
                        assert work[label]['accounted_bytes'] <= 2097152
                        assert work[label]['measurement_entries'] <= 256
    for index,order in enumerate(binding['pair_orders'],1):
        first,last = (sequences[index,v] for v in order)
        assert first['ended_ns'] <= last['started_ns']
    process_path = HERE/'engineering/process_01/RESULTS.json'
    process = read(process_path)
    assert process['passed'] and not process['errors']
    assert [row['state'] for row in process['business']] == ['cold','repeat','edit']
    for row in process['business']:
        verify(row,'B')
    inputs[str(process_path.relative_to(ROOT))] = sha(process_path)
    result = dict(passed=True,source_sha256=SOURCES,candidate_commit=COMMITS['B'],
        planned_main_rows=30,actual_main_rows=30,process_rows=3,counts=dict(counts),
        unique_surface_point_proofs=len(point_proofs),input_results=inputs,
        paired_order_verified=True,qualification_old_promises_verified=True,
        same_full_geometry_states_verified=20,cache_capacity_preserved=True,
        images=0,evaluation_consumers=0,protected_files_unchanged=True)
    with (HERE/'ROOT_RESULTS_AUDIT.json').open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
