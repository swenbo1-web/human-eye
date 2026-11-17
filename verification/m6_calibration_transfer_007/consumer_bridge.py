"""Stdio tools for actual consumer edits and independent saved-mesh readback."""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "m6_shape_pretrain_001/private/deps"))
import numpy as np
from python_executor import execute, validate_read_only_packet, legacy as process_metrics
from image_inputs import image_inputs, image_content


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def tool(name, description, properties, required=()):
    return dict(name=name, description=description, inputSchema=dict(type="object", properties=properties,
        required=list(required), additionalProperties=False))


def json_value(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError("unsupported_tool_JSON_value_" + type(value).__name__)


def file_identity(path):
    path = path.resolve()
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def binding_digest(binding):
    return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")).hexdigest()


PRIVATE_KEYS = {
    "source_spec", "source_original", "source_original_blend", "original_asset", "base_npz", "case_dir",
    "initial_npz", "clean_vertices", "reference_vertices", "clean_3d", "clean_npz", "clean_blend",
    "damage_mask", "damaged_mask", "support_mask", "inverse_displacements", "generation_parameters",
    "known_clean", "truth", "ground_truth", "private_evaluation",
    "seed", "noise", "noise_array", "noise_seed", "construction", "construction_parameters",
    "source_specification", "generation_seed",
}


def public_value(value, allowed_roots):
    if isinstance(value, dict):
        return {key: public_value(item, allowed_roots) for key, item in value.items() if key not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [public_value(item, allowed_roots) for item in value]
    if isinstance(value, str) and (re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("/", "\\\\"))):
        path = Path(value).resolve()
        if not any(path.is_relative_to(root) for root in allowed_roots):
            return "[server-private path]"
        return path.relative_to(HERE).as_posix()
    if isinstance(value, str):
        for prefix in (str(HERE), HERE.as_posix()):
            value = value.replace(prefix + "\\", "").replace(prefix + "/", "")
    return value


def png_row(path, index, role, camera):
    identity = file_identity(Path(path))
    raw = Path(path).read_bytes()
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError("preview_requires_valid_PNG_header")
    width, height = struct.unpack(">II", raw[16:24])
    if [width, height] != camera["specification"]["resolution"]:
        raise ValueError("preview_resolution_must_match_frozen_camera")
    return dict(identity, index=index, role=role, width=width, height=height, mimeType="image/png", camera=camera)


def checked_identity(expected):
    path = Path(expected["path"])
    path = (path if path.is_absolute() else HERE / path).resolve()
    actual = file_identity(path)
    if any(actual[key] != expected[key] for key in ("bytes", "sha256")):
        raise ValueError("preview_bound_artifact_identity_changed")
    return path


def validate_preview(manifest_path, task, session=None):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_bytes())
    binding = manifest["binding"]
    session = Path(session).resolve() if session else manifest_path.parents[2]
    session_key = hashlib.sha256(str(session).casefold().encode()).hexdigest()
    version = binding["version"]
    if type(version) is not int or version < 1 or binding["session_key"] != session_key:
        raise ValueError("preview_session_version_binding_invalid")
    if manifest_path != session / "previews" / ("v" + str(version)) / "PREVIEW.json":
        raise ValueError("preview_manifest_outside_bound_session_version")
    saved_path = checked_identity(binding["saved_blend"])
    if not saved_path.is_relative_to(session):
        raise ValueError("preview_saved_blend_outside_session")
    renderer_path = checked_identity(manifest["renderer"])
    camera_path = checked_identity(manifest["cameras"])
    if renderer_path != HERE / "blender_render.py" or camera_path != HERE / "CAMERAS.json":
        raise ValueError("preview_renderer_or_camera_binding_invalid")
    views = json.loads(camera_path.read_bytes())["views"]
    receipt_path = checked_identity(manifest["render_receipt"])
    run_path = checked_identity(manifest["render_run"])
    expected_job_folder = HERE / "private/jobs" / manifest["render_job_label"]
    if receipt_path != expected_job_folder / "receipt.json" or run_path != expected_job_folder / "run.json":
        raise ValueError("preview_receipt_outside_bound_render_job")
    receipt, run = json.loads(receipt_path.read_bytes()), json.loads(run_path.read_bytes())
    if run["process"]["returncode"] != 0 or receipt.get("status") != "rendered_actual_saved_full_character":
        raise ValueError("preview_requires_successful_actual_render")
    if receipt["current_blend"]["sha256"] != binding["saved_blend"]["sha256"] or Path(receipt["current_blend"]["path"]).resolve() != saved_path:
        raise ValueError("preview_rendered_saved_blend_identity_mismatch")
    if receipt["execution"]["script"]["sha256"] != manifest["renderer"]["sha256"] or receipt.get("geometry_scale") != 1 or receipt.get("displacement_scale") != 1 or receipt.get("scene_changes_saved") is not False:
        raise ValueError("preview_render_execution_binding_invalid")
    if len(receipt["views"]) != len(views) or len(manifest["images"]) != len(views):
        raise ValueError("preview_must_include_every_frozen_view")
    rows = []
    for index, (view, rendered) in enumerate(zip(views, receipt["views"])):
        reference = next(item["camera"] for item in task["images"] if item["role"] == "current_" + view["name"])
        camera = {key: rendered[key] for key in ("specification", "camera_matrix_world", "world_to_image_affine_2_by_3", "world_to_image_offset", "pixel_convention")}
        if rendered["specification"] != view or camera != reference:
            raise ValueError("preview_camera_differs_from_frozen_input_camera")
        path = checked_identity(rendered["image"])
        if path.parent != manifest_path.parent / "images":
            raise ValueError("preview_PNG_outside_bound_version_directory")
        rows.append(png_row(path, index + 1, "current_" + view["name"], camera))
    if rows != manifest["images"]:
        raise ValueError("preview_PNG_metadata_changed")
    return manifest, rows


