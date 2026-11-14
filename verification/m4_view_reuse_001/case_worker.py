"""One isolated installed-owner case. Root freezes this file before execution."""

import time

ENTRY_NS = time.perf_counter_ns()

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import threading
import traceback


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def error_record(error):
    return dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc())


def memory_and_files(owner):
    """Count observable arrays once even when view/ref aliases share them."""
    unique = {}

    def add(value, label):
        if not isinstance(value, owner.session.np.ndarray):
            return
        row = unique.setdefault(id(value), dict(dtype=str(value.dtype), shape=list(value.shape),
                                               nbytes=int(value.nbytes), labels=[]))
        row['labels'].append(label)

    for i, mesh in enumerate(owner.session.meshes):
        for name in ('vertices', 'faces', 'edges'):
            add(getattr(mesh, name), 'mesh.' + str(i) + '.' + name)
    for i, values in enumerate(owner.session.face_ids):
        add(values, 'source_face_ids.' + str(i))
    for ref, arrays in owner.session.buffers.items():
        for name, values in arrays.items():
            add(values, ref + '.' + name)
    files = []
    for path in owner.out.rglob('*'):
        if path.is_file() and path.suffix.lower() in ('.png', '.npz'):
            files.append(dict(path=str(path), bytes=path.stat().st_size))
    return dict(unique_array_objects=len(unique), unique_array_payload_bytes=sum(r['nbytes'] for r in unique.values()),
                arrays=list(unique.values()), files=files,
                raw_buffer_unique_bytes=sum(r['nbytes'] for r in unique.values()
                    if any(label.endswith('.triangle_ids') for label in r['labels'])),
                scope='Observable mesh/face-ID and consumer-buffer arrays only. Ref/view aliases deduplicated. Product temporaries, allocator peak and RSS unmeasured.')


class Calls:
    def __init__(self, module, owner, output):
        self.module = module
        self.owner = owner
        self.output = output
        self.rows = []
        self.threads = []

    def call(self, tool, arguments, *, expect_error=False):
        started = time.perf_counter_ns()
        number = len(self.rows) + 1
        folder = self.output / ('request_' + str(number).zfill(2))
        folder.mkdir()
        message = dict(jsonrpc='2.0', id=number, method='tools/call',
                       params=dict(name=tool, arguments=arguments))
        request = dict(request_id=number, operation='attached_mcp', args=dict(kind='native', message=message))
        request_bytes = self.module.encoded(request)
        (folder / 'TCP_TX.bin').write_bytes(request_bytes)
        response = self.owner.handle(message)
        reply = dict(request_id=number, ok=True, result=response)
        payload = self.module.encoded(reply)
        (folder / 'TCP_RX.bin').write_bytes(payload)
        sender, receiver = socket.socketpair()
        received = bytearray()
        receive_errors = []

        def receive():
            try:
                receiver.settimeout(max(.01, min(10., (self.owner.deadline_ns-time.perf_counter_ns())/1e9)))
                while True:
                    block = receiver.recv(65536)
                    if not block:
                        break
                    received.extend(block)
            except BaseException as error:
                receive_errors.append(error_record(error))
            finally:
                receiver.close()

        thread = threading.Thread(target=receive)
        self.threads.append(thread)
        confirmed = False
        send_error = None
        try:
            thread.start()
            sender.settimeout(max(.01, min(10., (self.owner.deadline_ns-time.perf_counter_ns())/1e9)))
            sender.sendall(payload)
            sender.shutdown(socket.SHUT_WR)
            thread.join(timeout=10)
            if thread.is_alive() or receive_errors or bytes(received) != payload:
                raise RuntimeError('actual_local_socket_reply_mismatch')
            confirmed = True
        except BaseException as error:
            send_error = error_record(error)
            raise
        finally:
            sender.close()
            if thread.is_alive():
                receiver.close()
                thread.join(timeout=5)
            receiver.close()
            self.owner.complete_observation_delivery(message, reply, confirmed)
            self.owner.record_transport(request_bytes, reply, confirmed, send_error,
                                        started, time.perf_counter_ns())
        snapshot = dict(owner_metrics=self.owner.session.metrics(), memory=memory_and_files(self.owner))
        closed = time.perf_counter_ns()
        row = dict(sequence=number, tool=tool, arguments=arguments, started_ns=started, closed_ns=closed,
                   elapsed_ns=closed-started, response_sha256=hashlib.sha256(payload).hexdigest(),
                   actual_local_socket_bytes=len(received), local_socket_confirmed=confirmed,
                   transport_scope='Actual local socket pair, same Owner handler/encoder/delivery/transport functions; no CLI or provider.',
                   is_error=response['result']['isError'], snapshot=snapshot)
        self.rows.append(row)
        save(folder / 'CHECKPOINT.json', row)
        if row['is_error'] is not expect_error:
            raise AssertionError('unexpected_tool_error_state:' + json.dumps(response, ensure_ascii=False))
        return response


