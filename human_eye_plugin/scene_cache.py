"""Bounded immutable scene history and exact observation-only memoization.

This cache has no observation tokens, execution gates, rollback or host writes.
Every input is a complete world/metre snapshot. A missing object therefore means
removed from that snapshot, not inferred occlusion. Exact byte keys, never the
diagnostic rigid-fit tolerance, govern legacy measurement reuse. The resident
read owner can instead bind its private normalized meshes to a current capture
version; these bindings never enter persisted state or action authorization.
"""
from __future__ import annotations

from collections import OrderedDict, deque
import hashlib
import copy
import json
import sys
import threading
import time

import numpy as np


_GEOMETRY_FIELDS = ("vertices", "faces", "edges")
_ENTRY_ALLOWANCE = 256


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _decode(payload):
    return json.loads(payload)


def _charge(payload, key=None):
    # Retained immutable payload plus bookkeeping allowance, not a process RSS
    # cap. Temporary input arrays, serialization and computation are excluded.
    return sys.getsizeof(payload) + _ENTRY_ALLOWANCE + (sys.getsizeof(key) if key else 0)


def _mesh_dict(mesh):
    value = mesh.to_dict() if callable(getattr(mesh, "to_dict", None)) else mesh
    if not isinstance(value, dict):
        raise ValueError("mesh must be a mapping or MeshEntity3D")
    return value


def _validate_scene(scene):
    if (not isinstance(scene, dict) or scene.get("unit") != "m"
            or scene.get("coordinate_frame") != "world"
            or not isinstance(scene.get("revision"), str) or not scene["revision"].strip()):
        raise ValueError("complete scene needs a revision and world/metre provenance")
    items = scene.get("meshes")
    if not isinstance(items, list) or len(items) > 256:
        raise ValueError("scene cache accepts at most 256 meshes")
    identities, vertices_total, faces_total = set(), 0, 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("mesh must be an object")
        identity = item.get("object_id")
        if not isinstance(identity, str) or not identity or identity in identities:
            raise ValueError("stable object_id must be unique and nonempty")
        identities.add(identity)
        for field, shape in (("pivot_world", (3,)), ("local_axes", (3, 3))):
            if item.get(field) is not None:
                frame = np.asarray(item[field])
                if (frame.shape != shape or frame.dtype.kind not in "ifu"
                        or not np.isfinite(frame).all()):
                    raise ValueError("invalid " + field)
        for field, width in (("vertices", 3), ("faces", 3), ("edges", 2)):
            raw = item.get(field)
            if field == "edges" and (raw is None or raw == []):
                continue
            if not isinstance(raw, (list, tuple)):
                raise ValueError(field + " must be a list")
            if field == "vertices":
                vertices_total += len(raw)
                if vertices_total > 500_000:
                    raise ValueError("scene vertex budget exceeded")
            if field == "faces":
                faces_total += len(raw)
                if faces_total > 1_000_000:
                    raise ValueError("scene face budget exceeded")
            if field == "edges" and len(raw) > 3 * len(item.get("faces", ())):
                raise ValueError("edge hint budget exceeded")
            array = np.asarray(raw)
            if array.ndim != 2 or array.shape[1:] != (width,) or not len(array):
                raise ValueError("invalid " + field + " shape")
            if field == "vertices":
                if len(array) < 3 or array.dtype.kind not in "ifu" or not np.isfinite(array).all():
                    raise ValueError("vertices must contain finite numbers")
            elif (array.dtype.kind not in "iu" or np.min(array) < 0
                  or np.max(array) >= len(item["vertices"])):
                raise ValueError("invalid topology indices")