def verify_image_response(directory, task, initial_rows, session):
    directory = Path(directory)
    payload = json.loads((directory / "COMPLETE_RESULT.json").read_bytes())
    response = json.loads((directory / "RESPONSE.json").read_bytes())
    kind = payload.get("delivery_kind", "frozen_initial")
    rows = payload["images"]
    allowed_roots = [Path(session).resolve()] + [Path(row["path"]).resolve().parent for row in initial_rows]
    if kind == "frozen_initial":
        if rows != public_value(initial_rows, allowed_roots):
            raise ValueError("initial_image_delivery_differs_from_frozen_binding")
        version = 0
    elif kind == "saved_version_preview":
        manifest_path = checked_identity(payload["preview_manifest"])
        manifest, expected = validate_preview(manifest_path, task, session)
        if rows != public_value(expected, allowed_roots) or payload["saved_blend"] != public_value(manifest["binding"]["saved_blend"], allowed_roots):
            raise ValueError("preview_delivery_differs_from_actual_render_binding")
        version = manifest["binding"]["version"]
        if payload["version"] != version or payload["session_key"] != manifest["binding"]["session_key"]:
            raise ValueError("preview_delivery_session_version_mismatch")
    else:
        raise ValueError("unknown_image_delivery_kind")
    blocks = [block for block in response.get("content", []) if block.get("type") == "image"]
    if response.get("isError") or len(blocks) != len(rows):
        raise ValueError("MCP_image_block_count_mismatch")
    text = next(block["text"] for block in response["content"] if block["type"] == "text")
    if json.loads(text)["images"] != rows:
        raise ValueError("MCP_image_text_binding_mismatch")
    for block, row in zip(blocks, rows):
        raw = base64.b64decode(block["data"], validate=True)
        path = Path(row["path"])
        path = path if path.is_absolute() else HERE / path
        if block["mimeType"] != "image/png" or raw != path.read_bytes() or len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("MCP_image_bytes_differ_from_bound_PNG")
    cost = json.loads((directory / "COST.json").read_bytes())
    return dict(index=cost["index"], delivery_kind=kind, version=version, image_blocks=len(blocks),
        exact_source_PNG_bytes=True, PNG_bytes=sum(row["bytes"] for row in rows),
        base64_bytes=sum(len(block["data"]) for block in blocks),
        stdio_response_UTF8_bytes=cost.get("stdio_response_UTF8_bytes"), wall_s=cost["wall_s"],
        response=file_identity(directory / "RESPONSE.json"), preview=cost.get("preview"),
        saved_blend_sha256=payload.get("saved_blend", {}).get("sha256"))


