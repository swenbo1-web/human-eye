"""Shared raw Blender input, fixed SCENE raster and same-slot frame cache."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import time
from types import MappingProxyType

import numpy as np
from PIL import Image


PIXEL_CONVENTION = {
    "origin": "top_left",
    "array_order": "rows_y_then_columns_x",
    "sample_position": [0.5, 0.5],
    "ndc_x_to_image": "(ndc_x + 1) * (width - 1) / 2",
    "ndc_y_to_image": "(1 - ndc_y) * (height - 1) / 2",
    "depth": "positive camera-space metres, +inf for background",
    "background_owner": -1,
}
BUFFER_NAMES = ("color", "depth", "owners", "triangle_ids")
CAPTURE_CODE = Path(__file__).with_name("device_capture.py")
TRIANGLE_ID_SCOPE = "zero-based-global-source-triangles-in-mesh-order"


def _encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write_new(path, value):
    raw = _encode(value)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _span(started):
    closed = time.perf_counter_ns()
    return {"started_ns": started, "closed_ns": closed, "elapsed_ns": closed - started}


def _view_key(pose):
    return {key: pose[key] for key in ("name", "size_px", "view_matrix", "projection_matrix")}


def _validate_pose(pose, *, frozen):
    size = pose.get("size_px")
    if (pose.get("name") != "SCENE" or type(size) is not list or len(size) != 2
            or any(type(value) is not int or value < 1 for value in size)):
        raise ValueError("actual_scene_view_and_size_required")
    if frozen and size != [512, 512]:
        raise ValueError("fixed_display001_scene_size_required")
    for key in ("view_matrix", "projection_matrix"):
        matrix = np.asarray(pose[key], dtype=np.float64)
        if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
            raise ValueError("finite_fixed_camera_matrix_required:" + key)


def freeze_camera(display_result, output):
    """Copy only the pose and provenance of the original actual DISPLAY001 frame."""
    started = time.perf_counter_ns()
    archive = Path(display_result).resolve()
    raw = archive.read_bytes()
    result = json.loads(raw)
    if result.get("result_kind") != "source_region":
        raise ValueError("display001_source_region_producer_archive_required")
    frames = [frame for frame in result["frames"] if frame.get("view_name") == "SCENE"]
    if len(frames) != 1:
        raise ValueError("one_original_display001_scene_frame_required")
    frame = frames[0]
    pose = frame["pose"]
    _validate_pose(pose, frozen=True)
    packet = {
        "schema": "m4-live-source-region-display001-camera-v1",
        "views": [pose], "pixel_convention": copy.deepcopy(PIXEL_CONVENTION),
        "camera_sha256": _sha(_encode(_view_key(pose))),
        "provenance": {
            "source": "DISPLAY001 original actual SCENE frame",
            "producer_result_path": str(archive), "producer_result_sha256": _sha(raw),
            "frame_identity": frame["frame_identity"], "image_sha256": frame["image_sha256"],
            "arrays_sha256": frame["arrays_sha256"],
        },
        "freeze_read": _span(started),
    }
    _write_new(Path(output), packet)
    return packet


class FrameDevice:
    """Retain current raw geometry and the actual frame artifacts for one owned slot."""

    def __init__(self, runroot, camera, asset_sha256, group, label, native_call,
                 terminal_call=None, budget=None, phase="formal", check=lambda: None):
        self.runroot = Path(runroot).resolve()
        self.camera = copy.deepcopy(camera)
        if len(self.camera["views"]) != 1 or self.camera["pixel_convention"] != PIXEL_CONVENTION:
            raise ValueError("one_fixed_scene_camera_with_shared_pixel_convention_required")
        self.pose = self.camera["views"][0]
        _validate_pose(self.pose, frozen=True)
        self.cameras = {"views": [copy.deepcopy(_view_key(self.pose))],
                        "pixel_convention": copy.deepcopy(camera["pixel_convention"])}
        if self.camera["camera_sha256"] != _sha(_encode(_view_key(self.pose))):
            raise ValueError("fixed_camera_digest_mismatch")
        self.asset_sha256 = asset_sha256
        self.group = group
        self.label = label
        self.phase = phase
        self.native_call = native_call
        self.terminal_call = native_call if terminal_call is None else terminal_call
        self.budget = budget
        self.check = check
        self.buffers = {}
        self.by_ref = {}
        self.by_view = {}
        self.source_reads = []
        self.events = []
        self._native_counter = 0
        self._source_counter = 0
        self._scene = None
        self._renderer = None
        self._preferred_product_ref = None
        self._terminal_receipt = None

    def _record(self, event, **details):
        self.events.append({"event": event, "at_ns": time.perf_counter_ns(), **details})

    def _capture(self, *, terminal):
        self._source_counter += 1
        ref = "live-source-" + str(self._source_counter).zfill(3)
        if terminal:
            path = self.runroot / "terminal_sources" / (ref + ".json")
        else:
            path = self.runroot / "raw_sources" / (ref + ".json")
        path.parent.mkdir(exist_ok=True)
        started = time.perf_counter_ns()
        source_code = CAPTURE_CODE.read_text(encoding="utf-8") + (
            "\ncapture_device(bpy, " + repr(str(path)) + ", " + repr(self.asset_sha256)
            + ", terminal=" + repr(terminal) + ")"
        )
        code = "exec(compile(" + repr(source_code) + ", '<m4-live-device-capture>', 'exec'), {'bpy': bpy})"
        callback = self.terminal_call if terminal else self.native_call
        record = {"source_ref": ref, "path": str(path), "terminal": terminal, "status": "failed"}
        self.source_reads.append(record)
        try:
            result = callback(code, trusted=True, timeout_s=30)
            if result.get("error") is not None:
                raise RuntimeError("owned_blender_scene_read_failed:" + str(result["error"]))
            marker = "M4_LIVE_SOURCE_CAPTURE:"
            lines = [line[len(marker):] for line in result["stdout"].splitlines() if line.startswith(marker)]
            if len(lines) != 1:
                raise ValueError("one_owned_scene_capture_receipt_required")
            worker = json.loads(lines[0])
            raw = path.read_bytes()
            digest = _sha(raw)
            if (len(raw), digest) != (worker["bytes"], worker["sha256"]):
                raise ValueError("owned_scene_capture_readback_mismatch")
            scene = json.loads(raw)
            if scene["source"]["pid"] != worker["pid"] or scene["source"]["asset_sha256"] != self.asset_sha256:
                raise ValueError("owned_scene_capture_source_identity_mismatch")
            if not scene["objects"] or [item["visible_get"] for item in scene["objects"]] != scene["display_object_mask"]:
                raise ValueError("complete_current_scene_display_mask_required")
            arrays = [item["evaluated"] if terminal else item for item in scene["objects"]]
            record.update(sha256=digest, bytes=len(raw), worker=worker,
                          evaluated_counts={"vertices": sum(len(item["vertices"]) for item in arrays),
                                            "triangles": sum(len(item["triangles"]) for item in arrays),
                                            "polygons": sum(item["polygon_count"] for item in arrays)})
            if terminal:
                arrays = [item["native"] for item in scene["objects"]]
                record["native_counts"] = {"vertices": sum(len(item["vertices"]) for item in arrays),
                                           "triangles": sum(len(item["triangles"]) for item in arrays),
                                           "polygons": sum(item["polygon_count"] for item in arrays)}
                final = self.runroot / "TERMINAL_SOURCE.json"
                os.link(path, final)
                record.update(path=str(final), worker_path=str(path))
            scene["source_ref"] = ref
            record["status"] = "complete"
            return scene
        except Exception as error:
            record["error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        finally:
            record["parent_read"] = _span(started)
            self.save_evidence()

    def _raw_scene(self, requested_by):
        if self._scene is None:
            self._scene = self._capture(terminal=False)
            self._record("geometry_captured", requested_by=requested_by, source_ref=self._scene["source_ref"])
        else:
            self._record("geometry_cache_hit", requested_by=requested_by, source_ref=self._scene["source_ref"])
        return self._scene

    def scene_data(self, selectors=None):
        self.check()
        names = None
        if selectors is not None:
            if type(selectors) is not list or any(type(item) is not str for item in selectors):
                raise ValueError("raw_object_names_or_null_required")
            names = set(selectors)
        result = copy.deepcopy(self._raw_scene("scene_data"))
        if names is not None:
            objects = result["objects"]
            original_offsets = result["source_face_offsets"]
            result["objects"] = [item for item in objects if item["name"] in names]
            if {item["name"] for item in result["objects"]} != names:
                raise ValueError("raw_selected_object_missing")
            result["source_triangle_ranges"] = {
                obj["name"]: original_offsets[index:index + 2]
                for index, obj in enumerate(objects) if obj["name"] in names
            }
            if len(result["objects"]) != len(objects):
                result.pop("source_face_offsets")
                result["display_object_mask"] = [item["visible_get"] for item in result["objects"]]
        self.save_evidence()
        self.check()
        return result

    def _prepare_raster(self):
        scene = self._raw_scene("render_views")
        if self._renderer is not None:
            self._record("native_raster_geometry_cache_hit", source_ref=scene["source_ref"])
            return self._renderer
        started = time.perf_counter_ns()
        from human_eye_module1_operators import MeshEntity3D
        from human_eye_plugin.attention_raster import rasterize_attention

        meshes, raw_ids = [], []
        offsets = scene["source_face_offsets"]
        for index, item in enumerate(scene["objects"]):
            mesh = MeshEntity3D(
                object_id=item["object_id"], mark_label="raw_" + str(index), name=item["name"],
                vertices=np.asarray(item["vertices"], dtype=np.float64),
                faces=np.asarray(item["triangles"], dtype=np.int32), edges=np.empty((0, 2), dtype=np.int32),
                color_rgb=(180, 190, 205), local_axes=np.eye(3, dtype=np.float64),
                axes_source="world_geometry", axes_confidence="explicit",
                axes_reason="world_coordinates_no_transform",
            )
            meshes.append(mesh)
            raw_ids.append(np.arange(offsets[index], offsets[index + 1], dtype=np.int32))
        self._renderer = (rasterize_attention, tuple(meshes), tuple(raw_ids))
        self._record("native_raster_geometry_prepared", source_ref=scene["source_ref"],
                     geometry_bytes=sum(mesh.vertices.nbytes + mesh.faces.nbytes for mesh in meshes),
                     source_triangle_id_bytes=sum(ids.nbytes for ids in raw_ids), **_span(started))
        return self._renderer

    def _register(self, row, arrays):
        names, ids = row["object_names"], row["object_ids"]
        offsets, mask = row["source_face_offsets"], row["display_object_mask"]
        if (len(names) != len(ids) or len(set(ids)) != len(ids)
                or len(mask) != len(ids) or any(type(value) is not bool for value in mask)
                or len(offsets) != len(ids) + 1 or offsets[0] != 0
                or any(first >= last for first, last in zip(offsets, offsets[1:]))):
            raise ValueError("full_ordered_source_owner_mapping_required")
        width, height = row["size_px"]
        for name, dtype, shape in (
                ("color", np.uint8, (height, width, 3)),
                ("depth", np.float64, (height, width)),
                ("owners", np.int32, (height, width)),
                ("triangle_ids", np.int32, (height, width))):
            if arrays[name].dtype != dtype or arrays[name].shape != shape:
                raise ValueError("actual_frame_array_dtype_and_size_required:" + name)
        owners, triangles = arrays["owners"], arrays["triangle_ids"]
        background = owners == -1
        depth = arrays["depth"]
        if (np.any(owners < -1) or np.any(owners >= len(ids))
                or np.any(triangles[background] != -1)
                or not np.all(np.isposinf(depth[background]))
                or not np.all(np.isfinite(depth[~background]) & (depth[~background] > 0))):
            raise ValueError("frame_depth_and_background_owner_consistency_required")
        for index, participates in enumerate(mask):
            triangle_samples = triangles[owners == index]
            if ((not participates and triangle_samples.size)
                    or np.any(triangle_samples < offsets[index]) or np.any(triangle_samples >= offsets[index + 1])):
                raise ValueError("actual_frame_display_and_source_triangle_owners_required")
        for values in arrays.values():
            values.setflags(write=False)
        ref = row["ref"]
        row["buffer_handle"] = ref
        row["status"] = "completed"
        row["triangle_id_scope"] = TRIANGLE_ID_SCOPE
        row["buffer_payload_bytes"] = sum(values.nbytes for values in arrays.values())
        self.by_ref[ref] = row
        self.buffers[ref] = MappingProxyType(arrays)
        if row["origin"] == "product" and self._preferred_product_ref is None:
            self._preferred_product_ref = ref
        preferred = self._preferred_product_ref or ref
        self.by_view[row["view"]] = self.by_ref[preferred]
        self.buffers[row["view"]] = self.buffers[preferred]

    def _native_frame(self):
        rasterize, meshes, raw_ids = self._prepare_raster()
        scene = self._scene
        self._native_counter += 1
        ordinal = self._native_counter
        view = np.asarray(self.pose["view_matrix"], dtype=np.float64)
        projection = np.asarray(self.pose["projection_matrix"], dtype=np.float64)
        size = self.pose["size_px"][0]
        object_mask = tuple(scene["display_object_mask"])
        self.check()
        token = None if self.budget is None else self.budget.reserve("raster_attempt", self.label, self.phase, 1)
        status = "failed"
        started = time.perf_counter_ns()
        try:
            result = rasterize(meshes, view, projection, size, return_owner=True, return_patch_owner=True,
                               face_patch_ids=raw_ids, object_mask=object_mask)
            status = "raster_returned"
        finally:
            raster_stage = _span(started)
            details = {"runtime": str(self.runroot), "view": "SCENE", "origin": "common_native",
                       "ordinal": ordinal, **raster_stage}
            self._record("native_raster_attempt", status=status, **details)
            if token is not None:
                self.budget.settle_rasters(token, actual=1, lower_bound=1, evidence=details, outcome=status)
        if len(result) != len(BUFFER_NAMES):
            raise ValueError("complete_rgb_depth_and_dual_owner_raster_required")
        arrays = dict(zip(BUFFER_NAMES, result))
        folder = self.runroot / "native_frames" / str(ordinal).zfill(3)
        folder.mkdir(parents=True)
        png, npz = folder / "SCENE.png", folder / "SCENE.npz"
        started = time.perf_counter_ns()
        try:
            with png.open("xb") as stream:
                Image.fromarray(arrays["color"], mode="RGB").save(stream, format="PNG")
        finally:
            png_stage = _span(started)
            self._record("native_PNG_encoding", ordinal=ordinal, bytes=png.stat().st_size if png.exists() else 0,
                         **png_stage)
        started = time.perf_counter_ns()
        try:
            with npz.open("xb") as stream:
                np.savez_compressed(stream, **arrays, face_patch_offsets=np.asarray(scene["source_face_offsets"]),
                                    display_object_mask=np.asarray(object_mask))
        finally:
            npz_stage = _span(started)
            self._record("native_NPZ_encoding", ordinal=ordinal, bytes=npz.stat().st_size if npz.exists() else 0,
                         **npz_stage)
        png_sha, npz_sha = _sha(png.read_bytes()), _sha(npz.read_bytes())
        identity = _sha(_encode([scene["source"], ordinal, self.camera["camera_sha256"], png_sha, npz_sha]))
        row = {
            "ref": "native-image:" + identity, "frame_identity": identity, "view": "SCENE", "view_name": "SCENE",
            "pose": copy.deepcopy(self.pose), "size_px": list(self.pose["size_px"]),
            "camera_sha256": self.camera["camera_sha256"], "fixed_camera_matches": True,
            "PNG": str(png), "NPZ": str(npz), "PNG_sha256": png_sha, "NPZ_sha256": npz_sha,
            "PNG_bytes": png.stat().st_size, "NPZ_bytes": npz.stat().st_size,
            "source_ref": scene["source_ref"], "origin": "common_native",
            "object_names": [obj["name"] for obj in scene["objects"]],
            "object_ids": [obj["object_id"] for obj in scene["objects"]],
            "object_instance_ids": [obj["instance_id"] for obj in scene["objects"]],
            "source_face_offsets": list(scene["source_face_offsets"]),
            "display_object_mask": list(object_mask),
            "stages": {"actual_raster": raster_stage, "PNG_encoding": png_stage, "NPZ_encoding": npz_stage},
        }
        self._register(row, arrays)
        return row

    def render_views(self, names, fresh=False):
        self.check()
        if (type(names) not in (list, tuple) or not 1 <= len(names) <= 6 or set(names) != {"SCENE"}
                or type(fresh) is not bool):
            raise ValueError("fixed_SCENE_view_and_fresh_boolean_required")
        try:
            row = None if fresh else self.by_view.get("SCENE")
            cached = row is not None
            if cached:
                self._record("frame_cache_hit", ref=row["ref"], origin=row["origin"], requested_by="render_views")
            else:
                row = self._native_frame()
            keys = ("ref", "frame_identity", "view", "view_name", "pose", "size_px", "camera_sha256",
                    "fixed_camera_matches", "PNG_sha256", "NPZ_sha256", "source_ref", "origin", "object_names",
                    "object_ids", "object_instance_ids", "source_face_offsets", "display_object_mask",
                    "triangle_id_scope", "buffer_handle", "status")
            public = {key: copy.deepcopy(row[key]) for key in keys}
            self.check()
            return [dict(copy.deepcopy(public), cached=cached or index > 0,
                         new_raster_attempts=int(not cached and index == 0)) for index in range(len(names))]
        finally:
            self.save_evidence()

    def adopt_product_result(self, full, entry=None):
        """Bind the producer's existing archives to the ordinary frame/image API."""
        self.check()
        if self.group != "P":
            raise ValueError("product_frame_requires_product_slot")
        if full.get("result_kind") != "source_region" or not full.get("frames"):
            return []
        binding = full["binding"]
        objects = sorted(binding["objects"], key=lambda item: item["object_index"])
        if [item["object_index"] for item in objects] != list(range(len(objects))):
            raise ValueError("complete_product_frame_mesh_order_required")
        retained = []
        try:
            for frame in full["frames"]:
                ref = frame["image_ref"]
                existing = self.by_ref.get(ref)
                if existing is not None:
                    if (frame["frame_identity"], frame["image_sha256"], frame["arrays_sha256"]) != (
                            existing["frame_identity"], existing["PNG_sha256"], existing["NPZ_sha256"]):
                        raise ValueError("producer_frame_reuse_identity_mismatch")
                    self._record("frame_cache_hit", ref=ref, origin="product", requested_by="product_read")
                    retained.append(ref)
                    continue
                started = time.perf_counter_ns()
                png, npz = (Path(frame[key]).resolve() for key in ("image_path", "arrays_path"))
                if not png.is_relative_to(self.runroot) or not npz.is_relative_to(self.runroot):
                    raise ValueError("producer_frame_outside_current_slot")
                png_sha, npz_sha = _sha(png.read_bytes()), _sha(npz.read_bytes())
                if (png_sha, npz_sha) != (frame["image_sha256"], frame["arrays_sha256"]):
                    raise ValueError("original_producer_frame_hash_mismatch")
                with np.load(npz, allow_pickle=False) as archive:
                    arrays = {name: archive[name] for name in BUFFER_NAMES}
                    offsets = archive["face_patch_offsets"].tolist()
                    mask = archive["display_object_mask"].tolist()
                if mask != binding["image_scope"]["participation_mask"]:
                    raise ValueError("producer_archive_and_display_binding_mismatch")
                pose = frame["pose"]
                _validate_pose(pose, frozen=False)
                if frame["view_name"] != pose["name"]:
                    raise ValueError("product_frame_view_name_mismatch")
                row = {
                    "ref": ref, "frame_identity": frame["frame_identity"], "view": "SCENE", "view_name": "SCENE",
                    "pose": copy.deepcopy(pose), "size_px": list(pose["size_px"]),
                    "camera_sha256": _sha(_encode(_view_key(pose))),
                    "fixed_camera_matches": _view_key(pose) == _view_key(self.pose),
                    "PNG": str(png), "NPZ": str(npz), "PNG_sha256": png_sha, "NPZ_sha256": npz_sha,
                    "PNG_bytes": png.stat().st_size, "NPZ_bytes": npz.stat().st_size,
                    "source_ref": "product-binding:" + frame["host_binding_sha256"], "origin": "product",
                    "object_names": [item["object_name"] for item in objects],
                    "object_ids": [item["host_id"] for item in objects],
                    "object_instance_ids": [item["instance_id"] for item in objects],
                    "source_face_offsets": offsets, "display_object_mask": mask,
                    "producer": copy.deepcopy(frame), "full_result": copy.deepcopy(entry),
                    "stages": copy.deepcopy(frame.get("stages", {})),
                }
                self._register(row, arrays)
                self._record("original_product_frame_adopted", ref=ref, PNG_bytes=row["PNG_bytes"],
                             NPZ_bytes=row["NPZ_bytes"], **_span(started))
                retained.append(ref)
            self.check()
            return retained
        finally:
            self.save_evidence()

    def image_specification(self, ref):
        row = self.by_ref.get(ref)
        if row is None:
            raise ValueError("current_slot_image_reference_required")
        path = Path(row["PNG"])
        started = time.perf_counter_ns()
        raw = path.read_bytes()
        if _sha(raw) != row["PNG_sha256"]:
            raise ValueError("current_image_bytes_changed")
        self._record("frame_cache_hit", ref=ref, origin=row["origin"], requested_by="image_specification",
                     verified_PNG_bytes=len(raw), **_span(started))
        width, height = row["size_px"]
        return {"ref": ref, "file": path.name, "PNG_bytes": len(raw), "sha256": row["PNG_sha256"],
                "width": width, "height": height, "mimeType": "image/png"}, path.parent

    def save_evidence(self):
        packet = {
            "schema": "m4-live-source-region-device-evidence-v1", "label": self.label, "group": self.group,
            "asset_sha256": self.asset_sha256, "camera": self.camera,
            "frames": list(self.by_ref.values()), "sources": self.source_reads, "events": self.events,
            "terminal_source": self._terminal_receipt,
        }
        path = self.runroot / "DEVICE_EVIDENCE.json"
        temporary = path.with_suffix(".next")
        temporary.write_bytes(_encode(packet))
        temporary.replace(path)
        return packet

    def export_terminal(self):
        """Read fresh native and evaluated source arrays while the owned slot is alive."""
        if self._terminal_receipt is not None:
            return copy.deepcopy(self._terminal_receipt)
        self._capture(terminal=True)
        self._terminal_receipt = copy.deepcopy(self.source_reads[-1])
        self.save_evidence()
        return copy.deepcopy(self._terminal_receipt)
