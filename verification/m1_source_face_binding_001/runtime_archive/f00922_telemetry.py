"""Request-local, content-free timing and provider-usage evidence.

Durations use a monotonic clock and are inclusive: nested spans must not be
added together.  A GPU submission span is never a completed GPU calculation.
This module does not infer model usage, inspect host sessions, or write files.
The caller supplies a best-effort writer; writer failures cannot change the
outcome of an already performed host operation.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
import uuid


SCHEMA_VERSION = "1.0"
_CURRENT_TRACE = ContextVar("human_eye_request_trace", default=None)
_CURRENT_SPAN = ContextVar("human_eye_request_span", default=None)
_ACTIVE_LOCK = threading.RLock()
_ACTIVE = set()
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,79}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_REQUEST_SOURCES = frozenset({'service', 'mcp_transport', 'host_hook', 'direct_router'})
_IMAGE_EVENT_LIMIT = 32
_KINDS = frozenset({"cpu", "host", "io", "queue", "startup", "encoding",
                    "provider_request", "gpu_submission", "gpu_synchronized", "other"})
_CORRELATIONS = frozenset({"experiment_id", "trial_id", "session_id", "observation_id", "turn_id", "tool_use_id",
                           "scene_revision", "implementation_revision", "aggregation_key",
                           "goal_id", "segment_id", "step_id", "task_id", "task_run_id"})
_ANNOTATIONS = frozenset({"include_image", "cache_hit", "measurement_cache_hit", "status",
    "source_revision", "model", "provider", "input_format", "delivery", "operation_id",
    "route", "scene_fingerprint", "mutation_started", "mutation_completed", "build_id",
    "engine_invoked", "host_execution_verified", "task_succeeded", "requires_reobserve",
    "host_connection_reused", "request_origin", "protocol_version", "input_bytes",
    "output_bytes", "object_count", "vertex_count", "face_count", "retry_count", "source_name",
    "verified", "execution_verified", "goal_evaluation", "measurement_valid", "axes_valid",
    "mcp_request_id", "mcp_request_id_type", "goal_revision", "step_index",
    "request_budget_s", "request_budget_scope", "request_budget_status",
    "request_budget_stage", "request_budget_enforcement", "host_prewrite_refused",
    "receipt_replayed", "historical_receipt"})


def _identifier(value, field, *, optional=True):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
        raise ValueError(field + " must be a nonempty identifier of at most 256 characters")
    return value


def _counter(value, field):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError(field + " must be a nonnegative integer or None")
    return value


def raw_record_digest(record):
    """Hash a caller-selected provider usage record without retaining its body."""
    encoded = json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def process_peak_rss():
    """Return the process lifetime high-water RSS, never label it request RSS."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                    (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(),
                                               ctypes.byref(counters), counters.cb):
                raise OSError("GetProcessMemoryInfo failed")
            value, source = int(counters.PeakWorkingSetSize), "GetProcessMemoryInfo.PeakWorkingSetSize"
        else:
            import resource
            value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            value *= 1 if sys.platform == "darwin" else 1024
            source = "getrusage.ru_maxrss"
        return {"bytes": value, "scope": "process_lifetime_peak", "source": source}
    except (OSError, ImportError, AttributeError, ValueError, TypeError):
        return {"bytes": None, "scope": "process_lifetime_peak", "source": "unavailable"}