def _change_kind(before, after):
    """Describe a changed world mesh; fitting never affects exact cache keys."""
    if before.get("faces") != after.get("faces") or before.get("edges") != after.get("edges"):
        return {"kind": "geometry", "reason": "topology_changed"}
    a, b = np.asarray(before["vertices"], dtype=float), np.asarray(after["vertices"], dtype=float)
    if a.shape != b.shape:
        return {"kind": "geometry", "reason": "vertex_count_changed"}
    # Classification is optional descriptive data. Extreme finite coordinates
    # must not turn a cache update into an SVD failure or an infinite JSON value.
    with np.errstate(over="ignore", invalid="ignore"):
        aa, bb = a - a.mean(axis=0), b - b.mean(axis=0)
        covariance = aa.T @ bb
    if not np.isfinite(covariance).all():
        return {"kind": "geometry", "reason": "rigid_fit_numeric_range"}
    try:
        left, _, right = np.linalg.svd(covariance)
    except np.linalg.LinAlgError:
        return {"kind": "geometry", "reason": "rigid_fit_unavailable"}
    correction = np.eye(3)
    correction[-1, -1] = 1 if np.linalg.det(left @ right) >= 0 else -1
    rotation = left @ correction @ right
    with np.errstate(over="ignore", invalid="ignore"):
        residual = float(np.max(np.linalg.norm(aa @ rotation - bb, axis=1)))
    if not np.isfinite(residual):
        return {"kind": "geometry", "reason": "rigid_fit_numeric_range"}
    tolerance = max(1e-12, float(np.max(np.abs(np.concatenate((a, b))))) * np.finfo(float).eps * 64)
    return {"kind": "transform" if residual <= tolerance else "geometry",
            "rigid_fit_residual_m": residual, "classification_tolerance_m": tolerance,
            "classification_used_for_reuse": False}


