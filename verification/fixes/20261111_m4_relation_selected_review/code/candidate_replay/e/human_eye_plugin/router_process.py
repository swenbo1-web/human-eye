"""Dependency-free transport from a live host to the external eye runtime.

Load this file directly in Blender or another embedded Python interpreter. Only
the external Python process needs the engine's NumPy and Pillow dependencies.
This module neither imports the engine nor performs any model API requests.
"""
from __future__ import annotations

from collections import deque
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any


_MAX_REQUEST_CHARS = 32 * 1024 * 1024
_MAX_RESPONSE_CHARS = 64 * 1024 * 1024


class RouterProcessError(RuntimeError):
    """The router process failed; discard this connection and observe again."""

    def __init__(self, message: str, diagnostics: tuple[str, ...] = ()) -> None:
        self.diagnostics = diagnostics
        super().__init__(message)


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number: " + value)


class ExternalRouterProcess:
    """Persistent JSON-lines client whose timeout covers writes and reads."""

    def __init__(self, python_executable: str | os.PathLike[str],
                 project_root: str | os.PathLike[str], *, readback_atol_m: float = 1e-6,
                 quad_size: int = 64, timeout_s: float = 30.0) -> None:
        if (isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float))
                or not math.isfinite(timeout_s) or timeout_s <= 0):
            raise ValueError("timeout_s must be finite and greater than zero")
        if (isinstance(readback_atol_m, bool) or not isinstance(readback_atol_m, (int, float))
                or not math.isfinite(readback_atol_m) or not 0 <= readback_atol_m <= 1e-5):
            raise ValueError("readback_atol_m must be finite and in [0, 1e-5]")
        if type(quad_size) is not int or not 64 <= quad_size <= 512:
            raise ValueError("quad_size must be an integer in [64, 512]")
        executable = Path(python_executable).expanduser().resolve()
        root = Path(project_root).expanduser().resolve()
        if not executable.is_file():
            raise FileNotFoundError("External Python executable does not exist: " + str(executable))
        if not (root / "human_eye_plugin" / "router_server.py").is_file():
            raise ValueError("project_root must contain human_eye_plugin/router_server.py")
        self.timeout_s = float(timeout_s)
        self._lock = threading.RLock()
        self._responses: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=8)
        self._diagnostics: deque[str] = deque(maxlen=64)
        self._sequence = 0
        self._closed = False
        self._poisoned = False
        self._writer: threading.Thread | None = None
        command = [str(executable), "-B", "-m", "human_eye_plugin.router_server",
                   "--readback-atol-m", str(float(readback_atol_m)), "--quad-size", str(quad_size)]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUNBUFFERED"] = "1"
        try:
            self._process = subprocess.Popen(command, cwd=str(root), stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                             text=True, encoding="utf-8", errors="strict", bufsize=1,
                                             shell=False, creationflags=flags, env=environment)
        except OSError as exc:
            raise RouterProcessError("Could not launch the external router: " + str(exc)) from exc
        self._stdout_thread = threading.Thread(target=self._read_stdout, name="human-eye-router-stdout", daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, name="human-eye-router-stderr", daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return tuple(self._diagnostics)

    @property
    def is_alive(self) -> bool:
        return not self._closed and not self._poisoned and self._process.poll() is None

    def _ensure_live(self) -> None:
        if self._closed or self._poisoned:
            raise RouterProcessError("External router connection is closed or invalidated", self.diagnostics)
        if self._process.poll() is not None:
            self._fail("External router exited before the request")

    def handle_event(self, event: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(event, dict):
            raise ValueError("event must be a JSON object")
        with self._lock:
            self._ensure_live()
            self._sequence += 1
            request_id = self._sequence
            payload = json.dumps({"id": request_id, "payload": event}, ensure_ascii=True,
                                 allow_nan=False, separators=(",", ":")) + "\n"
            if len(payload) > _MAX_REQUEST_CHARS:
                raise ValueError("Router request exceeds the 32 MiB transport limit")
            deadline = time.monotonic() + self.timeout_s
            sent: queue.Queue[Any] = queue.Queue(maxsize=1)

            def write_payload() -> None:
                try:
                    assert self._process.stdin is not None
                    self._process.stdin.write(payload)
                    self._process.stdin.flush()
                    sent.put_nowait(None)
                except (OSError, ValueError) as exc:
                    sent.put_nowait(exc)

            # A worker also bounds a stalled pipe write when sending mesh data.
            # It never reads or mutates Blender objects.
            self._writer = threading.Thread(target=write_payload, name="human-eye-router-writer", daemon=True)
            self._writer.start()
            try:
                write_error = sent.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                self._fail("External router request timed out while writing")
            if write_error is not None:
                self._fail("External router input failed: " + str(write_error))
            try:
                kind, response = self._responses.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                self._fail("External router request timed out while waiting for evidence")
            if kind != "response" or self._poisoned:
                self._fail(str(response) if kind != "response" else "External router response stream was invalidated")
            if (not isinstance(response, dict) or type(response.get("id")) is not int
                    or response["id"] != request_id):
                self._fail("External router response ID does not match the request")
            if ("result" in response) == ("error" in response):
                self._fail("External router response must contain exactly one of result or error")
            if "error" in response:
                error = response["error"]
                message = error.get("message", "request rejected") if isinstance(error, dict) else "invalid error response"
                self._fail("External router rejected the event: " + str(message))
            if not isinstance(response["result"], dict):
                self._fail("External router evidence must be a JSON object")
            return response["result"]

    def _enqueue(self, item: tuple[str, Any]) -> None:
        try:
            self._responses.put_nowait(item)
        except queue.Full:
            self._poisoned = True
            self._diagnostics.append("External router emitted unsolicited responses beyond its buffer limit")

    def _read_stdout(self) -> None:
        try:
            assert self._process.stdout is not None
            while True:
                line = self._process.stdout.readline(_MAX_RESPONSE_CHARS + 1)
                if not line:
                    break
                if len(line) > _MAX_RESPONSE_CHARS:
                    self._enqueue(("failure", "External router response exceeds the 64 MiB transport limit"))
                    return
                try:
                    response = json.loads(line, parse_constant=_reject_constant)
                    json.dumps(response, allow_nan=False)
                except (ValueError, TypeError) as exc:
                    self._enqueue(("failure", "Invalid external router response JSON: " + str(exc)))
                    return
                self._enqueue(("response", response))
        except (OSError, ValueError) as exc:
            self._enqueue(("failure", "External router output failed: " + str(exc)))
        finally:
            self._enqueue(("failure", "External router closed its output stream"))

    def _read_stderr(self) -> None:
        try:
            assert self._process.stderr is not None
            while True:
                line = self._process.stderr.readline(4096)
                if not line:
                    break
                self._diagnostics.append(line.rstrip()[:1000])
        except (OSError, ValueError):
            pass

    def _terminate_child(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2.0)

    def _fail(self, reason: str) -> None:
        self._poisoned = True
        self._terminate_child()
        raise RouterProcessError(reason, self.diagnostics)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            # No protocol shutdown event exists. EOF ends the router's loop.
            if not self._poisoned and self._process.poll() is None:
                try:
                    assert self._process.stdin is not None
                    self._process.stdin.close()
                    self._process.wait(timeout=2.0)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    self._terminate_child()
            else:
                self._terminate_child()
            for thread in (self._writer, self._stdout_thread, self._stderr_thread):
                if thread is not None:
                    thread.join(timeout=1.0)
            for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
                if stream is not None:
                    stream.close()

    def __enter__(self) -> "ExternalRouterProcess":
        self._ensure_live()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()


__all__ = ["ExternalRouterProcess", "RouterProcessError"]
