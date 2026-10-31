"""Build and validate a clean, uniquely named release without rewriting old ZIPs."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = '9.7.2+20261023.attention.cache'
REVISION = 'v1-attention-cache-20261022'
NAME = 'human_eye_engine_9_7_2_20261023_attention_cache'
TEMPLATES = ROOT / 'deployment/cloud_current'
EVIDENCE = ROOT / 'verification/fixes/20261023_cloud_package'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def python(args, cwd, *, input=None, timeout=180):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, '-B', *args], cwd=cwd, env=env, input=input,
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def portable(source):
    lines = source.splitlines(keepends=True)
    spans = []
    for node in ast.parse(source).body:
        if (isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and node.target.id in ('_cand', '_cand_dir')
                and any(isinstance(item, ast.Constant) and isinstance(item.value, str)
                        and item.value.startswith('D:') for item in ast.walk(node.iter))):
            spans.append((node.lineno - 1, node.end_lineno))
    for first, last in reversed(spans):
        lines[first:last] = ['# Portable release uses installed and package-relative imports.\n']
    result = ''.join(lines)
    ast.parse(result)
    return result, len(spans)


def ensure_console_scripts(project):
    """Add missing release aliases while preserving an explicit production entry."""
    document = tomllib.loads(project)
    scripts = document.get('project', {}).get('scripts', {})
    desired = {
        'human-eye-live': 'human_eye_plugin.production_server:main',
        'human-eye-configure': 'human_eye_plugin.agent_setup:main',
    }
    missing = {key: value for key, value in desired.items() if key not in scripts}
    if not missing:
        return project
    newline = '\r\n' if '\r\n' in project else '\n'
    additions = ''.join(key + ' = "' + value + '"' + newline for key, value in missing.items())
    match = re.search(r'(?m)^\[project\.scripts\][ \t]*(?:#[^\r\n]*)?(?:\r?\n|$)', project)
    if match:
        prefix = project[:match.end()]
        if not prefix.endswith('\n'):
            prefix += newline
        project = prefix + additions + project[match.end():]
    else:
        project = project.rstrip() + newline + newline + '[project.scripts]' + newline + additions
    # Fail during preparation rather than generating an invalid wheel project.
    tomllib.loads(project)
    return project


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    destination = ROOT / 'dist' / (NAME + '.zip')
    if destination.exists():
        raise FileExistsError('Release already exists; never silently replace an uploaded version')
    original = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    runtime = [name + '.py' for name in original['tool']['setuptools']['py-modules']]
    for package in original['tool']['setuptools']['packages']:
        runtime += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / package).glob('*.py'))]
    before = {p: sha(ROOT / p) for p in runtime}
    old_dist = {p.name: sha(p) for p in (ROOT / 'dist').iterdir() if p.is_file()}
    stage = Path(tempfile.mkdtemp(prefix='release_20261023_', dir=ROOT / 'artifacts'))
    bundle = stage / NAME
    bundle.mkdir()
    allowed = set()

    def add(relative, *, content=None, origin=None):
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if origin is not None:
            shutil.copy2(origin, target)
        else:
            target.write_text(content, encoding='utf-8', newline='\n')
        allowed.add(relative)
        return target

    edits = []
    for relative in sorted(runtime):
        content, count = portable((ROOT / relative).read_text(encoding='utf-8'))
        add('source/' + relative, content=content)
        if count:
            edits.append({'file': relative, 'removed_machine_import_fallbacks': count})
    project = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    project = project.replace('version = "9.7.2"', f'version = "{VERSION}"')
    project = project.replace('requires-python = ">=3.10"', 'requires-python = ">=3.11"')
    project = ensure_console_scripts(project)
    add('source/pyproject.toml', content=project)
    plugin = json.loads((ROOT / 'human_eye_plugin/plugin.json').read_text(encoding='utf-8'))
    plugin.update(description='Known-mesh 3D observation, beneficial contact attention, bounded scene history, '
        'host routing and checked rigid transforms.', buildRevision=REVISION)
    add('source/human_eye_plugin/plugin.json', content=json.dumps(plugin, ensure_ascii=False, indent=2) + '\n')
    add('source/human_eye_plugin/mcp_config.json', origin=ROOT / 'deployment/cloud/mcp_config.json')
    examples = ['agents/configure.py', 'agents/live_entry.py', 'agents/hook_entry.py',
                'blender_worker.py', 'automatic_3d_routing.py']
    for relative in examples:
        add('source/examples/' + relative, origin=ROOT / 'examples' / relative)
    for relative in ['README.md', 'RELEASE_NOTES.md', 'Dockerfile', '.dockerignore',
                     'config/live-connector.example.json']:
        add(relative, origin=TEMPLATES / relative)
    add('source/README.md', origin=TEMPLATES / 'README.md')
    add('requirements.lock.txt', origin=ROOT / 'deployment/cloud/requirements.lock.txt')
    add('verify_bundle.py', origin=ROOT / 'deployment/cloud/verify_bundle.py')
    add('examples/sdk_smoke.py', origin=ROOT / 'deployment/cloud/examples/sdk_smoke.py')
    add('examples/engine_smoke.py', origin=TEMPLATES / 'examples/engine_smoke.py')
    add('config/mcp-legacy-demo.json', origin=ROOT / 'deployment/cloud/mcp_config.json')
    add('config/mcp-live.example.json', content=json.dumps({'mcpServers': {'human_eye_live': {
        'command': 'python', 'args': ['-m', 'human_eye_plugin.live_spatial_mcp', '--config',
        '/ABSOLUTE/PATH/TO/RELEASE/config/live-connector.example.json']}}}, indent=2) + '\n')
    for path in sorted((ROOT / 'docs').glob('*.md')):
        content = path.read_text(encoding='utf-8').replace('D:/hefe', '<ENGINE_SOURCE>')
        content = re.sub(r'\[[^\]\n]+\]\([^\n)]*verification/[^\n)]*\)',
                         '[release validation](../RELEASE_NOTES.md)', content)
        content = ('> Historical source documentation. Local evidence and deployment status refer to '
                   'the original development environment; use the release README for installation.\n\n' + content)
        add('docs/' + path.name, content=content)
    wheels = bundle / 'wheels'
    wheels.mkdir()
    python(['-m', 'pip', 'wheel', str(bundle / 'source'), '--no-deps', '--no-build-isolation',
            '--wheel-dir', str(wheels), '--disable-pip-version-check'], stage)
    wheel, = wheels.glob('*.whl')
    allowed.add(wheel.relative_to(bundle).as_posix())
    with zipfile.ZipFile(wheel) as archive:
        for relative in runtime:
            assert archive.read(relative) == (bundle / 'source' / relative).read_bytes(), relative
        assert 'human_eye_plugin/attention_raster.py' in archive.namelist()
        wheel_metadata = archive.read(next(p for p in archive.namelist() if p.endswith('.dist-info/METADATA'))).decode()
        assert 'Version: ' + VERSION in wheel_metadata
    installed = Path(tempfile.mkdtemp(prefix='release_install_', dir=ROOT / 'artifacts'))
    python(['-m', 'pip', 'install', '--no-deps', '--no-compile', '--target', str(installed), str(wheel),
            '--disable-pip-version-check'], stage)
    # The default setup/worker entry files are shipped alongside source, rather
    # than falsely claiming these companion scripts are part of a pure wheel.
    def installed_script(name, args=()):
        script = str(bundle / 'examples' / name)
        return python(['-c', 'import runpy,sys; sys.argv=' + repr([script, *args]) +
                       '; runpy.run_path(sys.argv[0], run_name="__main__")'], installed)
    smoke = json.loads(installed_script('engine_smoke.py', ['--expect-root', str(installed)]))
    legacy = json.loads(installed_script('sdk_smoke.py'))
    requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
                {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
    wire = ''.join(json.dumps(item) + '\n' for item in requests)
    legacy_replies = [json.loads(line) for line in python(['-m', 'human_eye_plugin.mcp_server'], installed, input=wire).splitlines()]
    live_replies = [json.loads(line) for line in python(['-m', 'human_eye_plugin.live_spatial_mcp', '--config',
        str(bundle / 'config/live-connector.example.json')], installed, input=wire).splitlines()]
    assert len(legacy_replies[1]['result']['tools']) == 6
    assert len(live_replies[1]['result']['tools']) == 3
    native = json.loads(python(['-m', 'human_eye_plugin.router_server'], installed,
        input=json.dumps({'event': 'before_model', 'session_id': 'release-smoke', 'task_kind': 'general'}) + '\n'))
    assert native['result']['route'] == 'native'
    project_dir = stage / 'empty_agent_project'
    project_dir.mkdir()
    preview = json.loads(python(['-m', 'human_eye_plugin.agent_setup', '--agent', 'mcp', '--project', str(project_dir),
        '--engine-root', str(bundle / 'source')], installed))
    assert not list(project_dir.iterdir()), 'Dry run must not write user project files'
    # Run self-contained, high-value regression modules against the installed
    # wheel; tests and captured host snapshots never enter the upload ZIP.
    modules = ['test_attention_policy', 'test_attention_rendering', 'test_attention_dwell', 'test_scene_cache',
        'test_attention_cache_flow', 'test_mcp_goal_verification', 'test_task_verification',
        'test_strict_execution_collision', 'test_v1_observation_flow']
    helpers = ['test_auto_router', 'test_host_runtime', 'test_live_service', 'test_live_hooks', 'test_live_spatial_mcp']
    verification = installed / 'verification'
    verification.mkdir()
    for name in modules + helpers:
        shutil.copy2(ROOT / 'verification' / (name + '.py'), verification / (name + '.py'))
    # Use a single JSON runner for a precise installed-test count.
    test_record = json.loads(python(['-c',
        'import io,json,unittest; s=unittest.TestSuite(); '
        'names=' + repr(['verification.' + n for n in modules]) + '; '
        '[s.addTests(unittest.defaultTestLoader.loadTestsFromName(n)) for n in names]; '
        'stream=io.StringIO(); r=unittest.TextTestRunner(stream=stream).run(s); '
        'print(json.dumps(dict(tests=r.testsRun,passed=r.wasSuccessful(),'
        'failure_detail=stream.getvalue() if not r.wasSuccessful() else None))); '
        'raise SystemExit(not r.wasSuccessful())'], installed))
    checks = {'installed_engine_smoke': smoke, 'legacy_sdk_smoke': legacy,
        'installed_regressions': test_record, 'live_mcp_tools': 3, 'legacy_mcp_tools': 6,
        'router_native_passthrough': True, 'agent_setup_dry_run': True,
        'wheel_runtime_files_match_source': True, 'platform': sys.platform,
        'linux_container_executed': False, 'live_blender_contacted_in_packaging': False,
        'model_api_calls': 0}
    add('validation/installation.json', content=json.dumps(checks, ensure_ascii=False, indent=2) + '\n')
    build = {'release_version': VERSION, 'engine_base_version': original['project']['version'],
        'implementation_revision': REVISION, 'runtime_source_files': len(runtime),
        'origin_source_sha256': before, 'portable_copy_edits': edits,
        'copy_metadata_changes': ['release wheel version', 'Python>=3.11', 'additional live/setup entry points',
                                  'accurate plugin description and portable legacy MCP launcher'],
        'not_included': ['credentials', 'user configuration', 'live state', 'learning knowledge',
                         'private blind-test records', 'platform dependency binaries'],
        'validation': checks}
    add('BUILD_INFO.json', content=json.dumps(build, ensure_ascii=False, indent=2) + '\n')
    forbidden = {'.codex', '.human-eye', '.agents', '__pycache__', 'auth.json', '.env', 'live-state.json', 'AGENTS.md'}
    for relative in allowed:
        path = bundle / relative
        assert not any(part in forbidden for part in Path(relative).parts), relative
        if path.suffix in {'.py', '.md', '.toml', '.json'}:
            text = path.read_text(encoding='utf-8')
            assert all(term not in text for term in ('D:/hefe', 'D:\\hefe', 'C:\\Users', 'C:/Users')), relative
    manifest = {relative: sha(bundle / relative) for relative in sorted(allowed)}
    add('MANIFEST.json', content=json.dumps({'version': VERSION, 'files': manifest}, indent=2) + '\n')
    assert json.loads(python(['verify_bundle.py'], bundle))['passed']
    for name, expected in before.items():
        assert sha(ROOT / name) == expected, name
    for name, expected in old_dist.items():
        assert sha(ROOT / 'dist' / name) == expected, name
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in sorted(allowed):
            archive.write(bundle / relative, NAME + '/' + relative)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(allowed)
        for relative, expected in manifest.items():
            assert hashlib.sha256(archive.read(NAME + '/' + relative)).hexdigest() == expected
    digest = sha(destination)
    checksum = destination.with_suffix('.sha256.txt')
    checksum.write_text(f'{digest}  {destination.name}\n', encoding='utf-8')
    result = {'file': destination.name, 'bytes': destination.stat().st_size, 'sha256': digest,
        'local_path': str(destination), 'checksum_path': str(checksum), 'stage_path': str(bundle),
        'release_version': VERSION, 'runtime_source_files': len(runtime), 'bundle_files': len(allowed),
        'installed_regressions': test_record, 'passed': True, 'old_distribution_unchanged': True,
        'engine_source_unchanged': True, 'linux_container_executed': False}
    write_json(EVIDENCE / 'build_result.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
