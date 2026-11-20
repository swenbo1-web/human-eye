"""Exercise installed MCP schema and formal-loop imports with zero real slots."""

import argparse
from pathlib import Path
import socket
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DISPLAY, GENERIC_WORKER, HERE, NS, PRIOR, PRODUCT_BINDING, ROOT, SOURCE_SHA, asset_identity, read, save, sha


def main(output):
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned -I -B interpreter required')
    output.mkdir(parents=True, exist_ok=False)
    begin = time.perf_counter_ns()
    binding = read(PRODUCT_BINDING)
    shared_path = NS.parent / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json'
    shared = read(shared_path)
    sys.path[:0] = [str(NS), binding['dependency_root'], shared['dependency_root']]
    from run_slot import diagnostic_plan
    from consumer import consumer_adapter
    from runtime import transport
    from budget import Budget

    originals = []
    with socket.socket() as offline_host:
        offline_host.bind(('127.0.0.1', 0))
        conf = output / 'PRODUCT_CONFIG.json'
        save(conf, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                    'project_root': binding['install_root'], 'state_file': str(output / 'local-state.json'),
                    'audit_file': str(output / 'product_audit.jsonl'), 'request_budget_s': 10,
                    'expected_identity': {'source_sha256': SOURCE_SHA},
                    'blender': {'host': '127.0.0.1', 'port': offline_host.getsockname()[1], 'timeout_s': 1}})
        command = [sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'mcp_entry.py'),
                   '--binding', str(PRODUCT_BINDING), '--config', str(conf), '--ledger', str(output / 'budget'),
                   '--evidence', str(output / 'mcp_io'), '--phase', 'qualification', '--label', 'QP',
                   '--archive', str(output / 'product_full')]
        client = transport.StdioClient(command, output, output / 'mcp', begin + 30_000_000_000)
        try:
            initial = client.call({'jsonrpc': '2.0', 'id': 'preflight-init', 'method': 'initialize',
                'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                           'clientInfo': {'name': 'cross-scale-qualification-preflight', 'version': '1'}}})
            identity = initial['result']['_meta']['human_eye']
            originals.append(('INITIALIZE.json', initial))
            client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            listing = client.call({'jsonrpc': '2.0', 'id': 'preflight-tools', 'method': 'tools/list'})
            originals.append(('INSTALLED_TOOLS.json', listing))
        finally:
            closed = client.finish()
    for name, raw in originals:
        save(output / name, raw)
    actual = [row for row in listing['result']['tools'] if row['name'] == 'human_eye_scene_observe']
    schema = NS / 'inputs/PRODUCT_SCHEMA.json'
    counts = Budget(output / 'budget').snapshot()['counts']
    if (identity['source_kind'] != 'installed_distribution' or identity['source_sha256'] != SOURCE_SHA
            or actual != [read(schema)] or not closed['confirmed'] or closed['exit_code'] != 0
            or list((output / 'product_full').glob('call_*'))
            or any(counts[key] for key in ('Blender_start_attempts', 'all_raster_upper', 'business_admissions',
                                           'consumer_admissions'))):
        raise ValueError('pinned_installed_schema_or_zero_model_schema_preflight_failed')
    _, proof, _ = consumer_adapter()
    _, asset_digest = asset_identity()
    extra = [PRIOR / 'harness' / name for name in ('budget.py', 'owned_runtime.py', 'mcp_entry.py',
            'reused/verified_bootstrap.py', 'frame_device.py', 'device_capture.py')]
    extra.extend(DISPLAY / 'harness/reused' / name for name in ('process_proof.py', 'stdio_checks.py', 'wire_meter.py'))
    extra.extend((GENERIC_WORKER, GENERIC_WORKER.with_name('wire_meter.py'),
                  ROOT / 'verification/m4_target_task_consumption_001/native_consumer_audit.py', shared_path))
    receipt = {'passed': True, 'elapsed_ns': time.perf_counter_ns() - begin, 'schema_sha256': sha(schema),
               'product_identity': identity, 'asset_sha256': asset_digest, 'stdio_close': closed,
               'budget_counts': counts, 'diagnostic_calls_per_arm': {group: len(diagnostic_plan(group)) for group in ('N', 'P')},
               'formal_execution_sources': proof['execution_sources'], 'profile': proof,
               'additional_runtime_sources': [{'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
                                              for path in extra]}
    save(output / 'PREFLIGHT.json', receipt)
    print(output / 'PREFLIGHT.json', sha(output / 'PREFLIGHT.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    main(parser.parse_args().output.resolve())
