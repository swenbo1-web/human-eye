"""Prove the three actual rejected task-set requests and replay their public contract."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import zipfile


CASES = (
    ('N15_P1', 'd59b954f', 'perf050_readonly_product_pilot_001', 'P1', 4, 'N15', 'N23',
     ['surface_proximity'], None, '4064a22157012db95522501f66cba05f60ee17a34bb3b98ee8e51df8486490bd'),
    ('N15_P3', '11481bd57', 'perf050_source_region_final_image_p3', 'P3', 4, 'N15', 'N23',
     ['surface_proximity'], 'brief', '5b2e2ff21b068936b8ab951be585272d9b871a896d7a0a882dfed020896298c7'),
    ('M09_P2', 'c41b10677', 'perf050_target_observation_first_image_p2', 'P2', 2, 'M09', 'M03',
     ['surface_proximity', 'nearest_witness'], 'full',
     'eaccba2ec88abc035c62841a765f99ecae5f50e34dd8e7867b09dc17cb6d9dc9'),
)
ERROR = 'task set requires surface_proximity with closed_solid_relation or spatial_relation and optional aabb'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(data):
    return sha256(data).hexdigest()


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, allow_nan=False) + '\r\n').encode('utf-8')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


class Archive:
    """Verify both ZIP membership and the exact current original file for each used member."""

    def __init__(self, repo, commit, namespace):
        self.commit = git(repo, 'rev-parse', commit).decode().strip()
        self.index_path = f'verification/{namespace}/RUNTIME_INDEX.json'
        self.index_bytes = git(repo, 'show', f'{self.commit}:{self.index_path}')
        index = json.loads(self.index_bytes)
        self.path = Path(index['archive']['path'])
        self.root = self.path.parent
        raw = self.path.read_bytes()
        self.archive = {'path': str(self.path), 'bytes': len(raw), 'sha256': digest(raw)}
        require(self.archive['bytes'] == index['archive']['bytes']
                and self.archive['sha256'] == index['archive']['sha256'], 'original_archive_hash_or_size_changed')
        self.entries = {row['path']: row for row in index['files']}
        self.zip = zipfile.ZipFile(self.path)
        require(len(self.entries) == index['count'] == len(self.zip.namelist())
                and self.entries.keys() == set(self.zip.namelist()), 'original_archive_membership_changed')
        self.pins = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.zip.close()

    def read(self, member):
        item = self.entries[member]
        data = self.zip.read(member)
        path = self.root / member
        require(digest(data) == item['sha256'] and len(data) == item['bytes']
                and path.read_bytes() == data, 'original_member_bytes_changed:' + member)
        self.pins[member] = {**item, 'absolute_path': str(path)}
        return data

    def json(self, member):
        return json.loads(self.read(member))

    def under(self, prefix, leaf):
        return sorted(name for name in self.entries if name.startswith(prefix) and name.endswith(leaf))


def verify_original(repo, case):
    label, commit, namespace, slot_id, attempt, target, candidate, facts, detail, old_source = case
    with Archive(repo, commit, namespace) as old:
        slot = f'slots/{slot_id}'
        owner = f'{slot}/owner/tool_{attempt:02d}'
        product_receipt = old.json(f'{owner}/PRODUCT_RECEIPT.json')
        receipt = product_receipt['receipt']
        inner = f"{slot}/mcp/rpc_{receipt['index']:02d}"
        inner_tx_raw, inner_rx_raw = (old.read(f'{inner}/{name}.bin') for name in ('TX', 'RX'))
        inner_tx, inner_rx = map(json.loads, (inner_tx_raw, inner_rx_raw))
        actual_args = {'include_image': False, 'query': {
            'mode': 'task', 'target': {'name': target}, 'candidates': [{'name': candidate}],
            'requested_facts': facts}}
        if detail is not None:
            actual_args['response_detail'] = detail
        expect_request = {'name': 'human_eye_scene_observe', 'arguments': actual_args}
        require('producer_archive' not in product_receipt and receipt['error'] is None
                and receipt['RX_sha256'] == digest(inner_rx_raw)
                and receipt['TX_bytes'] == len(inner_tx_raw) and receipt['RX_bytes'] == len(inner_rx_raw)
                and inner_tx == old.json(f'{owner}/PRODUCT_REQUEST.json')
                and inner_rx == old.json(f'{owner}/PRODUCT_RESPONSE.json')
                and inner_tx['id'] == inner_rx['id'] == receipt['id'] == product_receipt['id']
                and inner_tx['params'] == expect_request and inner_tx['method'] == 'tools/call',
                'original_inner_show_rejection_binding_failed')
        result = inner_rx['result']
        one, = result['content']
        body = json.loads(one['text'])
        require(one['type'] == 'text' and result['isError'] is True and body['status'] == 'error'
                and body['error'] == ERROR and body['execution_status'] == 'not_executed'
                and body['executed'] is False and body['host_mutation_started'] is False
                and body['connector_state_write_attempts'] == body['connector_state_write_commits'] == 0,
                'expected_rejection_reason_or_side_effect_receipt_changed')
        caller = old.json(f'{slot}/consumer/BUSINESS_SOURCE_BINDING.json')
        contract, = [row for row in caller['result_contracts'] if row['attempt'] == attempt]
        attached, = [
            rx for rx in old.under(f'{slot}/consumer/attachments/bridge_', '/RX.bin')
            if old.json(rx.replace('/RX.bin', '/RECEIPT.json')).get('attempt') == attempt
        ]
        outer_tx_path = attached.replace('/RX.bin', '/TX.bin')
        outer_tx_raw, outer_rx_raw = old.read(outer_tx_path), old.read(attached)
        outer_tx, outer_rx = map(json.loads, (outer_tx_raw, outer_rx_raw))
        require(contract['matched'] and contract['reason'] == 'content_and_envelope_match'
                and contract['classification'] == 'tool_error' and contract['CLI_images'] == 0
                and digest(outer_tx_raw) == contract['TX_sha256'] and digest(outer_rx_raw) == contract['RX_sha256']
                and outer_tx == old.json(f'{owner}/REQUEST.json') and outer_rx == old.json(f'{owner}/RESPONSE.json')
                and all(outer_tx['params'][key] == value for key, value in expect_request.items())
                and outer_rx['result'] == result and outer_rx['id'] == outer_tx['id'] == contract['caller_identity']['RPC_id'],
                'outer_raw_cli_stdio_do_not_bind_same_rejection')
        tcp_tx_path, = [
            name for name in old.under(f'{slot}/owner/rpc_', '/TCP_TX.bin')
            if old.json(name).get('args', {}).get('attempt') == attempt
        ]
        tcp_rx_path = tcp_tx_path.replace('/TCP_TX.bin', '/TCP_RX.bin')
        tcp_tx, tcp_rx = old.json(tcp_tx_path), old.json(tcp_rx_path)
        require(tcp_tx['operation'] == 'attached_mcp' and tcp_tx['args']['message'] == outer_tx
                and tcp_rx['ok'] and tcp_rx['request_id'] == tcp_tx['request_id'] and tcp_rx['result'] == outer_rx,
                'outer_owner_TCP_wrapper_unbound')
        stdout_path = f'{slot}/consumer/stdout.raw.bin'
        stdout = old.read(stdout_path)
        item_id = contract['caller_identity']['CLI_event_item_id']
        item, = [row['item'] for raw in stdout.splitlines() if raw.strip()
                 for row in [json.loads(raw)] if row.get('type') == 'item.completed'
                 and row.get('item', {}).get('id') == item_id]
        timed, = [row['event']['item'] for raw in old.read(f'{slot}/consumer/events.jsonl').splitlines() if raw.strip()
                  for row in [json.loads(raw)] if row['event'].get('type') == 'item.completed'
                  and row['event'].get('item', {}).get('id') == item_id]
        require(timed == item and item['type'] == 'mcp_tool_call'
                and item['tool'] == expect_request['name'] and item['arguments'] == actual_args
                and item['result']['content'] == result['content']
                and len(one['text'].encode()) == contract['source_text_UTF8_bytes'] == contract['CLI_text_UTF8_bytes'],
                'raw_and_timed_CLI_rejection_unbound')
        slot_result = old.json(f'{slot}/SLOT_RESULT.json')
        publication = old.json(f'{slot}/SLOT_PUBLICATION.json')
        require(slot_result['closure_verification']['passed'] and slot_result['status'] == 'completed'
                and publication['result_sha256'] == old.pins[f'{slot}/SLOT_RESULT.json']['sha256'],
                'archived_slot_closure_or_publication_unbound')
        installed = old.json(f'{slot}/MCP_IDENTITY.json')
        configured = old.json(f'{slot}/PRODUCT_CONFIG.json')['expected_identity']
        require(installed['source_sha256'] == configured['source_sha256'] == old_source,
                'original_runtime_identity_unbound')
        note = {'label': label, 'attempt': attempt, 'historical_evidence_commit': old.commit,
                'runtime_index': old.index_path, 'index_sha256': digest(old.index_bytes), 'raw_archive': old.archive,
                'original_runtime_source_sha256': old_source, 'request': actual_args, 'error_detail': body,
                'inner_request': old.pins[f'{inner}/TX.bin'], 'inner_response': old.pins[f'{inner}/RX.bin'],
                'outer_request': old.pins[outer_tx_path], 'outer_response': old.pins[attached],
                'owner_TCP_request': old.pins[tcp_tx_path], 'owner_TCP_response': old.pins[tcp_rx_path],
                'CLI_item_id': item_id, 'CLI_time_received_ns': contract['CLI_received_ns'],
                'CLI_original_stdout': old.pins[stdout_path],
                'inner_RTT_ns': receipt['elapsed_ns'],
                'outer_provider_visible_RTT_ns': contract['CLI_received_ns'] - contract['receipt']['received_ns'],
                'reply_body_bytes': len(one['text'].encode()), 'images': contract['CLI_images'],
                'source_pins': list(old.pins.values())}
        return note, inner_tx, inner_rx_raw


def worker(install, cases):
    binding = json.loads(install.read_bytes())
    require(len(binding['source_manifest']) == 143, 'wrong_install_source_count')
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    from human_eye_plugin.runtime_identity import runtime_identity

    observed = runtime_identity()
    require(observed['source_kind'] == 'installed_distribution'
            and observed['source_sha256'] == binding['source_sha256'], 'replay_import_not_isolated_install')

    class NoObserve:
        request_budget_s = None
        _request_budget = LiveSpatialService._request_budget
        request_error_fields = staticmethod(LiveSpatialService.request_error_fields)

        def __init__(self):
            self.observe_calls = 0

        def observe(self, *args, **kwargs):
            self.observe_calls += 1
            raise AssertionError('invalid_public_request_reached_service_observation')

    rows = []
    for label, request, expected_digest, expected_size in cases:
        service = NoObserve()
        server = LiveSpatialMCPServer(service, default_session_id='rejects-only-no-host')
        reply = server.handle_jsonrpc_message(deepcopy(request))
        packet = encoded(reply)
        require(service.observe_calls == 0 and len(packet) == expected_size
                and digest(packet) == expected_digest, 'old_rejection_changed_or_reached_service:' + label)
        rows.append({'label': label, 'MCP_replay_response_bytes': len(packet),
                     'MCP_replay_response_sha256': digest(packet), 'observe_calls': service.observe_calls,
                     'exact_original_inner_response': True})
    return {'source_sha256': observed['source_sha256'], 'revision': binding['preparation_git'],
            'source_kind': observed['source_kind'], 'install_binding_sha256': digest(install.read_bytes()),
            'results': rows}


def replay(install, cases):
    result = subprocess.run([sys.executable, '-IB', str(Path(__file__).resolve()), '--worker', str(install.resolve())],
                            input=json.dumps(cases).encode(), capture_output=True, timeout=30, check=True)
    return json.loads(result.stdout)


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'requires_-I_-B')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--install', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker, json.load(sys.stdin)), ensure_ascii=False, allow_nan=False))
        return
    if not all((args.repo, args.install, args.output)):
        parser.error('--repo, --install and --output are required')
    originals, replay_inputs = [], []
    for case in CASES:
        note, request, raw = verify_original(args.repo, case)
        originals.append(note)
        replay_inputs.append([case[0], request, digest(raw), len(raw)])
    baseline = replay(args.install, replay_inputs)
    candidate = replay(args.candidate, replay_inputs) if args.candidate else None
    report = {'schema': 'm1-pair-distance-entry-actual-rejections-v1', 'originals': originals, 'baseline': baseline,
              'candidate': candidate, 'actual_historical_rejections': len(originals), 'observed_Blender_starts': 0,
              'observed_model_starts': 0, 'scope': 'Actual old inner and outer wire, same-request isolated validator '
              'and formatter replay with real error budget fields, no observe or host entry.'}
    with args.output.open('x', encoding='utf-8', newline='\n') as output:
        json.dump(report, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.write('\n')
    print(args.output, digest(args.output.read_bytes()))


if __name__ == '__main__':
    main()
