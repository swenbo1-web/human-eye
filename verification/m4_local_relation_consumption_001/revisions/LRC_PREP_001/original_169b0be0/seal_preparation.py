"""Seal this finite three-arm preparation; no model, product or Blender launch."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'verification/m4_observation_baseline_001'
CYCLE = 'M4-LOCAL-RELATION-CONSUMPTION-001'
read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    plan, old = read(HERE/'PLAN.json'), read(OLD/'PLAN.json')
    assert plan['cycle_id'] == plan['batch'] == CYCLE
    assert plan['current_preparation_consumer_budget'] == 0
    assert not any((HERE/name).exists() for name in ('GO.json', 'STARTED.json', 'RUN_RESULT.json', 'cells'))
    assert plan['logical_denominator'] == 9 and plan['per_arm'] == 3
    sequence, mapping = plan['sequence'], read(HERE/'private/ANON_MAP.json')['rows']
    assert sequence == read(HERE/'SEQUENCE.json')['sequence']
    assert [row['group'] for row in sequence] == ['N','P0','P1','P0','P1','N','P1','N','P0']
    assert [row['cell'] for row in sequence] == ['lrc'+str(i).zfill(2) for i in range(1,10)]
    assert len(mapping) == len({row['anonymous_id'] for row in mapping}) == 9
    assert all(re.fullmatch(r'answer_[0-9a-f]{16}', row['anonymous_id']) for row in mapping)
    assert all(all(row[k] == slot[k] for k in ('cell','task','round','group'))
               for row, slot in zip(mapping, sequence, strict=True))
    assert not {r['anonymous_id'] for r in mapping} & {r['anonymous_id'] for r in read(OLD/'private/ANON_MAP.json')['rows']}
    for key in ('model','requested_effort','max_session_seconds','total_cell_seconds','actor_startup_seconds',
                'tool_attempts','physical_RPC_limit','tool_response_bytes','tool_timeout_s','code_bytes',
                'image_count','new_images','tool_images','model_retries','inputs','tasks','CLI_sha256'):
        assert plan[key] == old[key], key
    for row in read(HERE/'INPUT_REUSE.json')['reused']:
        assert sha(ROOT/row['original']) == sha(ROOT/row['new']) == row['sha256']
    for name in ('actor.py','consumer_transport.py'):
        assert (HERE/'runtime'/name).read_bytes() == (OLD/'runtime'/name).read_bytes(), name
    assert read(HERE/'runtime/GROUP_TEST_RESULT_01.json')['exit_code'] == 0
    assert read(HERE/'runtime/PREPARED_INPUT.json')['model_consumers'] == 0
    identities = read(HERE/'installations/IDENTITIES.json')
    assert identities['status'] == 'PASS' and not identities['issues']
    for profile, expected in (('P0', plan['baseline_source_sha256']), ('P1', plan['candidate_source_sha256'])):
        ready = read(HERE/'installations'/(profile+'_READY.json'))
        assert ready == plan['installations'][profile]
        assert ready['source_count'] == 137 and ready['source_sha256'] == expected
        assert ready['installed_identity_passed'] and ready['no_default_activation']
        assert sha(ready['entry']) == ready['launcher_sha256']
        for row in identities['profiles'][profile]['source_manifest']:
            assert sha(Path(ready['install_root'])/row['path']) == row['sha256']
        tools = read(HERE/'schemas'/(profile+'_PUBLIC_TOOLS.json'))
        assert len(tools) == 2 and {r['name'] for r in tools} == {'human_eye_spatial_relations','human_eye_surface_nearest'}
    cli = read(OLD/'runtime/CLI_IMAGE_CAPABILITY.json')
    assert sha(cli['cli_path']) == cli['cli_sha256'] == plan['CLI_sha256']
    scoring, previous = read(HERE/'scoring/SCORING_CONTRACT.json'), read(OLD/'scoring/SCORING_CONTRACT.json')
    allowed = {'cycle_id','scope','fixed_sample_policy'}
    assert set(scoring) == set(previous) | {'sample_metadata'}
    assert all(scoring[key] == previous[key] for key in previous if key not in allowed)
    assert scoring['sample_metadata']['logical_denominator'] == 9
    assert scoring['sample_metadata']['anonymous_mapping_sha256'] == sha(HERE/'private/ANON_MAP.json')
    assert sha(HERE/'scoring/TRUTH.json') == old['independent_truth_sha256']
    for name in ('INPUT_BINDING.json','SOURCE_BINDING.json','REFERENCE_REPLAY.json'):
        assert (HERE/'scoring'/name).read_bytes() == (OLD/'scoring'/name).read_bytes()
    synthetic = read(HERE/plan['synthetic_validation_result'])
    assert synthetic['passed'] is True and synthetic['model_consumers'] == 0
    assert synthetic['product_calls'] == synthetic['Blender_sessions'] == 0
    assert not any(synthetic['external_attempts'].values())
    for name, digest in plan['dispatch_input_sha256'].items():
        assert sha(HERE/name) == digest, name
    assert sha(HERE/'runtime/driver.py') == plan['preflight_driver_sha256']
    assert sha(HERE/'runtime/consumer_transport.py') == plan['consumer_transport_sha256']
    assert sha(HERE/'runtime/actor.py') == plan['actor_sha256']
    assert sha(HERE/'quality_handoff/pack_quality.py') == plan['quality_handoff_script_sha256']
    assert sha(HERE/'scoring/SCORING_CONTRACT.json') == plan['scoring_contract_sha256']
    assert sha(HERE/'BENEFIT_CONTRACT.json') == plan['benefit_contract_sha256']
    paths = sorted(p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                   and p.name not in ('ARTIFACT_INDEX.json','FREEZE.json','PREP_READY.json'))
    for path in paths:
        assert not path.is_symlink()
        if path.suffix == '.py': compile(path.read_bytes(), str(path), 'exec', dont_inherit=True)
    rows = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p)) for p in paths]
    save(HERE/'ARTIFACT_INDEX.json', dict(cycle_id=CYCLE, files=rows, file_count=len(rows),
        bytes=sum(r['bytes'] for r in rows), exclusions='Self-referential seal/index/readiness files and disposable bytecode only; all synthetic failures and scripts retained'))
    freeze = dict(cycle_id=CYCLE, status='PREP_READY', formal_GO=False, model_consumers=0,
        product_processes=0, Blender_sessions=0, CLI_processes=0, formal_consumers_planned=9,
        repetitions_each_arm=3, independent_scene_count=1, plan_sha256=sha(HERE/'PLAN.json'),
        private_anonymous_map_sha256=sha(HERE/'private/ANON_MAP.json'),
        artifact_index_sha256=sha(HERE/'ARTIFACT_INDEX.json'),
        product_sources={p:dict(commit=plan['installations'][p]['commit'], source_count=137,
                              source_sha256=plan['installations'][p]['source_sha256']) for p in ('P0','P1')},
        historical_consumers_pooled=False, installed_release_activated_as_default=False,
        actual_consumer_quality_or_cost_measured=False, old_six_cell_GO_valid=False,
        AL_registration='unbound host_epoch5, own Hook handle unavailable; no borrowed task writes',
        stop='End preparation after callback; require separate unique current-cycle root GO')
    save(HERE/'FREEZE.json', freeze)
    print(json.dumps(freeze))


if __name__ == '__main__':
    main()