class RequestTrace:
    """One request attempt. Nesting creates a child trace, not another model step.

    ``writer(record)`` receives JSON-compatible metadata after context cleanup.
    Its failure is reported by ``delivery_status`` and never raised. Optional
    ``aggregation_key`` explicitly declares compatible benchmark samples; the
    analyser refuses to pool requests without such a key.
    """

    def __init__(self, operation, *, writer=None, request_id=None, experiment_id=None,
                 turn_id=None, tool_use_id=None,
                 trial_id=None, session_id=None, observation_id=None, scene_revision=None,
                 implementation_revision=None, aggregation_key=None, scope="engine_request",
                 attempt_index=0, retry_of_request_id=None):
        if not isinstance(operation, str) or not _NAME.fullmatch(operation):
            raise ValueError("operation must be a short controlled name")
        if scope not in ("engine_request", "provider_request", "benchmark_request"):
            raise ValueError("Unsupported trace scope")
        if writer is not None and not callable(writer):
            raise ValueError("writer must be callable")
        _counter(attempt_index, "attempt_index")
        if attempt_index is None:
            raise ValueError("attempt_index cannot be None")
        self._writer = writer
        self._lock = threading.RLock()
        self._entered = self._finished = False
        self._image_request_bound = False
        self._origin_ns = None
        self.delivery_status = "not_requested" if writer is None else "pending"
        self._data = {"schema_version": SCHEMA_VERSION, "trace_id": uuid.uuid4().hex,
            "request_id": _identifier(request_id or uuid.uuid4().hex, "request_id"),
            "parent_trace_id": None, "parent_span_id": None, "scope": scope,
            "operation": operation, "attempt_index": attempt_index,
            "retry_of_request_id": _identifier(retry_of_request_id, "retry_of_request_id"),
            "correlation": {}, "annotations": {}, "clock": "perf_counter_ns",
            "duration_scope": "one_request_attempt_wall_clock",
            "duration_semantics": "inclusive_do_not_sum_nested_spans",
            "trace_delivery_timing": "writer_excluded_from_request_duration",
            "started_at_utc": None, "duration_ns": None, "outcome": "unknown",
            "error_type": None, "pid": os.getpid(), "thread_id": None, "spans": [],
            "usage": [], "telemetry_issues": [], "peak_rss": None,
            "image_events": [], "image_events_truncated": False,
            "concurrency": {"scope": "instrumented_traces_in_this_process",
                            "active_at_start": None, "max_observed": None}}
        for key, value in {"experiment_id": experiment_id, "trial_id": trial_id,
                "turn_id": turn_id, "tool_use_id": tool_use_id,
                "session_id": session_id, "observation_id": observation_id,
                "scene_revision": scene_revision, "implementation_revision": implementation_revision,
                "aggregation_key": aggregation_key}.items():
            self._data["correlation"][key] = _identifier(value, key)

    def _issue(self, code):
        with self._lock:
            if code not in self._data["telemetry_issues"] and len(self._data["telemetry_issues"]) < 32:
                self._data["telemetry_issues"].append(code)

    def __enter__(self):
        if self._entered:
            raise RuntimeError("RequestTrace is single-use")
        self._entered = True
        parent = _CURRENT_TRACE.get()
        if parent is not None:
            self._data["parent_trace_id"] = parent.trace_id
            self._data["parent_span_id"] = _CURRENT_SPAN.get()
        self._origin_ns = time.perf_counter_ns()
        self._data["started_at_utc"] = datetime.now(timezone.utc).isoformat()
        self._data["thread_id"] = threading.get_ident()
        self._data["peak_rss"] = process_peak_rss()
        self._trace_token = _CURRENT_TRACE.set(self)
        self._span_token = _CURRENT_SPAN.set(None)
        with _ACTIVE_LOCK:
            _ACTIVE.add(self)
            count = len(_ACTIVE)
            self._data["concurrency"]["active_at_start"] = count
            for trace in _ACTIVE:
                trace._data["concurrency"]["max_observed"] = max(
                    trace._data["concurrency"]["max_observed"] or 0, count)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            with self._lock:
                self._data["duration_ns"] = max(0, time.perf_counter_ns() - self._origin_ns)
                if exc_type is not None:
                    self._data["outcome"] = "error"
                    self._data["error_type"] = exc_type.__name__
                elif self._data["outcome"] == "unknown":
                    self._data["outcome"] = "completed"
                peak = process_peak_rss()
                old_peak = self._data["peak_rss"]
                if peak["bytes"] is not None and (old_peak["bytes"] is None or peak["bytes"] > old_peak["bytes"]):
                    self._data["peak_rss"] = peak
                if any(item["duration_ns"] is None for item in self._data["spans"]):
                    self._issue("unfinished_spans_at_request_end")
                self._finished = True
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE.discard(self)
            _CURRENT_SPAN.reset(self._span_token)
            _CURRENT_TRACE.reset(self._trace_token)
        if self._writer is not None:
            try:
                result = self._writer(self.record)
                self.delivery_status = "failed" if result is False else "delivered"
            except Exception:
                self.delivery_status = "failed"
        return False

    @property
    def trace_id(self):
        return self._data["trace_id"]

    @property
    def request_id(self):
        return self._data["request_id"]

    @property
    def task_correlation(self):
        """Read two labels without copying the growing request/span record."""
        with self._lock:
            return {key: self._data['correlation'].get(key) for key in ('task_id', 'task_run_id')}

    @property
    def record(self):
        with self._lock:
            return copy.deepcopy(self._data)

    def set_image_request(self, value, *, source_name):
        """Bind outer request intent once, including explicit unknown (None).

        Entry owners resolve public API defaults before calling. Router stages
        must use record_image_event, never infer or change this request mode.
        """
        try:
            if value is not None and type(value) is not bool:
                raise ValueError('invalid_image_request')
            if not isinstance(source_name, str) or source_name not in _IMAGE_REQUEST_SOURCES:
                raise ValueError('invalid_image_request_source')
            with self._lock:
                if self._finished:
                    return False
                annotations = self._data['annotations']
                if self._image_request_bound:
                    if annotations.get('include_image') is value:
                        return True
                    self._issue('image_request_conflict')
                    return False
                annotations.update(include_image=value, image_request_source=source_name,
                    image_request_scope='outer_request_not_nested_stage')
                self._image_request_bound = True
            return True
        except (ValueError, TypeError):
            self._issue('invalid_image_request')
            return False

    def record_image_event(self, event_name, event_include_image, image_present):
        """Bounded stage diagnostics; presence includes reused cached payloads."""
        try:
            if not isinstance(event_name, str) or not _NAME.fullmatch(event_name):
                raise ValueError('invalid_image_event_name')
            if any(value is not None and type(value) is not bool
                   for value in (event_include_image, image_present)):
                raise ValueError('invalid_image_event_boolean')
            with self._lock:
                if self._finished:
                    return False
                self._data['annotations'].update(event_include_image=event_include_image,
                                                  event_image_present=image_present)
                if len(self._data['image_events']) >= _IMAGE_EVENT_LIMIT:
                    self._data['image_events_truncated'] = True
                    self._issue('image_events_truncated')
                    return False
                self._data['image_events'].append({'event_name': event_name,
                    'span_id': _CURRENT_SPAN.get(), 'event_include_image': event_include_image,
                    'image_present': image_present,
                    'scope': 'router_result_payload_not_service_final_or_model_consumption'})
            return True
        except (ValueError, TypeError):
            self._issue('invalid_image_event')
            return False

    def record_image_artifact(self, scope, *, image_present=None, native_block_count=None):
        """Record only a completed owner's local result, never model receipt.

        service_result owns final service payload presence. mcp_content owns
        the native block count after full transport content construction.
        Neither presence nor cache reuse implies rendering in this request.
        """
        try:
            if scope == 'service_result':
                if (image_present is not None and type(image_present) is not bool
                        or native_block_count is not None):
                    raise ValueError('invalid_service_image_artifact')
                key, value = 'service_image_present', image_present
            elif scope == 'mcp_content':
                if image_present is not None:
                    raise ValueError('invalid_mcp_image_artifact')
                key, value = 'mcp_native_image_block_count', _counter(native_block_count, 'native_block_count')
            else:
                raise ValueError('invalid_image_artifact_scope')
            with self._lock:
                if self._finished:
                    return False
                self._data['annotations'][key] = value
                self._data['annotations']['image_artifact_scope'] = 'local_result_payload_not_model_consumption'
            return True
        except (ValueError, TypeError):
            self._issue('invalid_image_artifact')
            return False

    def annotate(self, **fields):
        """Add only allowlisted, scalar facts; never arbitrary request contents.

        Malformed ancillary metadata returns False and records a content-free
        issue. It must not turn completed scene work into a retryable error.
        """
        try:
            prepared = []
            for key, value in fields.items():
                if key in _CORRELATIONS:
                    prepared.append(("correlation", key, _identifier(value, key)))
                elif key in _ANNOTATIONS:
                    if key == 'include_image' and value is not None and type(value) is not bool:
                        raise ValueError('invalid_image_request_boolean')
                    if key == 'host_prewrite_refused' and value is not None and type(value) is not bool:
                        raise ValueError('invalid_host_prewrite_refusal_boolean')
                    if key in {'goal_revision', 'step_index'}:
                        _counter(value, key)
                    if key == 'request_budget_s' and value is not None:
                        if (type(value) not in (int, float) or not math.isfinite(value)
                                or value <= 0):
                            raise ValueError('invalid_request_budget')
                    if key == 'request_budget_status' and value not in (None, 'busy', 'expired'):
                        raise ValueError('invalid_request_budget_status')
                    if key in {'request_budget_scope', 'request_budget_stage', 'request_budget_enforcement'}:
                        if value is not None and (not isinstance(value, str) or not _NAME.fullmatch(value)):
                            raise ValueError('invalid_request_budget_label')
                    if key == "mcp_request_id":
                        # Native JSON-RPC identity is transport-local, never a
                        # host turn/tool ID or this trace's generated request_id.
                        # Keep 7 and "7" distinct; empty strings and null are
                        # legal RPC IDs. Bound evidence without changing RPC.
                        if (value is not None and type(value) not in (str, int)
                                or isinstance(value, str) and len(value) > 256):
                            raise ValueError("invalid_mcp_request_id")
                        prepared.append(("annotations", key, value))
                        continue
                    if key == "mcp_request_id_type" and value not in (None, "string", "integer", "null"):
                        raise ValueError("invalid_mcp_request_id_type")
                    if value is not None and type(value) not in (str, bool, int, float):
                        raise ValueError("non_scalar_metadata")
                    if isinstance(value, str):
                        _identifier(value, key)
                    if type(value) is float and not math.isfinite(value):
                        raise ValueError("non_finite_metadata")
                    prepared.append(("annotations", key, value))
                else:
                    raise ValueError("unsupported_metadata_field")
            with self._lock:
                if self._finished:
                    return False
                if self._image_request_bound and any(key == 'include_image'
                        and self._data['annotations'].get('include_image') is not value
                        for _, key, value in prepared):
                    # Legacy annotations cannot bypass an explicit owner or
                    # replace a deliberate unknown with a nested default.
                    self._issue('image_request_conflict')
                    return False
                for group, key, value in prepared:
                    self._data[group][key] = value
            return True
        except (ValueError, TypeError, OverflowError):
            self._issue("invalid_annotation")
            return False

    def set_outcome(self, outcome):
        try:
            if not isinstance(outcome, str) or not _NAME.fullmatch(outcome):
                raise ValueError("invalid_outcome")
            with self._lock:
                if self._finished:
                    return False
                self._data["outcome"] = outcome
            return True
        except (ValueError, TypeError):
            self._issue("invalid_outcome")
            return False

    def record_usage(self, *, provider=None, model=None, source="unavailable",
                     input_tokens=None, output_tokens=None, cached_input_tokens=None,
                     reasoning_tokens=None, total_tokens=None, total_includes_reasoning=None,
                     raw_record_sha256=None, provider_request_id=None, step_index=None):
        """Store reported provider counts, never guess missing usage as zero.

        Cached input is a subset of input; reasoning is a subset of output.
        ``total_tokens`` is provider-reported and is not reconstructed. Unknown
        total inclusion semantics remain None even if arithmetic happens to fit.
        Each record is one provider response/step, not cumulative session usage.
        """
        try:
            item = {"provider": _identifier(provider, "provider"),
                "model": _identifier(model, "model"), "source": _identifier(source, "source", optional=False),
                "provider_request_id": _identifier(provider_request_id, "provider_request_id"),
                "step_index": _counter(step_index, "step_index"),
                "scope": "single_provider_response", "input_tokens": _counter(input_tokens, "input_tokens"),
                "output_tokens": _counter(output_tokens, "output_tokens"),
                "cached_input_tokens": _counter(cached_input_tokens, "cached_input_tokens"),
                "reasoning_tokens": _counter(reasoning_tokens, "reasoning_tokens"),
                "total_tokens": _counter(total_tokens, "total_tokens"),
                "total_includes_reasoning": total_includes_reasoning,
                "cached_input_semantics": "subset_of_input_tokens",
                "reasoning_semantics": "subset_of_output_tokens",
                "raw_record_sha256": raw_record_sha256}
            if total_includes_reasoning is not None and type(total_includes_reasoning) is not bool:
                raise ValueError("invalid_total_semantics")
            if raw_record_sha256 is not None and (not isinstance(raw_record_sha256, str)
                                                  or not _DIGEST.fullmatch(raw_record_sha256)):
                raise ValueError("invalid_digest")
            if (cached_input_tokens is not None and input_tokens is not None and cached_input_tokens > input_tokens
                    or reasoning_tokens is not None and output_tokens is not None and reasoning_tokens > output_tokens):
                raise ValueError("subset_exceeds_total")
            counts_known = any(item[key] is not None for key in ("input_tokens", "output_tokens",
                "cached_input_tokens", "reasoning_tokens", "total_tokens"))
            if counts_known and source == "unavailable":
                raise ValueError("known_counts_require_source")
            if (input_tokens is not None and output_tokens is not None and total_tokens is not None
                    and total_includes_reasoning is True and total_tokens != input_tokens + output_tokens):
                raise ValueError("inconsistent_total")
            item["usage_available"] = counts_known
            with self._lock:
                if self._finished:
                    return False
                self._data["usage"].append(item)
            return True
        except (ValueError, TypeError):
            self._issue("invalid_usage_record")
            return False


