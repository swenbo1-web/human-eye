"""Use two isolated installations to replay whole-object measurement on current sealed sources."""

import argparse
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory


sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import AREAS, WINDOWS, check_witness, fixture, pin, read, require, truth

HERE = Path(__file__).resolve().parent
BASE_PRODUCT = '95fd44bb8c4b6b992d8849f38ffbe5d778b0ac5a'
BASE_SOURCE = 'eaccba2ec88abc035c62841a765f99ecae5f50e34dd8e7867b09dc17cb6d9dc9'
TOOL = 'human_eye_scene_observe'


def text_wire(packet):
    return (json.dumps(packet, ensure_ascii=False, allow_nan=False) + '\r\n').encode()


def save_wire(path, data):
    with path.open('xb') as out:
        out.write(data)
    return pin(path)


def configuration(root, binding):
    file = root / 'live.json'
    file.write_bytes(json.dumps({
        'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
        'project_root': binding['install_root'], 'state_file': str(root / 'state.json'),
        'audit_file': str(root / 'audit.jsonl'), 'expected_identity': {'source_sha256': binding['source_sha256']},
        'blender': {'host': '127.0.0.1', 'port': 1, 'timeout_s': 1}, 'request_budget_s': 20,
    }).encode())
    return file


def actual_catalogue(binding, config):
    launcher = ('import sys; sys.path[0:0]=sys.argv[1:3]; '
                'from human_eye_plugin.live_spatial_mcp import main; raise SystemExit(main(sys.argv[3:]))')
    cmd = [sys.executable, '-I', '-B', '-X', 'utf8', '-c', launcher, binding['install_root'],
           binding['dependency_root'], '--config', str(config)]
    tx = [
        {'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize',
         'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                    'clientInfo': {'name': 'm1-pair-distance_entry-list', 'version': '1'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 'catalogue', 'method': 'tools/list'},
    ]
    p = subprocess.run(cmd, input=b''.join(map(text_wire, tx)), capture_output=True, timeout=30)
    require(p.returncode == 0, 'actual_installed_tools_list_failed/' + p.stderr.decode(errors='replace')[-2000:])
    init, listing = [json.loads(line) for line in p.stdout.splitlines()]
    identity = init['result']['_meta']['human_eye']
    require(init['id'] == 'init' and listing['id'] == 'catalogue'
            and identity['source_sha256'] == binding['source_sha256']
            and identity['source_kind'] == 'installed_distribution' and len(listing['result']['tools']) == 5
            and not (config.parent / 'state.json').exists(),
            'real_stdio_catalogue_did_not_boot_actual_installed_product')
    return init, listing, p.stdout


class FullHost:
    def __init__(self, capture):
        self.capture = capture
        self.calls = []
        self.closed = False

    def capture_scene(self):
        self.calls.append('complete_scene_meshes')
        return deepcopy(self.capture)

    def close(self):
        self.closed = True


class SelectedHost(FullHost):
    def __init__(self, capture, selectors):
        super().__init__(capture)
        self.selectors = selectors

    def capture_task_scene(self, selectors):
        require(selectors == self.selectors, 'ordered_selector_does_not_match_current_native_archive')
        self.calls.append('selected_objects')
        return deepcopy(self.capture)

    def capture_scene(self):
        raise ValueError('selected_object_route_bypassed_current_packet')


def request(name, query):
    return {'jsonrpc': '2.0', 'id': name, 'method': 'tools/call', 'params': {
        'name': TOOL, 'arguments': {'include_image': False, 'query': {'mode': 'task', **query},
                                   'response_detail': 'brief'}}}


def task_wire(mcp, service, requests):
    incoming = StringIO(''.join(json.dumps(msg, ensure_ascii=False) + '\n' for msg in requests))
    outgoing = StringIO(newline='\r\n')
    mcp.run_stdio_mcp_server(service, input_stream=incoming, output_stream=outgoing)
    lines = [line.encode('utf8') for line in outgoing.getvalue().splitlines(keepends=True)]
    decoded = [json.loads(line) for line in lines]
    IDs = [row['id'] for row in decoded]
    require(IDs == [row['id'] for row in requests], 'actual_installed_task_stdio_IDs_changed')
    return dict(zip(IDs, decoded, strict=True)), dict(zip(IDs, lines, strict=True))


def body(response):
    text, = response['result']['content']
    require(text['type'] == 'text' and not response['result']['isError'], 'expected_successful_text_only_MCP_result')
    return json.loads(text['text'])


def prove_task(v, fixture_name, source, mcp, service, directory, binding):
    pair = source['case']['pair']
    objects = [{'name': n} for n in pair]
    forward = {
        'ordered': request('ordered', {'objects': objects, 'requested_facts': ['surface_proximity']}),
        'set_spatial': request('set_spatial', {'target': objects[0], 'candidates': objects[1:],
                                               'requested_facts': ['surface_proximity', 'spatial_relation']}),
        'set_closed': request('set_closed', {'target': objects[0], 'candidates': objects[1:],
                                              'requested_facts': ['surface_proximity', 'closed_solid_relation']}),
        'strict': request('strict', {'objects': objects, 'requested_facts': ['nearest_witness']}),
        'ordinary': request('ordinary', {'objects': objects, 'requested_facts': ['aabb']}),
    }
    reverse = request('reverse', {'objects': objects[::-1], 'requested_facts': ['surface_proximity']})
    config = configuration(directory, binding)
    host = SelectedHost(source['selected'], objects)
    selected = service(config, host=host, production_mode=True)
    by_name, lines = task_wire(mcp, selected, list(forward.values()))
    require(host.closed and host.calls == ['selected_objects'] * len(forward), 'read_route_or_stdio_close_changed')
    parent = FullHost(source['parent'])
    full = service(config, host=parent, production_mode=True)
    reversal, reversal_lines = task_wire(mcp, full, [reverse])
    by_name.update(reversal)
    lines.update(reversal_lines)
    require(parent.closed and parent.calls == ['complete_scene_meshes'], 'whole_source_reverse_order_route_changed')
    expected = truth(v, fixture_name, source)
    proofs = {}
    bodies = {key: body(reply) for key, reply in by_name.items()}
    for label in ('ordered', 'reverse', 'set_spatial', 'set_closed'):
        data = bodies[label]
        relational = label.startswith('set_')
        want_scope = 'complete_scene_meshes' if label == 'reverse' else 'selected_objects'
        require(data['result_kind'] == 'task_query' and data['execution_authority'] is False
                and data['unit'] == 'm' and data['coordinate_frame'] == 'world'
                and data['binding']['runtime_source_sha256'] == binding['source_sha256']
                and data['binding'].get('capture_scope', 'complete_scene_meshes') == want_scope
                and [r['name'] for r in data['binding']['objects']] ==
                    (pair[::-1] if label == 'reverse' else pair)
                and data['pair_order'] == ('target_to_candidate' if relational else 'A_to_B'),
                'current_pair_order_capture_or_binding_mismatch/' + label)
        expected_version = 'task-query-set-v2' if label == 'set_spatial' else (
            'task-query-set-v1' if label == 'set_closed' else 'task-query-v3')
        require(data['schema_version'] == expected_version,
                'existing_task_schema_or_facts_changed/' + label)
        facts = data['pairs'][0]['facts'] if relational else data['facts']
        observed = facts['surface_proximity']
        require(observed['status'] == 'measured' and observed['witness_status'] == 'measured'
                and observed['direction_status'] == 'measured', 'positive_surface_witness_not_available')
        value = observed['value']
        if label == 'set_spatial':
            require(observed == source['archive_result']['pairs'][0]['facts']['surface_proximity']
                    and facts['spatial_relation'] == source['archive_result']['pairs'][0]['facts']['spatial_relation']
                    and facts['spatial_relation']['value'] == 'separated', 'replayed_relational_task_changed_old_accepted_facts')
        proofs[label] = {'schema_version': data['schema_version'], 'objects': [x['name'] for x in data['binding']['objects']],
                         'actual_capture_scope': want_scope, 'distance_m': value['distance_m'], **check_witness(
                             value['nearest_witness'], value['distance_m'], expected, source, v, reverse=label == 'reverse')}
        if relational:
            key = label.removeprefix('set_') + ('_relation' if label == 'set_spatial' else '_solid_relation')
            proofs[label]['original_relation_fact'] = facts[key]
    require(set(bodies['ordered']['facts']) == {'surface_proximity'}
            and set(bodies['strict']['facts']) == {'nearest_witness'}
            and set(bodies['ordinary']['facts']) == {'aabb'}
            and all(x['status'] == 'measured' for x in bodies['ordinary']['facts']['aabb']),
            'ordered_scope_or_unrequested_facts_leaked')
    strict = bodies['strict']['facts']['nearest_witness']
    if fixture_name == 'N15':
        require(strict['status'] == 'measured', 'closed_assembly_strict_witness_no_longer_available/' + str(strict))
        checks = check_witness(strict['value'], expected['distance_m'], expected, source, v)
    else:
        require(strict['status'] == 'unknown' and strict['value'] is None
                and strict['reason'] == 'unsupported_solid_geometry', 'open_surface_strict_witness_scope_changed')
        checks = None
    proofs['strict'] = {'strict_fact': strict, 'proof': checks}
    proofs['ordinary'] = {'aabb': bodies['ordinary']['facts']['aabb']}
    return {'denominators': source['case']['counts'], 'archive_legal_attempt': source['archive_legal_attempt'],
            'source_pins': source['pins'] + expected['pins'] + [proofs['ordered']['pin']],
            'truth': expected['independent'], 'proofs': proofs,
            'requested': {**forward, 'reverse': reverse}, 'raw': by_name, 'raw_lines': lines}


def worker(repo, binding_path, stem):
    binding = read(binding_path)
    require(len(binding['source_manifest']) == 143, 'wrong_runtime_source_manifest_count')
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    require(identity['source_sha256'] == binding['source_sha256']
            and identity['source_kind'] == 'installed_distribution'
            and Path(mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),
            'positive_replay_not_installed_product')
    with TemporaryDirectory(prefix='p_', dir=HERE) as name:
        root = Path(name)
        init, catalog, stdout = actual_catalogue(binding, configuration(root, binding))
        receipt = save_wire(stem / 'CATALOGUE_STDOUT.bin', stdout)
        cases = {}
        for label in AREAS:
            folder = root / label
            folder.mkdir()
            source = fixture(repo / 'verification', label)
            record = prove_task(repo / 'verification', label, source, mcp, LiveSpatialService, folder, binding)
            record['raw_pins'] = {key: save_wire(stem / (label + '_' + key + '_RX.bin'), raw)
                                  for key, raw in record.pop('raw_lines').items()}
            cases[label] = record
    output = {'source_sha256': identity['source_sha256'], 'listing': catalog,
              'catalogue_actual_stdout': receipt, 'init_product_identity': init['result']['_meta']['human_eye'],
              'cases': cases}
    sys.stdout.buffer.write(json.dumps(output, ensure_ascii=False, allow_nan=False, default=str).encode('utf8'))


def run_worker(repo, binding, folder):
    folder.mkdir()
    args = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--repo', str(repo),
            '--worker', str(binding), '--wire-dir', str(folder)]
    return json.loads(subprocess.check_output(args, timeout=95))