def frames(response):
    return json.loads(response['result']['content'][0]['text'])['images']


def frame_arrays(owner, ref):
    return owner.session.buffers[ref]


def assert_dual_owner(owner):
    checked = []
    for ref, row in owner.session.by_ref.items():
        arrays = frame_arrays(owner, ref)
        if 'patch_owners' not in arrays or 'triangle_ids' not in arrays:
            continue
        np = owner.session.np
        raw, patch = arrays['triangle_ids'], arrays['patch_owners']
        assert raw.dtype == np.dtype('int32') and raw.shape == patch.shape
        mapping, offsets = arrays['face_patch_ids'], arrays['face_patch_offsets']
        foreground = raw >= 0
        assert np.all(raw[foreground] < len(mapping))
        assert np.array_equal(patch[foreground], mapping[raw[foreground]])
        assert np.all(raw[~foreground] == -1)
        assert np.all(patch[~foreground] == -1)
        for obj in range(len(offsets)-1):
            mask = foreground & (raw >= offsets[obj]) & (raw < offsets[obj+1])
            assert np.all(arrays['owners'][mask] == obj)
        with np.load(row['NPZ'], allow_pickle=False) as archive:
            for name, value in arrays.items():
                assert np.array_equal(archive[name], value, equal_nan=True) if value.dtype.kind in 'fc' else np.array_equal(archive[name], value)
        checked.append(ref)
    return checked


def product_reuse(owner, calls):
    calls.call('active_observation', dict(include_images=True))
    session = owner.session
    assert len(session.attempts) == 3
    before = dict(session.by_ref)
    ref = session.by_view['SCENE']['ref']
    arrays = session.buffers[ref]
    publication = {r: (row['PNG'], row['NPZ'], row['PNG_sha256'], row['NPZ_sha256']) for r, row in before.items()}
    for _ in range(3):
        response = calls.call('render_views', dict(names=['SCENE'], include_images=True))
        frame = frames(response)[0]
        assert frame['cached'] is True and frame['new_raster_attempts'] == 0 and frame['ref'] == ref
        assert session.buffers[ref] is arrays and session.buffers['SCENE'] is arrays
        assert all(session.buffers[ref][name] is value for name, value in arrays.items())
    assert len(session.attempts) == 3 and sum(a['view_name']=='SCENE' for a in session.attempts) == 1
    assert publication == {r: (row['PNG'], row['NPZ'], row['PNG_sha256'], row['NPZ_sha256']) for r,row in session.by_ref.items()}
    assert len(assert_dual_owner(owner)) == 3
    return dict(checks=['I01','I02','I03','I08'], expected_rasters=3,
                old_refs_preserved=True, same_array_objects_reused=True)


