"""Record the bounded offline suite and actual source identity; no Blender."""
import ast
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
DEST = Path(__file__).with_name('offline_qualification_01.json')
MODULES = ['verification.test_m4_capture_001', 'verification.test_blender_host_contracts',
    'verification.test_selected_task_host', 'verification.test_selected_task_query',
    'verification.test_blender_mcp_host', 'verification.test_surface_proximity_001',
    'verification.test_surface_proximity_pruning_001', 'verification.test_surface_scope_regression']


def source_identity():
    source = ROOT/'human_eye_plugin/runtime_identity.py'
    constants = {}
    for node in ast.parse(source.read_bytes()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in {'BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES'}:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    names = list(constants['_ROOT_MODULES'])
    for package in ('human_eye_plugin', 'human_eye_module1_operators'):
        names.extend(package+'/'+p.name for p in (ROOT/package).glob('*.py'))
    files = [{'path': p, 'sha256': hashlib.sha256((ROOT/p).read_bytes()).hexdigest()} for p in sorted(names)]
    raw = {'base_version': constants['BASE_VERSION'], 'implementation_revision': constants['IMPLEMENTATION_REVISION'], 'files': files}
    digest = hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    return {'source_count': len(files), 'source_sha256': digest, 'files': files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEST)
    destination = parser.parse_args().out.resolve()
    if not destination.is_relative_to(Path(__file__).resolve().parent):
        raise SystemExit('Receipt must stay in this evidence directory')
    if destination.exists(): raise SystemExit('Receipt already exists; do not overwrite or resample automatically')
    start = datetime.now(timezone.utc).isoformat()
    source = source_identity()
    parsed = []
    for path in (Path(__file__).with_name('real_qa.py'), Path(__file__).with_name('blender_assets.py')):
        ast.parse(path.read_bytes(), filename=str(path))
        parsed.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    command = [sys.executable, '-B', '-m', 'unittest', *MODULES, '-q']
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    begin = time.perf_counter_ns()
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=120)
    elapsed = time.perf_counter_ns()-begin
    after = source_identity()
    output = (result.stdout+result.stderr).decode('utf8', errors='replace')
    match = re.search(r'Ran (\d+) tests', output)
    receipt = {'kind': 'offline_only_not_Blender_performance', 'start_utc': start,
        'end_utc': datetime.now(timezone.utc).isoformat(), 'argv': command, 'cwd': str(ROOT),
        'exit_code': result.returncode, 'command_wall_ns': elapsed,
        'stdout': result.stdout.decode('utf8', errors='replace'), 'stderr': result.stderr.decode('utf8', errors='replace'),
        'tests_run': int(match.group(1)) if match else None, 'new_case_classes': 12,
        'source': source, 'source_unchanged_through_suite': after == source,
        'prepared_QA_scripts_syntax_checked': parsed, 'Blender_runs': 0, 'model_consumers': 0,
        'model_API_calls': 0, 'installs': 0, 'subagents': 0}
    destination.write_bytes((json.dumps(receipt, indent=2)+'\n').encode())
    print(json.dumps({k: receipt[k] for k in ('exit_code', 'tests_run', 'new_case_classes', 'source_unchanged_through_suite')}, indent=2))
    print('source_sha256='+source['source_sha256'])
    print('receipt='+str(destination))
    if result.returncode != 0 or after != source: raise SystemExit(1)


if __name__ == '__main__': main()
