"""Frozen-weight acceptance only: tests, fresh lazy load, and saved holdout."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import statistics
import sys
import time
import types
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent)]
package=types.ModuleType('human_eye_plugin');package.__path__=[str(ROOT/'human_eye_plugin')]
sys.modules['human_eye_plugin']=package
import numpy as np
from human_eye_plugin import arm_twist_expert as expert


def main():
    source_paths=[ROOT/'human_eye_plugin'/name for name in ('arm_twist_expert.py','arm_twist_weights.py')]
    sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    output=Path(sys.argv[1]).resolve();output.mkdir(parents=True,exist_ok=True)
    raw=gzip.decompress((Path(__file__).parent/'run_01/dataset.json.gz').read_bytes())
    cases=json.loads(raw)
    expert.get_default_expert.cache_clear()
    before='human_eye_plugin.arm_twist_weights' in sys.modules
    t0=time.perf_counter_ns();model=expert.get_default_expert();cold_load_ns=time.perf_counter_ns()-t0
    assert not before
    assert expert.get_default_expert() is model
    from human_eye_plugin.arm_twist_weights import PARAMETERS
    assert hashlib.sha256(raw).hexdigest()==PARAMETERS['training']['dataset_sha256']
    heldout=[case for case in cases if case['metadata']['split']=='test']
    fit=json.loads((Path(__file__).parent/'run_01/result.json').read_bytes())
    expected={row['case_id']:row for row in fit['per_case']}
    durations=[]
    for case in heldout:
        t0=time.perf_counter_ns();report=expert.analyze(case['packet']);durations.append(time.perf_counter_ns()-t0)
        assert report['status']=='estimated'
        observed=[region['predicted_severity'] for region in report['regions']]
        assert np.allclose(observed,expected[case['metadata']['case_id']]['model'],rtol=0,atol=1e-14)
        for section,region in zip(case['packet']['sections'],report['regions']):
            assert region['vertex_ids']==[case['packet']['vertex_ids'][i] for i in section]
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='*test*.py')
    for pattern in ('test_rig_pose.py','test_surface_deformation.py'):
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'verification'),pattern=pattern))
    log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    unchanged=sources=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    from human_eye_plugin.runtime_identity import runtime_identity
    identity=runtime_identity()
    record={'passed':result.wasSuccessful() and unchanged,'tests':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'weights_initially_unloaded':not before,
        'model_object_reused':True,'weights_cold_load_ms':cold_load_ns/1e6,
        'saved_holdout_fresh_public_analyze_cases':len(heldout),
        'public_analyze_median_ms':statistics.median(durations)/1e6,'public_analyze_max_ms':max(durations)/1e6,
        'product_sources_unchanged':unchanged,'product_sources':sources,
        'source_sha256':identity['source_sha256'],'source_count':len(identity['source_files']),
        'dataset_sha256':hashlib.sha256(raw).hexdigest(),'training_performed_by_verifier':False,
        'blender_processes':0,'external_api_calls':0}
    (output/'unit.log').write_text(log.getvalue(),encoding='utf8',newline='\n')
    (output/'result.json').write_text(json.dumps(record,indent=2),encoding='utf8',newline='\n')
    print(json.dumps(record))
    if not record['passed']:raise SystemExit(1)


if __name__=='__main__':main()
