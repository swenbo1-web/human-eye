"""Audit sealed saved evidence without launching consumers or product code."""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
ROOT = BATCH.parents[1]
ADMIN_ROOT = Path('D:/hefe')
SEAL_PATH = ADMIN_ROOT / 'verification/fixes/20261112_m4_spatial_fact_consumption_review/QUALITY_SEAL.json'
SEAL_SHA = 'fa467d121359d8ffff45693887de2598f1d34a811bf031849215042ef0e44852'
ROOT_COMMIT = '3a4b090532e01920110e6ee2be1702bc1c45c265'
AUTHOR_COMMIT = '5cdf62f311f94890ca569d06c1a858f1578225e4'
PACKET_SHA = 'efc074849f20b15f6ad1702467c765dbb576f5846b68e7a00754c776abd1fb9f'
SOURCE_SHA = '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390'
SOURCE_COMMIT = 'e836e03f4b3821f869c72ac3e50df5204f28b50f'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf8')


def wire(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf8') + b'\n'


class Audit:
    def __init__(self):
        self.inputs = {}
        self.checks = []

    def raw(self, path):
        path = Path(path).resolve()
        raw = path.read_bytes()
        before = self.inputs.setdefault(str(path), digest(raw))
        if before != digest(raw):
            raise ValueError('input changed during audit ' + str(path))
        return raw

    def read(self, path):
        return json.loads(self.raw(path))

    def check(self, name, passed):
        self.checks.append({'name': name, 'passed': bool(passed)})

    def git_blob(self, commit, relative):
        result = subprocess.run(['git', '-C', str(ROOT), 'cat-file', 'blob', commit + ':' + relative],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return result.stdout

    def git_commit(self, commit):
        result = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', commit + '^{commit}'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return result.stdout.decode('ascii').strip()


def geometry(value):
    return {'unit': value.get('unit_scale_m', value.get('scale_length')),
            'objects': sorted([{'name': row['name'], 'vertices_local': row['vertices_local'],
                'matrix_world': row['matrix_world'], 'faces': row.get('faces', row.get('triangles'))}
                for row in value['objects']], key=lambda row: row['name'])}


def project_request(value):
    result = {key: item for key, item in value.items() if key not in ('id', 'jsonrpc', '_meta')}
    if isinstance(result.get('params'), dict):
        result['params'] = {key: item for key, item in result['params'].items() if key != '_meta'}
    return result


def project_response(value):
    return {key: item for key, item in value.items() if key not in ('id', 'jsonrpc', '_meta')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', default='RESULTS.json')
    parser.add_argument('--report', default='REPORT.md')
    args = parser.parse_args()
    assert all(Path(name).name == name and name not in ('.', '..') for name in (args.result, args.report))
    assert not (HERE / args.result).exists() and not (HERE / args.report).exists()
    audit = Audit()
    seal_raw = audit.raw(SEAL_PATH)
    audit.check('quality_seal_exact_sha', digest(seal_raw) == SEAL_SHA)
    seal = json.loads(seal_raw)
    audit.check('root_and_author_commit_identity', audit.git_commit(ROOT_COMMIT) == ROOT_COMMIT
                and audit.git_commit(AUTHOR_COMMIT) == AUTHOR_COMMIT)
    seal_relative = SEAL_PATH.relative_to(ADMIN_ROOT).as_posix()
    audit.check('quality_seal_committed_root_bytes', audit.git_blob(ROOT_COMMIT, seal_relative) == seal_raw)
    audit.check('seal_author_public_plan_binding', seal['author_evidence_commit'] == AUTHOR_COMMIT
                and seal['public_packet_sha256'] == PACKET_SHA
                and seal['root_and_independent_scorer_agree'] is True
                and seal['private_map_cost_usage_read_before_seal'] is False)
    audit.check('seal_file_manifest_hash', digest(canonical(seal['files'])) == seal['file_manifest_sha256'])
    sealed_files = []
    for item in seal['files']:
        raw = audit.raw(ADMIN_ROOT / item['path'])
        sealed_files.append(len(raw) == item['bytes'] and digest(raw) == item['sha256']
                            and audit.git_blob(ROOT_COMMIT, item['path']) == raw)
    audit.check('all_sealed_quality_files_match_disk_and_commit', all(sealed_files))

    plan = audit.read(BATCH / 'PLAN.json')
    freeze = audit.read(BATCH / 'FREEZE.json')
    go = audit.read(BATCH / 'GO.json')
    plan_sha = digest(audit.raw(BATCH / 'PLAN.json'))
    audit.check('frozen_authorized_plan', plan_sha == freeze['plan_sha256'] == go['plan_sha256']
                and go['max_consumers'] == 6 and go['authorized'] is True)
    audit.check('fixed_root_plan', digest(audit.raw(BATCH / 'ROOT_PLAN.md')) == seal['root_plan_sha256']
                == plan['root_plan_sha256'])
    audit.check('dispatch_inputs_unchanged', all(digest(audit.raw(BATCH / name)) == expected
                for name, expected in plan['dispatch_input_sha256'].items()))
    audit.check('external_inputs_unchanged', all(digest(audit.raw(Path(name))) == expected
                for name, expected in plan['external_input_sha256'].items()))
    ready = plan['installation_ready']
    binding = audit.read(Path(ready['release']) / 'admin/RUNTIME_BINDING.json')
    files = binding['source_files']
    source_identity = {'base_version': binding['identity']['base_version'],
        'implementation_revision': binding['identity']['implementation_revision'], 'files': files}
    source_raw = json.dumps(source_identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf8')
    audit.check('same_137_source_identity', len(files) == 137 and digest(source_raw) == SOURCE_SHA
                == plan['candidate_source_sha256'] and ready['commit'] == SOURCE_COMMIT)
    audit.check('worktree_and_installation_source_bytes', all(digest(audit.raw(ROOT / item['path']))
                == item['sha256'] == digest(audit.raw(Path(ready['install_root']) / item['path'])) for item in files))
    protected = audit.read(BATCH / 'preflight/PROTECTED_BEFORE.json')
    audit.check('original_protected_inputs', all((digest(audit.raw(Path(name))) if Path(name).is_file() else None)
                == expected for name, expected in protected.items()))

    base = ROOT / 'verification/native_plugin_complex_003/actor.py'
    tree = ast.parse(audit.raw(base))
    native_schema = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'NATIVE' for target in node.targets)))
    previous = ROOT / 'verification/m3_sufficient_separation_001/entry/run_01'
    observe_schema = [tool for tool in audit.read(previous / 'TOOLS.json')['result']['tools']
                      if tool['name'] == 'human_eye_scene_observe']
    audit.check('full_common_native_and_ordinary_schema', len(observe_schema) == 1
                and audit.read(BATCH / 'schemas/COMMON_NATIVE.json') == native_schema
                and audit.read(BATCH / 'schemas/N_CONSUMER_TOOLS.json') == [native_schema]
                and audit.read(BATCH / 'schemas/P_CONSUMER_TOOLS.json') == [native_schema, observe_schema[0]]
                and audit.read(BATCH / 'schemas/P_PUBLIC_TOOLS.json') == observe_schema)
    configuration = audit.read(BATCH / 'preflight/CONSUMER_CONFIGURATION.json')
    audit.check('frozen_model_and_isolation_settings', configuration['settings']['model'] == 'gpt-6.1-sol'
                and configuration['settings']['model_reasoning_effort'] == 'medium'
                and configuration['settings']['forced_login_method'] == 'chatgpt'
                and configuration['settings']['project_doc_max_bytes'] == 0
                and all(configuration['settings'][name] is False for name in ('features.hooks',
                    'features.memories', 'memories.use_memories', 'features.apps', 'features.plugins',
                    'features.multi_agent', 'features.multi_agent_v2', 'skills.bundled.enabled',
                    'skills.include_instructions', 'features.shell_tool', 'features.view_image')))
    asset_sha = plan['inputs']['scene_sha256']
    expected_geometry = geometry(audit.read(BATCH / 'scoring/ACTUAL_SNAPSHOT.json'))
    audit.check('exact_prior_actual_asset_and_snapshot', digest(audit.raw(BATCH / plan['inputs']['scene']))
                == digest(audit.raw(previous / 'native/input.blend')) == asset_sha
                and digest(audit.raw(BATCH / 'scoring/ACTUAL_SNAPSHOT.json'))
                == digest(audit.raw(previous / 'ACTUAL_SNAPSHOT.json')))

    handoff = BATCH / 'runtime/handoff_01'
    public, private = handoff / 'public', handoff / 'private'
    provenance = audit.read(private / 'PROVENANCE.json')
    mapping = audit.read(BATCH / 'private/ANON_MAP.json')
    run = audit.read(BATCH / 'RUN_RESULT.json')
    records = run['records']
    audit.check('same_six_no_retry_or_replacement', len(records) == 6 and run['stop'] is None
                and run['no_replacements'] is True and run['all_planned_dispatched'] is True
                and all(all(row[key] == slot[key] for key in ('cell', 'task', 'round', 'group'))
                    for row, slot in zip(records, plan['sequence'], strict=True)))
    audit.check('private_mapping_frozen_and_consistent', digest(audit.raw(BATCH / 'private/ANON_MAP.json'))
                == plan['private_anonymous_map_sha256'] and mapping == provenance['fixed_anonymous_map']
                and len(mapping['rows']) == 6 and len({row['anonymous_id'] for row in mapping['rows']}) == 6)
    anchors = ('PLAN.json', 'FREEZE.json', 'GO.json', 'RUN_RESULT.json', 'PUBLIC_PACKET_MANIFEST.json',
               'runtime/handoff_01/private/PROVENANCE.json', 'private/ANON_MAP.json')
    audit.check('author_evidence_commit_anchors', all(audit.git_blob(AUTHOR_COMMIT,
                'verification/m4_spatial_fact_consumption_001/' + name) == audit.raw(BATCH / name) for name in anchors))
    audit.check('provenance_control_source_bytes', all(digest(audit.raw(BATCH / name)) == expected
                == digest(audit.raw(private / 'control' / name)) for name, expected in provenance['control_sha256'].items()))
    public_files = {path.relative_to(public).as_posix(): path for path in public.rglob('*') if path.is_file()}
    file_list = [{'path': name, 'bytes': path.stat().st_size, 'sha256': digest(audit.raw(path))}
                 for name, path in sorted(public_files.items())]
    audit.check('sealed_public_packet_digest', digest(canonical(file_list)) == PACKET_SHA)
    audit.check('provenance_public_complete_hashes', {name: digest(audit.raw(path)) for name, path in public_files.items()}
                == provenance['public_files_sha256'])
    index = audit.read(public / 'INDEX.json')
    audit.check('public_fixed_six_no_rescoring', len(index['answers']) == index['fixed_slots'] == 6
                and index['scoring_performed'] is False)
    provenance_by_cell = {row['mapping']['cell']: row for row in provenance['answers']}
    index_by_id = {row['anonymous_id']: row for row in index['answers']}
    cells = []
    for row in records:
        folder = BATCH / 'cells' / row['cell']
        detail = provenance_by_cell[row['cell']]
        anonymous_id = detail['mapping']['anonymous_id']
        original_files = {path.relative_to(folder).as_posix(): digest(audit.raw(path))
                          for path in folder.rglob('*') if path.is_file()}
        audit.check(row['cell'] + '_all_original_files_retained', original_files == detail['source_files_sha256'])
        archive = private / 'raw' / (anonymous_id + '.zip')
        audit.raw(archive)
        with zipfile.ZipFile(archive) as stream:
            archived = {name: digest(stream.read(name)) for name in stream.namelist()}
        audit.check(row['cell'] + '_archive_exact_complete_originals', archived == original_files)
        consumer = audit.read(folder / 'CONSUMER.json')
        finish = audit.read(folder / 'OWNER_FINISH.json')
        close = audit.read(folder / 'owner/CLOSE.json')
        native = close['native_close']
        closed = close['worker_closed']
        config = audit.read(folder / 'ACTOR_CONFIG.json')
        native_config = audit.read(folder / 'owner/native/CONFIG.json')
        audit.check(row['cell'] + '_source_config_initial_final_binding', row['consumer'] == consumer
            and row['finish'] == finish and finish['close'] == close and config['asset_sha256'] == asset_sha
            and digest(audit.raw(folder / 'owner/native/input.blend')) == asset_sha
            and native_config['deadline_ns'] == config['worker_deadline_ns'] == row['worker_deadline_ns']
            and geometry(audit.read(folder / 'owner/INITIAL.json')) == expected_geometry
            == geometry(audit.read(folder / 'owner/FINAL.json')) and close['geometry_unchanged'] is True
            and close['asset_unchanged'] is True and native['source_file_unchanged'] is True
            and native['protected_files_unchanged'] is True)
        runtime_exit = close['product_runtime_exit']
        exit_confirmed = runtime_exit is None or (runtime_exit['confirmed'] is True and runtime_exit['exited'] is True
            and runtime_exit['exit_code'] == 0 and runtime_exit['handle_closed'] is True)
        audit.check(row['cell'] + '_actual_owned_process_exit', consumer['process_reaped'] is True
            and consumer['readers_stopped'] is True and consumer['exit_code'] == 0 and finish['confirmed'] is True
            and close['confirmed'] is True and native['process_reaped'] is True and native['exit_code'] == 0
            and closed['poisoned'] is False and exit_confirmed and not close['errors'])
        audit.check(row['cell'] + '_zero_images_and_protocol', consumer['input_image_count'] == consumer['public_image_count'] == 0
            and '--image' not in consumer['argv'] and close['zero_new_images_budget_met'] is True
            and close['image_construction']['status'] == 'not_observed_in_recorded_scope'
            and consumer['safe_to_continue'] is True and not consumer['bridge_protocol_errors']
            and not consumer['unexpected_tool_deviations'] and not consumer['mutation_unknown']
            and consumer['bridge_cleanup']['confirmed'] is not False)
        product_rpc = folder / 'owner/plugin/RPC.json'
        if product_rpc.exists():
            audit.check(row['cell'] + '_actual_product_channel_and_identity', audit.read(product_rpc)['poisoned'] is False
                and row['product_channel_poisoned'] is False
                and audit.read(folder / 'owner/PRODUCT_RUNTIME_PROOF.json')['confirmed'] is True
                and audit.read(folder / 'owner/PLUGIN_INITIALIZE.json')['result']['_meta']['human_eye']['source_sha256'] == SOURCE_SHA)
        tools = audit.read(folder / 'owner/TOOLS.json')
        attempts = tools['tools']
        directories = sorted(folder.glob('owner/tool_*'), key=lambda path: int(path.name.split('_')[1]))
        public_evidence = audit.read(public / anonymous_id / 'tool_evidence.json')
        audit.check(row['cell'] + '_all_attempts_present', len(directories) == len(attempts) == tools['attempts']
                    == len(public_evidence['owner_attempts']) and tools['attempts'] <= 32)
        response_bytes = 0
        for number, (directory, attempt, projected) in enumerate(zip(directories, attempts,
                public_evidence['owner_attempts'], strict=True), 1):
            request = audit.read(directory / 'REQUEST.json')
            response_paths = [path for path in (directory / 'RESPONSE.json', directory / 'ERROR_RESPONSE.json') if path.exists()]
            response_bytes += attempt['response_bytes']
            audit.check(row['cell'] + '_attempt_' + str(number) + '_complete_binding',
                audit.read(directory / 'ATTEMPT.json') == attempt and attempt['attempt'] == number
                and request['params']['name'] == attempt['name'] and projected['order'] == number
                and projected['request'] == project_request(request)
                and len(response_paths) == len(projected['responses'])
                and attempt['response_bytes'] == sum(len(wire(audit.read(path))) for path in response_paths)
                and all(audit.read(path).get('id') == request.get('id')
                    and project_response(audit.read(path)) == public_response['value']
                    for path, public_response in zip(response_paths, projected['responses'], strict=True)))
        audit.check(row['cell'] + '_cumulative_response_byte_ledger', response_bytes == tools['wire_tool_bytes']
                    and response_bytes <= 1048576 and native_config['max_calls'] == 128
                    and all(len(audit.raw(path)) <= 262144 for path in folder.glob('owner/native/call_*/SCRIPT.py')))
        expected_tools = audit.read(BATCH / 'schemas' / (row['group'] + '_CONSUMER_TOOLS.json'))
        lists = []
        for path in folder.glob('attachments/bridge_*/*/TX.bin'):
            request = audit.read(path)
            if request.get('method') == 'tools/list':
                lists.append(audit.read(path.with_name('RX.bin'))['result']['tools'] == expected_tools)
        audit.check(row['cell'] + '_actual_full_tool_declaration', bool(lists) and all(lists))
        answer = index_by_id[anonymous_id]
        audit.check(row['cell'] + '_original_answer_bytes_preserved', audit.raw(folder / 'PUBLIC_FINAL.txt')
                    == consumer['final'].encode('utf8') == audit.raw(public / anonymous_id / answer['answer_file']))
        bridge = consumer['bridge_cleanup']
        cells.append({'cell': row['cell'], 'group': row['group'], 'anonymous_id': anonymous_id,
            'actual_owner_exit_confirmed': finish['confirmed'], 'actual_native_exit_confirmed': native['process_reaped'] and native['exit_code'] == 0,
            'actual_product_runtime_exit_confirmed': None if runtime_exit is None else runtime_exit['confirmed'],
            'thin_EXIT_confirmed': bridge['confirmed'], 'thin_EXIT_receipt_status': bridge['receipt_status'],
            'thin_EXIT_missing_count': bridge['missing_exit_count']})
    audit.check('all_original_inputs_stable_through_audit', all(digest(Path(name).read_bytes()) == expected
                for name, expected in audit.inputs.items()))
    result = {'schema': 'm4-unsealed-source-integrity-v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'passed': all(item['passed'] for item in audit.checks), 'checks': audit.checks,
        'seal_sha256': SEAL_SHA, 'root_commit': ROOT_COMMIT, 'author_commit': AUTHOR_COMMIT,
        'plan_sha256': plan_sha, 'public_packet_sha256': PACKET_SHA, 'source_sha256': SOURCE_SHA,
        'source_count': 137, 'cells': cells, 'input_files_sha256': audit.inputs,
        'checker_sha256': digest(Path(__file__).read_bytes()), 'model_calls': 0, 'product_calls': 0,
        'Blender_calls': 0, 'formal_driver_calls': 0, 'Git_operations': 'read-only cat-file and rev-parse',
        'scope': 'saved evidence integrity; accepted sealed quality is not rescored',
        'limitations': ['thin-client EXIT missing remains unknown',
            'native terminal geometry/file protection and PNG/render observation retain their frozen scope',
            'retained runtime handles attest recorded actual process exits; no current PID-reuse inference']}
    with (HERE / args.result).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    failed = [item['name'] for item in audit.checks if not item['passed']]
    unknown = sum(cell['thin_EXIT_confirmed'] is None for cell in cells)
    lines = ['# Independent unsealed source integrity review', '',
        'Passed.' if result['passed'] else 'Failed checks remain.', '',
        'The exact quality seal and every sealed quality file match their committed root bytes. '
        'The author evidence anchors, frozen plan, public packet and private provenance remain bound.', '',
        'The same 137 runtime sources match the worktree and isolated installation. Frozen schemas, '
        'configuration, actual tools/list, assets, initial/final geometry and complete owner attempts match their saved evidence.', '',
        'All six registered owner/native process exits and applicable actual product runtime exits are confirmed. '
        + str(unknown) + ' thin-client EXIT states remain unknown and are preserved separately.', '',
        'Original archives retain every original file. Public projections and original answer bytes match their '
        'source hashes. No model, product, Blender or formal driver execution occurred during this review.', '',
        'Native Python auditing, terminal checks and image observation retain their registered scope. '
        'The saved receipts cannot establish every transient operation or unexposed provider behavior.', '',
        'Quality seal SHA256 `' + SEAL_SHA + '`.', '', 'Public packet SHA256 `' + PACKET_SHA + '`.', '',
        'Checker SHA256 `' + result['checker_sha256'] + '`.', '',
        'Failed checks ' + json.dumps(failed, ensure_ascii=False) + '.', '']
    with (HERE / args.report).open('x', encoding='utf8', newline='\n') as stream:
        stream.write('\n'.join(lines))
    print(json.dumps({'passed': result['passed'], 'checks': len(audit.checks), 'failed': failed,
                      'thin_EXIT_unknown_cells': unknown, 'original_files_modified': 0}))


if __name__ == '__main__':
    main()
