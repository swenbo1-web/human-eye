"""Verification-only, process-local meters for SCALE-DIAG-001.

``install(service)`` instruments the service's existing host/read context and
the already imported product functions. It does not change product sources,
arguments, budgets, cache policy, or return values. Use one serial runner per
process; call ``close()`` when finished. ``reset()`` resets only measurements,
never the service's caches.

All durations are inclusive wall time. Nested stages must not be added. The
outer runner includes wrapper overhead; no estimated overhead is subtracted.
Socket bytes are observed at successful send/receive boundaries. A failed
sendall may have sent an unknown prefix and is explicitly marked inexact.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import wraps
import importlib
import time


_ACTIVE_METER = None
_MAX_DETAIL_ROWS = 1024
_MISSING = object()


def _argument(args, kwargs, position, name, default=None):
    return args[position] if len(args) > position else kwargs.get(name, default)


def _buffer_size(value):
    return memoryview(value).nbytes


class _SocketProxy:
    """Delegate socket behavior while observing bytes, without retaining data."""

    def __init__(self, connection, meter):
        self._connection = connection
        self._meter = meter

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, *args):
        return self._connection.__exit__(*args)

    def sendall(self, data, *args, **kwargs):
        size = _buffer_size(data)
        self._meter._counts['socket_send_attempt_bytes'] += size
        start = time.perf_counter_ns()
        failed = False
        try:
            result = self._connection.sendall(data, *args, **kwargs)
            self._meter._counts['socket_send_bytes'] += size
            return result
        except BaseException:
            failed = True
            self._meter._counts['socket_send_partial_unknown_calls'] += 1
            raise
        finally:
            self._meter._record('socket.sendall', start, failed)

    def send(self, data, *args, **kwargs):
        self._meter._counts['socket_send_attempt_bytes'] += _buffer_size(data)
        start = time.perf_counter_ns()
        failed = False
        try:
            sent = self._connection.send(data, *args, **kwargs)
            self._meter._counts['socket_send_bytes'] += sent
            return sent
        except BaseException:
            failed = True
            self._meter._counts['socket_send_partial_unknown_calls'] += 1
            raise
        finally:
            self._meter._record('socket.send', start, failed)

    def recv(self, *args, **kwargs):
        start = time.perf_counter_ns()
        failed = False
        try:
            data = self._connection.recv(*args, **kwargs)
            self._meter._counts['socket_recv_bytes'] += len(data)
            self._meter._counts['socket_recv_calls'] += 1
            return data
        except BaseException:
            failed = True
            raise
        finally:
            self._meter._record('socket.recv', start, failed)

    def recv_into(self, *args, **kwargs):
        start = time.perf_counter_ns()
        failed = False
        try:
            received = self._connection.recv_into(*args, **kwargs)
            self._meter._counts['socket_recv_bytes'] += received
            self._meter._counts['socket_recv_calls'] += 1
            return received
        except BaseException:
            failed = True
            raise
        finally:
            self._meter._record('socket.recv_into', start, failed)


class Meter:
    """One serial process's verification instrumentation and detached results."""

    def __init__(self, service):
        self.service = service
        self.host = service.host
        self.context = service._read_context
        service_module = getattr(service.observe, '__module__', type(service).__module__)
        package = service_module.rsplit('.', 1)[0]
        self.modules = {name: importlib.import_module(package + '.' + name) for name in (
            'live_service', 'task_query', 'surface_proximity', 'surface_geometry', 'telemetry')}
        self._patches = []
        self._closed = False
        self._bvh_depth = 0
        self._stages = {}
        self._counts = Counter()
        self._commands = Counter()
        self._details = {}
        self._issues = []
        self._baseline = None

    def _record(self, name, started_ns, failed=False):
        elapsed = max(0, time.perf_counter_ns() - started_ns)
        row = self._stages.setdefault(name, dict(calls=0, duration_ns=0, max_ns=0, errors=0))
        row['calls'] += 1
        row['duration_ns'] += elapsed
        row['max_ns'] = max(row['max_ns'], elapsed)
        row['errors'] += int(failed)

    def _detail(self, name, value):
        rows = self._details.setdefault(name, [])
        if len(rows) < _MAX_DETAIL_ROWS:
            rows.append(deepcopy(value))
        else:
            self._counts['detail_rows_dropped'] += 1

    def _inspect(self, callback, *args):
        try:
            callback(*args)
        except Exception as exc:
            # Verification extraction may not replace a real product outcome.
            issue = type(exc).__name__ + ':' + str(exc)
            if issue not in self._issues and len(self._issues) < 32:
                self._issues.append(issue)

    def _patch(self, owner, name, replacement):
        own_value = vars(owner).get(name, _MISSING)
        self._patches.append((owner, name, own_value))
        setattr(owner, name, replacement)

    def _timed(self, owner, name, stage, *, before=None, after=None):
        original = getattr(owner, name)

        @wraps(original)
        def measured(*args, **kwargs):
            if before is not None:
                self._inspect(before, args, kwargs)
            start = time.perf_counter_ns()
            failed = False
            try:
                result = original(*args, **kwargs)
            except BaseException:
                failed = True
                raise
            finally:
                self._record(stage, start, failed)
            if after is not None:
                self._inspect(after, args, kwargs, result)
            return result

        self._patch(owner, name, measured)

    def _state(self):
        decoder = getattr(self.host, '_scene_decoder', None)
        state = dict(scene_cache=self.context.scene_cache.stats(),
            read_context=dict(selection_entries=len(self.context._selections),
                result_entries=sum(len(row['results']) for row in self.context._selections.values()),
                normalized_entries=sum(row['normalized'] is not None
                                       for row in self.context._selections.values())),
            decoder_work=decoder.work_totals() if decoder is not None else None)
        if decoder is not None:
            state['decoder_cache'] = dict(resource_entries=len(decoder._resources),
                world_entries=len(decoder._world),
                resource_vertices=sum(len(row['vertices_local']) for row in decoder._resources.values()),
                resource_faces=sum(len(row['faces']) for row in decoder._resources.values()))
        return state

    def reset(self):
        """Start a measurement cell, retaining all product/cache state."""
        if self._closed:
            raise RuntimeError('Meter is closed')
        self._stages = {}
        self._counts = Counter()
        self._commands = Counter()
        self._details = {}
        self._issues = []
        self._baseline = self._state()

    def snapshot(self):
        """Return detached metadata; cache bytes are not process/request RSS."""
        return deepcopy(dict(schema='scale-diag-001-meter-v1',
            timing_semantics='inclusive_do_not_sum_nested',
            overhead='verification_wrappers_included_in_outer_runner_not_subtracted',
            stages=self._stages, counts=self._counts, rpc_by_command=self._commands,
            details=self._details, issues=self._issues, baseline=self._baseline,
            current=self._state(),
            socket_send_bytes_exact=not bool(self._counts['socket_send_partial_unknown_calls']),
            peak_rss=self.modules['telemetry'].process_peak_rss(),
            memory_scope=('scene_cache_accounted_bytes_exclude_read_context_normalized_results_'
                          'decoder_host_and_temporary_python_allocations')))

    def _capture(self, args, kwargs, result):
        if not isinstance(result, dict):
            return
        scene = result.get('capture', result)
        meshes = scene.get('meshes', [])
        self._detail('captures', dict(work=result.get('work'),
            capture_state=scene.get('capture_state'), mesh_count=len(meshes),
            expanded_vertices=sum(len(mesh['vertices']) for mesh in meshes),
            expanded_faces=sum(len(mesh['faces']) for mesh in meshes),
            coverage_count=len(result.get('coverage', []))))

    def _kernel(self, kind, args, kwargs, result):
        left = _argument(args, kwargs, 0, 'left')
        right = _argument(args, kwargs, 1, 'right')
        self._detail('kernels', dict(kind=kind,
            object_ids=[left.object_id, right.object_id],
            faces=[len(left.faces), len(right.faces)],
            vertices=[len(left.vertices), len(right.vertices)],
            measurement_valid=result.get('measurement_valid'), reason=result.get('reason'),
            relation=result.get('relation'), distance_m=result.get('distance_m'),
            work=result.get('work')))

    def _install(self):
        original_connect = self.host._connect

        @wraps(original_connect)
        def connect(*args, **kwargs):
            started = time.perf_counter_ns()
            failed = False
            try:
                connection = original_connect(*args, **kwargs)
                self._counts['socket_connections'] += 1
                return _SocketProxy(connection, self)
            except BaseException:
                failed = True
                raise
            finally:
                self._record('host.connect', started, failed)

        self._patch(self.host, '_connect', connect)
        self._timed(self.host, '_exchange', 'host.exchange', before=lambda args, kwargs:
            self._counts.update(exchange_calls=1,
                exchange_payload_bytes=_buffer_size(_argument(args, kwargs, 0, 'payload'))))

        def request_enter(args, kwargs):
            self._commands[str(_argument(args, kwargs, 0, 'command'))] += 1

        self._timed(self.host, '_request', 'host.request', before=request_enter)
        for name in ('capture_scene', 'capture_task_scene', 'capture_nearest_candidates'):
            self._timed(self.host, name, 'host.' + name, after=self._capture)
        decoder = self.host._scene_decoder

        def decoded(args, kwargs, result):
            packet = _argument(args, kwargs, 0, 'packet')
            resources = packet.get('resources', [])
            self._detail('decoder_packets', dict(schema=packet.get('schema'),
                resource_rows=len(resources),
                resource_vertices=sum(len(row['vertices_local']) for row in resources),
                resource_faces=sum(len(row['faces']) for row in resources),
                live_resource_rows=len(packet.get('live_resources', []))))

        self._timed(decoder, 'apply', 'ipc.resource_decode_and_world_expand', after=decoded)
        self._timed(self.modules['live_service'], '_validated_scene', 'scene.normalize_validate')
        task = self.modules['task_query']
        self._timed(task, 'measure_surface_proximity', 'kernel.surface_proximity',
            after=lambda args, kwargs, result: self._kernel('surface_proximity', args, kwargs, result))
        self._timed(task, 'classify_closed_solids', 'kernel.closed_solid',
            after=lambda args, kwargs, result: self._kernel('closed_solid', args, kwargs, result))

        surface = self.modules['surface_proximity']
        original_admit = surface._admit

        def admission_detail(args, kwargs, failed, reason):
            meshes = _argument(args, kwargs, 0, 'meshes')
            # Actual production callers provide a pair tuple. Do not consume
            # an arbitrary iterator a second time merely for verification.
            if not isinstance(meshes, (list, tuple)):
                self._detail('admission', dict(accepted=not failed, reason=reason,
                    input_counts='unmeasured_nonsequence'))
                return
            sizes = [len(mesh.faces) for mesh in meshes]
            self._detail('admission', dict(faces=sizes, face_sum=sum(sizes),
                triangle_product=sizes[0] * sizes[1] if len(sizes) == 2 else None,
                max_faces=surface.MAX_FACES, max_triangle_pairs=surface.MAX_TRIANGLE_PAIRS,
                accepted=not failed, reason=reason))

        @wraps(original_admit)
        def admit(*args, **kwargs):
            started = time.perf_counter_ns()
            failed = False
            reason = None
            try:
                return original_admit(*args, **kwargs)
            except BaseException as exc:
                failed = True
                reason = str(exc)
                raise
            finally:
                self._record('geometry.admit', started, failed)
                self._inspect(admission_detail, args, kwargs, failed, reason)

        self._patch(surface, '_admit', admit)
        self._timed(surface, '_integer_frame', 'geometry.exact_prepare')
        self._timed(surface, '_nearest', 'geometry.nearest_pair_loop')
        original_bvh = self.modules['surface_geometry']._bvh

        @wraps(original_bvh)
        def bvh(*args, **kwargs):
            outer = self._bvh_depth == 0
            started = time.perf_counter_ns() if outer else None
            self._bvh_depth += 1
            failed = False
            try:
                return original_bvh(*args, **kwargs)
            except BaseException:
                failed = True
                raise
            finally:
                self._bvh_depth -= 1
                if outer:
                    self._record('geometry.closed_bvh_build', started, failed)

        self._patch(self.modules['surface_geometry'], '_bvh', bvh)
        original_activate = self.context.activate

        @wraps(original_activate)
        def activate(*args, **kwargs):
            old_generation = self.context._generation
            old_keys = set(self.context._selections)
            started = time.perf_counter_ns()
            failed = False
            try:
                result = original_activate(*args, **kwargs)
            except BaseException:
                failed = True
                raise
            finally:
                self._record('cache.read_activate', started, failed)
            self._counts['read_generation_changes'] += int(old_generation != self.context._generation)
            hit = self.context._capture in old_keys
            self._counts['read_selection_hits' if hit else 'read_selection_misses'] += 1
            return result

        self._patch(self.context, 'activate', activate)
        original_normalized = self.context.normalized

        @wraps(original_normalized)
        def normalized(*args, **kwargs):
            hit = self.context._normalized is not None
            started = time.perf_counter_ns()
            failed = False
            try:
                result = original_normalized(*args, **kwargs)
            except BaseException:
                failed = True
                raise
            finally:
                self._record('cache.read_normalized', started, failed)
            self._counts['normalized_hits' if hit else 'normalized_misses'] += 1
            return result

        self._patch(self.context, 'normalized', normalized)

        def result_done(args, kwargs, result):
            self._counts['result_cache_hits' if result[1] else 'result_cache_misses'] += 1

        self._timed(self.context, 'result', 'cache.read_result', after=result_done)
        self._timed(self.context, 'reset', 'cache.read_reset', after=lambda args, kwargs, result:
            self._counts.update(read_context_resets=1))
        self.reset()

    def close(self):
        """Restore every attribute, including inherited bound-method lookup."""
        global _ACTIVE_METER
        if self._closed:
            return
        for owner, name, value in reversed(self._patches):
            if value is _MISSING:
                delattr(owner, name)
            else:
                setattr(owner, name, value)
        self._patches.clear()
        self._closed = True
        if _ACTIVE_METER is self:
            _ACTIVE_METER = None

    uninstall = close

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


def install(service):
    """Install once in an isolated, serial verification process."""
    global _ACTIVE_METER
    if _ACTIVE_METER is not None:
        raise RuntimeError('Only one SCALE-DIAG-001 meter may be installed per process')
    meter = Meter(service)
    try:
        meter._install()
    except BaseException:
        meter.close()
        raise
    _ACTIVE_METER = meter
    return meter
