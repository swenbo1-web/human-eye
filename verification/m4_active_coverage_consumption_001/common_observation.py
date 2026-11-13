"""Common fresh-scene observation and the optional frozen active coverage chain."""

import copy
from dataclasses import asdict
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE = ROOT / "verification/m4_active_coverage_001"
CORE = BASELINE / "coverage.py"
ADAPTER = BASELINE / "render/adapter.py"
CORE_SHA = "2561ecaf2f2df98ec7c03ed48cb95dd08c34f10ce73c1e9ecc2e32f31c41daf4"
ADAPTER_SHA = "df7e207ebd38c2876c54683e29899fccbe23187a4dd544cde1fcd9ed6ace82cd"
SITE = Path("D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Lib/site-packages")


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, default=str, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    raw = encoded(value)
    with Path(path).open("wb") as stream:
        stream.write(raw)
    return raw


def check_deadline(deadline_ns):
    if time.perf_counter_ns() >= deadline_ns:
        raise TimeoutError("original_route_deadline")


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


class Trace:
    def __init__(self, path, group):
        self.stream = Path(path).open("xb")
        self.group = group
        self.sequence = 0

    def emit(self, event, durable=False, **fields):
        self.sequence += 1
        row = {"sequence": self.sequence, "event": event, "monotonic_ns": time.perf_counter_ns(),
               "process_id": os.getpid(), "group": self.group, **fields}
        self.stream.write(encoded(row))
        self.stream.flush()
        if durable:
            os.fsync(self.stream.fileno())
        return row

    def close(self):
        self.stream.close()


