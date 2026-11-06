"""Main-thread loopback pump for one Blender MCP connection at a time."""

import math
import socket
from threading import get_ident, main_thread
import traceback


_CHUNK = 64 * 1024


class Bridge:
    """Own a loopback listener, one entry and one unsent response.

    Construct and drive on the main thread. The entry factory makes an object
    with `handle_line(frame)` and `close()`. Input frames exclude LF. A handler
    response includes LF, and a notification may return None.
    """

    def __init__(self, entry_factory, *, host="127.0.0.1", port=0, interval=0.005):
        self._require_main()
        if host != "127.0.0.1":
            raise ValueError("The bridge listens only on 127.0.0.1")
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("The pump interval must be positive and finite")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind((host, port))
            listener.listen(1)
            listener.setblocking(False)
            self.address = listener.getsockname()
        except BaseException:
            listener.close()
            raise
        self._listener = listener
        self._entry_factory = entry_factory
        self._interval = interval
        self._connection = self._entry = None
        self._input = bytearray()
        self._line_start = self._scan_start = 0
        self._response = None
        self._send_offset = 0
        self._timers = self._timer_callback = None

    @staticmethod
    def _require_main():
        if get_ident() != main_thread().ident:
            raise RuntimeError("The bridge runs on the main thread")

    def _accept(self):
        try:
            connection, _ = self._listener.accept()
        except BlockingIOError:
            return
        try:
            connection.setblocking(False)
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._entry = self._entry_factory()
        except BaseException:
            connection.close()
            raise
        self._connection = connection

    def _drop_client(self):
        connection, self._connection = self._connection, None
        entry, self._entry = self._entry, None
        self._input.clear()
        self._line_start = self._scan_start = 0
        self._response = None
        self._send_offset = 0
        try:
            if connection is not None:
                connection.close()
        finally:
            if entry is not None:
                entry.close()

    def _next_line(self):
        end = self._input.find(b"\n", self._scan_start)
        if end < 0:
            # Keep only the unfinished frame before the next read.
            if self._line_start:
                del self._input[:self._line_start]
                self._line_start = 0
            self._scan_start = len(self._input)
            return None
        frame = bytes(memoryview(self._input)[self._line_start:end])
        self._line_start = self._scan_start = end + 1
        if self._line_start == len(self._input):
            self._input.clear()
            self._line_start = self._scan_start = 0
        return frame

    def _read(self):
        try:
            chunk = self._connection.recv(_CHUNK)
        except BlockingIOError:
            return
        except OSError:
            self._drop_client()
            return
        if chunk:
            self._input.extend(chunk)
        else:
            self._drop_client()

    def _send(self):
        try:
            sent = self._connection.send(memoryview(self._response)[self._send_offset:])
        except BlockingIOError:
            return
        except OSError:
            self._drop_client()
            return
        if not sent:
            self._drop_client()
            return
        self._send_offset += sent
        if self._send_offset == len(self._response):
            self._response = None
            self._send_offset = 0

    def pump(self):
        """Make one nonblocking tick and return the timer interval."""
        self._require_main()
        if self._listener is None:
            return None
        if self._connection is None:
            self._accept()
            if self._connection is None:
                return self._interval
        if self._response is not None:
            self._send()
            return self._interval
        line = self._next_line()
        if line is None:
            self._read()
            line = self._next_line()
        if line is not None:
            try:
                response = self._entry.handle_line(line)
            except BaseException:
                self._drop_client()
                raise
            if response is not None and self._connection is not None:
                self._response = response
                self._send()
        return self._interval if self._listener is not None else None

    def _timer_tick(self):
        try:
            return self.pump()
        except Exception:
            traceback.print_exc()
            self._timers = None
            self.stop()
            return None

    def stop(self):
        """Unregister this pump and close the connection and its entry."""
        self._require_main()
        timers, self._timers = self._timers, None
        callback, self._timer_callback = self._timer_callback, None
        listener, self._listener = self._listener, None
        self._entry_factory = None
        try:
            if timers is not None and timers.is_registered(callback):
                timers.unregister(callback)
        finally:
            try:
                if listener is not None:
                    listener.close()
            finally:
                self._drop_client()


def start(entry_factory, *, host="127.0.0.1", port=0, interval=0.005):
    """Open the listener and schedule its pump in Blender."""
    Bridge._require_main()
    import bpy

    bridge = Bridge(entry_factory, host=host, port=port, interval=interval)
    bridge._timers = bpy.app.timers
    bridge._timer_callback = bridge._timer_tick
    try:
        bridge._timers.register(bridge._timer_callback, first_interval=0.0)
    except BaseException:
        bridge.stop()
        raise
    return bridge
