"""Static preparation only: saved metadata, byte hashing and one Git blob read.

Never imports the product, executes its Python, launches Codex/Blender, rebuilds
or installs. Original-byte copies may already exist only if still identical.
New reports are exclusive creations; do not overwrite an earlier result.
"""
import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
SCHEMAS = BATCH / 'schemas'
OLD = ROOT / 'verification/m4_observation_baseline_001'
ENGINEERING = ROOT / 'verification/m4_local_relation_evidence_001'
PIN = {
    'P0': ('107641ec19919d56aa843c1949261590fc338148',
        '7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1',
        OLD / 'installation/READY.json', 'baseline_S'),
    'P1': ('e077fce38b5951efff8166b3b688d05ffa2ebf04',
        '53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732',
        ENGINEERING / 'installation/READY.json', 'candidate_S'),
}
sha = lambda raw: hashlib.sha256(raw).hexdigest()
inputs = {}
issues = []
checks = []


def check(value, label):
    checks.append(label)
    if not value:
        issues.append(label)


def blob(path):
    path = Path(path)
    raw = path.read_bytes()
    inputs[str(path)] = sha(raw)
    return raw


def read(path):
    return json.loads(blob(path))


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        check(path.read_bytes() == raw, 'existing_original_copy.' + str(path))
    else:
        with path.open('xb') as stream:
            stream.write(raw)


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def constants(raw, names):
    result = {}
    for node in ast.parse(raw).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names:
            result[node.targets[0].id] = ast.literal_eval(node.value)
    return result


def substitute(text, expression, replacement, flags=re.M):
    result, count = re.subn(expression, lambda match: replacement, text, flags=flags)
    if count != 1:
        raise ValueError('Expected one fixed template substitution: ' + expression)
    return result


def exact_differences(a, b, path='$'):
    if isinstance(a, dict) and isinstance(b, dict):
        return [row for key in sorted(set(a) | set(b)) for row in
            ([{'path': path+'/'+key, 'P0': a.get(key), 'P1': b.get(key)}] if key not in a or key not in b
             else exact_differences(a[key], b[key], path+'/'+key))]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [row for i, (left, right) in enumerate(zip(a, b))
            for row in exact_differences(left, right, path+'/'+str(i))]
    return [] if type(a) is type(b) and a == b else [{'path': path, 'P0': a, 'P1': b}]


