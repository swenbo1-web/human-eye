"""Freeze the verified archived inputs and the three actual stdio replay arms."""
import json
from hashlib import sha256
from pathlib import Path
from runpy import run_path

NS = Path(__file__).resolve().parent
V = NS.parent
ROOT = Path('D:/he_m1_source_region_no_image_measurement_packet_001')
BASE = V / 'm1_region_task_witness_image_path_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'
PLAN = '6e1a0d03cbe0a1a69a1639ca176ce67e89569049'


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    path = path.resolve(strict=True)
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def freeze():
    expected = ('holdout_A1_full', 'holdout_B1_full', 'independent_P1_full', 'holdout_A1_brief', 'holdout_B1_brief')
    score_files = [ROOT / 'original_scores_verified' / f'{label}.json' for label in expected]
    verified = [read(path) for path in score_files]
    if not all(row['passed'] for row in verified):
        raise ValueError('historical geometry preflight did not pass')
    imports = (V/'m4_source_region_display_001/harness/reused/stdio_checks.py',
               V/'m1_region_task_brief_client_profile_001/product_replay.py',
               V/'m1_region_task_witness_image_path_001/harness/replay.py',
               V/'m4_live_source_region_task_003/harness/reused/verified_bootstrap.py',
               V/'m4_cross_scale_live_qualification_001/checks/delivery.py',
               V/'m5_global_observe_measure_qualification_001/checks/live_wire.py',
               V/'m5_observe_measure_001/oracle.py')
    files = [ROOT/'PLAN.md', BASE, CANDIDATE, NS/'install/BUILD_INSTALL.json', *imports,
             *sorted(NS.glob('*.py')), *sorted((NS/'harness').glob('*.py')), *sorted((NS/'checks').glob('*.py')), ROOT/'independent_controls.json', ROOT/'preflight_02/INDEX.json', *score_files]
    if not (NS/'harness/run.py').is_file():
        raise ValueError('stdio replay harness has not finished preflight')
    identities = {}
    for label, binding_path in (('base', BASE), ('candidate', CANDIDATE)):
        binding = read(binding_path)
        wheel = pin(Path(binding['wheel_path']))
        if len(binding['source_manifest']) != 143 or wheel['sha256'] != binding['wheel_sha256']:
            raise ValueError('run binding or wheel changed', label)
        identities[label] = {key: binding[key] for key in ('preparation_git', 'source_sha256', 'wheel_sha256', 'install_root')}
        files.append(Path(wheel['path']))
    sources = {Path(row['path']) for result in verified
               for row in [result['sealed_originals']['archive'], result['sealed_originals']['index'],
                           *result['sealed_originals']['members'].values()]}
    pins = [pin(path) for path in sorted(set(files) | sources)]
    frozen = {'plan_git': PLAN, 'identities': identities, 'local_inputs': pins,
              'arms': {'baseline_standard': ['base', 'standard'],
                       'candidate_standard': ['candidate', 'standard'],
                       'candidate_evidence': ['candidate', 'evidence']},
              'compact_utf8_bytes_limit': 10800, 'CLI_header_bytes': [33,34,35],
              'CLI_public_result_bytes':12000,'CLI_history_approximate_tokens':3000,
              'positive_cases': list(expected[:3]), 'new_qualification_arms': 3,
              'new_candidate_installs': 1, 'new_blender': 0, 'new_models': 0,
              'new_rasters': 0, 'additional_fee': 0, 'replacements': 0}
    with (NS/'FROZEN.json').open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(frozen, ensure_ascii=False, indent=2) + '\n')
    print(pin(NS/'FROZEN.json'))


if __name__ == '__main__':
    freeze()
