"""Offline audit and concise report from retained real-run bytes only."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
WARM = {'shared_repeat_AB', 'shared_return_AB', 'shared_return_AD', 'shared_return_AB_again',
        'shared_reconnect_repeat', 'ordinary_task_repeat', 'ordinary_nearest_repeat', 'ordinary_task_after_nearest',
        'owned_task_repeat', 'owned_return_AB', 'owned_nearest_repeat', 'owned_task_after_transform_repeat',
        'owned_nearest_after_transform_repeat', 'owned_narrow_repeat'}
WORK = ('to_mesh', 'triangulations', 'resource_builds', 'world_transforms')

def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line]

def json_stream(path):
    content = path.read_bytes().decode('utf8')
    decoder, result, index = json.JSONDecoder(), [], 0
    while index < len(content):
        while index < len(content) and content[index].isspace(): index += 1
        if index == len(content): break
        value, index = decoder.raw_decode(content, index)
        result.append(value)
    return result

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def diff(after, before, keys=WORK):
    return {key: after[key] - before[key] for key in keys}

def main():
    run = Path(sys.argv[1]).resolve()
    evidence = json.loads((run / 'RESULTS.json').read_text(encoding='utf8'))
    assert evidence['passed'] and evidence['record_count'] == 34
    records, groups, previous_host = evidence['records'], {}, {}
    by_label = {r['label']: r for r in records}
    checks = []
    def check(name, value):
        assert value, name
        checks.append(name)
    check('before/after runtime identity exact', (run / 'identity_before.json').read_bytes() == (run / 'identity_after.json').read_bytes())
    for record in records:
        client, metric = record['client'], record['metric']
        group = groups.setdefault(client, {'tool_count': 0, 'tool_stdio_tx_bytes': 0, 'tool_stdio_rx_bytes': 0,
                                           'tool_transport_bytes': Counter(), 'calls': Counter()})
        group['tool_count'] += 1
        group['tool_stdio_tx_bytes'] += record['stdio_tx_bytes']
        group['tool_stdio_rx_bytes'] += record['stdio_rx_bytes']
        group['tool_transport_bytes'].update(metric['transport_bytes'])
        group['calls'].update(metric['calls'])
        check(record['label'] + ' raw metric maps to tool', metric['name'] == record['tool'])
        if record['tool'] != 'human_eye_transform':
            check(record['label'] + ' ledger unchanged', record['ledger_before_sha256'] == record['ledger_after_sha256'])
            check(record['label'] + ' native oracle', record['oracle']['abs_error_m'] < 1e-7)
        if 'host_after' in record:
            check(record['label'] + ' exactly one resident host', len(record['host_after']) == 1)
            current = record['host_after'][0]['stats']
            before = record['host_before'][0]['stats'] if record['host_before'] else None
        else:
            snapshots = [row for row in record['owned_worker_events'] if row['event'] == 'worker_snapshot']
            check(record['label'] + ' actual owned host snapshot', bool(snapshots))
            current, before = snapshots[-1]['work'], previous_host.get(client)
        record['audit_host_after'] = current
        record['audit_host_increment'] = diff(current, before) if before else None
        previous_host[client] = current
        if record['label'] in WARM:
            check(record['label'] + ' zero resident work', diff(current, before) == dict.fromkeys(WORK, 0))
            check(record['label'] + ' zero decoder transforms', metric['decoder_before'] == metric['decoder_after'])
            suffixes = (':_validated_scene', ':from_dict', ':task_result', ':classify_closed_solids',
                        ':measure_surface_proximity', ':measure_pair_geometry', ':_rank_surface_results')
            check(record['label'] + ' zero normalization/solver/rank', not any(n and key.endswith(suffixes) for key, n in metric['calls'].items()))
    for client, group in groups.items():
        folder = run / client
        tx, rx = json_stream(folder / 'stdio_tx.bin'), json_stream(folder / 'stdio_rx.bin')
        check(client + ' complete stdio envelopes pair', [r['id'] for r in tx] == [r['id'] for r in rx])
        group['whole_session_stdio_tx_bytes'] = (folder / 'stdio_tx.bin').stat().st_size
        group['whole_session_stdio_rx_bytes'] = (folder / 'stdio_rx.bin').stat().st_size
        group['stdio_request_count'] = len(tx)
        check(client + ' initialization/list outside tool sums', len(tx) == group['tool_count'] + 2)
        group['whole_session_transport_bytes'] = {p.name: p.stat().st_size for p in folder.glob('*_*.bin') if not p.name.startswith('stdio_')}
        for name, count in group['tool_transport_bytes'].items():
            check(client + ' actual transport byte accounting ' + name, count <= group['whole_session_transport_bytes'][name])
        group['non_tool_transport_bytes'] = {name: count - group['tool_transport_bytes'].get(name, 0)
                                             for name, count in group['whole_session_transport_bytes'].items()}
        check(client + ' clean stdio exit', json.loads((folder / 'exit.json').read_text())['returncode'] == 0)
        if client.startswith('shared'):
            requests, responses = json_stream(folder / 'mcp_tx.bin'), json_stream(folder / 'mcp_rx.bin')
            check(client + ' raw socket request/response count', len(requests) == len(responses) == group['tool_count'])
            packets = []
            for request, response in zip(requests, responses):
                code = request['params']['code']
                prefix = '_request = _json.loads('
                literal = next(line[len(prefix):-1] for line in code.splitlines() if line.startswith(prefix))
                inner_request = json.loads(ast.literal_eval(literal))
                value = response['result']['result']
                assert value.startswith('HUMAN_EYE_BLENDER_MCP:')
                packet = json.loads(value[len('HUMAN_EYE_BLENDER_MCP:'):])['result']
                packets.append({'command': inner_request['command'], 'resource_count': len(packet['resources']),
                                'schema': packet['schema']})
            group['raw_socket_packets'] = packets
        else:
            requests = json_stream(folder / 'owned_tx.bin')
            raw = (folder / 'owned_rx.bin').read_bytes()
            responses = [json.loads(line[len(b'HUMAN_EYE_RPC:'):]) for line in raw.splitlines() if line.startswith(b'HUMAN_EYE_RPC:')]
            check(client + ' owned raw request/response IDs', [r['id'] for r in requests] == [r['id'] for r in responses])
            group['owned_commands'] = dict(Counter(r['command'] for r in requests))
            observer = rows(folder / 'worker_observer.jsonl')
            attached = [row for row in observer if row['event'] == 'observer_attached']
            check(client + ' observer fixed host module', len(attached) == 1 and attached[0]['host_module'] == 'human_eye_blender_host_worker')
            group['owned_worker_pid'] = attached[0]['pid']
            group['c_call_calibration'] = {'supported': False,
                'evidence': 'cold actual resident to_mesh=2 but no RNA to_mesh c_call events were emitted',
                'full_capture_to_mesh': None, 'full_capture_triangulation': None, 'full_capture_world_maps': None}
            launches = [row for row in rows(folder / 'metrics.jsonl') if row['event'] == 'default_worker_launch']
            check(client + ' no worker override', len(launches) == 1 and launches[0]['worker_path_override'] is False)
        group['tool_transport_bytes'] = dict(group['tool_transport_bytes'])
        group['calls'] = dict(group['calls'])
    def token(label):
        values = {json.dumps(row['capture_state'], sort_keys=True) for row in by_label[label]['metric']['capture_states']}
        check(label + ' captured token despite multiple function levels', len(values) == 1)
        return json.loads(values.pop())
    for left, right in (('shared_cold_AB', 'shared_repeat_AB'), ('shared_cold_AB', 'shared_return_AB'),
                        ('shared_switch_AD', 'shared_return_AD'), ('owned_task_cold', 'owned_return_AB')):
        check(left + '/' + right + ' stable token', token(left) == token(right))
    for left, right in (('shared_return_AB_again', 'shared_metadata_color'), ('shared_metadata_color', 'shared_pose'),
                        ('shared_pose', 'shared_geometry'), ('owned_task_cold', 'owned_task_after_transform')):
        check(left + '/' + right + ' invalidated revision', token(right)['revision'] > token(left)['revision'])
    check('shared reconnect retains resident instance', token('shared_units_epoch') == token('shared_reconnect_cold'))
    epochs = [token(label)['epoch'] for label in ('shared_units_epoch', 'shared_scene_lifecycle', 'shared_load_lifecycle')]
    check('scene/load lifecycle increments epoch', epochs == [1, 2, 3])
    check('metadata zero extraction/maps', by_label['shared_metadata_color']['audit_host_increment'] == dict.fromkeys(WORK, 0))
    check('pose one map zero extraction', by_label['shared_pose']['audit_host_increment'] == dict(to_mesh=0, triangulations=0, resource_builds=0, world_transforms=1))
    check('mesh one extraction/map', by_label['shared_geometry']['audit_host_increment'] == dict.fromkeys(WORK, 1))
    check('fixture exact file bytes unchanged', evidence['generated_fixture_before_sha256'] == evidence['generated_fixture_after_sha256'] == evidence['owned_fixture_copy_after_sha256'])
    cleanup = json.loads((run / 'process_check_02.json').read_text(encoding='utf-8-sig'))
    check('own Blender PIDs/commandline absent', cleanup['matching_count'] == 0 and set(cleanup['owned_worker_pids']) == {groups['owned_ordinary']['owned_worker_pid'], groups['owned_narrow']['owned_worker_pid']})
    selected = []
    for record in records:
        selected.append({'label': record['label'], 'full_tool_rtt_ms': record['full_tool_rtt_ms'],
                         'dispatch_content_ms': record['metric']['dispatch_content_ms'],
                         'stdio_tx_bytes': record['stdio_tx_bytes'], 'stdio_rx_bytes': record['stdio_rx_bytes'],
                         'transport_bytes': record['metric']['transport_bytes'],
                         'resident_work_after': record['audit_host_after'], 'resident_work_increment': record['audit_host_increment'],
                         'decoder_before': record['metric']['decoder_before'], 'decoder_after': record['metric']['decoder_after'],
                         'calls': record['metric']['calls'], 'oracle': record.get('oracle')})
    summary = {'passed': True, 'audit_checks': len(checks), 'checks': checks,
               'common_commit': evidence['common_commit'], 'runtime_source_sha256': evidence['runtime_source_sha256'],
               'real_tool_requests': len(records), 'warm_requests': len(WARM), 'warm_labels': sorted(WARM),
               'max_native_oracle_abs_error_m': max(r['oracle']['abs_error_m'] for r in records if 'oracle' in r),
               'complete_command_ms': evidence['complete_command_ms'], 'groups': groups, 'tools': selected,
               'generated_fixture_sha256': evidence['generated_fixture_before_sha256'],
               'cleanup': cleanup, 'shared_fixture_termination_returncode': evidence['shared_fixture_process_exit'],
               'shared_fixture_pid': None,
               'limitations': ['One instrumented real sequence; no benchmark statistics or timing target qualification',
                   'Observer overhead is included and unquantified, not subtracted',
                   'Cold owned resident counters are actual cumulative values; pre-first-capture host stats not recorded',
                   'RNA to_mesh does not emit the selected c_call event; full action to_mesh/triangulation/world-map work unknown',
                   'Resident counters only cover resident capture; resources=[] was never used to infer extraction counts',
                   'Shared fixture PID was not recorded; Popen.terminate+wait returned 1 and scoped post-run process check is empty',
                   'Native oracle is direct RNA for the generated no-modifier fixture and its axis support intervals, not a general mesh-distance oracle',
                   'Frame/units labels contain epoch historically, but these changes advance revision; only scene/load changes advance epoch']}
    (run / 'SUMMARY.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    lines = [f"34/34 real tool requests passed on `{evidence['common_commit']}` (133-source SHA `{evidence['runtime_source_sha256']}`).",
             '', f"The offline audit passed {len(checks)} checks. Shared: 21 tools; default owned ordinary: 11; default owned narrow: 2. All five stdio sessions exited 0. The shared fixture server was explicitly terminated and waited, returning 1. Owned worker PIDs 31840/19704 and the scoped fixture command line are absent in `process_check_02.json`. The shared fixture PID was not recorded.",
             '', 'The 14 repeated/return requests had zero normalization, Mesh construction, task solver, geometry kernel and ranking calls, with zero additional resident to_mesh/triangulation/resource builds/world maps and zero decoder world maps. Each still performed a real capture request and decoder application. AB→AD built one new resource; returning to either selection reused both layers. Metadata color advanced revision with zero geometry work; pose remapped one object without to_mesh; the vertex edit rebuilt one resource and remapped one object. Scene and file load advanced epoch 1→2→3. Frame/units advanced revision, despite the historical record labels ending in `_epoch`.',
             '', 'Shared execution used the real production launcher in narrow and ordinary modes. Owned execution composed the default BlenderProcessHost, LiveSpatialService and stdio API, keeping the verified default worker expression and adding a validation-only observer before it. A real transform returned verified; following task/nearest reads kept the action ledger byte-identical. The initial shared opaque ledger also remained byte-identical. Model tool results contained no internal capture token, resource references or delta payloads.',
             '', f"Independent direct Blender RNA world-coordinate oracles agreed on all 33 reads; maximum absolute distance error was {summary['max_native_oracle_abs_error_m']:.12g} m. This oracle is exact for the generated plain fixture faces and the edited bottom corner. Both generated blend files stayed byte-identical at SHA `{summary['generated_fixture_sha256']}`; no user asset was opened. Product source manifests were checked before and after, byte-for-byte equal.",
             '', 'Representative observed costs (one sequence, including observer overhead):', '',
             '| Request | Full stdio RTT ms | Stdio TX/RX B | MCP or owned TX/RX B |',
             '|---|---:|---:|---:|']
    representatives = ['shared_cold_AB', 'shared_repeat_AB', 'shared_switch_AD', 'shared_return_AB', 'shared_metadata_color',
                       'shared_pose', 'shared_geometry', 'ordinary_nearest_cold', 'ordinary_nearest_repeat',
                       'owned_task_cold', 'owned_task_repeat', 'owned_return_AB', 'owned_real_transform',
                       'owned_task_after_transform', 'owned_nearest_after_transform_repeat', 'owned_narrow_repeat']
    for label in representatives:
        r = by_label[label]; transport = r['metric']['transport_bytes']; prefix = 'mcp' if r['client'].startswith('shared') else 'owned'
        lines.append(f"| {label} | {r['full_tool_rtt_ms']:.3f} | {r['stdio_tx_bytes']}/{r['stdio_rx_bytes']} | {transport[prefix+'_tx.bin']}/{transport[prefix+'_rx.bin']} |")
    lines += ['', 'Tool-only bytes and whole-session bytes are distinct domains. Whole sessions include initialize/tools-list, plus owned capabilities, shutdown and Blender stdout banners. Socket and pipe data are copied as actual bytes; owned pipe copies occur below UTF-8 decoding and universal newline conversion. These nested stdio and host byte counts must not be added as a single payload cost.', '',
              '| Session | Tools | Tool stdio TX/RX B | Whole stdio TX/RX B | Tool host TX/RX B | Whole host TX/RX B |',
              '|---|---:|---:|---:|---:|---:|']
    for client, g in groups.items():
        prefix = 'mcp' if client.startswith('shared') else 'owned'; t=g['tool_transport_bytes']; w=g['whole_session_transport_bytes']
        lines.append(f"| {client} | {g['tool_count']} | {g['tool_stdio_tx_bytes']}/{g['tool_stdio_rx_bytes']} | {g['whole_session_stdio_tx_bytes']}/{g['whole_session_stdio_rx_bytes']} | {t[prefix+'_tx.bin']}/{t[prefix+'_rx.bin']} | {w[prefix+'_tx.bin']}/{w[prefix+'_rx.bin']} |")
    lines += ['', 'The full command took 8.607 seconds. Per-tool full RTT runs from before stdin write through receiving the complete stdout line; child dispatch/content timing excludes final JSON encoding and stdout publication. Python profiling, byte copies/appends, metrics and independent worker RNA snapshots add unquantified overhead, which is included and not subtracted. This is a correctness and work-reuse observation, not a benchmark or performance target claim.',
              '', 'The actual residency counters are retained for every tool. The optional C-call probe did not receive Blender RNA to_mesh events (cold residency reported 2 extractions while C-call events were empty), so it failed calibration. Full capture work inside the owned action, including to_mesh, triangulation and world mapping, remains **unknown**. Resident action counts are narrower and must not be presented as total host work. No zero-work conclusion came from an empty delta resource list.',
              '', 'Raw stdin/stdout, socket/owned pipes, observer events, startup source identity, tool metrics, controls, native snapshots and exact executing harness source snapshots are retained under `actual_run_01/`. The earlier fake-RNA failed run and corrected run remain untouched. No real retry was needed.',
              '', 'Artifacts: `actual_run_01/RESULTS.json`, `actual_run_01/SUMMARY.json`, `actual_run_01.log`, `actual_run_01/process_check_02.json`.']
    (HERE / 'ACTUAL_REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf8')
    print(json.dumps({'passed': True, 'checks': len(checks), 'tools': len(records), 'warm': len(WARM),
                      'max_error_m': summary['max_native_oracle_abs_error_m']}, indent=2))

if __name__ == '__main__': main()
