"""Replay sealed read-only producers through the installed production CLI and stdio."""

import argparse
from contextlib import contextmanager
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
import time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parent
EXTERNAL = Path('D:/he_m1_region_task_first_packet_projection_001')
RETAINED = run_path(str(VERIFICATION / 'm1_region_task_brief_client_profile_001/product_replay.py'))
FORMAL = RETAINED['FORMAL']
fixture, archived, pin, compact = (RETAINED[name] for name in ('fixture', 'archived', 'pin', 'compact'))
TOOL = RETAINED['TOOL']
BAD_PNG_SESSION = 'qualification-corrupt-archived-PNG-digest'
STALE_REGION_SESSION = 'qualification-stale-source-region-reference'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open('xb') as output:
        output.write(compact(value) + b'\n')


def append(path, value):
    with Path(path).open('ab') as output:
        output.write(compact(value) + b'\n')


def fixtures(slot, extras=()):
    records = RETAINED['fixtures'](slot)
    for name, batch, label, ordinal in extras:
        require(name not in records, 'duplicate_archived_replay_control/' + name)
        records[name] = fixture(batch, label, ordinal)
    return records


def requests(slot, extras=()):
    records = fixtures(slot, extras)
    result = RETAINED['requests'](slot)
    for name, _, _, _ in extras:
        result[name] = deepcopy(records[name]['request'])
    discover = result['discover_full']
    result['bad_png'] = {**deepcopy(discover), 'session_id': BAD_PNG_SESSION}

    source = records['source_unknown']['producer']['region_ref']
    stale = {key: deepcopy(value) for key, value in source.items() if key != 'region_id'}
    stale['document_epoch'] = ('0' if stale['document_epoch'] != '0' * 64 else '1') * 64
    unsigned = json.dumps(stale, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()
    stale['region_id'] = 'source-region:' + sha256(unsigned).hexdigest()
    stale_request = deepcopy(result['source_region_no_image'])
    query = stale_request['query']
    query.pop('region')
    query['region_ref'] = stale
    result['stale_region'] = {**stale_request, 'session_id': STALE_REGION_SESSION}
    return result


@lru_cache(maxsize=1)
def transport():
    # Reuse the exact retained externally held pipe/EOF recorder.
    path = VERIFICATION / 'm4_source_region_display_001/harness/reused/stdio_checks.py'
    return SimpleNamespace(**run_path(str(path)))


def rpc(identifier, method, **params):
    return {'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params}


def hello(client):
    initialized = client.call(rpc('initialize', 'initialize', protocolVersion='2025-03-26', capabilities={},
                                  clientInfo={'name':'region-task-first-packet-qualification', 'version':'1'}))
    require('human_eye' in initialized.get('result', {}).get('_meta', {}), 'actual_production_initialization_failed')
    client.call({'jsonrpc':'2.0', 'method':'notifications/initialized'})
    listed = client.call(rpc('catalogue', 'tools/list'))
    require(isinstance(listed.get('result', {}).get('tools'), list), 'actual_production_tools_list_failed')
    return initialized, listed


@contextmanager
def stock(root, binding_path, slot, *, isolated=False, deadline_ns=None, request_budget_s=30, extras=()):
    """Open one actual Python-held production process and retain all outer wire bytes."""
    root = Path(root).resolve()
    require(root.is_relative_to(EXTERNAL) and root != EXTERNAL, 'stock_outside_private_replay_root')
    root.mkdir(parents=True, exist_ok=False)
    command = [str(Path(sys.executable).resolve()), '-IB', '-X', 'utf8', str(Path(__file__).resolve()),
               '--worker', str(root / 'worker'), '--binding', str(Path(binding_path).resolve(strict=True)), '--slot', slot,
               '--request-budget-s', str(request_budget_s)]
    if isolated:
        command.append('--region-task-evidence')
    for name, batch, label, ordinal in extras:
        command.extend(['--extra', f'{name}:{batch}:{label}:{ordinal}'])
    deadline = deadline_ns if deadline_ns is not None else time.perf_counter_ns() + 120_000_000_000
    child = transport().StdioClient(command, root, root / 'wire', deadline)
    try:
        yield child
    finally:
        closed = child.finish()
        save(root / 'STOCK_CLOSE.json', closed)
        require(closed['confirmed'] and closed['exit_code'] == 0 and closed['process_handle_closed'],
                'actual_production_stdio_close_unproven/' + root.name)
        eof = read(root / 'worker/EOF.json')
        require(eof['closed'] and eof['host_attempts'] == eof['new_rasters'] == 0,
                'actual_archived_service_EOF_or_read_only_scope_unproven/' + root.name)


def worker(root, binding_path, slot, isolated, request_budget_s, extras):
    install = read(binding_path)
    base = Path(install['install_root']).resolve(strict=True)
    dependencies = Path(install['dependency_root']).resolve(strict=True)
    wheel = pin(Path(install['wheel_path']))
    require(wheel['sha256'] == install['wheel_sha256'], 'installed_replay_wheel_digest_changed')
    require(len(install['source_manifest']) == 143, 'installed_replay_source_count_changed')
    sys.path[:0] = [str(base), str(dependencies)]
    from human_eye_plugin import live_service, live_spatial_mcp, production_server
    from human_eye_plugin.query_policy import validate_query
    from human_eye_plugin.runtime_identity import runtime_identity
    from human_eye_plugin.source_region import validate_region_ref

    actual = runtime_identity(mode='live')
    require(actual['source_kind'] == 'installed_distribution' and actual['source_sha256'] == install['source_sha256']
            and actual['source_files'] == install['source_manifest'], 'installed_replay_runtime_identity_changed')
    require(all(Path(module.__file__).resolve().is_relative_to(base)
                for module in (live_service, live_spatial_mcp, production_server)), 'replay_imported_outside_install')
    registered = fixtures(slot, extras)
    lookup = {(compact(validate_query(record['request']['query'])), record['request'].get('include_image', True)): record
              for record in registered.values()}
    require(len(lookup) == len(registered), 'ambiguous_archived_observe_fixture')
    terminal, terminal_pin = archived(FORMAL, 'slots', 'P3', 'TERMINAL_SOURCE.json')
    archived_sources = {row['object_id']:row for row in terminal['objects']}
    unknown = registered['source_unknown']['producer']
    observed_objects = unknown['binding']['objects']
    require(len(observed_objects) == len(archived_sources) == 21, 'archived_unknown_scene_objects_changed')
    counts = []
    for row in observed_objects:
        item = archived_sources[row['host_id']]
        require((item['name'], item['instance_id']) == (row['object_name'], row['instance_id']),
                'archived_unknown_object_identity_changed')
        counts.append(len(item['evaluated']['triangles']))
    root = root.resolve()
    require(root.is_relative_to(EXTERNAL) and root != EXTERNAL, 'worker_outside_private_replay_root')
    root.mkdir(parents=True, exist_ok=False)
    config = root / 'PRODUCT_CONFIG.json'
    save(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                  'project_root': str(base), 'state_file': str(root / 'product_state.json'),
                  'audit_file': str(root / 'product_audit.jsonl'), 'request_budget_s': request_budget_s,
                  'expected_identity': {'source_sha256':actual['source_sha256']}})
    args = ['--config', str(config)]
    if isolated:
        args.append('--region-task-evidence')
    source_pins = {row['path']:row for record in registered.values() for row in record['pins']}
    for row in (pin(binding_path), wheel, terminal_pin, *(pin(Path(module.__file__))
                for module in (live_service, live_spatial_mcp, production_server))):
        source_pins[row['path']]=row
    save(root/'INPUTS.json', {'slot':slot, 'edition':'isolated_evidence' if isolated else 'standard',
         'launcher':'human_eye_plugin.production_server:main', 'production_argv':args,
         'source_sha256':actual['source_sha256'], 'source_pins':list(source_pins.values()),
         'fixtures':{key:row['case'] for key,row in registered.items()}})

    class NoHost:
        attempts = 0

        def __getattr__(self, name):
            if name in ('runtime_identity', 'runtime_manifest', 'verify_readonly_source', 'package_identity', 'source_identity'):
                raise AttributeError(name)
            self.attempts += 1
            raise AssertionError('no_Blender_host_in_replay/' + name)

    class Replay(live_service.LiveSpatialService):
        def __init__(self, config_path, *, production_mode=False):
            require(Path(config_path).resolve() == config and production_mode is True,
                    'actual_production_service_construction_not_used')
            self.dispatches = self.observe_calls = self.stale_refs = 0
            self.codec_events = []
            super().__init__(config_path, host=NoHost(), production_mode=production_mode)

        def observe(self, session_id, *args, **kwargs):
            self.observe_calls += 1
            append(root/'SERVICE_CALLS.jsonl', {'index':self.observe_calls, 'session_id':session_id,
                   'positional':args, 'keywords':kwargs, 'started_ns':time.perf_counter_ns()})
            return super().observe(session_id, *args, **kwargs)

        def _archived_observe(self, session_id, query, include_image):
            key = (compact(validate_query(query)), include_image)
            record = lookup.get(key)
            require(record is not None, 'archived_fixture_for_exact_validated_query_required')
            value = deepcopy(record['producer'])
            self.dispatches += 1
            fault = session_id == BAD_PNG_SESSION
            if fault:
                require(record is registered['discovery'], 'fault_control_requires_original_discovery')
                value['frames'][0]['image_sha256'] = '0' * 64
            if record is registered['source_unknown']:
                # Bind the existing production blocker lookup to saved identities and face counts.
                rid = value['region_ref']['region_id']
                selected = value['facts']['region']['host_id']
                index, = [i for i, obj in enumerate(value['binding']['objects']) if obj['host_id'] == selected]
                self._read_context.activate(value['binding'], 'source_region', query)
                private = SimpleNamespace(region_ref=value['region_ref'], observation=value, binding=value['binding'],
                    meshes=[SimpleNamespace(faces=range(size)) for size in counts], object_index=index,
                    source_triangle_indices=value['region_ref']['source_triangle_indices'])
                self._read_context.prepared('source_regions', lambda: {'regions': {rid: private}})
            append(root/'PRODUCER_CALLS.jsonl', {'index':self.dispatches, 'source':record['case'], 'query':query,
                'include_image':include_image, 'source_sha256':record['pins'][0]['sha256'],
                'bad_archived_PNG_digest_control':fault, 'started_ns':time.perf_counter_ns()})
            return value

        def _observe_active_observation(self, session_id, *, include_image, selector, task_query, region_task):
            query = {'mode':'active_observation'}
            if selector is not None:
                query['objects'] = [selector]
            if task_query is not None:
                query['task_query'] = task_query
            if region_task is not None:
                query['region_task'] = region_task
            return self._archived_observe(session_id, query, include_image)

        def _observe_source_region(self, session_id, query, *, include_image):
            if session_id == STALE_REGION_SESSION:
                require(not include_image and 'region_ref' in query, 'stale_reference_control_contract')
                self.stale_refs += 1
                # The real validator rejects the changed epoch before any geometry access.
                return validate_region_ref(None, query['region_ref'], self._check_request_budget,
                                           _binding=unknown['binding'])
            return self._archived_observe(session_id, query, include_image)

        def record_event(self, event, **fields):
            if event in ('active_observation_mcp_content', 'source_region_mcp_content'):
                self.codec_events.append({'event':event, **fields})
            return super().record_event(event, **fields)

        def close(self):
            save(root/'EOF.json', {'closed':True, 'production_mode':self.production_mode,
                 'observe_service_calls':self.observe_calls, 'observe_dispatches':self.dispatches,
                 'stale_ref_checks':self.stale_refs, 'host_attempts':self.host.attempts, 'new_rasters':0,
                 'source_sha256':actual['source_sha256'], 'encoder_events':self.codec_events})

    # The installed entry still parses real options, resolves configuration, constructs the
    # real service in production mode, and chooses and runs the installed stdio server.
    live_service.LiveSpatialService = Replay
    return production_server.main(args)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--slot', choices=('P2', 'P3'), required=True)
    parser.add_argument('--region-task-evidence', action='store_true')
    parser.add_argument('--request-budget-s', type=float, default=30)
    parser.add_argument('--extra', action='append', default=[])
    options = parser.parse_args()
    entries = []
    for value in options.extra:
        name, batch, label, ordinal = value.split(':')
        entries.append((name, batch, label, int(ordinal)))
    raise SystemExit(worker(options.worker, options.binding.resolve(strict=True), options.slot,
                            options.region_task_evidence, options.request_budget_s, entries))
