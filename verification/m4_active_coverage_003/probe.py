"""Four registered import/lifecycle probes. This target performs no rendering."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import traceback


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, default=str) + '\n').encode('utf8')


def publish(folder, name, value, replace=False):
    target, partial = folder / name, folder / (name + '.part')
    if not replace and target.exists():
        raise FileExistsError(str(target))
    raw = encoded(value)
    with partial.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(partial, target)
    else:
        os.rename(partial, target)
    return hashlib.sha256(raw).hexdigest()


class Trace:
    def __init__(self, folder, run_id, scenario):
        self.stream = (folder / 'TRACE.jsonl').open('xb')
        self.run_id, self.scenario, self.sequence = run_id, scenario, 0

    def emit(self, event, durable=False, **fields):
        self.sequence += 1
        self.stream.write(encoded({'sequence': self.sequence, 'event': event,
            'monotonic_ns': time.perf_counter_ns(), 'run_id': self.run_id,
            'scenario': self.scenario, 'process_id': os.getpid(), **fields}))
        self.stream.flush()
        if durable:
            os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


class RegisteredProbeFailure(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=('normal', 'nonzero', 'timeout', 'receipt_failure'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if not args.output.is_absolute():
        raise ValueError('absolute_probe_output_required')
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    trace = Trace(folder, args.run_id, args.scenario)
    identity = {'scenario': args.scenario, 'run_id': args.run_id, 'process_id': os.getpid(),
                'output_directory': str(folder), 'probe_path': str(Path(__file__).resolve()),
                'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        trace.emit('probe_started', durable=True)
        install_audit = globals()['ACTIVE003_INSTALL_OLD_AUDIT']
        dependencies = globals()['ACTIVE003_LOAD_DEPENDENCIES']
        audit = install_audit(trace)
        _, _, environment = dependencies()
        environment_sha = publish(folder, 'ENVIRONMENT.json', environment)
        publish(folder, 'AUDIT.json', audit)
        phase = 'waiting' if args.scenario == 'timeout' else 'ready'
        publish(folder, 'STATE.json', {**identity, 'phase': phase, 'marker_actions': 0}, replace=True)
        trace.emit('waiting' if phase == 'waiting' else 'dependencies_ready', durable=True)
        publish(folder, 'HANDSHAKE.json', {**identity, 'phase': phase,
                'environment_sha256': environment_sha, 'environment_file': 'ENVIRONMENT.json'})
        if args.scenario == 'timeout':
            while True:
                time.sleep(1)
        if args.scenario == 'nonzero':
            raise RegisteredProbeFailure('registered_nonzero_probe_failure')
        if args.scenario == 'receipt_failure':
            marker = {**identity, 'action': 'write_local_marker', 'action_count': 1,
                      'executed_ns': time.perf_counter_ns()}
            marker_sha = publish(folder, 'MARKER.json', marker)
            trace.emit('marker_written', durable=True, marker_sha256=marker_sha, action_count=1)
            publish(folder, 'STATE.json', {**identity, 'phase': 'action_executed_receipt_omitted',
                    'marker_actions': 1, 'marker_sha256': marker_sha}, replace=True)
            return 0
        publish(folder, 'RECEIPT.json', {**identity, 'status': 'completed',
                'environment_sha256': environment_sha, 'marker_actions': 0})
        publish(folder, 'STATE.json', {**identity, 'phase': 'completed', 'marker_actions': 0}, replace=True)
        trace.emit('probe_completed', durable=True)
        return 0
    except BaseException as error:
        failure = {**identity, 'phase': 'failed', 'type': type(error).__name__, 'message': str(error),
                   'traceback': traceback.format_exc()}
        publish(folder, 'STATE.json', failure, replace=True)
        trace.emit('probe_failed', durable=True, type=type(error).__name__, message=str(error))
        raise
    finally:
        trace.close()


if __name__ == '__main__':
    raise SystemExit(main())