def current_trace():
    return _CURRENT_TRACE.get()


@contextmanager
def best_effort_trace(operation, **kwargs):
    """Run business work even if ancillary trace construction or cleanup fails.

    Yields a RequestTrace on successful entry, otherwise None. The original
    business exception always wins. Context is restored independently of the
    RequestTrace's own enter/exit methods, including partial entry and an exit
    that completed then raised. A failed writer is never retried here.
    """
    previous_trace, previous_span = _CURRENT_TRACE.get(), _CURRENT_SPAN.get()
    trace_token = _CURRENT_TRACE.set(previous_trace)
    span_token = _CURRENT_SPAN.set(previous_span)
    trace = None

    def restore_local_context():
        # Only this wrapper's trace is removed; concurrently active traces in
        # other tasks/threads and the enclosing parent remain registered.
        if trace is not None:
            with _ACTIVE_LOCK:
                _ACTIVE.discard(trace)
            trace._finished = True
        _CURRENT_SPAN.set(previous_span)
        _CURRENT_TRACE.set(previous_trace)

    try:
        try:
            trace = RequestTrace(operation, **kwargs)
            trace.__enter__()
        except Exception:
            restore_local_context()
            yield None
            return
        try:
            yield trace
        except BaseException:
            failure = sys.exc_info()
            try:
                trace.__exit__(*failure)
            except Exception:
                pass
            raise
        else:
            try:
                trace.__exit__(None, None, None)
            except Exception:
                pass
    finally:
        restore_local_context()
        _CURRENT_SPAN.reset(span_token)
        _CURRENT_TRACE.reset(trace_token)