class SpatialSceneCache:
    """Content-addressed complete snapshots and successful pair measurements.

    ``max_bytes`` bounds accounted retained bytes: immutable serialized bytes,
    key sizes and a fixed per-entry bookkeeping allowance. This is not a bound
    on interpreter RSS or temporary computation. Frames and measurements share
    the budget. Eviction removes oldest frames, then least-used support results,
    then pair measurements; an oversized single frame/result is not retained.

    ``pair_measurement`` is for observations only. The execution path must call
    its geometry evaluator directly on a fresh host snapshot.
    """
    def __init__(self, *, max_bytes=8 * 1024 * 1024, max_frames=16, max_measurements=256):
        if (type(max_bytes) is not int or not 1024 <= max_bytes <= 64 * 1024 * 1024
                or type(max_frames) is not int or not 1 <= max_frames <= 256
                or type(max_measurements) is not int or not 1 <= max_measurements <= 4096):
            raise ValueError("invalid scene cache limits")
        self.max_bytes, self.max_frames, self.max_measurements = max_bytes, max_frames, max_measurements
        self._blobs = {}
        # Links are derived while writing immutable content, never accepted
        # from an imported manifest. The fixed blob bookkeeping allowance
        # includes these references; GC need not decode every object per frame.
        self._geometry_links = {}
        self._frames = deque()
        self._measurements = OrderedDict()
        self._solid_support = OrderedDict()
        self._latest_scene_payload = self._latest_frame = None
        # Same immutable-payload accounting as before, maintained only at the
        # owning mutation points. Admission/trim must not scan every retained
        # entry for each of a hundred first-time support results.
        self._blob_bytes = self._frame_bytes = 0
        self._measurement_bytes = self._support_bytes = self._payload_bytes = 0
        self._lock = threading.RLock()
        self._hits = self._misses = self._computations = 0
        self._support_hits = self._support_misses = 0
        self._estimated_saved_ms = 0.0
        self._read_meshes = {}

    def _bind_read_meshes(self, version, meshes):
        """Only the resident owner binds its private normalized mesh objects."""
        with self._lock:
            self._read_meshes = ({id(mesh): (mesh, (version, mesh.object_id)) for mesh in meshes}
                                 if version is not None else {})

    def _measurement_mesh(self, mesh):
        entry = self._read_meshes.get(id(mesh))
        if entry is not None and entry[0] is mesh:
            return {'read_resource_version': entry[1]}
        return _mesh_dict(mesh)

    def _bytes(self):
        return (self._blob_bytes + self._frame_bytes + self._measurement_bytes
                + self._support_bytes + self._payload_bytes)

    def _slow_recount_bytes(self):
        """Read-only audit oracle; never repairs counters or runs on a lookup."""
        with self._lock:
            return self._recount_payload_bytes()

    def _recount_payload_bytes(self):
        return (sum(_charge(v, k) for k, v in self._blobs.items())
                + sum(_charge(v) for v in self._frames)
                + sum(_charge(v[0], k) + 64 for k, v in self._measurements.items())
                + sum(_charge(v, k) for k, v in self._solid_support.items())
                + (_charge(self._latest_scene_payload) if self._latest_scene_payload is not None else 0))

    def _set_latest_scene(self, payload, frame=None, *, payload_charge=None):
        charge = (_charge(payload) if payload_charge is None else payload_charge) if payload is not None else 0
        self._latest_scene_payload, self._latest_frame = payload, frame
        self._payload_bytes = charge

    def _drop_oldest_frame(self):
        frame = self._frames.popleft()
        self._frame_bytes -= _charge(frame)

    def _gc(self):
        needed = set()
        for frame in self._frames:
            for _, content_hash in _decode(frame)["objects"]:
                needed.add(content_hash)
                needed.add(self._geometry_links[content_hash])
        for key in tuple(self._blobs):
            if key not in needed:
                self._blob_bytes -= _charge(self._blobs.pop(key), key)
        self._geometry_links = {key: value for key, value in self._geometry_links.items() if key in needed}

    def _trim(self):
        removed = False
        while len(self._frames) > self.max_frames:
            self._drop_oldest_frame()
            removed = True
        if removed:
            self._gc()
        while self._bytes() > self.max_bytes and len(self._frames) > 1:
            self._drop_oldest_frame()
            self._gc()
        while (len(self._solid_support) > self.max_measurements
               or self._bytes() > self.max_bytes and self._solid_support):
            key, payload = self._solid_support.popitem(last=False)
            self._support_bytes -= _charge(payload, key)
        while (len(self._measurements) > self.max_measurements
               or self._bytes() > self.max_bytes and self._measurements):
            key, (payload, _) = self._measurements.popitem(last=False)
            self._measurement_bytes -= _charge(payload, key) + 64
        if self._bytes() > self.max_bytes:
            self._frames.clear()
            self._blobs.clear()
            self._geometry_links.clear()
            self._blob_bytes = self._frame_bytes = 0
            self._set_latest_scene(None)

    def stats(self):
        with self._lock:
            return {"frames": len(self._frames), "content_blobs": len(self._blobs),
                    "measurement_entries": len(self._measurements), "accounted_bytes": self._bytes(),
                    "max_bytes": self.max_bytes, "max_frames": self.max_frames,
                    "measurement_hits": self._hits, "measurement_misses": self._misses,
                    "measurement_computations": self._computations,
                    "solid_support_entries": len(self._solid_support),
                    "solid_support_hits": self._support_hits,
                    "solid_support_misses": self._support_misses,
                    "solid_support_scope": "exact_content_observation_only_not_execution",
                    "estimated_compute_ms_avoided": self._estimated_saved_ms,
                    "savings_basis": "duration_of_original_compute_excludes_lookup_overhead",
                    "byte_accounting": "immutable_payload_and_per_entry_allowance_excludes_temporary_work",
                    "purpose": "observation_only_no_execution_authority"}

    def _object(self, content_hash):
        obj = _decode(self._blobs[content_hash])
        return {**obj["metadata"], **_decode(self._blobs[obj["geometry"]])}

    def snapshot(self, index=-1):
        """Return a detached JSON snapshot, never an alias into history."""
        with self._lock:
            frame = _decode(self._frames[index])
            return {**frame["metadata"], "meshes": [self._object(key) for _, key in frame["objects"]]}

    def find_snapshot(self, revision, fingerprint):
        """Find an exact retained observation base; never an execution token.

        Compare cheap frame provenance first, then complete reconstructed bytes
        for matching revisions. Revisions alone may repeat across different
        content. Nothing is pinned or given a longer lifetime by this lookup.
        """
        if (not isinstance(revision, str) or not revision.strip() or len(revision) > 256
                or not isinstance(fingerprint, str) or len(fingerprint) != 64
                or any(character not in '0123456789abcdef' for character in fingerprint)):
            raise ValueError('A complete revision and lowercase SHA256 are required')
        with self._lock:
            for encoded in reversed(self._frames):
                frame = _decode(encoded)
                if frame['metadata'].get('revision') != revision:
                    continue
                scene = {**frame['metadata'], 'meshes': [self._object(key) for _, key in frame['objects']]}
                if _digest(_encode(scene)) == fingerprint:
                    return scene
            return None

    def record_scene(self, scene):
        """Record a complete scene; revisions are provenance, not cache keys."""
        _validate_scene(scene)
        return self._record_validated_scene(scene)

    def _record_validated_scene(self, scene, *, canonical_scene_payload=None):
        """Internal normalized-scene path, with this operation's immutable bytes.

        Only the router's current full validation supplies ``payload``. It is
        compared as bytes, not an external revision/fingerprint or dict identity.
        Public inputs and imports always pass through ``record_scene`` instead.
        This history shortcut never supplies geometry support or action tokens.
        """
        if canonical_scene_payload is not None and type(canonical_scene_payload) is not bytes:
            raise ValueError("canonical scene payload must be immutable bytes")
        staged, refs, geometry_reused, objects_reused = {}, [], 0, 0
        with self._lock:
            if (canonical_scene_payload is not None
                    and canonical_scene_payload == self._latest_scene_payload
                    and self._frames and self._frames[-1] == self._latest_frame):
                # The latest retained frame was built from exactly these bytes.
                # Reuse only history bookkeeping; return newly detached fields.
                count = len(scene['meshes'])
                return {"scene_revision": scene["revision"],
                    "source": copy.deepcopy(scene.get("source", "host_snapshot")),
                    "scene_content_hash": _digest(self._latest_frame),
                    "changes": {"added": [], "removed": [], "transform": [], "geometry": [],
                        "metadata": [], "unchanged": [item['object_id'] for item in scene['meshes']],
                        "details": {}},
                    "retained": True, "duplicate_frame": True,
                    "geometry_blobs_reused": count, "object_blobs_reused": count,
                    "stats": self.stats()}
            previous = _decode(self._frames[-1]) if self._frames else None
            old_refs = dict(previous["objects"]) if previous else {}
            links = {}
            changes = {"added": [], "removed": [], "transform": [], "geometry": [],
                       "metadata": [], "unchanged": [], "details": {}}
            for item in scene["meshes"]:
                geometry = _encode({k: item[k] for k in _GEOMETRY_FIELDS if k in item})
                geometry_hash = _digest(geometry)
                metadata = {k: v for k, v in item.items() if k not in _GEOMETRY_FIELDS}
                content = _encode({"geometry": geometry_hash, "metadata": metadata})
                content_hash, identity = _digest(content), item["object_id"]
                geometry_reused += geometry_hash in self._blobs or geometry_hash in staged
                objects_reused += content_hash in self._blobs or content_hash in staged
                staged.setdefault(geometry_hash, geometry)
                staged.setdefault(content_hash, content)
                links[content_hash] = geometry_hash
                refs.append([identity, content_hash])
                if identity not in old_refs:
                    changes["added"].append(identity)
                elif content_hash == old_refs[identity]:
                    changes["unchanged"].append(identity)
                elif self._geometry_links[old_refs[identity]] == geometry_hash:
                    changes["metadata"].append(identity)
                else:
                    detail = _change_kind(self._object(old_refs[identity]), item)
                    changes[detail["kind"]].append(identity)
                    changes["details"][identity] = detail
            identities = {item[0] for item in refs}
            changes["removed"] = sorted(set(old_refs) - identities)
            frame = _encode({"metadata": {k: v for k, v in scene.items() if k != "meshes"}, "objects": refs})
            duplicate = bool(self._frames and frame == self._frames[-1])
            payload_charge = _charge(canonical_scene_payload) if canonical_scene_payload is not None else 0
            frame_charge = _charge(frame)
            staged_charges = {key: _charge(value, key) for key, value in staged.items()}
            frame_fits = frame_charge + sum(staged_charges.values()) + payload_charge <= self.max_bytes
            self._set_latest_scene(None)
            if not duplicate and frame_fits:
                for key, value in staged.items():
                    if key not in self._blobs:
                        self._blobs[key] = value
                        self._blob_bytes += staged_charges[key]
                self._geometry_links.update(links)
                self._frames.append(frame)
                self._frame_bytes += frame_charge
            if frame_fits and self._frames and self._frames[-1] == frame:
                self._set_latest_scene(canonical_scene_payload, frame, payload_charge=payload_charge)
            if frame_fits:
                self._trim()
            return {"scene_revision": scene["revision"], "source": scene.get("source", "host_snapshot"),
                    "scene_content_hash": _digest(frame), "changes": changes,
                    "retained": bool(self._frames and self._frames[-1] == frame),
                    "duplicate_frame": duplicate, "geometry_blobs_reused": geometry_reused,
                    "object_blobs_reused": objects_reused, "stats": self.stats()}

    def _observation_solid_support(self, mesh):
        """Exact-content, bounded, process-local support memo for observations.

        Legacy callers hash the complete current normalized mesh. Resident
        readers use the owner's private mesh/capture-version binding instead;
        model inputs cannot provide such a binding. Unknown results are not
        memoized; serialized result bytes prevent mutations through a return.
        Execution indexes deliberately never opt into this evaluator.
        """
        from .geometry_safety import solid_support_status
        key = _digest(_encode(self._measurement_mesh(mesh)))
        with self._lock:
            cached = self._solid_support.get(key)
            if cached is not None:
                self._solid_support.move_to_end(key)
                self._support_hits += 1
                return _decode(cached)
            self._support_misses += 1
            result = solid_support_status(_mesh_dict(mesh))
            if result.get('supported') is True:
                encoded = _encode(result)
                charge = _charge(encoded, key)
                if charge <= self.max_bytes:
                    previous = self._solid_support.get(key)
                    if previous is not None:
                        self._support_bytes -= _charge(previous, key)
                    self._solid_support[key] = encoded
                    self._support_bytes += charge
                    self._trim()
            return copy.deepcopy(result)

    def pair_measurement(self, focal, reference, compute, *, parameters=None, algorithm_version):
        """Return (detached_result, hit) for exactly the same ordered mesh pair.

        The caller supplies all evaluator parameters, including tolerances and
        requested output options. Failed/unknown results and exceptions are not
        memoized. Mesh metadata includes axes, pivot, identity and provenance.
        """
        if not isinstance(algorithm_version, str) or not algorithm_version:
            raise ValueError("an explicit measurement algorithm version is required")
        if parameters is not None and not isinstance(parameters, dict):
            raise ValueError("measurement parameters must be a mapping")
        key = _digest(_encode({"algorithm": algorithm_version, "parameters": parameters or {},
                              "focal": self._measurement_mesh(focal), "reference": self._measurement_mesh(reference)}))
        with self._lock:
            cached = self._measurements.get(key)
            if cached is not None:
                self._measurements.move_to_end(key)
                self._hits += 1
                self._estimated_saved_ms += cached[1]
                return _decode(cached[0]), True
            self._misses += 1
            start = time.perf_counter()
            self._computations += 1
            value = compute()
            elapsed_ms = (time.perf_counter() - start) * 1000
            # Canonical JSON also rejects NaN/Infinity anywhere in a result.
            encoded = _encode(value)
            if isinstance(value, dict) and value.get("measurement_valid") is True:
                charge = _charge(encoded, key) + 64
                if charge <= self.max_bytes:
                    previous = self._measurements.get(key)
                    if previous is not None:
                        self._measurement_bytes -= _charge(previous[0], key) + 64
                    self._measurements[key] = (encoded, elapsed_ms)
                    self._measurement_bytes += charge
                    self._trim()
            return _decode(encoded), False

    def export_state(self):
        """Export only history. No result, action permission or token survives."""
        with self._lock:
            return {"schema_version": "1.0", "purpose": "observation_only",
                    "blobs": {key: value.decode("utf-8") for key, value in self._blobs.items()},
                    "frames": [frame.decode("utf-8") for frame in self._frames]}

    def import_state(self, value, *, preserve_measurements=False):
        """Validate untrusted history atomically; never import measured values.

        ``preserve_measurements`` retains this same process's previously computed
        exact-key memo. It cannot load measurements from disk. A fresh process
        recomputes them on first observation even when history is present.
        """
        if type(preserve_measurements) is not bool:
            raise ValueError("preserve_measurements must be boolean")
        if (not isinstance(value, dict) or set(value) != {"schema_version", "purpose", "blobs", "frames"}
                or value.get("schema_version") != "1.0" or value.get("purpose") != "observation_only"
                or not isinstance(value.get("blobs"), dict) or not isinstance(value.get("frames"), list)
                or len(value["frames"]) > self.max_frames
                or len(value["blobs"]) > self.max_frames * 512):
            raise ValueError("invalid observation history state")
        encoded = _encode(value)
        if len(encoded) > self.max_bytes * 3:
            raise ValueError("history import exceeds resource budget")
        temp = SpatialSceneCache(max_bytes=self.max_bytes, max_frames=self.max_frames,
                                 max_measurements=self.max_measurements)
        blobs = {}
        for key, payload in value["blobs"].items():
            if not isinstance(key, str) or not isinstance(payload, str):
                raise ValueError("history blobs must be strings")
            raw = payload.encode("utf-8")
            if _digest(raw) != key or _encode(_decode(raw)) != raw:
                raise ValueError("history content hash or canonical encoding mismatch")
            blobs[key] = raw
        used = set()
        for text in value["frames"]:
            if not isinstance(text, str):
                raise ValueError("history frame must be a string")
            frame = _decode(text)
            if (not isinstance(frame, dict) or set(frame) != {"metadata", "objects"}
                    or not isinstance(frame["metadata"], dict) or "meshes" in frame["metadata"]
                    or not isinstance(frame["objects"], list) or len(frame["objects"]) > 256):
                raise ValueError("invalid history frame")
            meshes = []
            for ref in frame["objects"]:
                if not isinstance(ref, list) or len(ref) != 2 or any(not isinstance(v, str) for v in ref):
                    raise ValueError("invalid history object reference")
                identity, content_hash = ref
                if content_hash not in blobs:
                    raise ValueError("missing history object")
                obj = _decode(blobs[content_hash])
                if (not isinstance(obj, dict) or set(obj) != {"geometry", "metadata"}
                        or not isinstance(obj["metadata"], dict)
                        or obj["metadata"].get("object_id") != identity
                        or any(k in obj["metadata"] for k in _GEOMETRY_FIELDS)
                        or not isinstance(obj["geometry"], str) or obj["geometry"] not in blobs):
                    raise ValueError("invalid history object")
                geom = _decode(blobs[obj["geometry"]])
                if (not isinstance(geom, dict) or set(geom) - set(_GEOMETRY_FIELDS)
                        or not {"vertices", "faces"}.issubset(geom)):
                    raise ValueError("invalid history geometry")
                used.update((content_hash, obj["geometry"]))
                meshes.append({**obj["metadata"], **geom})
            result = temp.record_scene({**frame["metadata"], "meshes": meshes})
            if not result["retained"]:
                raise ValueError("history frame exceeds resource budget")
        if used != set(blobs) or len(temp._frames) != len(value["frames"]):
            raise ValueError("unreferenced or duplicate history data")
        with self._lock:
            self._blobs, self._frames = temp._blobs, temp._frames
            self._geometry_links = temp._geometry_links
            self._blob_bytes, self._frame_bytes = temp._blob_bytes, temp._frame_bytes
            self._set_latest_scene(None)
            if not preserve_measurements:
                self._measurements.clear()
                self._solid_support.clear()
                self._measurement_bytes = self._support_bytes = 0
            self._trim()