def normalize(packet):
    parsed = body(packet)
    installed = parsed['binding'].pop('runtime_source_sha256')
    trace = parsed.pop('trace_id')
    require(type(installed) is str and re.fullmatch('[0-9a-f]{64}', installed)
            and type(trace) is str and re.fullmatch('[0-9a-f]{32}', trace), 'actual_install_attestation_or_trace_missing')
    return parsed


def main(repo, baseline, candidate, output, wire_dir):
    require(not wire_dir.exists() and not output.exists(), 'fresh_preflight_output_required')
    declared = read(baseline)
    require(declared['preparation_git'] == BASE_PRODUCT and declared['source_sha256'] == BASE_SOURCE,
            'wrong_fixed_baseline')
    wire_dir.mkdir(parents=True)
    a = run_worker(repo, baseline, wire_dir / 'A')
    report = {'schema': 'm1-pair-distance-entry-installed-positive-v1', 'baseline': pin(baseline),
              'baseline_output': a, 'actual_blender': 0, 'actual_models': 0, 'new_geometry_assets': 0,
              'positive_replay_host_only': 'Read-only archival native captures replace Blender transport.'}
    if candidate is not None:
        b = run_worker(repo, candidate, wire_dir / 'B')
        before, after = deepcopy(a['listing']), deepcopy(b['listing'])
        old_tools, tools = (reply['result']['tools'] for reply in (before, after))
        old_tool, = [x for x in old_tools if x['name'] == TOOL]
        new_tool, = [x for x in tools if x['name'] == TOOL]
        old_description, new_description = old_tool.pop('description'), new_tool.pop('description')
        require(after == before and old_description != new_description and b['source_sha256'] != BASE_SOURCE,
                'actual_tools_list_changed_beyond_observe_description')
        descriptions = {'A': len(old_description.encode()), 'B': len(new_description.encode())}
        for case in AREAS:
            summaries = a['cases'][case], b['cases'][case]
            aa, bb = summaries
            require(aa['requested'] == bb['requested'] and aa['source_pins'] == bb['source_pins']
                    and aa['truth'] == bb['truth'] and aa['proofs'] == bb['proofs'],
                    'actual_pair_proof_or_fixture_changed/' + case)
            for label in aa['raw']:
                require(normalize(aa['raw'][label]) == normalize(bb['raw'][label]),
                        'actual_result_changed_apart_from_installed_identity_and_unique_trace/' + case + '/' + label)
        report.update(candidate=pin(candidate), candidate_output=b, tools_list_diff_only_observe_description=True,
                      unchanged_other_tool_definitions=len(old_tools)-1, description_utf8_bytes=descriptions,
                      catalogue_stdout_bytes={label: arm['catalogue_actual_stdout']['bytes']
                                               for label, arm in [('A', a), ('B', b)]},
                      result_semantic_equality_except_new_runtime_source_fingerprint_and_unique_trace_id=True,
                      acceptance='Engineering controls only. No natural model behavior or time claim.')
    report['passed'] = True
    with output.open('x', encoding='utf8', newline='\n') as sink:
        json.dump(report, sink, ensure_ascii=False, allow_nan=False, indent=2)
        sink.write('\n')
    print(pin(output), flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_Python_requires_-I_-B')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--wire-dir', type=Path, required=True)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    if args.worker:
        worker(repo, args.worker, args.wire_dir)
    else:
        baseline = args.baseline or repo / 'verification' / WINDOWS / 'install/PRODUCT_RUN_BINDING.json'
        if args.output is None:
            parser.error('--output required')
        main(repo, baseline, args.candidate, args.output, args.wire_dir)
