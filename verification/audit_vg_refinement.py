import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verification.vg_acceptance import read_images, verify_public_pixels

run = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / 'artifacts/vg_refinement/formal_002'
manifest = json.loads((run / 'run.json').read_text())
original = json.loads((ROOT / 'artifacts/vg/author_002/process_00/raw.json').read_text())
records = [json.loads((run / f'process_{p:02d}/raw.json').read_text()) for p in range(3)]
assert len({r['pid'] for r in records}) == 3
for path, digest in manifest['source_sha256'].items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path

results = []
all_pairs = []
sizes = []
for worker, raw in enumerate(records):
    assert raw['source_sha256_before'] == raw['source_sha256_after'] == manifest['source_sha256']
    assert len(raw['cases']) == 24 and len(raw['warmups']) == 5 and len(raw['hot_pairs']) == 31
    all_pairs.extend(raw['hot_pairs'])
    for index, pair in enumerate(raw['hot_pairs']):
        assert pair['scene_id'] == (index + 8 * worker) % 24
        expected_orders = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
        names = ('A_fixed', 'A_active', 'R_fixed', 'R_active')
        assert pair['order'] == [names[i] for i in expected_orders[(index+worker+index//24)%4]]
        for method in ('fixed','active'):
            eq = pair['equivalence'][method]
            assert all(eq[k] for k in ('rgba_equal','metadata_equal_except_camera_name','ancillary_chunks_equal','png_size_limit_passed'))
    cases = []
    for scene_id, item in enumerate(raw['cases']):
        assert item['scene_id'] == scene_id
        assert item['witness'] == original['cases'][scene_id]['witness']
        route_results, decoded = {}, {}
        for route in ('A_fixed','A_active','R_fixed','R_active'):
            method = route.split('_')[1]
            case = {**item, 'meshes': original['cases'][scene_id]['meshes'],
                    'first_observation': {'methods': {method: item['first_observation']['routes'][route]}},
                    'quality': {method: item['quality'][route]}}
            hud, bottom, hashes = read_images(case, method)
            assert hashes
            result = verify_public_pixels(case, method, hud, bottom)
            result['native_checks_passed'] = all(item['quality'][route]['checks'].values())
            result['accepted'] = result['passed'] and result['native_checks_passed']
            route_results[route] = result
            decoded[route] = hud, bottom
        for method in ('fixed','active'):
            assert all(np.array_equal(a,b) for a,b in zip(decoded['A_'+method],decoded['R_'+method]))
            files = [item['first_observation']['routes'][v+'_'+method]['artifacts']['hud'] for v in ('A','R')]
            sizes.append(files[1]['bytes']/files[0]['bytes'])
            assert sizes[-1] <= 1
        cases.append({'scene_id':scene_id,'family':item['family'],'routes':route_results})
    sets = {route:[c['scene_id'] for c in cases if c['routes'][route]['accepted']]
            for route in ('A_fixed','A_active','R_fixed','R_active')}
    assert len(sets['R_active']) == 24 and sets['R_active'] == sets['A_active']
    assert sets['R_fixed'] == sets['A_fixed'] and len(sets['R_fixed']) == 10
    assert all(v['rejected'] for controls in raw['negative_controls'].values() for v in controls.values())
    for control in raw['no_gap'].values():
        assert all(all(v['checks'].values()) for v in control['quality'].values())
        for method in ('fixed','active'):
            pixels = []
            for version in ('A','R'):
                artifact = control['routes'][version+'_'+method]['artifacts']['hud']
                path = Path(artifact['path'])
                assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact['sha256']
                pixels.append(np.asarray(Image.open(path).convert('RGBA')))
            assert np.array_equal(*pixels)
    results.append({'worker':worker,'pid':raw['pid'],'public_and_native_pass_sets':sets,'cases':cases})

def stats(pairs):
    a = [x['routes']['A_active']['elapsed_ns'] for x in pairs]
    r = [x['routes']['R_active']['elapsed_ns'] for x in pairs]
    p95 = lambda v: sorted(v)[math.ceil(.95*len(v))-1]
    diff = np.asarray(r,dtype=np.float64)-a
    rng = np.random.default_rng(721091)
    ci = np.quantile(np.median(diff[rng.integers(0,len(diff),(6000,len(diff)))],axis=1),(.025,.975))
    return {'count':len(a),'A_median_ms':statistics.median(a)/1e6,'R_median_ms':statistics.median(r)/1e6,
            'A_p95_ms':p95(a)/1e6,'R_p95_ms':p95(r)/1e6,'p95_ratio':p95(r)/p95(a),
            'paired_median_ci95_ms':(ci/1e6).tolist()}

result = {'decision':'ROOT_AUDIT_COMPLETE','pids':[r['pid'] for r in records],
          'source_sha256':manifest['source_sha256'], 'public_native_checks':results,
          'timing':{'total':stats(all_pairs),'processes':[stats(r['hot_pairs']) for r in records],
                    'families':{f:stats([p for p in all_pairs if p['family']==f])
                                for f in sorted({p['family'] for p in all_pairs})}},
          'cold_png_ratio_max':max(sizes),'cold_png_ratio_median':statistics.median(sizes),
          'pixel_check_scope':'Pillow cross-decoded 288 positive and 24 zero-distance public PNGs; native original geometry oracle reran in formal benchmark; raw native hits independently checked against public critical pixels here.',
          'source_hashes_match':True,'cold_pixel_equality':True,'hot_equivalence_records_checked':True}
(run/'root_audit.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({'timing':result['timing'],'png_max_ratio':max(sizes),'public_quality':'All processes fixed10/24 active24/24; no pixel or native quality loss'},indent=2))
