"""Freeze candidate runtime bytes before any main-asset product measurements."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from human_eye_plugin.runtime_identity import runtime_identity


def main():
    identity = runtime_identity()
    frozen = dict(input_commit='96fce78b98cb749885792112e039a406744d282b',
        parent_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        identity=identity, source_count=len(identity['source_files']),
        isolated_version='9.7.2+m4.surface.scan.r1',
        main_engineering_sequences=5, states=['cold', 'repeat', 'edit'],
        additional_host_path='single base directed BlenderProcessHost',
        product_main_asset_runs_before_freeze=0, evaluation_consumers=0, images=0,
        request_budget_s=30, client_timeout_s=35,
        final_targeted_tests=dict(passed=189, failed=0,
            sha256=hashlib.sha256((HERE/'FINAL_TARGETED_TESTS.txt').read_bytes()).hexdigest()),
        known_baseline_failure=dict(test='nearest_integration.g06',
            evidence='kernel_design/LEGACY_04_g06_baseline.txt',
            status='same failure reproduced on the frozen original 137-source baseline'),
        default_activation_changed=False)
    path = HERE/'CANDIDATE_SOURCE.json'
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(frozen, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(source_sha256=identity['source_sha256'], source_count=frozen['source_count'])))


if __name__ == '__main__':
    main()
