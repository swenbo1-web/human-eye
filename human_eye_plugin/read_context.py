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
    def __init__(self):
        self.lock = threading.RLock()
        self.scene_cache = SpatialSceneCache(max_bytes=2 * 1024 * 1024)
        self.reset()

    def reset(self, *, clear_measurements=False):
        if clear_measurements:
            self.scene_cache = SpatialSceneCache(max_bytes=2 * 1024 * 1024)
        self._capture = None
        self._normalized = None
        self._results = OrderedDict()
        self.scene_cache._bind_read_meshes(None, ())

    def activate(self, capture, entry, selection=None):
        token = capture_key(capture)
        key = (entry, token, query_key(selection)) if token is not None else object()
        if key != self._capture:
            self.reset()
            self._capture = key
        self._versioned = token is not None

    def normalized(self, normalize):
        if self._normalized is None:
            self._normalized = normalize()
            if self._versioned:
                self.scene_cache._bind_read_meshes(self._capture, self._normalized[1])
        return self._normalized

    def result(self, key, compute):
        cached = self._results.get(key)
        if cached is not None:
            self._results.move_to_end(key)
            return copy.deepcopy(cached), True
        value = compute()
        # No request trace or caller mutation is retained. Exceptions never
        # populate this map; partial/unknown retain their original status.
        self._results[key] = value
        if len(self._results) > 16:
            self._results.popitem(last=False)
        return copy.deepcopy(value), False
