"""Pin three existing public observations and the exact common task."""

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.with_name('m4_source_region_display_001')
RUNTIME = Path('D:/he_m4_source_region_consume_001')
PLANNING = '32254517bb6e18cbb3f6e9ab5318b13aa02a8a50'
PROMPT = '请分析这份已封存的Blender局部观测。报告选区到参考对象表面的最近距离、单位及见证来源，说明当前图片实际提供了哪些选区证据、选区可见像素数量以及仍有哪些部分未观察到。判断这个距离能支持哪些表面关系和实体内外结论。每项主要结论引用对应的区域或图像来源，信息不足时指出还缺什么。仅分析这份观测。'
TOOL = {'name': 'read_observation', 'description': '读取本会话绑定的一份封存观测，返回原产品JSON和PNG。采集时刻以返回的来源绑定为准。',
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    started = time.perf_counter_ns()
    RUNTIME.mkdir(exist_ok=False)
    (HERE / 'inputs').mkdir(exist_ok=False)
    (HERE / 'harness/reused').mkdir(parents=True, exist_ok=True)
    for name in ('M4_SOURCE_REGION_CONSUMPTION_001_PLAN.md', 'M4_SOURCE_REGION_DISPLAY_001_INDEPENDENT_REVIEW.md'):
        raw = subprocess.check_output(['git', 'show', PLANNING + ':docs/' + name], cwd=ROOT)
        (HERE / 'inputs' / name).write_bytes(raw)
    assert sha(HERE / 'inputs/M4_SOURCE_REGION_CONSUMPTION_001_PLAN.md') == '183a46ebc32275bc42c15417c8e4b124a0a5348d21495e1aea7a7669a8055fb1'
    (HERE / 'inputs/PROMPT.txt').write_bytes(PROMPT.encode('utf8'))
    save(HERE / 'inputs/TOOL_SCHEMA.json', TOOL)
    shutil.copyfile(PRIOR / 'public_schema/R0_scene_observe.json', HERE / 'inputs/FORMAL_PRODUCT_SCHEMA.json')
    shutil.copyfile(PRIOR / 'R0_RUN_BINDING.json', HERE / 'inputs/PRODUCT_BINDING.json')
    for name in ('process_proof.py',):
        shutil.copyfile(PRIOR / 'harness/reused' / name, HERE / 'harness/reused' / name)
    cases = []
    source_runtime = Path('D:/he_m4_source_region_display_001/sessions')
    for case_id, slot, index in [('S1', 'main', 1), ('S2', 'state', 2), ('S3', 'state', 4)]:
        folder = source_runtime / slot / 'product_calls' / ('call_' + str(index).zfill(3))
        response_path = folder / 'RESPONSE.json'
        response = json.loads(response_path.read_bytes())
        result = response['result']
        assert result.get('isError') is False
        assert [block['type'] for block in result['content']] == ['text', 'image']
        target = HERE / 'inputs' / case_id
        target.mkdir()
        shutil.copyfile(response_path, target / 'ORIGINAL_RESPONSE.json')
        save(target / 'TOOL_RESULT.json', result)
        brief = result['content'][0]['text'].encode('utf8')
        (target / 'ORIGINAL_BRIEF.json').write_bytes(brief)
        png = base64.b64decode(result['content'][1]['data'], validate=True)
        assert png == (folder / 'delivered/image_01.png').read_bytes()
        (target / 'ORIGINAL_IMAGE.png').write_bytes(png)
        cases.append({'case_id': case_id, 'source_slot': slot, 'source_public_index': index,
            'source_response': str(response_path), 'source_response_sha256': sha(response_path),
            'input_file': str((target / 'TOOL_RESULT.json').resolve()), 'input_sha256': sha(target / 'TOOL_RESULT.json'),
            'original_brief_sha256': sha(target / 'ORIGINAL_BRIEF.json'), 'brief_UTF8_bytes': len(brief),
            'PNG_sha256': sha(target / 'ORIGINAL_IMAGE.png'), 'PNG_bytes': len(png)})
    save(HERE / 'INPUTS.json', {'cases': cases, 'prompt_sha256': sha(HERE / 'inputs/PROMPT.txt'),
        'tool_schema_sha256': sha(HERE / 'inputs/TOOL_SCHEMA.json'), 'image_encoding_operations': 0})
    old = json.loads((PRIOR / 'BASELINE.json').read_bytes())
    save(HERE / 'BASELINE.json', {'task': 'M4-SOURCE-REGION-CONSUMPTION-001',
        'baseline_git': 'aa45f033ce662b7453dda77084b36da34640f558', 'planning_git': PLANNING,
        'product_git': '29f35a771c1d137455602adf28418f45e2788e6a',
        'source_sha256': 'af7c2cf6715e11f237e878fd6f66047d632b48e528f6b5abe28f6da66b5e232c',
        'asset': old['asset'], 'direct_pins': [{'path': str(PRIOR / name), 'sha256': sha(PRIOR / name)}
            for name in ('CONTENT_MANIFEST.json', 'DECISION.json', 'R0_RUN_BINDING.json')],
        'limits': {'consumers': 3, 'task_seconds': 450, 'process_seconds': 600, 'business_calls': 4,
                   'new_Blender': 0, 'new_product_calls': 0, 'raster': 0, 'PNG_or_NPZ_encoding': 0,
                   'training': 0, 'paid_API': 0, 'replacement_consumers': 0},
        'agent_learning': {'task_writes': 0, 'status': 'pending_no_current_context_handle'}})
    save(HERE / 'PREPARATION_TIMING.json', {'automated_input_preparation_started_ns': started,
        'automated_input_preparation_closed_ns': time.perf_counter_ns(),
        'scope': 'This script input copies, hashes and contract registration. Earlier planning and adapter authoring are not a measured wall-clock interval.',
        'new_Blender': 0, 'new_model': 0, 'image_encoding': 0})


if __name__ == '__main__':
    main()