def native_flow(owner, calls):
    session = owner.session
    first = frames(calls.call('render_views', dict(names=['SCENE'], include_images=True)))[0]
    old_ref = first['ref']
    old_arrays = session.buffers[old_ref]
    repeated = frames(calls.call('render_views', dict(names=['SCENE'], include_images=True)))[0]
    assert repeated['cached'] is True and repeated['ref'] == old_ref
    duplicate = frames(calls.call('render_views', dict(names=['SCENE','SCENE'], include_images=False)))
    assert len(session.attempts) == 1 and all(f['ref']==old_ref and f['cached'] for f in duplicate)
    mixed = frames(calls.call('render_views', dict(names=['SCENE','BACK','BACK'], include_images=False)))
    assert len(session.attempts) == 2 and mixed[0]['cached'] and mixed[1]['ref']==mixed[2]['ref'] and mixed[2]['cached']
    fresh = frames(calls.call('render_views', dict(names=['SCENE','SCENE'], include_images=True, fresh=True)))
    assert len(session.attempts) == 3 and fresh[0]['ref']!=old_ref and fresh[1]['ref']==fresh[0]['ref']
    assert fresh[0]['cached'] is False and fresh[1]['cached'] is True
    assert session.buffers[old_ref] is old_arrays and session.buffers['SCENE'] is session.buffers[fresh[0]['ref']]
    pose = session.poses['SCENE']
    pose['view_matrix'][0][3] += 1/512
    camera = frames(calls.call('render_views', dict(names=['SCENE'], include_images=False)))[0]
    assert len(session.attempts) == 4 and camera['reuse_reason']=='binding_changed'
    pose['projection_matrix'][0][0] *= .99
    projection = frames(calls.call('render_views', dict(names=['SCENE'], include_images=False)))[0]
    assert len(session.attempts) == 5 and projection['reuse_reason']=='binding_changed'
    old_generation = session._owner_generation
    session._owner_generation = (old_generation[0], 'controlled-integration-generation-change')
    generation = frames(calls.call('render_views', dict(names=['SCENE'], include_images=False)))[0]
    assert len(session.attempts) == 6 and generation['reuse_reason']=='binding_changed'
    current_generation = session._owner_generation
    session._owner_generation = ('controlled-schema-invalidation-only', current_generation[1])
    assert session.by_view['SCENE']['_reuse_binding'] != session._view_binding('SCENE')
    session._owner_generation = current_generation
    rejected = []
    original_source = session.source_inputs['scene_sha256']
    session.source_inputs['scene_sha256'] = '0'*64
    try:
        response = calls.call('render_views', dict(names=['SCENE'], include_images=False), expect_error=True)
        assert owner.logs[-1]['error']['message']=='source_or_object_order_changed_new_session_required'
        rejected.append('source_generation')
    finally:
        session.source_inputs['scene_sha256'] = original_source
    original_meshes = session.meshes
    session.meshes = []
    try:
        response = calls.call('render_views', dict(names=['SCENE'], include_images=False), expect_error=True)
        assert owner.logs[-1]['error']['message']=='source_or_object_order_changed_new_session_required'
        rejected.append('object_deletion_or_order')
    finally:
        session.meshes = original_meshes
    size = pose['size_px']
    pose['size_px'] = [256,256]
    try:
        response = calls.call('render_views', dict(names=['SCENE'], include_images=False), expect_error=True)
        assert owner.logs[-1]['error']['message']=='registered_512_camera_size_required'
        rejected.append('non512_size')
    finally:
        pose['size_px'] = size
    # This input has one mesh. Reversing one item is accurately a no-op.
    assert len(session.meshes)==1 and list(reversed(session.meshes))==session.meshes
    control_results = []
    original_faces = session.face_ids
    session.face_ids = [values.copy() for values in original_faces]
    try:
        try:
            session.render_views(['SCENE'])
        except ValueError as error:
            assert str(error)=='source_or_object_order_changed_new_session_required'
            control_results.append('face_array_identity_replacement_rejected')
        else:
            raise AssertionError('face_array_replacement_was_a_stale_hit')
    finally:
        session.face_ids = original_faces
    session.meshes = [copy.copy(mesh) for mesh in original_meshes]
    try:
        try:
            session.render_views(['SCENE'])
        except ValueError as error:
            assert str(error)=='source_or_object_order_changed_new_session_required'
            control_results.append('mesh_instance_replacement_rejected')
        else:
            raise AssertionError('mesh_instance_replacement_was_a_stale_hit')
    finally:
        session.meshes = original_meshes
    assert len(session.attempts) == 6 and session.buffers[old_ref] is old_arrays
    return dict(checks=['I04','I05','I06','I07','I09'], expected_rasters=6,
                rejected_without_raster=rejected, direct_validity_controls=control_results,
                single_object_reversal='No-op, not evidence for pure multi-object order invalidation.',
                generation_control='Actual map-token miss plus schema-token invalidation-only check; no new owner format is asserted.')