def main():
    if (HERE/'IDENTITIES.json').exists() or (SCHEMAS/'SCHEMA_DIFF.json').exists():
        raise FileExistsError('Preserve prior static preparation reports')
    ready, bindings, receipts = {}, {}, {}
    requests, request_keys = [], []
    templates = ('examples/agents/target_runtime_entry.py', 'examples/agents/installed_release.py')
    for role, (commit, expected, source, _) in PIN.items():
        raw = blob(source)
        put(HERE/(role+'_READY.json'), raw)
        ready[role] = json.loads(raw)
        item = ready[role]
        check(item['commit'] == commit and item['source_sha256'] == expected and item['source_count'] == 137,
            role+'.fixed_READY_identity')
        check(item['no_default_activation'] is True, role+'.historical_no_default_activation')
        bindings[role] = read(Path(item['release'])/'admin/RUNTIME_BINDING.json')
        receipts[role] = read(Path(item['receipt']))
        manifest = bindings[role]['source_files']
        check(len(manifest) == len({x['path'] for x in manifest}) == 137, role+'.exact_unique_137_manifest')
        check(manifest == sorted(manifest, key=lambda x: x['path']), role+'.manifest_sorted')
        for path in [x['path'] for x in manifest] + list(templates):
            requests.append((commit+':'+path+'\n').encode('ascii'))
            request_keys.append((role, path))
    # Only this read-only Git plumbing process is launched. No runtime or CLI.
    command = ['git', '-C', str(ROOT), 'cat-file', '--batch']
    process = subprocess.run(command, input=b''.join(requests), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=30, check=False)
    check(process.returncode == 0 and not process.stderr, 'Git_cat_file_read_only_success')
    stream = io.BytesIO(process.stdout)
    git = {}
    for key in request_keys:
        header = stream.readline().decode('ascii').rstrip('\n').split(' ')
        if len(header) != 3 or header[1] != 'blob':
            raise ValueError('Unresolved fixed Git blob: '+repr(key))
        oid, _, size = header
        raw = stream.read(int(size))
        if len(raw) != int(size) or stream.read(1) != b'\n':
            raise ValueError('Truncated Git blob framing')
        check(hashlib.sha1(b'blob '+size.encode()+b'\0'+raw).hexdigest() == oid,
            'Git_blob_object_hash.'+key[0]+'.'+key[1])
        git[key] = (raw, oid)
    check(not stream.read(), 'Git_cat_file_no_unparsed_tail')
    profiles, schemas, schema_sources = {}, {}, {}
    for role, (commit, expected, source, old_case) in PIN.items():
        item, binding, receipt = ready[role], bindings[role], receipts[role]
        install, release = Path(item['install_root']), Path(item['release'])
        manifest = binding['source_files']
        files = []
        for pin in manifest:
            path = pin['path']; raw = blob(install/path); git_raw, oid = git[(role, path)]
            check(sha(raw) == pin['sha256'] and raw == git_raw, role+'.installed_binding_Git.'+path)
            files.append({'path': path, 'sha256': sha(raw), 'bytes': len(raw), 'Git_blob': oid})
        literal = constants(blob(install/'human_eye_plugin/runtime_identity.py'),
            {'BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES'})
        actual_paths = set(literal['_ROOT_MODULES']) | {p.relative_to(install).as_posix()
            for package in ('human_eye_plugin', 'human_eye_module1_operators') for p in (install/package).glob('*.py')}
        check(actual_paths == {x['path'] for x in manifest}, role+'.no_extra_or_missing_runtime_sources')
        canonical = sha(json.dumps({'base_version': literal['BASE_VERSION'],
            'implementation_revision': literal['IMPLEMENTATION_REVISION'], 'files': manifest},
            sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
        check(canonical == expected == binding['identity']['source_sha256'], role+'.recomputed_canonical_source_hash')
        binding_path = release/'admin/RUNTIME_BINDING.json'
        entry_raw = blob(item['entry']); admin_raw = blob(release/'admin/installed_release.py')
        check(sha(blob(binding_path)) == item['binding_sha256'] == receipt['binding_sha256'], role+'.binding_SHA')
        check(sha(entry_raw) == item['launcher_sha256'] == binding['launcher_sha256'] == receipt['launcher_sha256'], role+'.launcher_SHA')
        check(sha(admin_raw) == binding['admin_sha256'] == receipt['admin_sha256'], role+'.admin_SHA')
        check(binding['site_packages'] == str(install) and binding['target_release'] == str(release)
            and binding['dependency_python'] == item['dependency_python'], role+'.binding_actual_paths')
        check(receipt['source_sha256'] == expected and receipt['fixed_commit'] == commit
            and receipt['source_commit_wheel_install_equal'] is True and receipt['isolated_identity_passed'] is True,
            role+'.historical_receipt_identity')
        expected_identity = {key: binding['identity'][key] for key in
            ('base_version', 'implementation_revision', 'source_sha256', 'build_id')}
        expected_identity['distribution_version'] = item['version']
        entry_text = git[(role, templates[0])][0].decode('utf8')
        for key, expression in (('RELEASE_NAME', repr(item['version'])),
                ('DEPENDENCY_PYTHON', 'Path('+repr(item['dependency_python'])+')'), ('SOURCE_SHA256', repr(expected))):
            entry_text = substitute(entry_text, '^'+key+' = .*$', key+' = '+expression)
        entry_text = substitute(entry_text, '^IDENTITY = .*?^ROOT_MODULES',
            'IDENTITY = '+repr(expected_identity)+'\nROOT_MODULES', re.M | re.S)
        entry_text = substitute(entry_text, r'len\(manifest\) != \d+', 'len(manifest) != 137')
        entry_text = substitute(entry_text, r'fixed \d+-file core', 'fixed 137-file core')
        expected_entry = entry_text.encode('utf8')
        expected_admin = substitute(git[(role, templates[1])][0].decode('utf8'),
            '^_TARGET_ENTRY_SHA256 = .*$', '_TARGET_ENTRY_SHA256 = '+repr(sha(expected_entry))).encode('utf8')
        check(entry_raw == expected_entry and admin_raw == expected_admin, role+'.generated_bootstrap_exact_fixed_Git_templates')
        build_path = Path(receipt['bundle'])/'BUILD.json'; build = read(build_path)
        wheels = [x for x in build['artifacts'] if x['file'].endswith('.whl')]
        check(len(wheels) == 1, role+'.one_original_wheel')
        wheel_path = Path(receipt['bundle'])/wheels[0]['file']; wheel_raw = blob(wheel_path)
        check(sha(wheel_raw) == item['wheel_sha256'] == wheels[0]['sha256'], role+'.original_wheel_SHA')
        with zipfile.ZipFile(io.BytesIO(wheel_raw)) as wheel:
            for pin in manifest:
                check(wheel.read(pin['path']) == git[(role,pin['path'])][0], role+'.wheel_Git_installed.'+pin['path'])
        python_path = Path(item['dependency_python']); python_raw = blob(python_path)
        pyvenv = python_path.parent.parent/'pyvenv.cfg'
        python_info = {'path': str(python_path), 'sha256': sha(python_raw), 'bytes': len(python_raw),
            'pyvenv_cfg_sha256': sha(blob(pyvenv)), 'executed_in_this_batch': False,
            'scope': 'Executable and venv config bytes only; not a fresh DLL/dependency import, login, quota or network check.'}
        origin = ENGINEERING/'entry/run_01'/old_case
        schema_raw = blob(origin/'PUBLIC_TOOLS.json'); schemas[role] = json.loads(schema_raw)
        put(SCHEMAS/(role+'_PUBLIC_TOOLS.json'), schema_raw)
        metadata_raw = blob(origin/'ACTUAL_METADATA_INITIALIZE.json'); metadata = json.loads(metadata_raw)['result']['_meta']['human_eye']
        listing_raw = blob(origin/'ACTUAL_METADATA_TOOLS.json'); listing = json.loads(listing_raw)['result']['tools']
        put(SCHEMAS/'original'/(role+'_ACTUAL_METADATA_INITIALIZE.json'), metadata_raw)
        put(SCHEMAS/'original'/(role+'_ACTUAL_METADATA_TOOLS.json'), listing_raw)
        check(listing == schemas[role] and len(listing) == 2
            and [x['name'] for x in listing] == ['human_eye_spatial_relations', 'human_eye_surface_nearest'], role+'.actual_exact_two_tool_directory')
        check(metadata['source_kind'] == 'installed_distribution' and metadata['source_sha256'] == expected
            and metadata['source_file_count'] == 137 and metadata['distribution_version'] == item['version'], role+'.historical_actual_installed_metadata')
        schema_sources[role] = {'source': str(origin/'PUBLIC_TOOLS.json'), 'source_sha256': sha(schema_raw),
            'copy': 'schemas/'+role+'_PUBLIC_TOOLS.json', 'actual_metadata_source': str(origin/'ACTUAL_METADATA_INITIALIZE.json'),
            'actual_metadata_sha256': sha(metadata_raw), 'actual_tools_source': str(origin/'ACTUAL_METADATA_TOOLS.json'),
            'actual_tools_sha256': sha(listing_raw), 'historical_actual_identity': metadata,
            'fresh_metadata_process_launched': False}
        profiles[role] = {'ready': 'installations/'+role+'_READY.json', 'ready_sha256': sha(blob(source)),
            'source_READY': str(source), 'source_sha256': expected, 'source_count': 137, 'commit': commit,
            'version': item['version'], 'entry': item['entry'], 'install_root': item['install_root'],
            'release': item['release'], 'dependency_python': python_info, 'binding_sha256': item['binding_sha256'],
            'launcher_sha256': sha(entry_raw), 'admin_sha256': sha(admin_raw), 'source_manifest': files,
            'schema': 'schemas/'+role+'_PUBLIC_TOOLS.json', 'schema_sha256': sha(schema_raw),
            'installation_receipt_sha256': sha(blob(item['receipt'])), 'original_wheel_sha256': sha(wheel_raw),
            'static_recomputed_source_and_bootstrap_match': True, 'runtime_loaded_identity': 'not newly measured; enforce again at authorized runtime'}
    diff = exact_differences(schemas['P0'], schemas['P1'])
    check([x['path'] for x in diff] == ['$/0/description'], 'schemas.only_reviewed_relations_description_change')
    phrase = 'A supported transverse crossing includes its captured triangles and an approximate boundary location when publishable. '
    check(schemas['P1'][0]['description'].replace(phrase, '', 1) == schemas['P0'][0]['description']
        and schemas['P1'][0]['description'].count(phrase) == 1, 'schemas.exact_reviewed_description_addition')
    common_raw = blob(OLD/'preflight/COMMON_NATIVE.json'); put(SCHEMAS/'COMMON_NATIVE.json', common_raw)
    native_ast = ast.parse(blob(ROOT/'verification/native_plugin_complex_003/actor.py'))
    native = next(ast.literal_eval(x.value) for x in native_ast.body if isinstance(x,ast.Assign)
        and isinstance(x.targets[0],ast.Name) and x.targets[0].id == 'NATIVE')
    check(json.loads(common_raw) == native, 'common_native.literal_matches_original_actor')
    capability_raw = blob(OLD/'runtime/CLI_IMAGE_CAPABILITY.json'); capability = json.loads(capability_raw)
    prepared_raw = blob(OLD/'runtime/PREPARED_INPUT.json'); prepared = json.loads(prepared_raw)
    put(HERE/'original/CLI_IMAGE_CAPABILITY.json', capability_raw)
    put(HERE/'original/PREPARED_INPUT.json', prepared_raw)
    cli_raw = blob(capability['cli_path'])
    check(sha(cli_raw) == capability['cli_sha256'] == '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6', 'CLI.current_file_exact_old_pinned_bytes')
    check(prepared['prompt_sha256'] == sha(blob(OLD/'input/PROMPT.txt')) == 'c443f907474a78ebb2491127d0064ea301d6c4ecbc6d60f1d91adc33fe1f9757', 'common_input.original_prompt_pin')
    check(prepared['initial_image']['sha256'] == sha(blob(prepared['initial_image']['path'])) == '42466e241a4239552fa418b7f79bf1fd73c10092f174c3e87444ed5e93cbed0a', 'common_input.original_image_pin')
    check(profiles['P0']['dependency_python'] == profiles['P1']['dependency_python'], 'both_profiles.same_dependency_executable_bytes')
    for path,digest in inputs.items():
        check(sha(Path(path).read_bytes()) == digest, 'original_unchanged.'+path)
    schema_report = {'cycle_id': 'M4-LOCAL-RELATION-CONSUMPTION-001', 'status': 'PASS' if not issues else 'FAIL',
        'schema_sources': schema_sources, 'exact_differences': diff, 'input_schemas_identical': schemas['P0'][0]['inputSchema'] == schemas['P1'][0]['inputSchema'],
        'nearest_tool_identical': schemas['P0'][1] == schemas['P1'][1], 'COMMON_NATIVE_sha256': sha(common_raw),
        'scope': 'Original-byte saved actual installed compact tool directories; no new metadata process. Difference is the reviewed local-evidence description only.'}
    save(SCHEMAS/'SCHEMA_DIFF.json', schema_report)
    report = {'cycle_id': 'M4-LOCAL-RELATION-CONSUMPTION-001', 'phase': 'PREPARATION_ONLY',
        'status': 'PASS' if not issues else 'FAIL', 'issues': issues, 'checks_total': len(checks),
        'checks_passed': len(checks)-len(issues), 'profiles': profiles,
        'schema_report': 'schemas/SCHEMA_DIFF.json', 'schema_report_sha256': sha((SCHEMAS/'SCHEMA_DIFF.json').read_bytes()),
        'CLI': {'path': capability['cli_path'], 'sha256': sha(cli_raw), 'bytes': len(cli_raw),
            'historical_version': capability['version'], 'historical_auth_mode': capability['auth_mode'],
            'historical_initial_image_flag_supported': capability['initial_image_flag_supported'],
            'current_executable_matches_historical_capability': True, 'CLI_launched_now': False,
            'current_login_quota_provider_network': 'unknown; not checked', 'actual_new_model_image_delivery': 'not_run'},
        'common_native': 'schemas/COMMON_NATIVE.json', 'common_native_sha256': sha(common_raw),
        'input_sha256': inputs, 'verification_script_sha256': sha(Path(__file__).read_bytes()),
        'process_scope': {'read_only_Git_cat_file_processes': 1, 'Codex_CLI_processes': 0, 'product_processes': 0,
            'Blender_sessions': 0, 'model_consumers': 0, 'builds': 0, 'installations': 0, 'default_configuration_changes': 0},
        'unknown_scope': 'This static audit confirms files currently present, not future process availability, dynamic dependency/DLL state, account limits or loaded identity. Authorized runtime must enforce fixed installed identity again.'}
    save(HERE/'IDENTITIES.json', report)
    print(json.dumps({'status': report['status'], 'checks_total': len(checks), 'issues': issues,
        'sources_checked': 274, 'profiles': 2, 'schema_diff_paths': [x['path'] for x in diff],
        'new_runtime_processes': 0, 'output': str(HERE/'IDENTITIES.json')}))
    return 0 if not issues else 1


if __name__ == '__main__':
    raise SystemExit(main())