class ObservationSession:
    def __init__(self, config):
        self.output = Path(config["output"]).resolve()
        self.group = config["group"]
        self.deadline_ns = config["worker_deadline_ns"]
        self.max_render_attempts = config.get("max_render_attempts", 6)
        if self.max_render_attempts != 6:
            raise ValueError("fixed_six_view_attempt_cap")
        self.trace = Trace(self.output / "TRACE.jsonl", self.group)
        self.started_ns = time.perf_counter_ns()
        self.attempts = []
        self.by_view = {}
        self.buffers = {}
        self.runtime_faults = []
        self.stages = []
        self.core = None
        self.index = None
        self.state = None
        self.active_steps = []
        self.audit = {"installed_before_dynamic_imports": True, "forbidden_old_evidence_reads": 0,
                      "old_evidence_read_attempts": [], "forbidden_old_writes": 0, "old_write_attempts": []}
        self.install_audit()
        check_deadline(self.deadline_ns)
        mark = time.perf_counter_ns()
        manifest_path = Path(config["input_manifest"]).resolve()
        manifest = json.loads(manifest_path.read_bytes())
        if manifest["schema"] != "active-coverage-consumption-001-inputs-v1":
            raise ValueError("common_input_manifest_schema")
        for key, path, expected in (("core", CORE, CORE_SHA), ("adapter", ADAPTER, ADAPTER_SHA)):
            source = manifest[key]
            if Path(source["path"]).resolve() != path.resolve() or source["sha256"] != expected:
                raise ValueError("frozen_" + key + "_binding")
        sources = {}
        for key in ("scene", "cameras"):
            source = (manifest_path.parent / manifest[key]["file"]).resolve()
            if source.parent != manifest_path.parent:
                raise ValueError("new_input_directory_binding")
            raw = source.read_bytes()
            if digest(raw) != manifest[key]["sha256"]:
                raise ValueError("new_" + key + "_source_changed")
            sources[key] = (source, raw)
        self.scene = json.loads(sources["scene"][1])
        self.cameras = json.loads(sources["cameras"][1])
        self.source_inputs = {"scene_path": str(sources["scene"][0]), "scene_sha256": digest(sources["scene"][1]),
            "camera_path": str(sources["cameras"][0]), "camera_sha256": digest(sources["cameras"][1]),
            "core_path": str(CORE.resolve()), "core_sha256": CORE_SHA,
            "adapter_path": str(ADAPTER.resolve()), "adapter_sha256": ADAPTER_SHA,
            "manifest_path": str(manifest_path), "manifest_sha256": digest(manifest_path.read_bytes())}
        self.poses = {pose["name"]: pose for pose in self.cameras["views"]}
        if len(self.poses) != 6 or any(pose["size_px"] != [512, 512] for pose in self.poses.values()):
            raise ValueError("fixed_six_512_camera_pool")
        self.stage("read_inputs", mark)
        mark = time.perf_counter_ns()
        if digest(ADAPTER.read_bytes()) != ADAPTER_SHA:
            raise ValueError("fixed_adapter_source_changed")
        self.adapter = load_module("_coverage_consumption_fixed_adapter", ADAPTER)
        self.np = self.adapter.np
        if not Path(self.np.__file__).resolve().is_relative_to(SITE.resolve()):
            raise ValueError("original_numpy_dependency_location")
        if not Path(self.adapter.PIL.__file__).resolve().is_relative_to(SITE.resolve()):
            raise ValueError("original_PIL_dependency_location")
        self.dependencies = self.adapter.dependency_binding()
        save(self.output / "DEPENDENCIES.json", self.dependencies)
        self.stage("dependencies", mark)
        mark = time.perf_counter_ns()
        self.meshes = self.adapter.load_meshes(self.scene)
        self.stage("resident_meshes", mark)
        self.trace.emit("observation_session_ready", durable=True,
                        source_inputs=self.source_inputs, candidate_views=list(self.poses))
        self.save()
        check_deadline(self.deadline_ns)

    def install_audit(self):
        allowed = {ADAPTER.resolve(),
            (ROOT / "verification/m4_surface_scan_compact_facts_001/installation/run_01/FIXED_BUILD_INPUTS.json").resolve(),
            (ROOT / "verification/m4_active_coverage_003/launch.py").resolve(),
            (ROOT / "verification/m4_active_coverage_003/bootstrap.py").resolve(),
            (ROOT / "verification/m4_active_coverage_003/inputs/DEPENDENCIES.json").resolve()}
        if self.group == "P":
            allowed.add(CORE.resolve())
        verification = (ROOT / "verification").resolve()
        own_slot = self.output.parent
        public_sources = {(HERE / name).resolve() for name in (
            "actor.py", "common_observation.py", "image_content.py", "PUBLIC_INTERFACE.md")}
        public_inputs = {(HERE / "inputs" / name).resolve() for name in (
            "SOURCES.json", "SCENE_GEOMETRY_RATIONAL.json", "CAMERAS.json", "PROMPT.txt")}

        def hook(event, arguments):
            if event != "open" or not isinstance(arguments[0], (str, bytes, os.PathLike)):
                return
            path = Path(os.fsdecode(arguments[0])).resolve()
            if not path.is_relative_to(verification):
                return
            mode, flags = arguments[1], arguments[2]
            writing = isinstance(mode, str) and any(character in mode for character in "wax+")
            writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if path.is_relative_to(own_slot):
                return
            if not writing and (path in public_sources or path in public_inputs):
                return
            cache = path.suffix == ".pyc" and (
                path.parent == ADAPTER.parent / "__pycache__" and path.name.startswith("adapter.") or
                self.group == "P" and path.parent == CORE.parent / "__pycache__" and path.name.startswith("coverage."))
            if not writing and (path in allowed or cache):
                return
            record = {"path": str(path), "mode": mode, "flags": flags}
            if writing:
                self.audit["forbidden_old_writes"] += 1
                self.audit["old_write_attempts"].append(record)
                self.trace.emit("forbidden_old_write", durable=True, **record)
                raise PermissionError("old_or_admin_evidence_write_forbidden")
            self.audit["forbidden_old_evidence_reads"] += 1
            self.audit["old_evidence_read_attempts"].append(record)
            self.trace.emit("forbidden_old_evidence_read", durable=True, **record)
            raise PermissionError("old_or_admin_evidence_read_forbidden")

        sys.addaudithook(hook)

    def stage(self, name, started, **extra):
        closed = time.perf_counter_ns()
        row = {"name": name, "started_ns": started, "closed_ns": closed,
               "elapsed_ns": closed - started, **extra}
        self.stages.append(row)
        self.trace.emit("stage_complete", **row)
        return row

    def snapshot(self):
        active = None
        if self.index is not None:
            active = {"index": {"scene_identity": self.index.scene_identity,
                "candidate_identity": self.index.candidate_identity, "roi_ids": list(self.index.region_ids),
                "regions": [asdict(region) for region in self.index.regions],
                "view_order": self.index.view_order, "view_masks": self.index.view_masks,
                "classifications": self.index.classifications, "stats": self.index.stats},
                "steps": self.active_steps, "final_state": self.state.summary()}
        return {"schema": "active-coverage-consumption-001-observations-v1", "process_id": os.getpid(),
                "group": self.group, "deadline_ns": self.deadline_ns, "started_ns": self.started_ns,
                "source_inputs": self.source_inputs, "render_attempts": self.attempts,
                "frames": [row for row in self.attempts if row["status"] == "completed"],
                "metrics": self.metrics(), "stages": self.stages, "active": active,
                "runtime_faults": self.runtime_faults, "audit": self.audit}

    def metrics(self):
        return {"render_attempts": len(self.attempts),
            "raster_completed": sum(row.get("render_closed_ns") is not None for row in self.attempts),
            "frames_completed": sum(row["status"] == "completed" for row in self.attempts),
            "PNG_bytes": sum(row.get("PNG_bytes", 0) for row in self.attempts),
            "NPZ_bytes": sum(row.get("NPZ_bytes", 0) for row in self.attempts),
            "array_payload_bytes": sum(row.get("array_payload_bytes", 0) for row in self.attempts),
            "pixel_test_attempts": sum(row.get("pixel_test_attempts", 0) for row in self.attempts),
            "pixel_tests": sum(len(row.get("pixel_rows", [])) for row in self.attempts),
            "max_render_attempts": self.max_render_attempts, "Blender_processes": 0,
            "array_payload_scope": "Generated ndarray payload bytes. Process RSS unmeasured."}

    def save(self):
        return save(self.output / "OBSERVATIONS.json", self.snapshot())

    def public_frame(self, frame, cached=False):
        return {"ref": frame["ref"], "view": frame["view_name"], "size_px": [512, 512],
                "mimeType": "image/png", "buffer_handle": frame["view_name"],
                "status": frame["status"], "cached": cached}

    def render_views(self, names):
        if not isinstance(names, (list, tuple)) or not names or any(name not in self.poses for name in names):
            raise ValueError("registered_camera_names_required")
        returned = []
        for name in names:
            check_deadline(self.deadline_ns)
            if name in self.by_view:
                frame = self.by_view[name]
                if frame["status"] != "completed":
                    raise RuntimeError("previous_view_attempt_failed")
                returned.append(self.public_frame(frame, cached=True))
                continue
            if len(self.attempts) >= self.max_render_attempts:
                raise ValueError("six_view_render_attempt_limit")
            attempt_id = len(self.attempts) + 1
            frame = {"attempt_id": attempt_id, "view_name": name, "ref": "image-" + str(attempt_id).zfill(2),
                     "status": "attempted", "pose": copy.deepcopy(self.poses[name]), "pixel_rows": [],
                     "pixel_qualification_completed": False, "render_started_ns": None,
                     "render_closed_ns": None, "completed_ns": None}
            self.attempts.append(frame)
            self.by_view[name] = frame
            folder = self.output / "frames" / (str(attempt_id).zfill(2) + "_" + name)
            try:
                intent = self.trace.emit("render_attempt", durable=True, attempt_id=attempt_id,
                                         view_name=name, ref=frame["ref"])
                frame["intent_ns"] = intent["monotonic_ns"]
                self.save()
                folder.mkdir(parents=True, exist_ok=False)
                check_deadline(self.deadline_ns)
                frame["render_started_ns"] = time.perf_counter_ns()
                buffers = self.adapter.render_one(self.meshes, self.poses[name])
                frame["render_closed_ns"] = time.perf_counter_ns()
                frame["status"] = "rendered"
                self.buffers[name] = buffers
                frame["array_payload_bytes"] = sum(value.nbytes for value in buffers.values())
                self.trace.emit("render_complete", durable=True, attempt_id=attempt_id,
                    view_name=name, started_ns=frame["render_started_ns"], closed_ns=frame["render_closed_ns"])
                self.stage("raster", frame["render_started_ns"], attempt_id=attempt_id, view_name=name)
                frame["arrays"] = {}
                for key, value in buffers.items():
                    frame["arrays"][key] = {"dtype": str(value.dtype), "dtype_str": value.dtype.str,
                        "shape": list(value.shape), "nbytes": int(value.nbytes), "sha256": digest(value.tobytes(order="C"))}
                    value.setflags(write=False)
                check_deadline(self.deadline_ns)
                mark = time.perf_counter_ns()
                png = folder / (name + ".png")
                with png.open("xb") as stream:
                    self.adapter.Image.fromarray(buffers["color"], mode="RGB").save(stream, format="PNG")
                frame.update(PNG=str(png.resolve()), PNG_bytes=png.stat().st_size, PNG_sha256=digest(png.read_bytes()))
                self.stage("PNG", mark, attempt_id=attempt_id)
                mark = time.perf_counter_ns()
                npz = folder / (name + ".npz")
                with npz.open("xb") as stream:
                    self.np.savez_compressed(stream, **buffers)
                frame.update(NPZ=str(npz.resolve()), NPZ_bytes=npz.stat().st_size, NPZ_sha256=digest(npz.read_bytes()))
                self.stage("NPZ", mark, attempt_id=attempt_id)
                frame["status"] = "completed"
                frame["completed_ns"] = time.perf_counter_ns()
                metadata = folder / "FRAME.json"
                frame["metadata_path"] = str(metadata.resolve())
                raw = save(metadata, frame)
                frame.update(metadata_sha256=digest(raw), metadata_bytes=len(raw))
                self.trace.emit("frame_complete", durable=True, attempt_id=attempt_id,
                    view_name=name, ref=frame["ref"], PNG_sha256=frame["PNG_sha256"], NPZ_sha256=frame["NPZ_sha256"])
                self.save()
                check_deadline(self.deadline_ns)
                returned.append(self.public_frame(frame))
            except BaseException as error:
                frame["status"] = "failed"
                frame["error"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
                self.runtime_faults.append({"stage": "render_views", "attempt_id": attempt_id, **frame["error"]})
                self.trace.emit("render_attempt_failed", durable=True, attempt_id=attempt_id, error=frame["error"])
                self.save()
                raise
        return returned

    def image_specification(self, ref):
        matches = [frame for frame in self.attempts if frame["ref"] == ref and frame["status"] == "completed"]
        if len(matches) != 1:
            raise ValueError("current_session_generated_image_reference_required")
        frame = matches[0]
        path = Path(frame["PNG"])
        return {"ref": ref, "file": path.name, "PNG_bytes": frame["PNG_bytes"], "sha256": frame["PNG_sha256"],
                "width": 512, "height": 512, "mimeType": "image/png"}, path.parent

    def load_active_index(self):
        if self.group != "P":
            raise ValueError("active_coverage_route_unavailable")
        if self.index is not None:
            return
        mark = time.perf_counter_ns()
        check_deadline(self.deadline_ns)
        if digest(CORE.read_bytes()) != CORE_SHA:
            raise ValueError("fixed_coverage_source_changed")
        self.core = load_module("_coverage_consumption_fixed_core", CORE)
        self.index = self.core.build_index(self.scene, self.cameras, "optimized")
        self.state = self.core.CoverageState(self.index)
        self.stage("active_index", mark)
        self.save()
        check_deadline(self.deadline_ns)

    def qualify_frame(self, frame):
        if frame["pixel_qualification_completed"]:
            return frame["pixel_rows"]
        mark = time.perf_counter_ns()
        frame["pixel_test_attempts"] = len(self.index.regions)
        try:
            frame["pixel_rows"] = self.adapter.readability_for_rois(
                self.meshes, self.poses[frame["view_name"]], self.buffers[frame["view_name"]], self.index.regions)
            frame["pixel_qualification_completed"] = True
            self.stage("active_pixels", mark, attempt_id=frame["attempt_id"])
            pixels = Path(frame["PNG"]).parent / "PIXELS.json"
            raw = save(pixels, {"ref": frame["ref"], "view_name": frame["view_name"], "pixel_rows": frame["pixel_rows"]})
            frame.update(pixels_path=str(pixels.resolve()), pixels_sha256=digest(raw), pixels_bytes=len(raw))
            self.save()
            check_deadline(self.deadline_ns)
            return frame["pixel_rows"]
        except BaseException as error:
            self.runtime_faults.append({"stage": "active_pixels", "attempt_id": frame["attempt_id"],
                "type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()})
            self.save()
            raise

    def active_coverage(self):
        try:
            self.load_active_index()
            while True:
                check_deadline(self.deadline_ns)
                name = self.state.next_view()
                if name is None:
                    break
                self.render_views([name])
                frame = self.by_view[name]
                rows = self.qualify_frame(frame)
                readable = sorted(row["roi_id"] for row in rows if row["readable"])
                receipt = {"scene_identity": self.index.scene_identity, "candidate_identity": self.index.candidate_identity,
                    "view_name": name, "actual_image_delivered": True, "image_path": frame["PNG"],
                    "image_sha256": frame["PNG_sha256"], "pixel_evidence_scope": "actual_common_depth_owner",
                    "readable_roi_ids": readable,
                    "delivery_scope": "Locally generated, readable and source-bound PNG. CLI transmission is separately counted."}
                mark = time.perf_counter_ns()
                update = self.state.observe(receipt)
                self.stage("active_observe", mark, attempt_id=frame["attempt_id"])
                complete = self.index.ids(self.index.view_masks[name])
                self.active_steps.append({"view_name": name, "ref": frame["ref"], "attempt_id": frame["attempt_id"],
                    "geometry_complete_roi_ids": complete, "readable_roi_ids": readable,
                    "pixel_shortfall_roi_ids": sorted(set(complete) - set(readable)), "receipt": receipt, "update": update})
                self.save()
            facts = self.active_facts()
            check_deadline(self.deadline_ns)
            return facts
        except BaseException as error:
            self.runtime_faults.append({"stage": "active_coverage", "type": type(error).__name__,
                                       "message": str(error), "traceback": traceback.format_exc()})
            self.save()
            raise

    def active_facts(self):
        covered = set(self.state.summary()["covered_roi_ids"])
        pool_uncovered = set(self.state.summary()["candidate_pool_uncovered_roi_ids"])
        panels = []
        for region in self.index.regions:
            evidence = []
            for name in self.state.observed_views:
                frame = self.by_view[name]
                row = next(value for value in frame["pixel_rows"] if value["roi_id"] == region.roi_id)
                if region.roi_id in self.index.ids(self.index.view_masks[name]) and row["readable"]:
                    evidence.append({"view": name, "ref": frame["ref"], "visible_surface_pixels": row["visible_surface_pixels"],
                        "contrasting_boundary_pixels": row["contrasting_boundary_pixels"]})
            status = "covered" if region.roi_id in covered else "uncovered"
            reason = None if status == "covered" else (
                "no_complete_geometric_view_in_registered_pool" if region.roi_id in pool_uncovered else "actual_pixel_or_observation_shortfall")
            panel = {"object": region.object_name, "object_index": region.object_index, "region_id": region.roi_id,
                     "status": status, "views": evidence, "reason": reason}
            if reason:
                panel["geometry_status_by_view"] = {name: self.index.classifications[name][region.roi_id]["status"]
                                                     for name in self.index.view_order}
            panels.append(panel)
        frames = [self.public_frame(self.by_view[name], cached=True) for name in self.state.observed_views]
        return {"panels": panels, "images": frames, "image_refs": [frame["ref"] for frame in frames],
                "scope": "Registered finite camera pool with current-session whole-scene rasters and actual owner/RGB pixel evidence.",
                "observation_scope": "Local generated PNG evidence. Attached image delivery is counted separately."}
