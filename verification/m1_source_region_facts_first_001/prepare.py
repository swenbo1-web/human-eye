"""Register immutable historical facts and unchanged consumer wording/scoring."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.with_name('m4_source_region_consumption_001')
DISPLAY = HERE.with_name('m4_source_region_display_001')
PLAN = '9f155d7632b569f41241f1a4d722c06dff67ffaa'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began = time.perf_counter_ns()
    (HERE / 'inputs').mkdir(exist_ok=False)
    (HERE / 'scoring').mkdir(exist_ok=False)
    (HERE / 'historical').mkdir(exist_ok=False)
    for name in ('M1_SOURCE_REGION_FACTS_FIRST_001_PLAN.md', 'M4_SOURCE_REGION_CONSUMPTION_001_INDEPENDENT_REVIEW.md'):
        (HERE / 'inputs' / name).write_bytes(subprocess.check_output(['git', 'show', PLAN + ':docs/' + name], cwd=ROOT))
    assert sha(HERE / 'inputs/M1_SOURCE_REGION_FACTS_FIRST_001_PLAN.md') == '986554c4406ac65af36779015779d6ed349c7e491ff06d3b3de4133b80373a98'
    for name in ('PROMPT.txt', 'TOOL_SCHEMA.json'):
        shutil.copyfile(OLD / 'inputs' / name, HERE / 'inputs' / name)
    for name in ('RUBRIC.json', 'CASE_ANSWERS.json', 'SCORE_METHOD.md'):
        shutil.copyfile(OLD / 'scoring' / name, HERE / 'scoring' / name)
    shutil.copyfile(DISPLAY / 'R0_RUN_BINDING.json', HERE / 'historical/PRODUCT_BINDING.json')
    rows = []
    for case, slot, index in [('S1', 'main', 1), ('S2', 'state', 2), ('S3', 'state', 4)]:
        target = HERE / 'historical' / case
        target.mkdir()
        records = [json.loads(line) for line in (Path('D:/he_m4_source_region_display_001/sessions') / slot / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()]
        call = next(row for row in records if row['internal_public_call_index'] == index)
        full_path = Path(call['producer_archive']['path'])
        assert sha(full_path) == call['producer_archive']['sha256']
        shutil.copyfile(full_path, target / 'SERVICE_RESULT.json')
        for name in ('TOOL_RESULT.json', 'ORIGINAL_RESPONSE.json', 'ORIGINAL_BRIEF.json', 'ORIGINAL_IMAGE.png'):
            shutil.copyfile(OLD / 'inputs' / case / name, target / name)
        rows.append({'case_id': case, 'source_slot': slot, 'source_public_index': index,
            'full_path': str((target / 'SERVICE_RESULT.json').resolve()), 'full_sha256': sha(full_path),
            'original_input_file': str((target / 'TOOL_RESULT.json').resolve()),
            'original_input_sha256': sha(target / 'TOOL_RESULT.json'),
            'PNG_path': str((target / 'ORIGINAL_IMAGE.png').resolve()), 'PNG_sha256': sha(target / 'ORIGINAL_IMAGE.png')})
    baseline = {'task': 'M1-SOURCE-REGION-FACTS-FIRST-001',
        'baseline_git': '28cc6fc728c9fb62d46120f3be14b46d673f675a', 'planning_git': PLAN,
        'accepted_product_git': '29f35a771c1d137455602adf28418f45e2788e6a',
        'accepted_source_sha256': 'af7c2cf6715e11f237e878fd6f66047d632b48e528f6b5abe28f6da66b5e232c',
        'cases': rows, 'consumer_group': 'F',
        'direct_pins': [{'path': str(path), 'sha256': sha(path)} for path in [
            OLD / 'CONTENT_MANIFEST.json', OLD / 'ANSWERS_SEALED.json', OLD / 'scoring/AUTHOR_SCORES.json',
            DISPLAY / 'CONTENT_MANIFEST.json', DISPLAY / 'R0_RUN_BINDING.json']],
        'limits': {'consumers': 3, 'replacement_consumers': 0, 'task_seconds': 450,
            'process_seconds': 600, 'all_completed_CLI_tools': 4, 'paired_windows_per_input': 5,
            'projection_iterations_per_window': 20, 'new_Blender': 0, 'new_product_solving': 0,
            'raster': 0, 'PNG_or_NPZ_encoding': 0, 'training': 0, 'paid_API': 0},
        'agent_learning': {'task_writes': 0, 'status': 'pending_no_current_context_handle'},
        'registered_ns': began, 'closed_ns': time.perf_counter_ns()}
    (HERE / 'BASELINE.json').write_text(json.dumps(baseline, sort_keys=True, indent=2) + '\n', encoding='utf8')


if __name__ == '__main__':
    main()
