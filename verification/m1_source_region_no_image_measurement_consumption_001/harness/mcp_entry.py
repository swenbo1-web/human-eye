"""Observe the installed production launcher without changing requests or replies."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission
from budget import Budget, encoded, save
from common import EXTERNAL, PRIOR, PRODUCT_BINDING, SOURCE_SHA, SLOTS, binding_for, evidence_enabled, load_retained, product_for, read


retained = load_retained('_region_task_held_wire_observer', PRIOR / 'harness/mcp_entry.py')


class AuditStreams(retained.AuditStreams):
    def __init__(self, *args, **kwargs):
        self.input_eof_ns = None
        super().__init__(*args, **kwargs)

    def readline(self, size=-1):
        raw = super().readline(size)
        if raw == b'':
            self.input_eof_ns = time.perf_counter_ns()
        return raw


def worker(args):
    binding = read(args.binding)
    source_sha = product_for(args.label)['source_sha256']
    if binding['source_sha256'] != source_sha or len(binding['source_manifest']) != 143:
        raise ValueError('fixed_region_task_product_required')
    sys.path.insert(0, binding['dependency_root'])
    bootstrap = retained.load_module('_region_task_verified_bootstrap',
                                     PRIOR / 'harness/reused/verified_bootstrap.py')
    guard = bootstrap.bootstrap(binding)
    setup = getattr(args, '_preflight_setup', None)
    if setup is not None:
        setup(binding)
    from human_eye_plugin import live_service, live_spatial_mcp, production_server

    root = Path(binding['install_root']).resolve(strict=True)
    if any(not Path(module.__file__).resolve().is_relative_to(root)
           for module in (live_service, live_spatial_mcp, production_server)):
        raise ValueError('actual_production_modules_must_be_installed')
    live_spatial_mcp._configure_utf8_stdio()
    ledger = Budget(args.ledger)
    args.archive.mkdir(parents=True, exist_ok=False)
    config = read(args.config)
    streams = AuditStreams(sys.stdin, sys.stdout, args.evidence, config['audit_file'],
                           ledger, args.phase, retained.numeric_source_phase(binding))
    holder = {}
    original_service = live_service.LiveSpatialService

    class ObservedService(original_service):
        """Record the original returned object and original pre-raster events."""

        def __init__(self, config_path, *values, **keywords):
            if (Path(config_path).resolve() != args.config.resolve()
                    or keywords.get('production_mode') is not True or holder):
                raise ValueError('one_actual_production_service_required')
            self._archive_counter = 0
            self._observed_close = None
            super().__init__(config_path, *values, **keywords)
            holder['service'] = self

        def record_event(self, event, **fields):
            if event not in ('active_observation_render_attempt', 'source_region_render_attempt'):
                return super().record_event(event, **fields)
            token = ledger.reserve('raster_attempt', args.label, args.phase, 1)
            audit_path = Path(config['audit_file'])
            offset = audit_path.stat().st_size if audit_path.exists() else 0
            value = super().record_event(event, **fields)
            tail = audit_path.read_bytes()[offset:]
            ledger.settle_rasters(token, actual=1, lower_bound=1,
                evidence={'audit_path': str(audit_path), 'tail_start_bytes': offset, 'tail_bytes': len(tail),
                          'tail_sha256': hashlib.sha256(tail).hexdigest(), 'event': event,
                          'boundary': 'original producer callback before construction; failures remain charged'},
                outcome='producer_attempt_admitted')
            return value

        def observe(self, *values, **keywords):
            self._archive_counter += 1
            directory = args.archive / ('call_' + str(self._archive_counter).zfill(3))
            directory.mkdir()
            before = retained.read_context_metadata(self)
            began = time.perf_counter_ns()
            raw = super().observe(*values, **keywords)
            produced = time.perf_counter_ns()
            after = retained.read_context_metadata(self)
            path = directory / 'SERVICE_RESULT.json'
            save(path, raw)
            save(directory / 'READ_CONTEXT.json', {'before': before, 'after': after})
            record = {'index': self._archive_counter, 'producer_returned_ns': produced,
                      'started_ns': began, 'saved_ns': time.perf_counter_ns(), 'path': str(path),
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'read_context': str(directory / 'READ_CONTEXT.json'),
                      'scope': 'same returned producer object before installed formatter; no second observe',
                      'new_observations_for_archive': 0}
            with (args.archive / 'INDEX.jsonl').open('ab') as stream:
                stream.write(encoded(record))
                stream.flush()
                os.fsync(stream.fileno())
            return raw

        def close(self):
            if self._observed_close is not None:
                return self._observed_close
            began = time.perf_counter_ns()
            receipt = {'pid': os.getpid(), 'source_sha256': source_sha, 'started_ns': began,
                       'closed': False, 'observe_calls': self._archive_counter,
                       'input_eof_observed': streams.input_eof_ns is not None,
                       'input_eof_ns': streams.input_eof_ns, 'host_close_called': False}
            try:
                close = getattr(super(), 'close', None)
                if callable(close):
                    receipt['host_close_called'] = True
                    result = close()
                else:
                    close = getattr(self.host, 'close', None)
                    if not callable(close):
                        raise ValueError('actual_host_close_required')
                    receipt['host_close_called'] = True
                    result = close()
                receipt['closed'] = True
                return result
            except BaseException as error:
                receipt['error'] = {'type': type(error).__name__, 'message': str(error)}
                raise
            finally:
                receipt['closed_ns'] = time.perf_counter_ns()
                self._observed_close = receipt
                save(args.evidence / 'EOF.json', receipt)

    production_arguments = ['--config', str(args.config.resolve())]
    if args.region_task_evidence:
        production_arguments.append('--region-task-evidence')
    runtime = {'pid': os.getpid(), 'parent_pid': os.getppid(), 'python': sys.executable,
               'entry': str(Path(__file__).resolve()),
               'entry_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'binding_sha256': hashlib.sha256(args.binding.read_bytes()).hexdigest(),
               'source_sha256': source_sha, 'label': args.label, 'phase': args.phase,
               'production_launcher': str(Path(production_server.__file__).resolve()),
               'production_argv': production_arguments,
               'region_task_evidence': args.region_task_evidence,
               'implementation': 'installed production_server.main and installed stdio server',
               'algorithm_monkeypatches': 0 if not getattr(args, '_replay_overrides', None) else 1,
               'archived_replay_overrides': getattr(args, '_replay_overrides', None),
               'external_observer_subclass': True,
               'full_archive': str(args.archive), 'per_attempt_budget_label': args.label,
               'stream_audit': 'original byte input/output forwarded; timing and raster accounting only',
               'numeric_pre_render_source_proof': streams.source_phase}
    for name in ('numpy', 'PIL'):
        module = sys.modules.get(name)
        runtime[name] = None if module is None else {
            'file': getattr(module, '__file__', None), 'version': getattr(module, '__version__', None)}
    save(args.evidence / 'RUNTIME.json', runtime)
    original_input, original_output = sys.stdin, sys.stdout
    exit_record = {'pid': os.getpid(), 'source_sha256': source_sha,
                   'production_return_code': None, 'production_returned': False}
    try:
        live_service.LiveSpatialService = ObservedService
        sys.stdin = sys.stdout = streams
        code = production_server.main(production_arguments)
        exit_record.update(production_return_code=code, production_returned=True)
        return code
    except BaseException as error:
        exit_record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        sys.stdin, sys.stdout = original_input, original_output
        live_service.LiveSpatialService = original_service
        service = holder.get('service')
        exit_record['service_constructed'] = service is not None
        exit_record['input_eof_observed'] = streams.input_eof_ns is not None
        try:
            if service is not None and service._observed_close is None:
                service.close()
            guard.verify_loaded()
            exit_record['installed_source_verified'] = True
        finally:
            exit_record['closed_ns'] = time.perf_counter_ns()
            save(args.evidence / 'WORKER_EXIT.json', exit_record)


def main():
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('registered_isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('binding', 'config', 'ledger', 'evidence', 'archive'):
        parser.add_argument('--' + field, type=Path, required=True)
    parser.add_argument('--phase', choices=('qualification', 'formal'), required=True)
    parser.add_argument('--label', choices=tuple(SLOTS), required=True)
    parser.add_argument('--region-task-evidence', action='store_true')
    args = parser.parse_args()
    slot = EXTERNAL / 'slots' / args.label
    expected = {'binding': binding_for(args.label), 'config': slot / 'PRODUCT_CONFIG.json',
                'ledger': EXTERNAL / 'budget', 'evidence': slot / 'mcp_io', 'archive': slot / 'product_full'}
    if (args.phase != SLOTS[args.label][1] or args.region_task_evidence != evidence_enabled(args.label)
            or any(getattr(args, key).resolve() != value.resolve() for key, value in expected.items())):
        raise ValueError('registered_production_arm_paths_and_flag_required')
    state = Path(read(args.config)['state_file'])
    if not state.is_absolute() or state != slot / 'product_state.json' or state.resolve() != state:
        raise ValueError('current_absolute_owned_state_required')
    admission.registered_product(args.label)
    return worker(args)


if __name__ == '__main__':
    raise SystemExit(main())
