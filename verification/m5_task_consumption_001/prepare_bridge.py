"""Prepare fixed public schemas, prompts and offline dependency/CLI receipts."""

import hashlib
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.with_name('m4_target_task_consumption_001')
BASE = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def text(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(value)


def main():
    started = time.perf_counter_ns()
    shared = json.loads((OLD / 'SHARED_DEPENDENCY.json').read_bytes())
    for name, digest in shared['files_sha256'].items():
        if sha(name) != digest:
            raise ValueError('existing_shared_dependency_changed')
    with (HERE / 'SHARED_DEPENDENCY.json').open('xb') as stream:
        stream.write((OLD / 'SHARED_DEPENDENCY.json').read_bytes())
    schemas = HERE / 'public_schema'
    schemas.mkdir(exist_ok=False)
    script = """
import hashlib,json,pathlib,sys
sys.path[:0]=[sys.argv[1], 'D:/he_anchor_001/venv/Lib/site-packages']
import human_eye_hook
from human_eye_plugin import live_spatial_mcp as module
tools=[row for row in module.LIVE_MCP_TOOLS_SCHEMA if row['name']=='human_eye_scene_observe']
assert len(tools)==1
p=pathlib.Path(module.__file__).resolve()
assert p.is_relative_to(pathlib.Path(sys.argv[1]).resolve())
print(json.dumps({'tool':tools[0],'module_file':str(p),'module_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
"""
    source_receipts = []
    for group in ('A', 'B'):
        binding = json.loads((HERE / (group + '_RUN_BINDING.json')).read_bytes())
        result = subprocess.run([str(BASE), '-I', '-B', '-X', 'utf8', '-c', script, binding['install_root']],
            capture_output=True, timeout=30, check=True)
        value = json.loads(result.stdout)
        expected = next(row['sha256'] for row in binding['source_manifest']
            if row['path'] == 'human_eye_plugin/live_spatial_mcp.py')
        if value['module_sha256'] != expected:
            raise ValueError('installed_public_schema_source_changed')
        save(schemas / (group + '_scene_observe.json'), value['tool'])
        source_receipts.append({'group': group, 'source_sha256': binding['source_sha256'],
            'module_file': value['module_file'], 'module_sha256': expected,
            'schema_sha256': sha(schemas / (group + '_scene_observe.json')),
            'pure_import_exit_code': result.returncode, 'new_actual_calls': 0})
    save(HERE / 'PUBLIC_SCHEMA_BINDINGS.json', {'schema': 'm5-task-public-schema-bindings-v1',
        'versions': source_receipts, 'scope': 'Pure installed-module import only. Runtime tools/list must match exactly before qualification.',
        'new_Blender_MCP_raster_model_calls': 0})
    route = ('Begin by obtaining the task facts from the installed public product API through execute_python or human_eye_scene_observe. '
        'Use default brief responses and current images. In one execute_python call you may invoke observe(query,include_image=True) and task(query) sequentially, retain both original results, and print the needed information. '
        'Their native PNG content is delivered in the same tool reply. Reuse current-session evidence and computed facts. Obtain additional evidence when it is missing or inconsistent. '
        'Both groups have the same ordinary Python, raw-source, low-level image and cache helpers. Keep the current scene read-only. Complete this single task within the existing turn and tool budget.\n')
    capabilities = {
        'A': 'This installed version provides active_observation and the original separate mode=task query. Both public requests may be issued together in one execute_python call using observe(...) followed by task(...). Each function returns the original public JSON.\n',
        'B': 'This installed version provides active_observation, the original mode=task query, and an optional task_query inside active_observation. A combined observe(...) returns the original observation with task_result. Separate observe(...) and task(...) remain available in the same execute_python call.\n',
    }
    text(HERE / 'inputs/ROUTING_COMMON.txt', route)
    common = (HERE / 'inputs/COMMON_TASK.txt').read_bytes()
    answer = (HERE / 'inputs/ANSWER_SCHEMA.json').read_bytes()
    for group in ('A', 'B'):
        text(HERE / 'inputs' / ('CAPABILITY_' + group + '.txt'), capabilities[group])
        prompt = route.encode() + b'\n' + capabilities[group].encode() + b'\n' + common + b'\n\nANSWER_SCHEMA.json\n' + answer
        with (HERE / 'inputs' / ('PROMPT_' + group + '.txt')).open('xb') as stream:
            stream.write(prompt)
    previous = json.loads((OLD / 'CLI_PREFLIGHT.json').read_bytes())
    binary = previous['binary']
    if sha(binary['path']) != binary['sha256']:
        raise ValueError('fixed_CLI_bytes_changed')
    version = subprocess.run([binary['path'], '--version'], capture_output=True, timeout=30)
    login = subprocess.run([binary['path'], 'login', 'status'], capture_output=True, timeout=30)
    if version.returncode or login.returncode:
        raise ValueError('CLI_version_or_login_preflight_failed')
    login_output = login.stdout + login.stderr
    if b'ChatGPT' not in login_output:
        raise ValueError('fixed_ChatGPT_login_mode_required')
    save(HERE / 'CLI_PREFLIGHT.json', {'schema': 'm5-task-cli-preflight-v1', 'binary': binary,
        'version': version.stdout.decode('utf-8').strip(), 'version_exit': version.returncode,
        'login_status_exit': login.returncode, 'authentication_mode': 'ChatGPT',
        'login_output_sha256': hashlib.sha256(login_output).hexdigest(), 'login_sensitive_output_retained': False,
        'original_interface_sha256': sha(OLD / 'CLI_PREFLIGHT.json'), 'started_ns': started,
        'closed_ns': time.perf_counter_ns(), 'model_calls': 0})
    prepare_original_n3()
    print(json.dumps({'public_schema_versions': 2, 'shared_original_files_verified': len(shared['files_sha256']),
        'prompts_fixed': 2, 'CLI_model_calls': 0, 'original_N3_fixture_retained': True}))


def prepare_original_n3():
    archive = json.loads((OLD / 'RUNTIME_ARCHIVE.json').read_bytes())
    candidates = []
    for row in archive['files']:
        if not row['relative_path'].startswith('formal/N3/') or not row['relative_path'].endswith('/REQUEST.json'):
            continue
        path = OLD / row['archive_path']
        request = json.loads(path.read_bytes())
        code = request.get('params', {}).get('arguments', {}).get('code', '')
        if '.__name__' in code:
            candidates.append((row, request, code, path))
    if not candidates or len({hashlib.sha256(item[2].encode()).hexdigest() for item in candidates}) != 1:
        raise ValueError('unique_original_N3_type_name_code_required')
    canonical = [item for item in candidates if '/owner/' in item[0]['relative_path']]
    if len(canonical) != 1:
        raise ValueError('canonical_original_N3_owner_request_required')
    row, request, code, path = canonical[0]
    fixtures = HERE / 'fixtures'
    fixtures.mkdir(exist_ok=True)
    text(fixtures / 'ORIGINAL_N3_TYPE_NAME.py.txt', code)
    save(fixtures / 'ORIGINAL_N3_REQUEST.json', request)
    save(fixtures / 'ORIGINAL_N3_PROVENANCE.json', {'schema': 'm5-original-N3-type-name-regression-v1',
        'archive_manifest_path': str(OLD / 'RUNTIME_ARCHIVE.json'), 'archive_manifest_sha256': sha(OLD / 'RUNTIME_ARCHIVE.json'),
        'original_relative_path': row['relative_path'], 'original_request_sha256': sha(path),
        'archived_path': str(path), 'original_code_sha256': hashlib.sha256(code.encode()).hexdigest(),
        'existing_archive_copies': [{'relative_path': item[0]['relative_path'], 'sha256': sha(item[3])} for item in candidates],
        'historical_trace_changed': False})


if __name__ == '__main__':
    main()
