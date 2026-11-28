"""Build and install one wheel from the committed task-focus candidate only."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import tomllib
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ast
from hashlib import sha256
import json

PRODUCT = '4225256485a82a9ddbdeeca61e1bbd3275574a6e'
BLENDER = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
SOURCE = '60eabe4f875aabbd6c7b1c24c7498ed06b53d10b40a0e70a0ab920b4a64631e0'
BATCH = 'M1-NEAREST-SURFACE-ENTRY-DISCOVERY-001'
BASELINE_CUSTODY = '60014204a745d00ea804dc06df0fff51dddecdbd16b5b6bcc22af01656ab117d'


def sha(raw):
    return sha256(raw).hexdigest()


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def confirm(record):
    p = Path(record['path']).resolve(strict=True)
    need(pin(p) == record, 'bytes_outside_frozen_install')
    return p


def save(path, body):
    with Path(path).open('x',encoding='utf8',newline='\n') as out:
        json.dump(body,out,indent=2,ensure_ascii=False)
        out.write('\n')


def git(checkout, *args):
    return subprocess.check_output(['git', '-C', str(checkout), *args])


def observation_description(tree):
    matches = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        literal = {key.value: value for key, value in zip(node.keys, node.values, strict=True)
                   if isinstance(key, ast.Constant)}
        name, text = literal.get('name'), literal.get('description')
        if (isinstance(name, ast.Constant) and name.value == 'human_eye_scene_observe'
                and isinstance(text, ast.Constant) and isinstance(text.value, str)):
            matches.append(text)
    text, = matches
    return text


def install(root, checkout, candidate, baseline_path):
    plan = pin(root / 'preflight/ADMIN_PLAN.md')
    need(root.name == BATCH and plan['sha256']=='62cd96e0673243bfb3f7cfaf183b79caacae52803c738cd706bece89d30400b9',
         'wrong_single_candidate_admin_plan')
    need(pin(baseline_path)['sha256'] == BASELINE_CUSTODY, 'baseline_custody_changed')
    baseline = read(baseline_path)
    need(baseline['passed'] and baseline['candidate_commit'] == PRODUCT
         and baseline['source_sha256'] == SOURCE
         and baseline['runtime_sources'] == 146, 'baseline_install_not_fixed')
    for name in ('python', 'blender', 'build', 'wheel'):
        confirm(baseline[name])
    need(sys.flags.isolated and sys.dont_write_bytecode
         and pin(sys.executable) == baseline['python']
         and baseline['blender']['sha256'] == BLENDER, 'wrong_install_interpreter')
    commit, parent = git(checkout, 'rev-list', '--parents', '-n', '1', candidate).decode().split()
    need(parent == PRODUCT and commit != PRODUCT and len(commit) == 40, 'candidate_not_direct_child')
    original_manifest = {row['path']: row['sha256'] for row in baseline['source_manifest']}
    source_file = 'human_eye_plugin/live_spatial_mcp.py'
    changed = set(git(checkout, 'diff', '--name-only', '-z', parent, commit).decode().rstrip('\0').split('\0'))
    need(changed == {source_file} and changed <= original_manifest.keys(), 'candidate_contains_out_of_scope_changes')
    original, modified = (ast.parse(git(checkout, 'show', ref + ':' + source_file)) for ref in (parent, commit))
    old_text, new_text = (observation_description(tree) for tree in (original, modified))
    description = {'original_utf8_bytes': len(old_text.value.encode('utf8')),
                   'candidate_utf8_bytes': len(new_text.value.encode('utf8'))}
    description['increase_bytes'] = description['candidate_utf8_bytes'] - description['original_utf8_bytes']
    need(description['increase_bytes'] > 0, 'description_was_not_added')
    new_text.value = old_text.value
    need(ast.dump(original) == ast.dump(modified), 'candidate_changed_more_than_top_level_observe_description')
    build_tool = Path(__file__).resolve().parents[1] / 'build_candidate_release.py'
    need(build_tool.read_bytes() == git(checkout, 'show', PRODUCT + ':verification/build_candidate_release.py'),
         'wheel_builder_has_drift')
    spec = importlib.util.spec_from_file_location('fixed_wheel_builder', build_tool)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    install_root = root / 'install'
    install_root.mkdir(exist_ok=False)
    staged = install_root / 'git_source'
    staged.mkdir()
    site = install_root / 'candidate-site'
    manifest = []
    for path in sorted(original_manifest.keys() | changed):
        builder.safe_name(path)
        raw = git(checkout, 'show', commit + ':' + path)
        digest = sha(raw)
        if path not in changed:
            need(digest == original_manifest[path], 'unlisted_source_modified/' + path)
        dst = staged / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(raw)
        manifest.append({'path': path, 'sha256': digest})
    for relative in ('pyproject.toml', 'human_eye_plugin/plugin.json', 'human_eye_plugin/mcp_config.json'):
        raw = git(checkout, 'show', commit + ':' + relative)
        need(raw == git(checkout, 'show', PRODUCT + ':' + relative), 'unlisted_packaging_change')
        (staged / relative).write_bytes(raw)
    project = tomllib.loads((staged / 'pyproject.toml').read_text(encoding='utf8'))['project']
    artifact, wheel_bytes = builder.wheel_bytes(staged, manifest, project, '9.7.2+m1nearestentry001')
    wheel_check = builder.verify_wheel(wheel_bytes)
    wheel = install_root / artifact
    wheel.write_bytes(wheel_bytes)
    args = [sys.executable, '-IB', '-m', 'pip', '--isolated', '--disable-pip-version-check',
            'install', '--no-index', '--no-deps', '--no-compile', '--target', str(site), str(wheel)]
    result = subprocess.run(args, capture_output=True, check=False)
    (install_root / 'pip.stdout').write_bytes(result.stdout)
    (install_root / 'pip.stderr').write_bytes(result.stderr)
    result.check_returncode()
    with ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.endswith('.dist-info/RECORD'):
                continue
            need((site / name).read_bytes() == archive.read(name), 'installed_wheel_member_mismatch/' + name)
    sys.path.insert(0, str(site))
    from human_eye_plugin import blender_process, live_spatial_mcp
    from human_eye_plugin import runtime_identity

    ident = runtime_identity.runtime_identity()
    need(ident['source_kind'] == 'installed_distribution' and ident['source_files'] == manifest
         and all(Path(m.__file__).resolve().is_relative_to(site)
                 for m in (runtime_identity, blender_process, live_spatial_mcp)), 'candidate_runtime_mismatch')
    for dep in baseline['dependencies'].values():
        confirm(dep['module'])
    build = install_root / 'BUILD.json'
    save(build, {'candidate_commit': commit, 'parent_commit': parent, 'changed': sorted(changed),
                 'runtime_identity': ident, 'wheel': pin(wheel), 'wheel_builder': pin(build_tool),
                 'wheel_verification': wheel_check, 'admin_plan': plan, 'description': description, 'builds': 1, 'installs': 1, 'Blender_launches': 0})
    save(root / 'preflight/BASELINE_INSTALL_CUSTODY.json', baseline)
    proof = dict(baseline, candidate_commit=commit, source_sha256=ident['source_sha256'],
                 runtime_sources=len(manifest), installation={'path': str(site)},
                 wheel=pin(wheel), build=pin(build), source_manifest=manifest, candidate_installs=1)
    save(root / 'preflight/INSTALL_CUSTODY.json', proof)
    print(f'Installed {commit} with {len(manifest)} verified runtime sources ({ident["source_sha256"]})')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=lambda x: Path(x).resolve(strict=True))
    parser.add_argument('checkout', type=lambda x: Path(x).resolve(strict=True))
    parser.add_argument('candidate')
    parser.add_argument('baseline_custody', type=lambda x: Path(x).resolve(strict=True))
    options = parser.parse_args()
    install(options.root, options.checkout, options.candidate, options.baseline_custody)
