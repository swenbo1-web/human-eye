"""Bind one explicit-entry diagnostic to the original immutable task suffix."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
OLD = HERE.with_name('m4_region_localization_consumption_001')
PREFIX = (
    'For this diagnostic, first call the available active_observation tool with include_images=true. '
    'Use its returned current-session facts and images to complete the inspection below. '
    'Use the other tools only when additional evidence is needed. '
    'If that tool is unavailable or fails, report the actual failure; completing the task through native '
    "tools alone does not establish this diagnostic's observation-entry qualification."
)


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    inputs = HERE / 'inputs'
    inputs.mkdir(parents=True, exist_ok=False)
    original = (OLD / 'inputs/PROMPT.txt').read_bytes()
    assert digest(original) == '3f848a42070580ad479e3de6507b9ffe09c59b9651c784c17608f0d752c1205a'
    prefix = PREFIX.encode('utf8')
    prompt = prefix + b'\n\n' + original
    (inputs / 'PREFIX.txt').write_bytes(prefix)
    (inputs / 'PROMPT_SUFFIX.txt').write_bytes(original)
    (inputs / 'PROMPT.txt').write_bytes(prompt)
    manifest = json.loads((OLD / 'inputs/SOURCES.json').read_bytes())
    for name in ('capture', 'scene', 'cameras', 'product_binding'):
        source = manifest[name]
        path = (Path(source['path']) if 'path' in source else OLD / 'inputs' / source['file']).resolve()
        assert digest(path.read_bytes()) == source['sha256']
        manifest[name] = {'path': str(path), 'sha256': source['sha256']}
    manifest['budget_contract'] = {
        'external_root': 'D:/he_explicit_001',
        'preparation_root': 'D:/he_explicit_001/preparation',
        'formal_root': 'D:/he_explicit_001/formal',
        'ledger_root': 'D:/he_explicit_001/raster_budget',
        'preparation_cap': 0, 'formal_cap': 6, 'total_cap': 44, 'per_slot_cap': 6,
    }
    save(inputs / 'SOURCES.json', manifest)
    plan_path = Path('D:/hefe/docs/M4_EXPLICIT_OBSERVATION_CONSUMPTION_001_PLAN.md')
    plan_blob = plan_path.read_bytes()
    assert digest(plan_blob) == 'a1e2b62ffd853e4e9b795d1852d1bbc60e27f4ba6be01d984acfa083fc07b7ee'
    (HERE / 'PLAN.md').write_bytes(plan_blob)
    plan = json.loads((OLD / 'PLAN.json').read_bytes())
    plan.update(schema='explicit-observation-consumption-001-plan-v1',
        task='M4-EXPLICIT-OBSERVATION-CONSUMPTION-001',
        baseline_commit='21b2871df70c5fedde4a916c67983ee40c626f89',
        administrator_plan_sha256=digest(plan_blob),
        sequence=[{'slot': 'P1', 'group': 'P'}],
        inputs={'prompt': str((inputs / 'PROMPT.txt').resolve()),
                'input_manifest': str((inputs / 'SOURCES.json').resolve())},
        external_root='D:/he_explicit_001', runtime_root='D:/he_explicit_001/formal',
        preparation_root='D:/he_explicit_001/preparation',
        formal_render_cap=6, preparation_render_cap=0, total_new_render_cap=6,
        preparation_local_check_groups=[], preparation_max_attempts_per_group=0,
        preparation_max_total_attempts=0, formal_batch_attempts=1,
        expected_prompt_sha256=digest(prompt), original_suffix_sha256=digest(original),
        prefix_sha256=digest(prefix),
        decision_rule='One actual fresh P turn. Separately qualify installed entry invocation, actual default-v3 text/images delivery and source-attributed consumption under the original task-quality rules. No native comparison or benefit ratio.',
        evidence_scope='Recorded-source module diagnostic. Explicit instruction, ordinary recovery within the same turn. Desktop Hook routing, spontaneous adoption and provider internal requests remain unmeasured.')
    save(HERE / 'PLAN.json', plan)
    save(HERE / 'INPUT_BINDING.json', {
        'original_prompt_path': str((OLD / 'inputs/PROMPT.txt').resolve()),
        'original_suffix_sha256': digest(original), 'prefix_sha256': digest(prefix),
        'new_prompt_sha256': digest(prompt), 'original_suffix_byte_exact': prompt.endswith(original),
        'separator_bytes': [10, 10], 'shared_tool_definitions_and_order': 'Original bridge.py is read-only reused.',
        'new_runtime_root': 'D:/he_explicit_001',
        'limits': {'fresh_contexts': 1, 'user_turns': 1, 'seconds': 450, 'tool_attempts': 12, 'raster_attempts': 6},
        'legacy_ledger_container_cap': 44,
        'effective_cap': 'One fresh actor, phase cap 6 and per-slot cap 6 enforce the new six-raster ceiling.',
        'new_model_or_raster_calls': 0,
    })
    print(json.dumps({'suffix_exact': True, 'prompt_sha256': digest(prompt),
                      'new_model_sessions': 0, 'new_rasters': 0}))


if __name__ == '__main__':
    main()
