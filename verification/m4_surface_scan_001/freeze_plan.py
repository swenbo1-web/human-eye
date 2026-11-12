"""Record the authorized surface-scan module and initial engineering protocol."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = 'a41e7d32f8c9fa1bf3b38117b015ff6848145862'
PLAN_SHA = '168dde76d53d8e17717112e7cc168936dd89a754eb3de8e867681c246bbdd2fd'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).strip().decode() == 'ea70339772159e5f0279784ebe18b1bf16e70439'
    (HERE / 'spec').mkdir(exist_ok=True)
    rows = []
    for name, target in (
        ('docs/M4_SURFACE_SCAN_001_PLAN.md', 'PLAN.md'),
        ('docs/M4_GROOVED_RAIL_TRANSFER_001_COST_REVIEW.md', 'PREVIOUS_REVIEW.md'),
        ('verification/fixes/20261112_m4_global_scan_design/REPORT.md', 'DESIGN_REFERENCE.md'),
    ):
        original = Path('D:/hefe') / name
        raw = original.read_bytes()
        assert subprocess.check_output(['git', 'show', PARENT + ':' + name], cwd=ROOT) == raw
        if target == 'PLAN.md':
            assert sha(original) == PLAN_SHA
        with (HERE / 'spec' / target).open('xb') as stream:
            stream.write(raw)
        rows.append({'root_path': name, 'copy': 'spec/' + target, 'sha256': sha(original)})
    binding = json.loads((ROOT / 'verification/m4_grooved_rail_transfer_001/SOURCE_BINDING.json').read_bytes())
    for row in binding['source_manifest']:
        assert sha(ROOT / row['path']) == row['sha256']
    save(HERE / 'BASELINE_SOURCE.json', binding)
    protected = [Path('C:/Users/Administrator/.codex/config.toml'), Path('D:/hefe/.codex/config.toml'),
                 ROOT / 'verification/m4_grooved_rail_transfer_001/asset/grooved_rail.blend']
    save(HERE / 'PROTECTED_BEFORE.json', {str(path): sha(path) for path in protected})
    save(HERE / 'WORK_ORDER.json', {
        'cycle': 'M4-SURFACE-SCAN-001', 'phase': 'qualification_and_initial_engineering',
        'recorded_utc': datetime.now(timezone.utc).isoformat(), 'parent_commit': PARENT,
        'baseline_commit': 'ea70339772159e5f0279784ebe18b1bf16e70439',
        'baseline_product_commit': 'e836e03f4b3821f869c72ac3e50df5204f28b50f',
        'baseline_source_sha256': binding['source_sha256'], 'source_count': 137,
        'specifications': rows,
        'execution_order': ['freeze unique geometry rules', 'qualify base and one edit with all 276 independent pair truths',
                            'commit input freeze', 'implement ordinary scan entry',
                            'freeze candidate and isolated install', 'directed regressions and engineering runs',
                            'initial-ready callback and administrator review'],
        'engineering_sequences': 5, 'engineering_sequence_states': ['cold', 'repeat', 'edit'],
        'benchmark_scope': 'Five independent process sequences of the same fixed scene. Startup/install costs separately retained.',
        'geometry_revision_limit': 1, 'geometry_revision_rule': 'Predeclare a single morphology change before construction. Apply only for input qualification, before product timing.',
        'evaluation_consumers': 0, 'images': 0, 'Google_or_paid_API_runs': 0,
        'AL': {'context_bound': False, 'host_epoch': 5, 'rebind_required': True,
               'task_registered': False, 'borrowed_handle': False},
        'pre_record_events': 'Read-only plan, baseline, current AL context and architecture inspection before this record.',
        'completion': 'Qualified fixed input, ordinary initial engineering entry and isolated evidence, callback and wait for independent review.',
    })
    print(json.dumps({'plan_sha256': PLAN_SHA, 'baseline_sources_verified': 137,
                      'engineering_sequences': 5, 'evaluation_consumers': 0}))


if __name__ == '__main__':
    main()