safe_request_trace = best_effort_trace


def annotate(**fields):
    trace = current_trace()
    return trace.annotate(**fields) if trace is not None else False


def set_image_request(value, *, source_name):
    try:
        trace = current_trace()
        return trace.set_image_request(value, source_name=source_name) if trace is not None else False
    except Exception:
        return False


def record_image_event(event_name, event_include_image, image_present):
    try:
        trace = current_trace()
        return trace.record_image_event(event_name, event_include_image, image_present) if trace is not None else False
    except Exception:
        return False


def record_image_artifact(scope, *, image_present=None, native_block_count=None):
    try:
        trace = current_trace()
        return trace.record_image_artifact(scope, image_present=image_present,
            native_block_count=native_block_count) if trace is not None else False
    except Exception:
        return False


def record_usage(**fields):
    trace = current_trace()
    return trace.record_usage(**fields) if trace is not None else False


@contextmanager
def span(name, *, kind="cpu", source_name=None):
    """Time an inclusive stage in the current request; inert without a trace."""
    trace = current_trace()
    if trace is None:
        yield None
        return
    if (not isinstance(name, str) or not _NAME.fullmatch(name) or not isinstance(kind, str) or kind not in _KINDS
            or source_name is not None and (not isinstance(source_name, str) or not _NAME.fullmatch(source_name))):
        trace._issue("invalid_span")
        yield None
        return
    with trace._lock:
        if trace._finished:
            yield None
            return
        start = time.perf_counter_ns()
        item = {"span_id": uuid.uuid4().hex, "parent_span_id": _CURRENT_SPAN.get(),
            "name": name, "kind": kind, "source_name": source_name,
            "start_offset_ns": max(0, start - trace._origin_ns),
            "duration_ns": None, "outcome": "running", "error_type": None,
            "thread_id": threading.get_ident(), "timing_semantics": "inclusive_wall_clock"}
        trace._data["spans"].append(item)
    token = _CURRENT_SPAN.set(item["span_id"])
    try:
        yield item["span_id"]
    except BaseException as exc:
        item["outcome"] = "error"
        item["error_type"] = type(exc).__name__
        raise
    else:
        item["outcome"] = "completed"
    finally:
        with trace._lock:
            item["duration_ns"] = max(0, time.perf_counter_ns() - start)
        _CURRENT_SPAN.reset(token)