def legacy_capability(owner, calls, control):
    session = owner.session
    frame = control['legacy_frame']
    for name in ('image_path','arrays_path'):
        expected = frame['image_sha256'] if name=='image_path' else frame['arrays_sha256']
        assert hashlib.sha256(Path(frame[name]).read_bytes()).hexdigest() == expected
    with session.np.load(frame['arrays_path'], allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    assert 'triangle_ids' not in arrays
    ref = 'legacy-readonly:' + frame['arrays_sha256']
    row = dict(view_name=frame['view_name'])
    session._register(row, Path(frame['image_path']), Path(frame['arrays_path']), ref, arrays, frame_metadata=frame)
    assert session.by_ref[ref]['triangle_id_capability'] is False
    response = frames(calls.call('render_views', dict(names=['SCENE'], include_images=False)))[0]
    assert response['reuse_reason']=='raw_triangle_capability_missing' and response['ref']!=ref
    assert response['triangle_id_capability'] is True and len(session.attempts)==1
    again = frames(calls.call('render_views', dict(names=['SCENE'], include_images=False)))[0]
    assert again['cached'] and again['ref']==response['ref'] and len(session.attempts)==1
    return dict(checks=['I10'], expected_rasters=1, legacy_readonly_capability_missing=True,
                legacy_scope='Actual sealed old NPZ is privately registered as a capability-miss control, never accepted as a new observation.')


def publication_failure(owner, calls):
    session = owner.session
    good = frames(calls.call('render_views', dict(names=['SCENE'], include_images=True)))[0]
    good_ref = good['ref']
    good_row = session.by_ref[good_ref]
    good_arrays = session.buffers[good_ref]
    original = session.np.savez_compressed
    called = []

    def fail_once(*args, **kwargs):
        called.append(True)
        raise OSError('registered-post-raster-publication-control')

    session.np.savez_compressed = fail_once
    try:
        calls.call('render_views', dict(names=['SCENE'], include_images=False, fresh=True), expect_error=True)
    finally:
        session.np.savez_compressed = original
    assert len(called)==1 and len(session.attempts)==2
    assert session.attempts[1]['status']=='postprocess_failed'
    assert session.by_view['SCENE'] is good_row and session.by_ref[good_ref] is good_row
    assert session.buffers['SCENE'] is good_arrays and session.buffers[good_ref] is good_arrays
    assert len(session.by_ref)==1
    old_hit = frames(calls.call('render_views', dict(names=['SCENE'], include_images=True)))[0]
    assert old_hit['cached'] and old_hit['ref']==good_ref and len(session.attempts)==2
    recovered = frames(calls.call('render_views', dict(names=['SCENE'], include_images=True, fresh=True)))[0]
    reused = frames(calls.call('render_views', dict(names=['SCENE'], include_images=True)))[0]
    assert len(session.attempts)==3 and recovered['ref']==reused['ref'] and reused['cached'] is True
    assert recovered['ref']!=good_ref and session.buffers[good_ref] is good_arrays
    assert session.buffers['SCENE'] is session.buffers[recovered['ref']]
    assert all(session.np.array_equal(values,session.buffers[recovered['ref']][name],equal_nan=True)
               for name,values in good_arrays.items())
    return dict(checks=['I11'], expected_rasters=3, failed_attempt_charged=True,
                partial_files_preserved=True, incomplete_frame_not_cached=True,
                prior_good_ref_preserved=True, old_good_hit_then_new_good_hit=True)


def benchmark(owner, calls, variant):
    calls.call('active_observation', dict(include_images=True))
    for _ in range(3):
        calls.call('render_views', dict(names=['SCENE'], include_images=True))
    assert len(owner.session.attempts) == (6 if variant=='old' else 3)
    return dict(checks=['fixed_cost_workflow'], expected_rasters=6 if variant=='old' else 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    options = parser.parse_args()
    config = read(options.config)
    control = config['verification_control']
    output = Path(control['output'])
    output.mkdir(parents=True, exist_ok=False)
    owner = None
    calls = None
    errors, close_errors = [], []
    outcome = None
    try:
        source = control['bridge']
        assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()==source['sha256']
        specification = importlib.util.spec_from_file_location('_view_reuse_actual_bridge', source['path'])
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        owner = module.Owner(config)
        calls = Calls(module, owner, output)
        mode = control['mode']
        if mode=='benchmark':
            outcome = benchmark(owner, calls, control['variant'])
        elif mode=='product_then_reuse':
            outcome = product_reuse(owner, calls)
        elif mode=='native_batch_fresh':
            outcome = native_flow(owner, calls)
        elif mode=='legacy_capability':
            outcome = legacy_capability(owner, calls, control)
        elif mode=='publication_failure':
            outcome = publication_failure(owner, calls)
        else:
            raise ValueError('registered_mode_required')
    except BaseException as error:
        errors.append(error_record(error))
    finally:
        close = None
        if owner is not None:
            try:
                all_threads_closed = calls is None or all(not thread.is_alive() for thread in calls.threads)
                close = owner.close(all_threads_closed, close_errors)
            except BaseException as error:
                close_errors.append(error_record(error))
        closed = time.perf_counter_ns()
        request_rows = [] if calls is None else calls.rows
        checkpoints = {}
        if control['mode']=='benchmark' and request_rows:
            for label,index in [('first',0),('first_plus_one_repeat',1),('first_plus_three_repeats',3)]:
                if index<len(request_rows):
                    end=request_rows[index]['closed_ns']
                    checkpoints[label]=dict(started_ns=ENTRY_NS,closed_ns=end,elapsed_ns=end-ENTRY_NS,
                        scope='Worker entry before bridge import/Owner/array setup through actual tool handling, encoding/local socket delivery, callbacks, transport metrics and bounded observational array/file snapshot. Bootstrap/interpreter startup are separately recorded by parent.')
        result = dict(schema='view-reuse-owner-case-v1', mode=control['mode'],variant=control.get('variant','new'),
            process_id=__import__('os').getpid(), started_ns=ENTRY_NS,closed_ns=closed,elapsed_ns=closed-ENTRY_NS,
            passed=not errors and not close_errors and close is not None and close['confirmed'] is True,
            errors=errors,close_errors=close_errors,outcome=outcome,requests=request_rows,checkpoints=checkpoints,
            owner_close=close,new_model_CLI_Blender_calls=0,
            scope='Real installed Owner and local byte delivery; no model consumer or GUI. Closure/source guard included in worker total, result publication excluded.')
        save(output/'WORKER_RESULT.json',result)
    print(json.dumps(dict(passed=result['passed'],mode=control['mode'],process_id=result['process_id'])))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