def verify_cli_image_event(item, directory):
    payload = json.loads((Path(directory) / "COMPLETE_RESULT.json").read_bytes())
    serialized = json.dumps(item.get("result", {}), ensure_ascii=True, sort_keys=True)
    hashes = [row["sha256"] for row in payload["images"]]
    if item.get("server") != "task_geometry" or item.get("tool") != "images" or item.get("error"):
        raise ValueError("completed_CLI_image_event_required")
    if item.get("status") not in (None, "completed") or not all(digest in serialized for digest in hashes):
        raise ValueError("CLI_image_metadata_SHA256_differs_from_complete_Bridge_result")
    return dict(metadata_SHA256_verified=True, image_SHA256=hashes,
        serialized_result_clipped="chars truncated" in serialized,
        complete_Bridge_response=file_identity(Path(directory) / "RESPONSE.json"),
        CLI_item_sha256=hashlib.sha256(json.dumps(item, ensure_ascii=True, sort_keys=True).encode()).hexdigest(),
        scope="CLI completed-event metadata SHA256 joined to complete Bridge blocks. CLI-clipped image base64 is retained as received.")


class Bridge:
    def __init__(self, options):
        self.options = options
        self.case, self.session, self.audit = options.case.resolve(), options.session.resolve(), options.audit.resolve()
        self.audit.mkdir(parents=True, exist_ok=True)
        self.started, self.calls, self.api = time.perf_counter(), [], None
        self.reference_packets = {}
        self.task = public_value(json.loads((self.case / "task.json").read_bytes()), [self.case / "images"])
        self.input_hashes = {name: hashlib.sha256((self.case / name).read_bytes()).hexdigest() for name in ("task.json", "input.npz")}
        self.images = image_inputs(self.case)
        self.tools = [
            tool("images", "At version zero, view the eight frozen normal-reference and damaged-current PNGs. After an edit, view four actual current saved-model PNGs using the same frozen cameras. Saved-version previews are cached by session/version/saved SHA.", {}),
            tool("execute_python", "Run numerical Python in a fresh bounded interpreter with NumPy/SciPy and numeric standard-library imports. "
                 "V/current/vertices are current world coordinates [N,3], V0 initial world coordinates, faces full source triangles, "
                 "F_ids/I_ids/protected_ids/source_ids, version,task,G,geometry are available. V0 and optional n0/normals come from the saved damaged initial/current model. "
                 "packet_path is the current numerical NPZ; payload_folder is your session payload directory. reference_packets contains already delivered, current-version geometry packets. "
                 "read_image_pixels(role) returns the bound normal/current PNG as a uint8 RGB array. image_roles lists roles and image_cameras maps each role to the shared camera projection. "
                 "save_fit_diagnostics(fit_target_ids,fit_offsets,fit_source_ids,fit_design_rank,fit_estimated_amplitude_m,**extra_arrays) records actual fitting support in payloads. "
                 "fit_offsets indexes flattened fit_source_ids for each target, rank and amplitude are per target, global fitting may use target -1, and optional coverage arrays use fit_ prefixes. "
                 "Pass fit_normals[M,3] when estimated amplitudes use a direction different from n0, such as a world-axis fit. "
                 "File reads are restricted to validated packets and payloads. "
                 "Use your own geometry algorithm. save_edit(ids, values, mode='positions_world'|'displacements_world') stores your computed finite "
                 "sparse edit and returns payload_id plus observed_version. Displacements are relative to the current snapshot. "
                 "Only submit_edit changes the isolated Blender model. Each Python invocation is fresh; print compact evidence.",
                 dict(code=dict(type="string")), ("code",)),
            tool("submit_edit", "Apply your saved sparse payload to this independent Blender copy and save a new blend. "
                 "Provide the observed snapshot version and a unique operation_id. Same operation_id supports receipt recovery. "
                 "Only I vertices are editable. Values are applied as computed. If a receipt is uncertain, query state before retrying.",
                 dict(payload_id=dict(type="string"), expected_version=dict(type="integer"), operation_id=dict(type="string")),
                 ("payload_id", "expected_version", "operation_id")),
            tool("state", "Read the current isolated-copy version, operation records and saved artifact identities.", {}),
            tool("save_readback", "Save/read the current isolated model through a new independent Blender process and report actual technical geometry quality. All legacy _m fields use source_native length units.", {}),
        ]
        if options.route == "facts":
            self.tools += [tool("focus", "Read current geometry facts and matched-PNG correspondence with active-core, low-difference outer fitting support, transition, unobserved and full-mesh positive-attention exclusion references. Full arrays are delivered as registered current-version packets.", {}),
                tool("resolve_ref", "Resolve a returned current-region reference to precise current geometry.",
                     dict(reference=dict(type="string")), ("reference",))]

    def load_api(self):
        if self.api is None:
            spec = importlib.util.spec_from_file_location("_refine_session_api", HERE / "session_api.py")
            self.api = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = self.api
            spec.loader.exec_module(self.api)
        return self.api

    def state(self):
        return self.load_api().load_state(self.session)

    def path(self, value):
        path = Path(value)
        path = (path if path.is_absolute() else self.session / path).resolve()
        if not path.is_relative_to(HERE / "private"):
            raise ValueError("geometry_packet_must_belong_to_current_batch")
        return path

    def snapshot_fields(self, state):
        with np.load(self.path(state["current_npz"]), allow_pickle=False) as current:
            vertices = current["vertices_world"] if "vertices_world" in current else current["vertices"]
            faces = current["faces"]
            source_ids = current["source_ids"] if "source_ids" in current else np.arange(len(vertices), dtype=np.int64)
            optional = {key: current[key] for key in ("normals", "n0", "B0", "B1", "local_edges",
                "matrix_world", "poly_offsets", "poly_vertices", "triangle_polygon_ids") if key in current}
        with np.load(self.path(state["initial_npz"]), allow_pickle=False) as initial:
            first = initial["vertices_world"] if "vertices_world" in initial else initial["vertices"]
            fields = dict(vertices=vertices, initial_vertices=first, faces=faces, source_ids=source_ids,
                F_ids=initial["F_source_ids"] if "F_source_ids" in initial else initial["F_ids"],
                I_ids=initial["I_ids"], protected_ids=initial["protected_ids"] if "protected_ids" in initial else np.setdiff1d(source_ids, initial["I_ids"]))
            for key in ("B0", "B1", "local_edges"):
                if key not in optional and key in initial:
                    optional[key] = initial[key]
        with np.load(self.case / "input.npz", allow_pickle=False) as baseline:
            expected = baseline["vertices_world"] if "vertices_world" in baseline else baseline["vertices"]
            if not np.array_equal(first, expected) or not np.array_equal(faces, baseline["faces"]):
                raise ValueError("consumer_initial_must_equal_its_saved_damaged_input")
        fields.update(optional)
        if not np.array_equal(source_ids, np.arange(len(vertices))):
            raise ValueError("preserved_full_source_ID_indexing_required")
        if not len(fields["I_ids"]):
            raise ValueError("reference_consumer_requires_nonempty_editable_domain")
        floating = ("vertices", "initial_vertices", "normals", "n0", "matrix_world")
        return {key: np.asarray(value, dtype=np.float64 if key in floating else np.int64) for key, value in fields.items()}

    def snapshot(self):
        started, cpu = time.perf_counter(), time.process_time()
        state = self.state()
        current_path, initial_path = self.path(state["current_npz"]).resolve(), self.path(state["initial_npz"]).resolve()
        current_identity = file_identity(current_path)
        initial_identity = current_identity if current_path == initial_path else file_identity(initial_path)
        sources = dict(current_npz=current_identity, initial_npz=initial_identity)
        session_key = hashlib.sha256(str(self.session).casefold().encode("utf8")).hexdigest()
        folder = self.session / "snapshots" / ("v" + str(state["version"]))
        manifest_path = folder / "snapshot.json"
        manifest = json.loads(manifest_path.read_bytes()) if manifest_path.exists() else None
        cache_hit = bool(manifest and manifest["binding"]["sources"] == sources
            and manifest["binding"]["version"] == state["version"] and manifest["binding"]["session_key"] == session_key)
        creation_wall = creation_cpu = 0.
        if cache_hit:
            if binding_digest(manifest["binding"]) != manifest["cache_key"]:
                raise ValueError("snapshot_cache_binding_changed")
            packet_path = folder / manifest["filename"]
            if packet_path.parent.resolve() != folder.resolve() or file_identity(packet_path)["sha256"] != manifest["sha256"]:
                raise ValueError("snapshot_cache_packet_changed")
        else:
            creation_started, creation_cpu_started = time.perf_counter(), time.process_time()
            fields = self.snapshot_fields(state)
            if file_identity(current_path) != current_identity or file_identity(initial_path) != initial_identity:
                raise ValueError("snapshot_source_changed_during_packet_creation")
            schema = {key: dict(dtype=str(value.dtype), shape=list(value.shape)) for key, value in fields.items()}
            binding = dict(session_key=session_key, version=state["version"], sources=sources, schema=schema)
            cache_key = binding_digest(binding)
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=folder, suffix=".npz", delete=False) as stream:
                temporary = Path(stream.name)
                np.savez(stream, **fields)
            try:
                packet_identity = file_identity(temporary)
                packet_path = folder / ("s" + packet_identity["sha256"][:16] + ".npz")
                if packet_path.exists() and file_identity(packet_path)["sha256"] != packet_identity["sha256"]:
                    raise ValueError("snapshot_packet_filename_collision")
                os.replace(temporary, packet_path)
            finally:
                temporary.unlink(missing_ok=True)
            manifest = dict(binding=binding, cache_key=cache_key, filename=packet_path.name,
                sha256=packet_identity["sha256"], bytes=packet_identity["bytes"])
            with tempfile.NamedTemporaryFile(dir=folder, suffix=".json", delete=False) as stream:
                temporary_manifest = Path(stream.name)
            write(temporary_manifest, manifest)
            os.replace(temporary_manifest, manifest_path)
            creation_wall, creation_cpu = time.perf_counter()-creation_started, time.process_time()-creation_cpu_started
        task = dict(self.task)
        packet = dict(path=str(packet_path), sha256=manifest["sha256"], bytes=manifest["bytes"],
            cache_key=manifest["cache_key"], binding=manifest["binding"])
        cost = dict(cache_hit=cache_hit, wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu,
            creation_wall_s=creation_wall, creation_CPU_s=creation_cpu, packet_bytes=manifest["bytes"],
            cache_key=manifest["cache_key"], source_identity_validation="current and initial NPZ SHA256 checked per snapshot",
            timing_scope="Packet creation is nested within snapshot wall and CPU.")
        extras = [item for item in self.reference_packets.values() if item["binding"]["session_version"] == state["version"]]
        cost["registered_reference_packet_count"] = len(extras)
        image_rows = self.shared_image_inputs()
        cost["shared_PNG_count"] = len(image_rows)
        cost["shared_PNG_bytes"] = sum(row["bytes"] for row in image_rows)
        return dict(version=state["version"], array_packet=packet, read_only_packets=extras,
            image_inputs=image_rows, snapshot_cost=cost), task

    def shared_image_inputs(self):
        rows, _, _ = self.current_images()
        combined = [row for row in self.images if row["role"].startswith("normal_")]
        combined += [row for row in rows if row["role"].startswith("current_")]
        camera_by_role = {row["role"]: row.get("camera", {}) for row in self.task["images"]}
        return [dict(row, camera=row.get("camera", camera_by_role[row["role"]]),
            case_images_root=str(self.case / "images")) for row in combined]

    def register_reference_packets(self, payload):
        descriptors = []

        def collect(value):
            if isinstance(value, dict):
                if "geometry_packet" in value:
                    descriptors.append(value["geometry_packet"])
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(payload)
        if descriptors:
            state = self.state()
            fields = self.snapshot_fields(state)
            for descriptor in descriptors:
                validate_read_only_packet(descriptor, self.session, state["version"], fields)
                self.reference_packets[descriptor["path"]] = descriptor
        return descriptors

    def relative_reference_packet_paths(self, value):
        if isinstance(value, dict):
            if "geometry_packet" in value:
                descriptor = value["geometry_packet"]
                path = Path(descriptor["path"])
                descriptor["path"] = Path(os.path.relpath(path if path.is_absolute() else HERE / path, self.session)).as_posix()
            for item in value.values():
                self.relative_reference_packet_paths(item)
        elif isinstance(value, list):
            for item in value:
                self.relative_reference_packet_paths(item)

    def current_images(self):
        started = time.perf_counter()
        state = self.state()
        version = state["version"]
        if version == 0:
            return self.images, dict(delivery_kind="frozen_initial", version=0), dict(cache_hit=True, render_invoked=False)
        saved = file_identity(self.path(state["current_blend"]))
        if not Path(saved["path"]).is_relative_to(self.session):
            raise ValueError("preview_saved_model_must_belong_to_this_session")
        session_key = hashlib.sha256(str(self.session).casefold().encode()).hexdigest()
        binding = dict(session_key=session_key, version=version, saved_blend=saved)
        directory = self.session / "previews" / ("v" + str(version))
        manifest_path = directory / "PREVIEW.json"
        cache_hit, render_invoked = manifest_path.exists(), False
        job_label = "preview_" + binding_digest(binding)[:24]
        job_folder = HERE / "private/jobs" / job_label
        if not cache_hit:
            run_path = job_folder / "run.json"
            if not run_path.exists():
                if job_folder.exists():
                    raise RuntimeError("preview_render_attempt_incomplete_inspect_owned_job_" + job_label)
                from background import run_job
                source_spec = json.loads(self.path(state["source_spec"]).read_bytes())
                cameras = json.loads((HERE / "CAMERAS.json").read_bytes())["views"]
                run_job("blender_render.py", dict(current_blend=saved["path"], object_name=source_spec["object_name"],
                    source_original=source_spec["source_original"], expected_input_sha256=saved["sha256"],
                    output_dir=str(directory / "images"), views=cameras), job_label)
                render_invoked = True
            run = json.loads(run_path.read_bytes())
            receipt_path = job_folder / "receipt.json"
            if run["process"]["returncode"] != 0 or not receipt_path.exists():
                raise RuntimeError("preview_render_attempt_failed_inspect_owned_job_" + job_label)
            receipt = json.loads(receipt_path.read_bytes())
            rows = [png_row(item["image"]["path"], index + 1, "current_" + item["specification"]["name"],
                {key: item[key] for key in ("specification", "camera_matrix_world", "world_to_image_affine_2_by_3", "world_to_image_offset", "pixel_convention")})
                for index, item in enumerate(receipt["views"])]
            manifest = dict(binding=binding, renderer=file_identity(HERE / "blender_render.py"),
                cameras=file_identity(HERE / "CAMERAS.json"), render_job_label=job_label,
                render_run=file_identity(run_path), render_receipt=file_identity(receipt_path), images=rows)
            temporary_manifest = directory / "PREVIEW.next.json"
            write(temporary_manifest, manifest)
            os.replace(temporary_manifest, manifest_path)
        manifest, rows = validate_preview(manifest_path, self.task, self.session)
        if manifest["binding"] != binding or file_identity(self.path(state["current_blend"])) != saved:
            raise ValueError("preview_saved_model_changed_during_image_delivery")
        metadata = dict(delivery_kind="saved_version_preview", version=version, session_key=session_key,
            saved_blend=saved, preview_manifest=file_identity(manifest_path), render_job_label=job_label,
            render_receipt_sha256=manifest["render_receipt"]["sha256"],
            renderer={key: manifest["renderer"][key] for key in ("bytes", "sha256")}, cameras=manifest["cameras"]["sha256"])
        cost = dict(cache_hit=cache_hit, render_invoked=render_invoked, render_job_label=job_label,
            render_run=manifest["render_run"], wall_s=time.perf_counter()-started)
        return rows, metadata, cost

    def call(self, params):
        started = time.perf_counter()
        index = len(self.calls) + 1
        folder = self.audit / ("tool_" + str(index).zfill(2))
        folder.mkdir(exist_ok=False)
        write(folder / "REQUEST.json", params)
        name, arguments = params.get("name"), params.get("arguments", {})
        record = dict(index=index, name=name, status="running")
        error, images = False, None
        try:
            if index > self.options.max_tool_calls:
                raise RuntimeError("fixed_tool_call_budget_exhausted")
            if name == "images":
                if arguments:
                    raise ValueError("images_requires_empty_arguments")
                rows, metadata, preview_cost = self.current_images()
                payload = dict(images=rows, transport="native_MCP_ImageContent", **metadata)
                images = image_content(rows)
                record.update(public_image_count=len(rows), public_image_bytes=sum(row["bytes"] for row in rows),
                    image_delivery_kind=metadata["delivery_kind"], image_version=metadata["version"], preview=preview_cost,
                    image_base64_bytes=sum(len(block["data"]) for block in images if block["type"]=="image"))
            elif name == "execute_python":
                if set(arguments) != {"code"} or type(arguments["code"]) is not str:
                    raise ValueError("execute_python_requires_code_string")
                snapshot, task = self.snapshot()
                record["snapshot"] = snapshot["snapshot_cost"]
                payload, execution = execute(arguments["code"], snapshot, task, self.session / "payloads", folder / "python",
                    timeout_s=self.options.python_timeout_s, output_chars=self.options.python_output_chars)
                record["execution"] = execution
                error = payload["error"] is not None
            elif name == "submit_edit":
                if set(arguments) != {"payload_id", "expected_version", "operation_id"}:
                    raise ValueError("submit_edit_fields_required")
                ident = arguments["payload_id"]
                if not isinstance(ident, str) or not re.fullmatch(r"p[0-9a-f]{32}", ident):
                    raise ValueError("invalid_own_payload_ID")
                metadata = json.loads((self.session / "payloads" / (ident + ".json")).read_bytes())
                if type(arguments["expected_version"]) is not int or metadata["observed_version"] != arguments["expected_version"]:
                    raise ValueError("payload_observed_version_mismatch")
                payload = self.load_api().submit_edit(self.session, self.session / "payloads" / (ident + ".npz"),
                    arguments["expected_version"], arguments["operation_id"])
            elif name in ("state", "save_readback", "focus"):
                if arguments:
                    raise ValueError("tool_requires_empty_arguments")
                if name == "state":
                    state = self.state()
                    payload = {key: state[key] for key in ("version", "status", "current_blend_identity") if key in state}
                    payload["operations"] = [{key: row[key] for key in ("operation_id", "version", "status", "saved_blend", "readback", "quality_record", "independently_reopened") if key in row}
                        for row in state.get("operations", [])]
                    payload["pending_operation"] = bool(state.get("pending"))
                elif name == "save_readback":
                    payload = self.load_api().save_readback(self.session)
                elif self.options.route == "facts":
                    payload = self.load_api().focus(self.session, image_rows=self.shared_image_inputs())
                else:
                    raise ValueError("focus_available_in_facts_route")
            elif name == "resolve_ref" and self.options.route == "facts":
                if set(arguments) != {"reference"} or type(arguments["reference"]) is not str:
                    raise ValueError("reference_string_required")
                payload = self.load_api().resolve_ref(self.session, arguments["reference"], image_rows=self.shared_image_inputs())
            else:
                raise ValueError("tool_unavailable_in_route")
            if name in ("focus", "resolve_ref"):
                self.register_reference_packets(payload)
            write(folder / "PRIVATE_RESULT.json", json.loads(json.dumps(payload, default=json_value)))
            payload = public_value(payload, [self.session, self.case / "images", HERE / "private/f"])
            if name in ("focus", "resolve_ref"):
                self.relative_reference_packet_paths(payload)
            complete = json.dumps(payload, ensure_ascii=True, allow_nan=False, default=json_value)
            payload = json.loads(complete)
            if images is not None:
                images[0] = dict(type="text", text=complete)
            write(folder / "COMPLETE_RESULT.json", payload)
            limit = self.options.fact_output_chars if name != "execute_python" else self.options.python_output_chars * 2 + 2000
            record.update(complete_text_UTF8_bytes=len(complete.encode("utf8")), truncated=len(complete) > limit)
            if record["truncated"]:
                complete = json.dumps(dict(truncated=True, preview=complete[:limit], original_UTF8_bytes=record["complete_text_UTF8_bytes"]), ensure_ascii=True)
            result = dict(content=images if images is not None else [dict(type="text", text=complete)], isError=error)
            record["status"] = "tool_error" if error else "completed"
        except BaseException as exception:
            payload = dict(error=type(exception).__name__, message=str(exception))
            write(folder / "PRIVATE_ERROR.json", payload)
            payload = public_value(payload, [self.session, self.case / "images", HERE / "private/f"])
            result = dict(content=[dict(type="text", text=json.dumps(payload, ensure_ascii=True))], isError=True)
            record["status"] = "failed"
        record.update(wall_s=time.perf_counter() - started,
            public_text_UTF8_bytes=sum(len(block["text"].encode("utf8")) for block in result["content"] if block["type"] == "text"))
        self.calls.append(record)
        write(folder / "RESPONSE.json", result)
        write(folder / "COST.json", record)
        self.save(False)
        return result

    def save(self, closed):
        after = {name: hashlib.sha256((self.case / name).read_bytes()).hexdigest() for name in self.input_hashes}
        write(self.audit / "BRIDGE_RESULT.json", dict(task_id=self.task["task_id"], route=self.options.route, closed=closed,
            calls=self.calls, initial_input_identities_before=self.input_hashes, initial_input_identities_after=after,
            process_id=os.getpid(), process_metrics=process_metrics.lifetime_metrics(),
            image_inputs=self.images, images_unchanged=image_inputs(self.case)==self.images,
            source_unchanged=self.input_hashes == after, wall_s=time.perf_counter() - self.started,
            execution_scope="Numerical Python in a fresh process with AST/import restrictions and CPython file-access audit enforcement. Only current version packet, delivered current-only references, bound PNGs and own payload files are accessible; process-level restrictions have no OS sandbox certification."))

    def serve(self):
        try:
            for raw in sys.stdin.buffer:
                request = json.loads(raw)
                method, ident = request.get("method"), request.get("id")
                if ident is None:
                    continue
                if method == "initialize":
                    result = dict(protocolVersion=request.get("params", {}).get("protocolVersion", "2024-11-05"),
                        capabilities=dict(tools=dict(listChanged=False)), serverInfo=dict(name="task_geometry", version="1"))
                elif method == "tools/list":
                    result = dict(tools=self.tools)
                elif method == "tools/call":
                    result = self.call(request.get("params", {}))
                elif method == "ping":
                    result = {}
                else:
                    reply = dict(jsonrpc="2.0", id=ident, error=dict(code=-32601, message="method_unavailable"))
                    sys.stdout.write(json.dumps(reply) + "\n")
                    sys.stdout.flush()
                    continue
                reply = json.dumps(dict(jsonrpc="2.0", id=ident, result=result), ensure_ascii=True, allow_nan=False) + "\n"
                if method == "tools/call":
                    self.calls[-1]["stdio_response_UTF8_bytes"] = len(reply.encode("utf8"))
                    write(self.audit / ("tool_"+str(self.calls[-1]["index"]).zfill(2)) / "COST.json", self.calls[-1])
                    self.save(False)
                sys.stdout.write(reply)
                sys.stdout.flush()
        finally:
            self.save(True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--route", choices=("native", "facts"), required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--max-tool-calls", type=int, default=12)
    parser.add_argument("--python-timeout-s", type=float, default=45)
    parser.add_argument("--python-output-chars", type=int, default=5000)
    parser.add_argument("--fact-output-chars", type=int, default=18000)
    Bridge(parser.parse_args()).serve()


if __name__ == "__main__":
    main()
