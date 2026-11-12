"""Process-local read state, independent of action journals and permissions."""
from collections import OrderedDict
import copy
import json
import threading

from .scene_cache import SpatialSceneCache


def capture_key(capture):
    value = capture.get('capture_state') if isinstance(capture, dict) else None
    if (type(value) is not dict or type(value.get('instance_id')) is not str
            or type(value.get('epoch')) is not int or type(value.get('revision')) is not int
            or type(value.get('selection_key')) is not str):
        return None
    return tuple(value[key] for key in ('instance_id', 'epoch', 'revision', 'selection_key'))


def query_key(query):
    return json.dumps(query, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class ReadContext:
    """Eight recent selections per generation, sixteen results per selection."""
    def __init__(self):
        self.lock = threading.RLock()
        self.scene_cache = SpatialSceneCache(max_bytes=2 * 1024 * 1024)
        self.reset()

    def reset(self, *, clear_measurements=False):
        if clear_measurements:
            self.scene_cache = SpatialSceneCache(max_bytes=2 * 1024 * 1024)
        self._capture = None
        self._generation = None
        self._selections = OrderedDict()
        self._normalized = None
        self._results = OrderedDict()
        self._surface_scan_key = None
        self._surface_scan_progress = {}
        self.scene_cache._bind_read_meshes(None, ())

    def activate(self, capture, entry, selection=None):
        token = capture_key(capture)
        generation = token[:3] if token is not None else object()
        if generation != self._generation:
            self.reset()
            self._generation = generation
        key = (entry, token, query_key(selection)) if token is not None else object()
        state = self._selections.get(key)
        if state is None:
            state = {'normalized': None, 'results': OrderedDict()}
            self._selections[key] = state
        self._selections.move_to_end(key)
        if len(self._selections) > 8:
            self._selections.popitem(last=False)
        self._capture = key
        self._normalized, self._results = state['normalized'], state['results']
        self._versioned = token is not None
        self.scene_cache._bind_read_meshes(
            key if self._versioned and self._normalized is not None else None,
            self._normalized[1] if self._normalized is not None else ())

    def normalized(self, normalize):
        if self._normalized is None:
            self._normalized = normalize()
            self._selections[self._capture]['normalized'] = self._normalized
            if self._versioned:
                self.scene_cache._bind_read_meshes(self._capture, self._normalized[1])
        return self._normalized

    def surface_scan_progress(self, key):
        """Resume one current scan with summaries under the same private capture."""
        binding = (self._capture, key)
        if binding != self._surface_scan_key:
            # A complete cached scan needs its matching negative diagnostics.
            # Rebuild that one result after switching away from this progress.
            self._results.pop(key, None)
            self._surface_scan_progress = {}
            self._surface_scan_key = binding
        return self._surface_scan_progress

    def result(self, key, compute, *, cache_partial=True):
        cached = self._results.get(key)
        if cached is not None:
            if cache_partial or isinstance(cached, dict) and cached.get('status') == 'complete':
                self._results.move_to_end(key)
                return copy.deepcopy(cached), True
            self._results.pop(key)
        value = compute()
        # No request trace or caller mutation is retained. Exceptions never
        # populate this map. Existing entries retain their original status.
        # A resumable scan opts out of retaining incomplete terminal results.
        if cache_partial or isinstance(value, dict) and value.get('status') == 'complete':
            self._results[key] = value
            if len(self._results) > 16:
                self._results.popitem(last=False)
        return copy.deepcopy(value), False
