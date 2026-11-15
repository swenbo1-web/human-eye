"""Current-geometry inspect/focus facts and version-bound region references."""

from contextlib import contextmanager
from collections import deque
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time

import numpy as np

HERE = Path(__file__).resolve().parent
_HELPER_PATH = HERE.parent / "m6_perception_001/region_common.py"
_HELPER_SPEC = importlib.util.spec_from_file_location("_task_perception_region_helpers", _HELPER_PATH)
_HELPERS = importlib.util.module_from_spec(_HELPER_SPEC)
_HELPER_SPEC.loader.exec_module(_HELPERS)
components = _HELPERS.components
geometry_facts = _HELPERS.geometry_facts
process_resources = _HELPERS.process_resources
source_ids_digest = _HELPERS.source_ids_digest

REFERENCE_PREFIX = "m6taskperception://v1/region/"


def array_digest(values):
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def json_digest(value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf8")).hexdigest()


def checked_ids(values, count, allow_empty=False):
    values = np.asarray(values)
    if values.ndim != 1 or not np.issubdtype(values.dtype, np.integer):
        raise ValueError("source_IDs_must_be_integer_vector")
    ids = np.sort(values.astype(np.int64))
    if (not allow_empty and not len(ids)) or len(np.unique(ids)) != len(ids):
        raise ValueError("source_IDs_empty_or_duplicated")
    if len(ids) and (ids[0] < 0 or ids[-1] >= count):
        raise ValueError("source_ID_out_of_range")
    return ids


def fixed_target_ids(faces, F_source_ids, count=64):
    """Frozen source-ID BFS target, independent of scores and perturbation labels."""
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("target_count_must_be_positive_integer")
    F = np.sort(np.asarray(F_source_ids, dtype=np.int64))
    adjacency = {int(source_id): set() for source_id in F}
    edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    inside = np.isin(edges, F).all(axis=1)
    for first, second in edges[inside]:
        adjacency[int(first)].add(int(second))
        adjacency[int(second)].add(int(first))
    available = set(adjacency)
    selected = []
    for seed in F:
        if int(seed) not in available:
            continue
        queue = deque([int(seed)])
        available.remove(int(seed))
        while queue:
            current = queue.popleft()
            selected.append(current)
            if len(selected) >= count:
                return np.asarray(sorted(selected), dtype=np.int64)
            for neighbor in sorted(adjacency[current]):
                if neighbor in available:
                    available.remove(neighbor)
                    queue.append(neighbor)
    return np.asarray(sorted(selected), dtype=np.int64)


class TaskPerception:
    """Cache current topology/geometry and load learned predictions only for inspect."""

    def __init__(self, root=HERE):
        started, cpu = time.perf_counter(), time.process_time()
        self.root = Path(root)
        index = self._read("INPUT_INDEX.json")
        self.cases = {row["alias"]: {"alias": row["alias"], "input": row["input"]} for row in index["cases"]}
        if len(self.cases) != len(index["cases"]):
            raise ValueError("duplicate_observation_alias")
        self.geometry_cache = {}
        self.features_cache = {}
        self.prediction_cache = {}
        self.features_index = None
        self.predictions_index = None
        self.features_index_sha256 = None
        self.predictions_index_sha256 = None
        self.calibration_sha256 = None
        self.setup_cost = dict(wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)
        self.setup_charged = False
        self.timings = {}

    def _read(self, relative):
        return json.loads((self.root / relative).read_bytes())

    @contextmanager
    def _measure(self, name):
        started, cpu = time.perf_counter(), time.process_time()
        try:
            yield
        finally:
            row = self.timings.setdefault(name, dict(wall_s=0., CPU_s=0., calls=0))
            row["wall_s"] += time.perf_counter() - started
            row["CPU_s"] += time.process_time() - cpu
            row["calls"] += 1

    def _begin(self):
        self.timings = {}
        return time.perf_counter(), time.process_time()

    def _finish(self, report, start):
        report["cost"] = dict(wall_s=time.perf_counter() - start[0], CPU_s=time.process_time() - start[1],
                              stages=self.timings, initial_index_setup=self.setup_cost if not self.setup_charged else None,
                              process_resources=process_resources(),
                              model_called_in_this_request=False)
        self.setup_charged = True
        return report

    def _load_geometry(self, alias):
        case = self.cases[alias]
        with self._measure("current_input_identity_read"):
            path = self.root / case["input"]["path"]
            raw_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if raw_sha != case["input"]["sha256"]:
                raise ValueError("current_input_version_changed")
        if alias in self.geometry_cache:
            return self.geometry_cache[alias]
        with self._measure("first_current_geometry_topology_preparation"):
            with np.load(path, allow_pickle=False) as data:
                vertices = np.asarray(data["vertices"], dtype=np.float64)
                faces = np.asarray(data["faces"], dtype=np.int64)
                F = np.asarray(data["F_source_ids"] if "F_source_ids" in data else data["F_ids"], dtype=np.int64)
            if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
                raise ValueError("invalid_current_vertices")
            if faces.ndim != 2 or faces.shape[1] != 3 or not len(faces) or faces.min() < 0 or faces.max() >= len(vertices):
                raise ValueError("invalid_current_triangles")
            checked_ids(F, len(vertices))
            triangle = vertices[faces]
            cross = np.cross(triangle[:, 1] - triangle[:, 0], triangle[:, 2] - triangle[:, 0])
            area = np.zeros(len(vertices), dtype=np.float64)
            normal_sum = np.zeros_like(vertices)
            cross_length = np.linalg.norm(cross, axis=1)
            for corner in range(3):
                np.add.at(area, faces[:, corner], cross_length / 6)
                np.add.at(normal_sum, faces[:, corner], cross)
            normal_length = np.linalg.norm(normal_sum, axis=1)
            normals = np.divide(normal_sum, normal_length[:, None], out=np.zeros_like(vertices), where=normal_length[:, None] > 0)
            edges = np.unique(np.sort(np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1), axis=0)
            lookup = np.full(len(vertices), -1, dtype=np.int64)
            lookup[F] = np.arange(len(F))
            within = (lookup[edges] >= 0).all(axis=1)
            F_edges = lookup[edges[within]].T
            identity = dict(observation_alias=alias, input_sha256=raw_sha,
                            current_vertices_sha256=array_digest(vertices), topology_sha256=array_digest(faces),
                            F_source_ids_sha256=source_ids_digest(F))
            geometry = dict(alias=alias, vertices=vertices, faces=faces, F=F, area=area, normals=normals,
                            normal_available=normal_length > 0, edges=edges, F_edges=F_edges, identity=identity)
            self.geometry_cache[alias] = geometry
        return geometry

    def _features(self, alias, geometry):
        with self._measure("feature_cache_identity_guard"):
            index_bytes = (self.root / "FEATURES.json").read_bytes()
            index_sha = hashlib.sha256(index_bytes).hexdigest()
            if self.features_index is None:
                self.features_index = {row["alias"]: row for row in json.loads(index_bytes)["cases"]}
                self.features_index_sha256 = index_sha
            if self.features_index_sha256 != index_sha:
                raise ValueError("feature_cache_index_changed")
            record = self.features_index[alias]
            path = self.root / record["path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("feature_cache_payload_changed")
            input_sha = record.get("current_input_sha256", record.get("input_sha256"))
            if input_sha is not None and input_sha != geometry["identity"]["input_sha256"]:
                raise ValueError("feature_cache_current_input_binding_mismatch")
        if alias not in self.features_cache:
            with self._measure("feature_cache_index_and_payload_read"):
                with np.load(path, allow_pickle=False) as payload:
                    values = dict(area=np.asarray(payload["area"], dtype=np.float64),
                                  baseline_score=np.asarray(payload["baseline_score"], dtype=np.float64),
                                  source_ids=np.asarray(payload["source_ids"], dtype=np.int64))
                F = geometry["F"]
                if any(value.shape != (len(F),) for value in values.values()):
                    raise ValueError("feature_F_mapping_shape_mismatch")
                if not np.array_equal(values["source_ids"], F):
                    raise ValueError("feature_current_source_mapping_mismatch")
                if not np.allclose(values["area"], geometry["area"][F], rtol=1e-12, atol=0):
                    raise ValueError("feature_current_lumped_area_mismatch")
                self.features_cache[alias] = values
        return self.features_cache[alias]

    def _prediction(self, alias, geometry):
        with self._measure("prediction_cache_identity_guard"):
            index_bytes = (self.root / "PREDICTIONS.json").read_bytes()
            index_sha = hashlib.sha256(index_bytes).hexdigest()
            if self.predictions_index is None:
                self.predictions_index = {row["alias"]: row for row in json.loads(index_bytes)["cases"]}
                self.predictions_index_sha256 = index_sha
            if self.predictions_index_sha256 != index_sha:
                raise ValueError("prediction_cache_index_changed")
            record = self.predictions_index[alias]
            path = self.root / record["path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("prediction_cache_payload_changed")
            input_sha = record.get("current_input_sha256", record.get("input_sha256"))
            if input_sha is not None and input_sha != geometry["identity"]["input_sha256"]:
                raise ValueError("prediction_cache_current_input_binding_mismatch")
            calibration_bytes = (self.root / "CALIBRATION.json").read_bytes()
            calibration_sha = hashlib.sha256(calibration_bytes).hexdigest()
            if self.calibration_sha256 is None:
                self.calibration_sha256 = calibration_sha
            if self.calibration_sha256 != calibration_sha:
                raise ValueError("calibration_changed_after_prediction_cache_read")
        if alias not in self.prediction_cache:
            with self._measure("prediction_cache_index_and_payload_read"):
                with np.load(path, allow_pickle=False) as payload:
                    score = np.asarray(payload["optimized_probability"], dtype=np.float64)
                    if "source_ids" in payload:
                        mapping_matches = np.array_equal(np.asarray(payload["source_ids"], dtype=np.int64), geometry["F"])
                    else:
                        mapping_digest = record.get("F_source_ids_sha256", record.get("source_ids_sha256"))
                        mapping_matches = mapping_digest == geometry["identity"]["F_source_ids_sha256"]
                if not mapping_matches:
                    raise ValueError("prediction_source_mapping_binding_mismatch_or_missing")
                threshold = float(json.loads(calibration_bytes)["optimized"]["threshold"])
                if score.shape != (len(geometry["F"]),) or not np.isfinite(score).all() or not np.isfinite(threshold):
                    raise ValueError("invalid_current_prediction")
                self.prediction_cache[alias] = dict(score=score, threshold=threshold)
        return self.prediction_cache[alias]

    def _facts(self, geometry, ids):
        vertices, area = geometry["vertices"][ids], geometry["area"][ids]
        facts = geometry_facts(vertices, area)
        total = float(area.sum())
        weighted_normal = np.sum(geometry["normals"][ids] * area[:, None], axis=0)
        normal_length = float(np.linalg.norm(weighted_normal))
        facts.update(points=len(ids), lumped_area_native=total, area_unit="source_native_squared",
                     mean_normal=(weighted_normal / normal_length).tolist() if normal_length else None,
                     mean_normal_definition="normalized_area_weighted_current_vertex_normal_sum",
                     unavailable_vertex_normals=int((~geometry["normal_available"][ids]).sum()),
                     area_definition="sum_of_current_full_source_triangle_area_divided_equally_among_its_three_vertices")
        return facts

    def _reference(self, geometry, ids, kind, provenance=None):
        ids = checked_ids(ids, len(geometry["vertices"]))
        identity = dict(geometry["identity"], contract="m6-task-perception-region-v1", kind=kind,
                        region_source_ids_sha256=source_ids_digest(ids), provenance=provenance)
        reference = REFERENCE_PREFIX + json_digest(identity)
        record = dict(identity=identity, source_ids=ids.tolist())
        encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf8")
        with self._measure("reference_binding_cache_write"):
            folder = self.root / "private/references"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (reference.rsplit("/", 1)[1] + ".json")
            if path.exists():
                if path.read_bytes() != encoded:
                    raise ValueError("region_reference_cache_identity_collision")
            else:
                with tempfile.NamedTemporaryFile(dir=folder, suffix=".tmp", delete=False) as output:
                    output.write(encoded)
                    temporary = Path(output.name)
                os.replace(temporary, path)
        return dict(reference=reference, kind=kind, geometry=self._facts(geometry, ids),
                    read_more=dict(resolver="resolve_region", reference=reference, context_reader="read_more"))

    def _regions(self, geometry, scores, selected, kind, provenance, max_regions):
        with self._measure(kind + "_connected_regions_and_facts"):
            groups = components(selected, geometry["F_edges"])
            F_area = geometry["area"][geometry["F"]]
            groups.sort(key=lambda rows: (-float(np.sum(F_area[rows] * scores[rows])), int(geometry["F"][rows].min())))
            regions = []
            for rows in groups:
                region = self._reference(geometry, geometry["F"][rows], kind, provenance)
                region["score"] = dict(min=float(scores[rows].min()), mean=float(scores[rows].mean()), max=float(scores[rows].max()))
                regions.append(region)
        return dict(region_count=len(regions), selected_points=int(selected.sum()),
                    selected_area_native=float(F_area[selected].sum()),
                    selected_area_fraction_of_scope=float(F_area[selected].sum() / F_area.sum()),
                    top_regions=regions[:max_regions], remaining_region_count=max(0, len(regions) - max_regions),
                    all_region_references=[region["reference"] for region in regions])

    def inspect(self, alias, mode="perception", request="", max_regions=3):
        start = self._begin()
        if mode not in ("geometry", "perception"):
            raise ValueError("unknown_inspection_mode")
        geometry = self._load_geometry(alias)
        features = self._features(alias, geometry)
        area = geometry["area"][geometry["F"]]
        if mode == "perception":
            prediction = self._prediction(alias, geometry)
            scores, threshold = prediction["score"], prediction["threshold"]
        else:
            scores, threshold = features["baseline_score"], None
        if not np.isfinite(scores).all() or not len(scores) or area.sum() <= 0:
            raise ValueError("unavailable_current_inspection_score")
        order = np.lexsort((geometry["F"], -scores))
        prefix = int(np.searchsorted(np.cumsum(area[order]), .25 * area.sum(), side="right"))
        attention_mask = np.zeros(len(area), dtype=bool)
        attention_mask[order[:prefix]] = True
        provenance = dict(mode=mode, score_sha256=array_digest(scores), threshold=threshold,
                          feature_cache_sha256=self.features_index[alias]["sha256"],
                          prediction_cache_sha256=self.predictions_index[alias]["sha256"] if mode == "perception" else None,
                          calibration_sha256=self.calibration_sha256 if mode == "perception" else None,
                          score_nature="uncalibrated_learned_probability" if mode == "perception" else "direct_geometry_score")
        scope = self._reference(geometry, geometry["F"], "inspection_scope")
        attention = self._regions(geometry, scores, attention_mask, "attention_candidate", provenance, max_regions)
        attention.update(area_budget=.25, selection="descending_score_prefix_with_total_lumped_area_at_most_budget", status="candidate_attention_requires_inspection")
        if threshold is None:
            anomaly = dict(available=False, nature="direct_geometry_attention_only")
        else:
            anomaly = self._regions(geometry, scores, scores > threshold, "threshold_prediction", provenance, max_regions)
            anomaly.update(available=True, threshold=threshold, comparison="strictly_greater", nature="learned_prediction_unconfirmed",
                           label="candidate_synthetic_local_surface_depression")
        report = dict(contract="m6-task-perception-facts-v1", entrypoint="inspect", task=dict(request=request, target_source="specified_inspection_scope"),
                      observation=geometry["identity"], inspection_scope=scope, attention=attention,
                      threshold_anomaly_prediction=anomaly, learned_output_used=mode == "perception", cached_prediction_used=mode == "perception",
                      measurements="computed_from_current_geometry", semantics="source_point_binding_only_no_anatomical_part_classifier")
        return self._finish(report, start)

    def focus(self, alias, target_ids, protected_ids=(), request="", mode="perception"):
        start = self._begin()
        geometry = self._load_geometry(alias)
        target = checked_ids(target_ids, len(geometry["vertices"]))
        protected = checked_ids(np.asarray(protected_ids, dtype=np.int64), len(geometry["vertices"]), allow_empty=True)
        background = np.setdiff1d(geometry["F"], target)
        provenance = dict(target_source="explicit_task_source_point_ids", requested_target_sha256=source_ids_digest(target))
        target_region = self._reference(geometry, target, "user_target", provenance)
        background_region = self._reference(geometry, background, "observable_background", provenance) if len(background) else None
        protected_region = self._reference(geometry, protected, "protected_from_editing", provenance) if len(protected) else None
        touching = geometry["edges"][np.isin(geometry["edges"], target).any(axis=1)]
        context_ids = np.unique(np.r_[target, touching.ravel()])
        context_region = self._reference(geometry, context_ids, "observable_topological_context", dict(parent_reference=target_region["reference"], ring_hops=1))
        editable = np.setdiff1d(target, protected)
        report = dict(contract="m6-task-perception-facts-v1", entrypoint="focus", task=dict(request=request, target_source="explicit_task_source_point_ids"),
                      observation=geometry["identity"], target=target_region, background=background_region, protected=protected_region,
                      context=context_region, context_definition="target_and_its_full_current_source_topology_one_ring",
                      target_points_outside_inspection_scope=int((~np.isin(target, geometry["F"])).sum()),
                      target_and_protection_overlap_points=int(np.intersect1d(target, protected).size),
                      editable_target_source_ids=editable.tolist(), background_observation_allowed=True,
                      anomaly_threshold_applied=False, learned_output_used=False, cached_prediction_used=False,
                      prediction=None, measurements="computed_from_current_geometry", semantics="explicit_target_binding_no_anatomical_part_classifier")
        return self._finish(report, start)

    def _resolve(self, reference):
        if not isinstance(reference, str) or not reference.startswith(REFERENCE_PREFIX):
            raise ValueError("invalid_region_reference")
        digest = reference[len(REFERENCE_PREFIX):]
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("invalid_region_reference_digest")
        record = self._read("private/references/" + digest + ".json")
        if json_digest(record["identity"]) != digest:
            raise ValueError("region_reference_identity_changed")
        geometry = self._load_geometry(record["identity"]["observation_alias"])
        for key, value in geometry["identity"].items():
            if record["identity"].get(key) != value:
                raise ValueError("stale_region_observation_binding")
        ids = checked_ids(np.asarray(record["source_ids"], dtype=np.int64), len(geometry["vertices"]))
        if source_ids_digest(ids) != record["identity"]["region_source_ids_sha256"]:
            raise ValueError("region_source_IDs_changed")
        return geometry, ids, record

    def resolve(self, reference, include_geometry=True):
        start = self._begin()
        with self._measure("reference_identity_read_and_current_resolution"):
            geometry, ids, record = self._resolve(reference)
            result = dict(reference=reference, identity=record["identity"], geometry=self._facts(geometry, ids), source_ids=ids.tolist())
            if include_geometry:
                result.update(current_positions_native=geometry["vertices"][ids].tolist(),
                              lumped_area_native=geometry["area"][ids].tolist(), current_vertex_normals=geometry["normals"][ids].tolist())
        return self._finish(result, start)

    def read_more(self, reference, ring_hops=1):
        start = self._begin()
        if isinstance(ring_hops, bool) or not isinstance(ring_hops, int) or ring_hops < 0:
            raise ValueError("ring_hops_must_be_nonnegative_integer")
        with self._measure("current_topological_context_expansion"):
            geometry, ids, _ = self._resolve(reference)
            selected = np.zeros(len(geometry["vertices"]), dtype=bool)
            selected[ids] = True
            for _ in range(ring_hops):
                incident = geometry["edges"][selected[geometry["edges"]].any(axis=1)]
                selected[incident.ravel()] = True
            context_ids = np.flatnonzero(selected)
            context = self._reference(geometry, context_ids, "observable_topological_context", dict(parent_reference=reference, ring_hops=ring_hops))
        return self._finish(dict(reference=reference, context=context, added_points=len(context_ids) - len(ids),
                                 background_observation_allowed=True, editing_authorized=False), start)


_PROTOTYPE = None


def prototype():
    global _PROTOTYPE
    if _PROTOTYPE is None:
        _PROTOTYPE = TaskPerception()
    return _PROTOTYPE


def task_payload(taskdir):
    taskdir = Path(taskdir)
    task = json.loads((taskdir / "task.json").read_bytes())
    with np.load(taskdir / task.get("input_file", "input.npz"), allow_pickle=False) as data:
        arrays = {key: data[key] for key in data.files}
    geometry = prototype()._load_geometry(task["geometry_alias"])
    F = arrays["F_ids"] if "F_ids" in arrays else arrays["F_source_ids"]
    if any(left.dtype != right.dtype or left.shape != right.shape or left.tobytes() != right.tobytes()
           for left, right in ((arrays["vertices"], geometry["vertices"]), (arrays["faces"], geometry["faces"]), (F.astype(np.int64), geometry["F"]))):
        raise ValueError("consumer_task_current_input_identity_mismatch")
    return task, arrays


def report(taskdir, route):
    started, cpu = time.perf_counter(), time.process_time()
    prototype().timings = {}
    task, arrays = task_payload(taskdir)
    validation_cost = dict(wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
                           stages=prototype().timings.copy())
    mode = "geometry" if route in ("facts", "geometry") else "perception"
    if route not in ("facts", "geometry", "learned", "perception"):
        raise ValueError("unknown_consumer_route")
    if task["entrypoint"] == "inspect":
        result = prototype().inspect(task["geometry_alias"], mode=mode, request=task["request_text"])
    elif task["entrypoint"] == "focus":
        result = prototype().focus(task["geometry_alias"], arrays["target_ids"], arrays.get("protected_ids", np.empty(0, dtype=np.int64)),
                                   request=task["request_text"], mode=mode)
    else:
        raise ValueError("unknown_task_entrypoint")
    result["cost"].update(wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu,
                          consumer_current_input_validation=validation_cost)
    return result


def resolve_region(taskdir, route, reference, include_geometry=True):
    started, cpu = time.perf_counter(), time.process_time()
    prototype().timings = {}
    task, _ = task_payload(taskdir)
    resolved = prototype().resolve(reference, include_geometry=include_geometry)
    if resolved["identity"]["observation_alias"] != task["geometry_alias"]:
        raise ValueError("region_reference_belongs_to_other_task_observation")
    resolved["cost"].update(wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu)
    return resolved


def read_more(taskdir, route, reference, ring_hops=1):
    started, cpu = time.perf_counter(), time.process_time()
    preflight = resolve_region(taskdir, route, reference, include_geometry=False)
    result = prototype().read_more(reference, ring_hops=ring_hops)
    result["cost"].update(wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu,
                          included_current_input_validation_and_resolution=preflight["cost"])
    return result
