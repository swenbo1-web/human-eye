"""Bind the authorized consumption phase to its accepted unique input."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = '25e4f21335a53b28c5688dc6611f13204a6fde15'
QUALIFICATION = ROOT / 'verification/m4_grooved_rail_transfer_001'
PREVIOUS = ROOT / 'verification/m4_spatial_fact_consumption_001'
MATERIALS = {
    'docs/M4_GROOVED_RAIL_TRANSFER_001_CONSUMPTION_PLAN.md': ('ROOT_PLAN.md', '198a5834b3c38ce6d981f3a686938598a4c337b51ea9326d491d5fb5ec4e80a4'),
    'docs/M4_GROOVED_RAIL_TRANSFER_001_QUALIFICATION_REVIEW.md': ('QUALIFICATION_REVIEW.md', '3834bd2de10764f2ec7a36a0afb2227c0749a620e65c84d6f9c0efdafd6b9453'),
    'verification/fixes/20261112_m4_grooved_rail_qualification_review/QUALIFICATION_REVIEW.json': ('QUALIFICATION_SEAL.json', '98222645f650e95519912519ac192f8a94f404483e272fafe0a9e443b7f063b9'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def copy(original, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(original.read_bytes())


def main():
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).strip().decode() == '9f38e8522cfeea9a580a19baad0e0d823eb1a16f'
    for name, (target, digest) in MATERIALS.items():
        original = Path('D:/hefe') / name
        assert sha(original) == digest
        assert subprocess.check_output(['git', 'show', PARENT + ':' + name], cwd=ROOT) == original.read_bytes()
        copy(original, HERE / target)
    manifest = json.loads((QUALIFICATION / 'QUALIFICATION_MANIFEST.json').read_bytes())
    expected_names = {row['path'] for row in manifest['files']} | {'QUALIFICATION_MANIFEST.json'}
    actual_names = {path.relative_to(QUALIFICATION).as_posix() for path in QUALIFICATION.rglob('*') if path.is_file()}
    assert actual_names == expected_names and len(actual_names) == 57
    for row in manifest['files']:
        path = QUALIFICATION / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    for original, target in (
        (QUALIFICATION / 'asset/grooved_rail.blend', HERE / 'input/scene.blend'),
        (QUALIFICATION / 'asset/ACTUAL_SNAPSHOT.json', HERE / 'scoring/ACTUAL_SNAPSHOT.json'),
        (QUALIFICATION / 'oracle/TRUTH.json', HERE / 'scoring/TRUTH.json'),
        (PREVIOUS / 'installations/P_READY.json', HERE / 'installations/P_READY.json'),
        (PREVIOUS / 'schemas/COMMON_NATIVE.json', HERE / 'schemas/COMMON_NATIVE.json'),
        (PREVIOUS / 'schemas/P_PUBLIC_TOOLS.json', HERE / 'schemas/P_PUBLIC_TOOLS.json'),
    ):
        copy(original, target)
    prompt = next(line[2:] for line in (HERE / 'ROOT_PLAN.md').read_text(encoding='utf8').splitlines() if line.startswith('> 检查'))
    with (HERE / 'input/PROMPT.txt').open('xb') as stream:
        stream.write(prompt.encode('utf8'))
    for name in ('runtime', 'preflight', 'private', 'quality', 'review'):
        (HERE / name).mkdir(exist_ok=True)
    save(HERE / 'WORK_ORDER.json', {
        'cycle_id': 'M4-GROOVED-RAIL-TRANSFER-001', 'phase': 'formal_consumption',
        'recorded_utc': datetime.now(timezone.utc).isoformat(), 'parent_commit': PARENT,
        'qualification_commit': '9f38e8522cfeea9a580a19baad0e0d823eb1a16f',
        'authorization': 'Administrator delegates preparation, freeze and one direct fixed six-consumer run, then anonymous quality handoff.',
        'logical_denominator': 6, 'model': 'gpt-6.1-sol', 'requested_effort': 'medium',
        'initial_images': 0, 'new_images': 0, 'product_pretests': 0,
        'quality_before_cost': True,
        'AL': {'context_bound': False, 'host_epoch': 5, 'rebind_required': True,
               'task_registered': False, 'borrowed_handle': False},
        'pre_record_events': 'Read-only parent plans, skill, session context and earlier adapter inspection preceded this record.',
    })
    protected = [ROOT / 'pyproject.toml', Path('C:/Users/Administrator/.codex/config.toml'),
                 Path('D:/hefe/.codex/config.toml'), PREVIOUS / 'input/scene.blend']
    protected.extend(QUALIFICATION / name for name in sorted(expected_names))
    save(HERE / 'preflight/PROTECTED_BEFORE.json', {str(path): sha(path) for path in protected})
    print(json.dumps({'qualified_files_verified': 57, 'prompt_bytes': len(prompt.encode('utf8')),
                      'product_pretests': 0, 'model_consumers': 0}))


if __name__ == '__main__':
    main()
