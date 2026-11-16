"""Register the fixed qualification and migrate only its required live plumbing."""

import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = ROOT / 'verification/m5_harness_recovery_001'
BASELINE = 'c041d4f038f72215aa4107a26fcbfd36aa53dd31'
PLAN_SHA = '88f78a772a13dc52e8c3070beb95e074fa1f7d8b4a392ded6b5bbf18ece77888'


def pin(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def migrate_runtime():
    original = (PRIOR / 'harness/owned_runtime.py').read_text(encoding='utf8')
    tree = ast.parse(original)
    methods = {'start', 'set_consumer_deadline', 'check', '_start_mcp', '_native_call',
               'scene_data', '_register', 'public_request', '_save_evidence', 'snapshot', 'close'}
    imports = ['import base64', 'import copy', 'import hashlib', 'import importlib.util',
               'import json', 'from pathlib import Path', 'import sys', 'import time', 'import traceback']
    functions = [ast.get_source_segment(original, node) for node in tree.body if isinstance(node, ast.FunctionDef)]
    context = """
HERE = Path(__file__).resolve().parent
NAMESPACE = HERE.parent
sys.path.insert(0, str(HERE))
from budget import Budget, save
PRODUCT_SHA256 = {'B': '7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a'}
EXTERNAL = Path('D:/he_m4_global_local_001')
ASSET = EXTERNAL / 'fixture/main.blend'
ASSET_SHA256 = json.loads((NAMESPACE / 'fixture/ASSET_BINDING.json').read_bytes())['asset_sha256']
"""
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'RootRuntime')
    body = []
    for node in cls.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in methods:
            continue
        lines = original.splitlines()
        begin = min([node.lineno] + [decorator.lineno for decorator in node.decorator_list]) - 1
        segment = '\n'.join(lines[begin:node.end_lineno])
        body.append(segment)
    output = '\n\n'.join(['"""Fixed B, direct root-held qualification runtime, without model consumers."""',
                              '\n'.join(imports), context, '\n\n'.join(functions),
                              'class RootRuntime:\n' + '\n\n'.join(body)]) + '\n'
    output = output.replace('group not in ("A", "B")', 'group != "B"')
    begin = output.index('            loaded = time.perf_counter_ns()')
    end = output.index('            bootstrap = module(', begin)
    output = output[:begin] + '            self.device = {"source": "existing_product_scope_fitted_six_cameras", "external_camera_override": False}\n' + output[end:]
    begin = output.index('            scratch = self.runroot / "blender_scratch"')
    end = output.index('            self._start_mcp()', begin)
    output = output[:begin] + output[end:]
    output = output.replace('code if trusted else wrap(code)', 'code')
    output = output.replace(', "camera_sha256": DEVICE_SHA256', '')
    ast.parse(output)
    (HERE / 'harness/owned_runtime.py').write_text(output, encoding='utf8', newline='\n')
    return pin(PRIOR / 'harness/owned_runtime.py')


def main():
    started = time.perf_counter_ns()
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != BASELINE:
        raise ValueError('accepted_baseline')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT):
        raise ValueError('clean_tracked_baseline')
    (HERE / 'reference').mkdir(exist_ok=True)
    (HERE / 'harness/reused').mkdir(parents=True, exist_ok=True)
    (HERE / 'public_schema').mkdir(exist_ok=True)
    references = []
    for source in (Path('D:/hefe/docs/M4_GLOBAL_LOCAL_QUALIFICATION_001_PLAN.md'),
                   Path('D:/hefe/docs/M1_M5_M6_COORDINATION_REVIEW_20261116.md'),
                   Path('D:/hefe/verification/fixes/20261116_m5_harness_recovery_review/discovery/DESIGN.md')):
        if source.name == 'M4_GLOBAL_LOCAL_QUALIFICATION_001_PLAN.md' and pin(source)['sha256'] != PLAN_SHA:
            raise ValueError('administrator_plan_identity')
        target = HERE / 'reference' / source.name
        shutil.copyfile(source, target)
        references.append(dict(original=pin(source), copy=pin(target)))
    copied = []
    for relative in ('B_RUN_BINDING.json', 'SHARED_DEPENDENCY.json', 'public_schema/B_scene_observe.json',
                     'harness/mcp_entry.py', 'harness/reused/owned_native.py', 'harness/reused/process_proof.py',
                     'harness/reused/stdio_checks.py', 'harness/reused/verified_bootstrap.py', 'harness/reused/wire_meter.py'):
        shutil.copyfile(PRIOR / relative, HERE / relative)
        copied.append(dict(original=pin(PRIOR / relative), copy=pin(HERE / relative)))
    budget = (PRIOR / 'harness/budget.py').read_text(encoding='utf8')
    budget = budget.replace('"Blender_start_attempts": 2, "all_rasters": 12', '"Blender_start_attempts": 3, "all_rasters": 18')
    (HERE / 'harness/budget.py').write_text(budget, encoding='utf8', newline='\n')
    original_runtime = migrate_runtime()
    save(HERE / 'BASELINE.json', dict(schema='m4-global-local-baseline-v1', task='M4-GLOBAL-LOCAL-QUALIFICATION-001',
        baseline_git=BASELINE, started_ns=started, runtime_root='D:/he_m4_global_local_001', references=references,
        protected_direct_seals=[pin(PRIOR / item) for item in ('CONTENT_MANIFEST.json', 'FINAL_AUDIT.json', 'FROZEN.json', 'DECISION.json')],
        migration_original=original_runtime, copied_inputs=copied,
        limits=dict(qualification_owned=3, qualification_rasters=18, model_consumers=0, paid_API_calls=0,
                    owned_seconds=600, public_request_seconds=30, per_session_public_calls=1),
        fixture_preparation=dict(Blender_processes=1, raster_attempts=0,
            scope='Authorized fixed-asset construction and saved readback precedes the three fresh read-only qualification sessions. Counted separately and included in total process and elapsed cost.'),
        actual_sequence=['global', 'local_open', 'local_covered'], product_changes_allowed=False,
        AL=dict(context_bound=False, host_epoch=5, registration='pending_current_chat_host_binding', writes=0),
        paused=['Google', 'API', 'key'], clock_scope='Registration onward, prior reading and delegation excluded.'))
    print(json.dumps(dict(registered=True, copied_direct_inputs=len(copied), actual_starts=0)))


if __name__ == '__main__':
    main()