def _percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    return (ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)) / 1_000_000


def summarize_traces(records):
    """Describe explicitly comparable request groups and stages, without fees.

    Groups also split on revision, operation, outcome, image/cache mode and
    provider identity. Repeated stages remain separate call samples; their
    percentiles are labelled stage-call wall time, never single-step inference.
    Trace IDs are deduplicated so concatenated log tails do not double count.
    """
    groups, seen, excluded = {}, set(), {"invalid_record": 0, "duplicate_trace": 0,
        "missing_aggregation_key": 0, "unfinished_request": 0}
    for record in records:
        if (not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION
                or not isinstance(record.get("trace_id"), str)
                or not isinstance(record.get("correlation"), dict)
                or not isinstance(record.get("annotations"), dict)
                or not isinstance(record.get("spans"), list)
                or not isinstance(record.get("usage"), list)):
            excluded["invalid_record"] += 1
            continue
        if record["trace_id"] in seen:
            excluded["duplicate_trace"] += 1
            continue
        seen.add(record["trace_id"])
        correlation, annotations = record["correlation"], record["annotations"]
        duration = record.get("duration_ns")
        if type(duration) is not int or duration < 0:
            excluded["unfinished_request"] += 1
            continue
        if not correlation.get("aggregation_key"):
            excluded["missing_aggregation_key"] += 1
            continue
        identity = {"aggregation_key": correlation["aggregation_key"],
            "experiment_id": correlation.get("experiment_id"),
            "implementation_revision": correlation.get("implementation_revision"),
            "build_id": annotations.get("build_id"),
            "scope": record.get("scope"), "operation": record.get("operation"),
            "outcome": record.get("outcome"), "include_image": annotations.get("include_image"),
            "image_request_source": annotations.get('image_request_source',
                'legacy_annotation_unowned' if 'include_image' in annotations else 'unknown'),
            "image_request_scope": annotations.get('image_request_scope',
                'legacy_annotation_unowned' if 'include_image' in annotations else 'unknown'),
            "cache_hit": annotations.get("cache_hit"),
            "provider": annotations.get("provider"), "model": annotations.get("model"),
            "attempt_index": record.get("attempt_index"),
            "max_observed_concurrency": record.get("concurrency", {}).get("max_observed")
                if isinstance(record.get("concurrency"), dict) else None,
            "usage_steps": [{key: usage.get(key) for key in ("provider", "model", "source", "scope")}
                for usage in record["usage"] if isinstance(usage, dict)]}
        try:
            key = json.dumps(identity, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            excluded["invalid_record"] += 1
            continue
        group = groups.setdefault(key, {"identity": identity, "requests": [], "stages": {},
            "request_ids": [], "known_usage_records": 0, "unknown_usage_records": 0,
            "process_peak_rss_bytes": [], "provider_usage": {}, "seen_provider_responses": set(),
            "duplicate_provider_usage_records": 0})
        group["requests"].append(duration)
        group["request_ids"].append(record.get("request_id"))
        for stage in record["spans"]:
            if (not isinstance(stage, dict) or type(stage.get("duration_ns")) is not int
                    or stage["duration_ns"] < 0):
                continue
            stage_key = (str(stage.get("name")), str(stage.get("kind")), str(stage.get("outcome")))
            group["stages"].setdefault(stage_key, []).append(stage["duration_ns"])
        if not record["usage"]:
            group["unknown_usage_records"] += 1
        for usage in record["usage"]:
            field = "known_usage_records" if isinstance(usage, dict) and usage.get("usage_available") is True else "unknown_usage_records"
            group[field] += 1
            if not isinstance(usage, dict):
                continue
            usage_key = tuple(str(usage.get(field)) for field in ("provider", "model", "source"))
            provider_id = usage.get("provider_request_id")
            if isinstance(provider_id, str) and provider_id:
                response_key = (usage_key[0], provider_id)
                if response_key in group["seen_provider_responses"]:
                    group["duplicate_provider_usage_records"] += 1
                    continue
                group["seen_provider_responses"].add(response_key)
            usage_summary = group["provider_usage"].setdefault(usage_key, {
                "provider": usage.get("provider"), "model": usage.get("model"),
                "source": usage.get("source"), "response_records": 0,
                "records_with_provider_response_id": 0,
                "count_scope": "sum_of_reported_single_response_counts_not_billable_cost",
                "fields": {field: {"known_value_sum": 0, "known_records": 0, "unknown_records": 0}
                    for field in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens")}})
            usage_summary["response_records"] += 1
            usage_summary["records_with_provider_response_id"] += int(isinstance(provider_id, str) and bool(provider_id))
            for field, counts in usage_summary["fields"].items():
                value = usage.get(field)
                if type(value) is int and value >= 0:
                    counts["known_value_sum"] += value
                    counts["known_records"] += 1
                else:
                    counts["unknown_records"] += 1
        rss = record.get("peak_rss")
        if isinstance(rss, dict) and type(rss.get("bytes")) is int and rss["bytes"] >= 0:
            group["process_peak_rss_bytes"].append(rss["bytes"])
    result = []
    def stats(samples):
        return {"count": len(samples), "p50_ms": _percentile(samples, .5),
                "p95_ms": _percentile(samples, .95), "p99_ms": _percentile(samples, .99),
                "minimum_ms": min(samples) / 1_000_000, "maximum_ms": max(samples) / 1_000_000}
    for group in groups.values():
        stages = [{"name": key[0], "kind": key[1], "outcome": key[2],
            "scope": "stage_call_inclusive_wall_clock", **stats(samples)}
            for key, samples in sorted(group.pop("stages").items())]
        rss = group.pop("process_peak_rss_bytes")
        provider_usage = list(group.pop("provider_usage").values())
        group.pop("seen_provider_responses")
        for usage in provider_usage:
            for counts in usage["fields"].values():
                counts["complete"] = counts["unknown_records"] == 0
                if counts["known_records"] == 0:
                    counts["known_value_sum"] = None
        result.append({**group, "requests": {"scope": "one_request_attempt_wall_clock",
            **stats(group["requests"])}, "stages": stages,
            "provider_usage": provider_usage,
            "peak_rss": {"bytes": max(rss) if rss else None, "scope": "process_lifetime_peak"}})
    return {"schema_version": SCHEMA_VERSION, "groups": result, "excluded": excluded,
        "percentile_method": "linear_interpolation_(n-1)*p",
        "interpretation": "descriptive_only_explicit_groups_no_model_speedup_or_cost_inference",
        "missing_usage_policy": "unknown_never_zero", "nested_span_policy": "do_not_sum"}


MAX_GOAL_SEGMENT_STEPS = 64
MAX_GOAL_SEGMENT_RECORDS = 256
_GOAL_COUNTERS = ('host_captures', 'host_commits', 'local_corrections',
                  'rendered_images', 'model_reviews', 'input_bytes', 'output_bytes')
_TOKEN_FIELDS = ('input_tokens', 'output_tokens', 'cached_input_tokens',
                 'reasoning_tokens', 'total_tokens')


def _bounded_metric_counter(value, field, *, optional=True):
    if value is None and optional:
        return None
    if type(value) is not int or not 0 <= value <= (1 << 63) - 1:
        raise ValueError(field + ' must be a nonnegative 63-bit integer')
    return value


def build_goal_step_metrics(*, segment_id, step_id, step_index, outcome,
                            operation_id=None, executed=None, execution_verified=None,
                            request_ids=(), counters=None, duration_ns=None):
    """Build bounded, caller-reported step evidence; never an action permission.

    Counters must describe nonoverlapping work actually observed for this step,
    not expected capture counts. Missing values stay unknown. A step duration
    is diagnostic only and is never added to the segment's wall time.
    """
    segment_id = _identifier(segment_id, 'segment_id', optional=False)
    step_id = _identifier(step_id, 'step_id', optional=False)
    operation_id = _identifier(operation_id, 'operation_id')
    _bounded_metric_counter(step_index, 'step_index', optional=False)
    if step_index >= MAX_GOAL_SEGMENT_STEPS:
        raise ValueError('step_index exceeds the bounded segment contract')
    if not isinstance(outcome, str) or not _NAME.fullmatch(outcome):
        raise ValueError('outcome must be a short controlled name')
    if any(value is not None and type(value) is not bool
           for value in (executed, execution_verified)):
        raise ValueError('execution fields must be booleans or None')
    if execution_verified is True and executed is not True:
        raise ValueError('verified execution requires confirmed execution')
    if not isinstance(request_ids, (list, tuple)) or len(request_ids) > 32:
        raise ValueError('request_ids must contain at most 32 identifiers')
    requests = [_identifier(value, 'request_id', optional=False) for value in request_ids]
    requests = sorted(set(requests))
    if counters is None:
        counters = {}
    if not isinstance(counters, dict) or set(counters) - set(_GOAL_COUNTERS):
        raise ValueError('unsupported goal-step counter')
    counts = {key: _bounded_metric_counter(counters.get(key), key) for key in _GOAL_COUNTERS}
    return {'schema_version': SCHEMA_VERSION, 'segment_id': segment_id,
        'step_id': step_id, 'step_index': step_index, 'operation_id': operation_id,
        'outcome': outcome, 'executed': executed, 'execution_verified': execution_verified,
        'request_ids': requests, 'counters': counts,
        'duration_ns': _bounded_metric_counter(duration_ns, 'duration_ns')}


def _segment_usage_summary(records):
    """Accept RequestTrace usage records; unidentified replies are not summed."""
    if not isinstance(records, (list, tuple)) or len(records) > MAX_GOAL_SEGMENT_RECORDS:
        raise ValueError('model_usage_records exceeds the bounded segment contract')
    allowed = {'provider', 'model', 'source', 'provider_request_id', 'step_index',
        'scope', 'total_includes_reasoning', 'cached_input_semantics', 'reasoning_semantics',
        'raw_record_sha256', 'usage_available', *_TOKEN_FIELDS}
    seen, groups, duplicates, unidentified = {}, {}, 0, 0
    for raw in records:
        if not isinstance(raw, dict) or set(raw) - allowed:
            raise ValueError('unsupported model usage record')
        if raw.get('scope') != 'single_provider_response':
            raise ValueError('model usage must describe one provider response')
        row = {key: _identifier(raw.get(key), key) for key in
               ('provider', 'model', 'provider_request_id')}
        row['source'] = _identifier(raw.get('source'), 'source', optional=False)
        row.update({key: _bounded_metric_counter(raw.get(key), key) for key in _TOKEN_FIELDS})
        _bounded_metric_counter(raw.get('step_index'), 'step_index')
        total_semantics = raw.get('total_includes_reasoning')
        if total_semantics is not None and type(total_semantics) is not bool:
            raise ValueError('invalid total token semantics')
        row['total_includes_reasoning'] = total_semantics
        digest = raw.get('raw_record_sha256')
        if digest is not None and (not isinstance(digest, str) or not _DIGEST.fullmatch(digest)):
            raise ValueError('invalid provider record digest')
        row['raw_record_sha256'] = digest
        for subset, total in (('cached_input_tokens', 'input_tokens'),
                              ('reasoning_tokens', 'output_tokens')):
            if row[subset] is not None and row[total] is not None and row[subset] > row[total]:
                raise ValueError('usage subset exceeds total')
        if total_semantics is True and all(row[key] is not None for key in
                                          ('input_tokens', 'output_tokens', 'total_tokens')):
            if row['total_tokens'] != row['input_tokens'] + row['output_tokens']:
                raise ValueError('inconsistent reported total tokens')
        known = any(row[key] is not None for key in _TOKEN_FIELDS)
        if known and row['source'] == 'unavailable':
            raise ValueError('known usage requires a reported source')
        if 'usage_available' in raw and (type(raw['usage_available']) is not bool
                                        or raw['usage_available'] != known):
            raise ValueError('usage availability contradicts reported counts')
        for key, expected in (('cached_input_semantics', 'subset_of_input_tokens'),
                              ('reasoning_semantics', 'subset_of_output_tokens')):
            if key in raw and raw[key] != expected:
                raise ValueError('unsupported usage subset semantics')
        if row['provider'] is None or row['provider_request_id'] is None:
            unidentified += 1
            continue
        identity = row['provider'], row['provider_request_id']
        if identity in seen:
            if seen[identity] != row:
                raise ValueError('conflicting provider response usage')
            duplicates += 1
            continue
        seen[identity] = row
        key = row['provider'], row['model'], row['source']
        group = groups.setdefault(key, {'provider': key[0], 'model': key[1], 'source': key[2],
            'response_records': 0,
            'fields': {field: {'known_value_sum': None, 'known_records': 0, 'unknown_records': 0}
                       for field in _TOKEN_FIELDS}})
        group['response_records'] += 1
        for field, counts in group['fields'].items():
            if row[field] is None:
                counts['unknown_records'] += 1
            else:
                counts['known_value_sum'] = (counts['known_value_sum'] or 0) + row[field]
                counts['known_records'] += 1
    for group in groups.values():
        for counts in group['fields'].values():
            counts['complete_for_identified_responses'] = counts['unknown_records'] == 0
    reported_counts = any(row[field] is not None for row in seen.values() for field in _TOKEN_FIELDS)
    return {'scope': 'reported_identified_provider_responses_not_billable_cost',
        'groups': list(groups.values()), 'identified_responses': len(seen),
        'duplicate_records': duplicates, 'unidentified_records_not_summed': unidentified,
        'availability': 'partial' if unidentified and reported_counts else 'reported' if reported_counts else 'unknown',
        'coverage': 'caller_supplied_records_not_proof_of_all_model_calls',
        'missing_usage_policy': 'unknown_never_zero'}


def summarize_goal_segment_metrics(steps, *, segment_id, duration_ns=None,
                                   outcome='unknown', model_usage_records=(),
                                   max_steps=MAX_GOAL_SEGMENT_STEPS):
    """Summarize one finite segment, not a whole multi-segment user task.

    Caller supplies elapsed monotonic wall time. Neither step durations nor
    nested request spans are added. Identical step replays count once; identity
    conflicts fail explicitly rather than silently hiding work. Pure validation
    errors are ancillary: callers must not retry a mutation because of them.
    """
    segment_id = _identifier(segment_id, 'segment_id', optional=False)
    if type(max_steps) is not int or not 1 <= max_steps <= MAX_GOAL_SEGMENT_STEPS:
        raise ValueError('max_steps is outside the bounded segment contract')
    if not isinstance(steps, (list, tuple)) or len(steps) > MAX_GOAL_SEGMENT_RECORDS:
        raise ValueError('steps exceeds the bounded segment record limit')
    if not isinstance(outcome, str) or not _NAME.fullmatch(outcome):
        raise ValueError('outcome must be a short controlled name')
    duration_ns = _bounded_metric_counter(duration_ns, 'duration_ns')
    seen, indices, operations, request_owners, duplicates = {}, {}, {}, {}, 0
    fields = {'schema_version', 'segment_id', 'step_id', 'step_index', 'operation_id',
        'outcome', 'executed', 'execution_verified', 'request_ids', 'counters', 'duration_ns'}
    for raw in steps:
        if not isinstance(raw, dict) or set(raw) - fields or raw.get('schema_version') != SCHEMA_VERSION:
            raise ValueError('invalid goal-step metric record')
        row = build_goal_step_metrics(**{key: value for key, value in raw.items() if key != 'schema_version'})
        if row['segment_id'] != segment_id:
            raise ValueError('goal-step record belongs to another segment')
        identity, index = row['step_id'], row['step_index']
        if identity in seen:
            if seen[identity] != row:
                raise ValueError('conflicting goal-step replay')
            duplicates += 1
            continue
        if index in indices or index >= max_steps:
            raise ValueError('conflicting or out-of-budget step index')
        op = row['operation_id']
        if op is not None and op in operations:
            raise ValueError('one operation cannot be counted as two steps')
        for request in row['request_ids']:
            # One outer MCP request can own several local steps. This is a
            # correlation union, never a count inferred from step occurrences.
            request_owners.setdefault(request, []).append(identity)
        if op is not None:
            operations[op] = identity
        indices[index] = identity
        seen[identity] = row
    counts = {field: {'known_value_sum': None, 'known_steps': 0, 'unknown_steps': 0}
              for field in _GOAL_COUNTERS}
    dispositions = {'confirmed_execution': 0, 'not_executed': 0,
                    'executed_unverified': 0, 'execution_unknown': 0}
    for row in seen.values():
        key = ('not_executed' if row['executed'] is False else
               'execution_unknown' if row['executed'] is None else
               'confirmed_execution' if row['execution_verified'] is True else 'executed_unverified')
        dispositions[key] += 1
        for field, total in counts.items():
            value = row['counters'][field]
            if value is None:
                total['unknown_steps'] += 1
            else:
                total['known_value_sum'] = (total['known_value_sum'] or 0) + value
                total['known_steps'] += 1
    for total in counts.values():
        total['complete_for_recorded_steps'] = bool(seen) and total['unknown_steps'] == 0
    return {'schema_version': SCHEMA_VERSION, 'segment_id': segment_id, 'outcome': outcome,
        'execution_authority': False, 'duration_ns': duration_ns,
        'duration_scope': 'one_goal_segment_wall_clock_not_whole_task',
        'duration_source': 'caller_monotonic_elapsed' if duration_ns is not None else 'unknown',
        'nested_span_policy': 'do_not_sum', 'unique_steps': len(seen),
        'duplicate_step_records': duplicates, 'step_indices': sorted(indices),
        'unique_operation_ids': len(operations), 'unique_step_request_ids': len(request_owners),
        'execution_counts': dispositions, 'counters': counts,
        'counter_scope': 'caller_reported_step_work_excludes_unassigned_segment_work',
        'model_usage': _segment_usage_summary(model_usage_records)}
