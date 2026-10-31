"""One immutable episode clock and independent owned-resource cancellation.

Expiry callbacks must be nonblocking: revoke admission, shut down sockets and
kill only the resource owned by that adapter. Process waiting/logging belongs
to a separately bounded cleanup step. This is not an OS hard-realtime promise.
"""
from __future__ import annotations

import math
import threading
import time
import uuid


class DeadlineExceeded(TimeoutError):
    pass


class EpisodeDeadline:
    def __init__(self, seconds, clock=time.monotonic, started=None, watchdog=True):
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 180:
            raise ValueError('episode duration must be finite and in (0,180]')
        if not callable(clock) or type(watchdog) is not bool:
            raise ValueError('invalid deadline clock/watchdog')
        beginning = clock() if started is None else started
        if type(beginning) not in (int, float) or not math.isfinite(beginning):
            raise ValueError('invalid monotonic start')
        self._started = float(beginning)
        self._expires_at = self._started + float(seconds)
        if not math.isfinite(self._expires_at) or self._expires_at <= self._started:
            raise ValueError('deadline is not representable')
        self._clock = clock
        self._id = uuid.uuid4().hex
        self._lock = threading.RLock()
        self._expired = threading.Event()
        self._callbacks = {}
        self._next_callback = 0
        self._reason = None
        self._callback_errors = []
        self._closed = False
        self._timer = None
        if watchdog:
            self._timer = threading.Timer(max(0., self._expires_at - clock()), self._watchdog_wake)
            self._timer.daemon = True
            self._timer.start()

    def _watchdog_wake(self):
        # Windows timer wakes and monotonic readings have finite resolution.
        # A premature wake must re-arm rather than revoke a still-valid task.
        with self._lock:
            if self._closed or self._expired.is_set():
                return
            left = self._expires_at - self._clock()
            if left > 0:
                self._timer = threading.Timer(left,self._watchdog_wake)
                self._timer.daemon = True
                self._timer.start()
                return
        self.expire()

    @property
    def started(self): return self._started

    @property
    def expires_at(self): return self._expires_at

    @property
    def clock(self): return self._clock

    @property
    def episode_id(self): return self._id

    @property
    def watchdog_active(self):
        return self._timer is not None and not self._closed and not self._expired.is_set()

    @property
    def expired(self):
        if self._clock() >= self._expires_at:
            self.expire()
        return self._expired.is_set()

    def remaining(self, cap=None):
        if cap is not None and (type(cap) not in (int, float) or not math.isfinite(cap) or cap <= 0):
            raise ValueError('local timeout cap must be positive finite')
        left = self._expires_at - self._clock()
        if self._closed:
            raise DeadlineExceeded('episode deadline has been closed after cleanup')
        if self._expired.is_set() or left <= 0:
            self.expire()
            raise DeadlineExceeded('episode absolute deadline exhausted')
        return left if cap is None else min(left, float(cap))

    def check(self):
        self.remaining()

    def _invoke(self, callback):
        try:
            callback()
        except BaseException as exc:
            with self._lock:
                self._callback_errors.append(type(exc).__name__)

    def add_expiry_callback(self, callback):
        if not callable(callback):
            raise ValueError('expiry callback must be callable')
        with self._lock:
            if self._closed:
                raise DeadlineExceeded('cannot register resources after deadline cleanup')
            self._next_callback += 1
            key = self._next_callback
            immediate = self._expired.is_set() or self._clock() >= self._expires_at
            if not immediate:
                self._callbacks[key] = callback
        if immediate:
            self.expire()
            self._invoke(callback)
        def unregister():
            with self._lock:
                self._callbacks.pop(key, None)
        return unregister

    def expire(self, reason='episode_absolute_deadline'):
        with self._lock:
            if self._expired.is_set():
                return
            self._reason = str(reason)
            self._expired.set()
            callbacks = list(self._callbacks.values())
            self._callbacks.clear()
        # Never hold the registry lock while an adapter touches its resources.
        for callback in callbacks:
            self._invoke(callback)

    def close(self):
        """Stop admission/timer after trusted owned cleanup; never renew time."""
        with self._lock:
            self._closed = True
            timer = self._timer
        if timer is not None:
            timer.cancel()

    def snapshot(self):
        with self._lock:
            return {'episode_id':self._id,'started_monotonic':self._started,
                'deadline_monotonic':self._expires_at,'expired':self._expired.is_set(),
                'reason':self._reason,'timer_closed':self._closed,
                'watchdog_active':self.watchdog_active,
                'registered_owned_callbacks':len(self._callbacks),
                'callback_errors':list(self._callback_errors)}
