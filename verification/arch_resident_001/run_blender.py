"""Reproducible owned Blender checks for resident capture and both bridges."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[2]
if 'human_eye_plugin' not in sys.modules:
    package = types.ModuleType('human_eye_plugin')
    package.__path__ = [str(ROOT / 'human_eye_plugin')]
    sys.modules['human_eye_plugin'] = package

from human_eye_plugin.blender_mcp_host import BlenderMCPHost, RPC_PREFIX
from human_eye_plugin.blender_process import BlenderProcessHost


class MeasuredHost(BlenderMCPHost):
    def _exchange(self, payload):
        self.last_request_bytes = len(payload)
        value = super()._exchange(payload)
        inner = value.get('result', {}).get('result', '')
        if inner.startswith(RPC_PREFIX):
            self.last_wire = json.loads(inner[len(RPC_PREFIX):]).get('result')
            self.last_wire_bytes = len(inner.encode('utf8'))
        return value


def control(port, **params):
    with socket.create_connection(('127.0.0.1', port), timeout=20) as client:
        client.sendall(json.dumps({'type': 'test_control', 'params': params}).encode())
        response = bytearray()
        while True:
            block = client.recv(65536)
            if not block:
                break
            response.extend(block)
        result = json.loads(response)
        if 'control' not in result:
            raise AssertionError(result)
        return result['control']


def gap(capture):
    rows = {m['name']: m for m in capture['meshes']}
    return min(p[2] for p in rows['BluePart']['vertices']) - max(p[2] for p in rows['GreyBase']['vertices'])


def main():
    output = Path(sys.argv[1]).resolve()
    world_reuse = '--world-reuse' in sys.argv[2:]
    output.mkdir(parents=True, exist_ok=True)
    fixture, ready = output / 'fixture.blend', output / ('ready-%d.json' % os.getpid())
    records = []
    product_paths = ['human_eye_plugin/' + name + '.py' for name in
        ('blender_host', 'blender_mcp_host', 'blender_process', 'blender_worker', 'scene_residency')]
    source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in product_paths}
    executable = Path('D:/Tools/blender5.2/blender.exe')
    started = time.perf_counter_ns()
    log = (output / 'blender.log').open('w', encoding='utf8')
    process = subprocess.Popen([str(executable), '--factory-startup', '--disable-autoexec', '--background',
        '--python', str(Path(__file__).with_name('blender_fixture.py')), '--', str(fixture), str(ready)],
        stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        until = time.monotonic() + 45
        while not ready.is_file():
            if process.poll() is not None or time.monotonic() > until:
                raise RuntimeError('Owned fixture startup failed; see blender.log')
            time.sleep(.05)
        startup_ms = (time.perf_counter_ns() - started) / 1e6
        port = json.loads(ready.read_text(encoding='utf8'))['port']
        host = MeasuredHost(ROOT, port=port, timeout_s=20)
        selectors = [{'name': 'BluePart'}, {'name': 'GreyBase'}]

        def query(label, fn):
            t0 = time.perf_counter_ns()
            value = fn()
            wire = host.last_wire
            capture = value.get('capture', value)
            records.append({'label': label, 'duration_ms': (time.perf_counter_ns() - t0) / 1e6,
                'request_bytes': host.last_request_bytes, 'response_bytes': host.last_wire_bytes,
                'state': capture.get('capture_state'), 'wire': wire})
            records[-1]['work_totals'] = control(port, op='stats')
            if world_reuse:
                records[-1]['decoder_work_totals'] = host._scene_decoder.work_totals()
            return value

        cold = query('mcp_task_cold', lambda: host.capture_task_scene(selectors))
        assert abs(gap(cold) - .004) < 1e-7, gap(cold)
        warm = query('mcp_task_warm', lambda: host.capture_task_scene(selectors))
        assert cold['capture_state'] == warm['capture_state']
        assert cold == warm
        assert records[0]['work_totals'][0]['stats']['resource_builds'] == 2
        assert records[1]['work_totals'][0]['stats']['resource_builds'] == 2
        assert len(records[1]['wire']['resources']) == 0
        if world_reuse:
            assert records[0]['decoder_work_totals'] == records[1]['decoder_work_totals']
            unchanged_work = records[1]['work_totals'][0]['stats']['world_transforms']
            unchanged_decoder = records[1]['decoder_work_totals']
            control(port, op='color', name='BluePart', color=[1, 0, 0, 1])
            colored = query('mcp_metadata_color', lambda: host.capture_task_scene(selectors))
            assert next(m for m in colored['meshes'] if m['name'] == 'BluePart')['color_rgb'] == [255, 0, 0]
            control(port, op='active', name='GreyBase')
            active = query('mcp_metadata_active', lambda: host.capture_task_scene(selectors))
            assert next(m for m in active['meshes'] if m['name'] == 'GreyBase')['is_focal_target'] is True
            control(port, op='rename', name='BluePart', new_name='BlueMeta')
            renamed = query('mcp_metadata_rename', lambda: host.capture_task_scene(
                [{'name': 'BlueMeta'}, {'name': 'GreyBase'}]))
            assert {m['name'] for m in renamed['meshes']} == {'BlueMeta', 'GreyBase'}
            control(port, op='rename', name='BlueMeta', new_name='BluePart')
            query('mcp_metadata_restore_name', lambda: host.capture_task_scene(selectors))
            for record in records[2:6]:
                assert record['work_totals'][0]['stats']['world_transforms'] == unchanged_work
                assert record['work_totals'][0]['stats']['resource_builds'] == 2
                assert record['decoder_work_totals'] == unchanged_decoder
                assert len(record['wire']['resources']) == 0
        control(port, op='translate', name='BluePart', dz=.002)
        pose = query('mcp_pose_change', lambda: host.capture_task_scene(selectors))
        assert abs(gap(pose) - .006) < 1e-7, gap(pose)
        assert pose['capture_state'] != warm['capture_state']
        assert records[-1]['work_totals'][0]['stats']['resource_builds'] == 2
        assert len(records[-1]['wire']['resources']) == 0
        if world_reuse:
            assert records[-1]['decoder_work_totals']['world_transforms'] == 3
            assert records[-1]['decoder_work_totals']['transformed_vertices'] == 24
        control(port, op='mesh', name='BluePart', dz=-.001)
        mesh = query('mcp_mesh_change', lambda: host.capture_task_scene(selectors))
        assert abs(gap(mesh) - .005) < 1e-7, gap(mesh)
        assert records[-1]['work_totals'][0]['stats']['resource_builds'] == 3
        assert len(records[-1]['wire']['resources']) == 1
        if world_reuse:
            assert records[-1]['decoder_work_totals']['world_transforms'] == 4
            assert records[-1]['decoder_work_totals']['transformed_vertices'] == 32
        full = query('mcp_full', host.capture_scene)
        assert abs(gap(full) - gap(mesh)) < 1e-12
        nearest = lambda: host.capture_nearest_candidates(None, time.perf_counter_ns()+15_000_000_000,
            64*1024*1024, selector={'name': 'BluePart'})
        near = query('mcp_nearest', nearest)
        assert abs(gap(near['capture']) - gap(full)) < 1e-12
        query('mcp_nearest_warm', nearest)
        if world_reuse:
            assert records[-1]['decoder_work_totals'] == records[-2]['decoder_work_totals'] == records[-3]['decoder_work_totals']
            assert records[-1]['work_totals'][0]['stats']['world_transforms'] == records[-3]['work_totals'][0]['stats']['world_transforms']
        control(port, op='rename', name='BluePart', new_name='BlueRenamed')
        missing = query('mcp_rename_old_name', lambda: host.capture_task_scene(selectors))
        assert not any(m['name'] == 'BluePart' for m in missing['meshes'])
        control(port, op='rename', name='BlueRenamed', new_name='BluePart')
        before_replace = query('mcp_before_replace', lambda: host.capture_task_scene(selectors))
        control(port, op='replace', name='BluePart')
        replaced = query('mcp_same_name_replacement', lambda: host.capture_task_scene(selectors))
        assert replaced['capture_state'] != before_replace['capture_state']
        assert abs(gap(replaced) - .009) < 1e-7
        control(port, op='units', scale=.1)
        scaled = query('mcp_units', lambda: host.capture_task_scene(selectors))
        assert abs(gap(scaled) - gap(replaced) * .1) < 1e-8
        control(port, op='frame', frame=2)
        framed = query('mcp_frame', lambda: host.capture_task_scene(selectors))
        assert framed['capture_state'] != scaled['capture_state']
        control(port, op='undo')
        undo = query('mcp_undo_invalidation', lambda: host.capture_task_scene(selectors))
        assert undo['capture_state']['epoch'] != framed['capture_state']['epoch']
        control(port, op='scene')
        scene = query('mcp_scene_switch', lambda: host.capture_task_scene(selectors))
        assert abs(gap(scene) - .014) < 1e-7
        assert scene['capture_state'] != undo['capture_state']
        control(port, op='delete', name='BluePart')
        deleted = query('mcp_delete', lambda: host.capture_task_scene(selectors))
        assert not any(m['name'] == 'BluePart' for m in deleted['meshes'])
        control(port, op='load', path=str(fixture))
        loaded = query('mcp_file_reload', lambda: host.capture_task_scene(selectors))
        assert abs(gap(loaded) - .004) < 1e-7
        assert loaded['capture_state'] != scene['capture_state']
        host.close()
        host = MeasuredHost(ROOT, port=port, timeout_s=20)
        reconnect = query('mcp_connector_reconnect', lambda: host.capture_task_scene(selectors))
        assert abs(gap(reconnect) - .004) < 1e-7
        records.append({'label': 'resident_stats', 'stats': control(port, op='stats')})
        source_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
        t0 = time.perf_counter_ns()
        with BlenderProcessHost(executable, fixture) as owned:
            records.append({'label': 'owned_startup', 'duration_ms': (time.perf_counter_ns()-t0)/1e6})
            for label, fn in [('owned_task', lambda: owned.capture_task_scene(selectors)),
                              ('owned_task_warm', lambda: owned.capture_task_scene(selectors)),
                              ('owned_nearest', lambda: owned.capture_nearest_candidates(None,
                                  time.perf_counter_ns()+15_000_000_000,64*1024*1024, selector={'name':'BluePart'})),
                              ('owned_nearest_warm', lambda: owned.capture_nearest_candidates(None,
                                  time.perf_counter_ns()+15_000_000_000,64*1024*1024, selector={'name':'BluePart'}))]:
                t0 = time.perf_counter_ns()
                value = fn()
                assert abs(gap(value.get('capture', value)) - .004) < 1e-7
                records.append({'label': label, 'duration_ms': (time.perf_counter_ns()-t0)/1e6,
                                'state': value.get('capture', value).get('capture_state')})
                if world_reuse:
                    records[-1]['decoder_work_totals'] = owned._scene_decoder.work_totals()
            if world_reuse:
                assert all(record['decoder_work_totals'] == records[-4]['decoder_work_totals'] for record in records[-4:])
        assert source_hash == hashlib.sha256(fixture.read_bytes()).hexdigest()
        assert source_hashes == {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in product_paths}
        from human_eye_plugin.runtime_identity import runtime_identity
        identity = runtime_identity()
        result = {'passed': True, 'fixture_startup_ms': startup_ms, 'records': records,
                  'fixture_unchanged': True, 'world_reuse_checks': world_reuse, 'product_sources': source_hashes,
                  'source_sha256': identity['source_sha256'], 'source_count': len(identity['source_files'])}
        (output / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf8')
        print(json.dumps({'passed': True, 'records': len(records), 'result': str(output/'result.json')}))
    except BaseException as exc:
        (output/'result.json').write_text(json.dumps({'passed':False, 'error':repr(exc), 'records':records},
            indent=2, allow_nan=False), encoding='utf8')
        raise
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        log.close()


if __name__ == '__main__':
    main()
