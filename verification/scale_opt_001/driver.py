"""Serial, interleaved O/C installed-product sampling for SCALE-OPT-001.

This file references SCALE-DIAG-001's frozen fixtures and original child
driver. It never imports the native solver or copies prior evidence/install
trees. Run only after INSTALLS.json and this batch's FREEZE.json are ready.
The coordinator is the sole sampler; a child always takes the original P
entry, budgets, readbacks, owned-session lifecycle, and timing boundaries.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
DIAG = HERE.parent / 'scale_diag_001'
STATIC = (
    ('G_low', 'G60_D12', 'G'), ('G_mid', 'G508', 'G'),
    ('G_high', 'G4092', 'G'), ('D_low', 'G60_D12', 'D'),
    ('D_mid', 'D48', 'D'), ('D_high', 'D192', 'D'),
)


def load(path):
    return json.loads(Path(path).read_bytes())


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False,
        indent=2) + '\n', encoding='utf8', newline='\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def installs(path):
    manifest = load(path)
    if manifest.get('passed') is not True or set(manifest.get('versions', {})) != {'O', 'C'}:
        raise ValueError('passed_O_C_install_manifest_required')
    for group, row in manifest['versions'].items():
        python, site = Path(row['python']), Path(row['installed_root'])
        canonical = row['source_sha256']
        if (not python.is_absolute() or not site.is_absolute() or not python.is_file()
                or site.resolve() != (python.parents[1] / 'Lib/site-packages').resolve()):
            raise ValueError(group + '_absolute_venv_python_and_site_required')
        if (not isinstance(canonical, str) or len(canonical) != 64
                or any(c not in '0123456789abcdef' for c in canonical)):
            raise ValueError(group + '_canonical_required')
        identity = row['identity']
        if (identity.get('source_kind') != 'installed_distribution'
                or identity.get('source_sha256') != canonical):
            raise ValueError(group + '_installed_identity_required')
    return manifest


def plan():
    """Freeze nine paired blocks before observing any timing; 39 cells/group."""
    blocks = [(cell, scene, mode, None) for cell, scene, mode in STATIC]
    blocks.extend(('T_round_%d' % i, 'D48', 'T', i) for i in range(3))
    result = []
    for block, (cell, scene, mode, repeat) in enumerate(blocks):
        order = ('O', 'C') if block % 2 == 0 else ('C', 'O')
        for position, group in enumerate(order):
            result.append(dict(index=len(result), block=block, position_in_block=position,
                pair_order=list(order), cell=cell, scene=scene, mode=mode, group=group,
                round=repeat, logical_expected=7 if mode == 'T' else 3))
    return result


def shared_inputs():
    """Hashes/reference paths only; do not copy frozen data into this batch."""
    paths = [DIAG / name for name in ('driver.py', 'session.py', 'instrument.py',
        'build_fixtures.py', 'FREEZE.json', 'oracle.py', 'ORACLE.json')]
    scenes = sorted({scene for _, scene, _ in STATIC})
    paths.extend(DIAG / 'fixtures' / (scene + suffix)
                 for scene in scenes for suffix in ('.blend', '.json'))
    paths.extend(DIAG / 'fixtures' / ('T%d.json' % i) for i in range(7))
    paths.append(DIAG / 'fixtures' / 'BUILD_COMPLETE.json')
    return {str(path.resolve()): sha(path) for path in paths}


def provenance(args, selected, installs_sha, freeze_sha):
    return dict(group=args.group, source_group='P', actor_os_pid=os.getpid(),
        actor_parent_os_pid=os.getppid(), coordinator_pid=args.coordinator_pid,
        python=sys.executable, base_executable=getattr(sys, '_base_executable', None),
        python_prefix=sys.prefix, selected_python=selected['python'],
        installed_root=selected['installed_root'], canonical=selected['source_sha256'],
        installs_file=str(Path(args.installs).resolve()), installs_sha256=installs_sha,
        freeze_file=str((HERE / 'FREEZE.json').resolve()), freeze_sha256=freeze_sha,
        driver_sha256=sha(__file__), shared_driver=str((DIAG / 'driver.py').resolve()),
        plan_index=args.plan_index, argv=sys.argv)


def child(args):
    """Delegate the real P child; relabel evidence without changing its input."""
    started = time.perf_counter_ns()
    out = Path(args.output).resolve()
    install_path = Path(args.installs).resolve()
    installs_sha, freeze_sha = sha(install_path), sha(HERE / 'FREEZE.json')
    if args.installs_sha256 and installs_sha != args.installs_sha256:
        raise ValueError('install_manifest_changed_before_child')
    if args.freeze_sha256 and freeze_sha != args.freeze_sha256:
        raise ValueError('batch_freeze_changed_before_child')
    manifest = installs(install_path)
    selected = manifest['versions'][args.group]
    if (Path(sys.executable).resolve() != Path(selected['python']).resolve()
            or Path(sys.prefix).resolve() != Path(selected['python']).parents[1].resolve()):
        raise ValueError('child_must_run_selected_venv')
    if args.plan_file:
        frozen = load(args.plan_file)
        if not 0 <= args.plan_index < len(frozen['chains']):
            raise ValueError('child_plan_index_out_of_range')
        entry = frozen['chains'][args.plan_index]
        if any(entry[key] != getattr(args, key) for key in ('group', 'mode', 'scene')):
            raise ValueError('child_does_not_match_frozen_plan')
        if (frozen['installs_sha256'] != installs_sha or frozen['freeze_sha256'] != freeze_sha
                or frozen['driver_sha256'] != sha(__file__)
                or frozen['shared_inputs_sha256'] != shared_inputs()):
            raise ValueError('frozen_inputs_changed_before_child')
    actor = provenance(args, selected, installs_sha, freeze_sha)
    # The shared child exclusively creates out. Keep early PID evidence beside
    # it so a failed launch/setup cannot erase the real actor/launcher split.
    dump(out.with_name(out.name + '.actor.json'), actor)
    base = module('scale_opt_shared_driver', DIAG / 'driver.py')
    base.PRODUCT_PY = Path(selected['python'])
    base.CANONICAL = selected['source_sha256']
    original_dump = base.dump
    rows = []
    delegated_at = None

    def record(path, value):
        path = Path(path)
        if path.name == 'CONFIG.json':
            if Path(value['project_root']).resolve() != Path(selected['installed_root']).resolve():
                raise ValueError('actual_product_root_differs_from_install_manifest')
            if value['request_budget_s'] != 30. or value['blender']['timeout_s'] != 30.:
                raise ValueError('original_thirty_second_budget_changed')
        if path.name == 'IDENTITY.json' and (value.get('source_sha256') != selected['source_sha256']
                or value.get('source_kind') != 'installed_distribution'
                or value.get('source_files') != selected['identity']['source_files']):
            raise ValueError('actual_source_identity_differs_from_install_manifest')
        if path.name.startswith('MEASUREMENT_') and path.suffix == '.json':
            value = dict(value, group=args.group, source_group='P', actor_os_pid=os.getpid(),
                actor_parent_os_pid=os.getppid(), canonical=selected['source_sha256'])
            rows.append(value)
        elif path.name == 'CHAIN.json':
            expected = 7 if args.mode == 'T' else 3
            value = dict(value, group=args.group, source_group='P', actor_os_pid=os.getpid(),
                actor_parent_os_pid=os.getppid(), owned_blender_pid=value.get('pid'),
                canonical=selected['source_sha256'], installed_root=selected['installed_root'],
                installs_sha256=installs_sha, freeze_sha256=freeze_sha,
                logical_expected=expected, logical_unexecuted=max(0, expected-len(rows)),
                recorded_request_exceptions=sum(row['exception'] is not None for row in rows),
                wrapper_before_shared_child_ns=delegated_at-started,
                driver_whole_chain_ns=time.perf_counter_ns()-started,
                chain_timing_scope='shared SCALE-DIAG child whole_chain_ns unchanged; driver_whole_chain_ns includes new manifest/provenance work')
        original_dump(path, value)

    base.dump = record
    delegated = argparse.Namespace(group='P', mode=args.mode, scene=args.scene, output=str(out))
    failure = None
    delegated_at = time.perf_counter_ns()
    try:
        base.child(delegated)
    except BaseException as exc:
        failure = dict(type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        base.dump = original_dump
        dump(out.with_name(out.name + '.actor_exit.json'), dict(actor_os_pid=os.getpid(),
            actor_parent_os_pid=os.getppid(), error=failure,
            driver_attempt_ns=time.perf_counter_ns()-started))


def coordinator(args):
    freeze_path, install_path = HERE / 'FREEZE.json', Path(args.installs).resolve()
    # Existence and hashes are enforced here; the root owns freeze contents.
    freeze_sha, installs_sha = sha(freeze_path), sha(install_path)
    manifest = installs(install_path)
    chains = plan()
    output = Path(args.output).resolve() if args.output else HERE / 'measurements'
    output.mkdir(parents=True, exist_ok=False)
    frozen = dict(schema='scale-opt-001-interleaved-plan-v1', task='SCALE-OPT-001',
        coordinator_os_pid=os.getpid(), chains=chains, logical_expected=78,
        logical_expected_by_group={'O':39, 'C':39}, physical_chains_expected=18,
        order_policy='alternating O,C / C,O by paired static cell or T round; own cold/cache per child',
        entry_policy='original installed P entry and 30 second budget for both versions',
        installs_file=str(install_path), installs_sha256=installs_sha,
        freeze_file=str(freeze_path), freeze_sha256=freeze_sha, driver_sha256=sha(__file__),
        shared_inputs_sha256=shared_inputs())
    plan_path = output / 'PLAN.json'
    dump(plan_path, frozen)
    receipts = []
    stopped = None
    for entry in chains:
        group = entry['group']
        name = entry['cell'] + '_' + group
        folder = output / name
        command = [manifest['versions'][group]['python'], '-I', '-B', '-X', 'utf8',
            str(Path(__file__).resolve()), '--child', '--group', group,
            '--mode', entry['mode'], '--scene', entry['scene'], '--output', str(folder),
            '--installs', str(install_path), '--installs-sha256', installs_sha,
            '--freeze-sha256', freeze_sha, '--plan-file', str(plan_path),
            '--plan-index', str(entry['index']), '--coordinator-pid', str(os.getpid())]
        marked = time.perf_counter_ns()
        process = None
        error = None
        exit_code = None
        with (output / (name + '.stdout.txt')).open('xb') as stdout, (output / (name + '.stderr.txt')).open('xb') as stderr:
            try:
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                    stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                dump(output / (name + '.launcher.json'), dict(venv_launcher_pid=process.pid,
                    coordinator_os_pid=os.getpid(), command=command, plan_index=entry['index']))
                try:
                    exit_code = process.wait(timeout=590)
                except subprocess.TimeoutExpired:
                    exit_code = 'coordinator_timeout'
                    # A venv launcher is not the real actor. Do not claim that
                    # killing it reaped its owned Blender; stop for inspection.
                    stopped = 'coordinator_timeout_owned_actor_cleanup_unverified'
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        error = dict(type=type(exc).__name__, message=str(exc))
            except OSError as exc:
                error = dict(type=type(exc).__name__, message=str(exc))
                exit_code = 'launch_error' if process is None else 'coordinator_io_error'
                if process is not None:
                    stopped = 'coordinator_io_error_owned_actor_cleanup_unverified'
        actor_path = output / (name + '.actor.json')
        chain_path = folder / 'CHAIN.json'
        actor = load(actor_path) if actor_path.is_file() else {}
        chain = load(chain_path) if chain_path.is_file() else {}
        receipt = dict(entry, actor_pid=actor.get('actor_os_pid'),
            actor_parent_os_pid=actor.get('actor_parent_os_pid'),
            venv_launcher_pid=process.pid if process is not None else None,
            owned_blender_pid=chain.get('owned_blender_pid'), exit_code=exit_code, error=error,
            full_process_ns=time.perf_counter_ns()-marked, recorded_rows=chain.get('rows', 0),
            logical_unexecuted=max(0, entry['logical_expected']-chain.get('rows', 0)),
            close=chain.get('close'), command=command)
        receipts.append(receipt)
        dump(output / 'RUNS.json', receipts)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
        if stopped:
            break
    dump(output / 'COMPLETE.json', dict(schema='scale-opt-001-run-complete-v1',
        physical_chains=len(receipts), physical_chains_expected=18, logical_expected=78,
        logical_recorded=sum(row['recorded_rows'] for row in receipts),
        logical_unexecuted=78-sum(row['recorded_rows'] for row in receipts),
        stopped_reason=stopped, runs=receipts, plan_file=str(plan_path),
        installs_sha256=installs_sha, freeze_sha256=freeze_sha))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--group', choices=('O', 'C'))
    parser.add_argument('--mode', choices=('G', 'D', 'T'))
    parser.add_argument('--scene', choices=tuple(sorted({scene for _, scene, _ in STATIC})))
    parser.add_argument('--output')
    parser.add_argument('--installs', default=str(HERE / 'INSTALLS.json'))
    parser.add_argument('--installs-sha256')
    parser.add_argument('--freeze-sha256')
    parser.add_argument('--plan-file')
    parser.add_argument('--plan-index', type=int, default=-1)
    parser.add_argument('--coordinator-pid', type=int)
    args = parser.parse_args()
    if args.child:
        if not all((args.group, args.mode, args.scene, args.output)):
            parser.error('--child requires group, mode, scene and output')
        return child(args)
    if not args.run:
        parser.error('sampling requires explicit --run')
    return coordinator(args)


if __name__ == '__main__':
    main()
