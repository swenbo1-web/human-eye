"""Local multimodal wire and ordinary-Python checks, with zero Pro sessions."""

import ast
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys
import time
from types import SimpleNamespace
import uuid
import zlib

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from consumer_bridge import Bridge, verify_cli_image_event, verify_image_response, write
from consumer_runner import CONSUMER_CWD, EXE, argv_for, fixed_sequence, prompt_for
from image_inputs import image_inputs
import numpy as np


def get(response):
    value = json.loads(response["content"][0]["text"])
    if response.get("isError"):
        raise AssertionError(str(value))
    return value


class MockAPI:
    def __init__(self, state):
        self.state, self.operations = state, {}

    def load_state(self, directory):
        return dict(self.state)

    def submit_edit(self, directory, payload, expected_version, operation_id):
        digest = hashlib.sha256(Path(payload).read_bytes()).hexdigest()
        if operation_id in self.operations:
            previous = self.operations[operation_id]
            if previous["payload_sha256"] != digest:
                raise ValueError("operation_payload_changed")
            return dict(previous, idempotent_receipt=True)
        if expected_version != self.state["version"]:
            raise ValueError("stale_expected_version")
        self.state["version"] += 1
        result = dict(operation_id=operation_id, version=self.state["version"], payload_sha256=digest,
            status="mock_saved", independently_reopened=False)
        self.operations[operation_id] = result
        return result

    def save_readback(self, directory):
        return dict(version=self.state["version"], status="mock_readback", independently_reopened=False)

    def focus(self, directory):
        return dict(target_source_ids=[2, 3], protected_source_ids=[0, 1], reference="mock_region_v" + str(self.state["version"]))

    def resolve_ref(self, directory, reference):
        if reference != "mock_region_v" + str(self.state["version"]):
            raise ValueError("stale_reference")
        from python_executor import geometry_digest
        with np.load(self.state["current_npz"], allow_pickle=False) as archive:
            vertices, faces, source_ids = archive["vertices_world"], archive["faces"], archive["source_ids"]
        fields = dict(source_ids=np.array([2, 3], dtype=np.int64), current_positions_world=vertices[[2, 3]],
            current_vertex_normals=np.tile([0., 0., 1.], (2, 1)), lumped_area_world=np.array([.25, .25]))
        session_key = hashlib.sha256(str(Path(directory).resolve()).casefold().encode()).hexdigest()
        packet = HERE / "private/f" / session_key[:16] / ("v" + str(self.state["version"])) / "arrays" / ("a" + "b" * 64 + ".npz")
        packet.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(packet, **fields)
        raw = packet.read_bytes()
        descriptor = dict(path=str(packet), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
            arrays={key:dict(dtype=str(value.dtype), shape=list(value.shape)) for key, value in fields.items()},
            binding=dict(session_key=session_key, session_version=self.state["version"], current_geometry_sha256=geometry_digest(vertices, faces, source_ids)), reference=reference)
        return dict(source_ids=[2, 3], geometry_packet=descriptor)

def main():
    started, cpu = time.perf_counter(), time.process_time()
    output = HERE / "private/consumer_preflight" / uuid.uuid4().hex[:10]
    case = output / "case"
    session = HERE / "private/sessions" / ("protocol_" + output.name)
    case.mkdir(parents=True, exist_ok=False)
    session.mkdir(parents=True)
    image_folder = case / "images"
    image_folder.mkdir()
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    images = []
    for index, role in enumerate(name + "_" + view for name in ("normal", "current") for view in ("whole_front", "forearm_front", "forearm_side", "forearm_45")):
        raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        raw += chunk(b"IDAT", zlib.compress(bytes([0, 20 * index, 50, 100]))) + chunk(b"IEND", b"")
        path = image_folder / (role + ".png")
        path.write_bytes(raw)
        images.append(dict(role=role, path=path.relative_to(case).as_posix(), sha256=hashlib.sha256(raw).hexdigest()))
    task = dict(task_id="repair", images=images, image_count=len(images),
        objective="Repair the specified local forearm depression using normal PNG references.")
    write(case / "task.json", task)
    vertices = np.array([[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.]])
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    np.savez_compressed(case / "input.npz", vertices=vertices, vertices_world=vertices, faces=faces,
        source_ids=np.arange(4), F_source_ids=np.arange(4), I_ids=np.array([2, 3]), protected_ids=np.array([0, 1]),
        n0=np.tile([0., 0., 1.], (4, 1)), B0=np.array([0]), B1=np.array([1]), local_edges=np.array([[0,1],[1,2],[2,3]]))
    state = dict(version=0, current_npz=str(case / "input.npz"), initial_npz=str(case / "input.npz"), source_spec={})
    fixture_blend = session / "fixture.blend"
    fixture_blend.write_bytes(b"protocol-only identity fixture, never opened by Blender\n")
    state["current_blend"] = str(fixture_blend)
    state["source_original"] = "D:/private_original/clean.blend"
    write(session / "session.json", state)
    rows = image_inputs(case)
    before = {row["path"]:row["sha256"] for row in rows}
    config = dict(model="gpt-6.1-sol", reasoning_effort="medium", max_tool_calls=12, max_session_seconds=600,
        image_transport="mcp",
        answer_schema=dict(task_id="repair", status="pass/fail/unknown", image_observations="actual visual comparison", operation_id="record ID"))
    checks = {}
    help_started = time.perf_counter()
    help_result = subprocess.run([str(EXE), "exec", "--help"], capture_output=True, timeout=30)
    (output / "CLI_HELP.txt").write_bytes(help_result.stdout)
    checks["real_CLI_help_supports_image_attachment"] = help_result.returncode == 0 and b"--image <FILE>..." in help_result.stdout
    help_wall = time.perf_counter()-help_started
    # argv_for requires an actual prepared session, so use only a temporary
    # in-memory HERE rebind for the argument-level protocol check.
    import consumer_runner
    runner_here = consumer_runner.HERE
    consumer_runner.HERE = output
    temporary_session = output / "private/sessions/run_repair_native/session.json"
    write(temporary_session, state)
    write(output / "private/sessions/run_repair_facts/session.json", state)
    try:
        command, native_tools = argv_for(case, "native", output / "private/consumers/run/repair/native", config)
        facts_command, facts_tools = argv_for(case, "facts", output / "private/consumers/run/repair/facts", config)
    finally:
        consumer_runner.HERE = runner_here
    attachments = [command[index + 1] for index, item in enumerate(command) if item == "--image"]
    checks["MCP_transport_avoids_duplicate_CLI_images"] = attachments == []
    checks["both_routes_same_attachment_bytes"] = attachments == [facts_command[index + 1] for index, item in enumerate(facts_command) if item == "--image"]
    cli_config = dict(config, image_transport="cli")
    consumer_runner.HERE = output
    try:
        cli_command, _ = argv_for(case, "native", output / "private/consumers/run/repair/native", cli_config)
    finally:
        consumer_runner.HERE = runner_here
    checks["optional_CLI_argument_construction_preserves_exact_PNGs"] = [cli_command[index+1] for index,item in enumerate(cli_command) if item=="--image"] == [row["path"] for row in rows]
    checks["native_shared_tools"] = native_tools == ["images", "execute_python", "submit_edit", "state", "save_readback"]
    checks["facts_only_additional_observation_tools"] = facts_tools == native_tools + ["focus", "resolve_ref"]
    checks["CLI_cwd_is_neutral_repository"] = command[command.index("-C") + 1] == str(CONSUMER_CWD) and "m6_degrid" not in str(CONSUMER_CWD).lower()
    fixed = [dict(stage="run", task_id="repair", route=route) for route in ("facts", "native")]
    checks["PLAN_uses_two_fixed_consumers"] = fixed_sequence(dict(sequence=fixed)) == fixed
    checks["one_shared_prompt_without_route_name"] = prompt_for(task, config) == prompt_for(dict(task), config) and b"h,ell" not in prompt_for(task, config)
    checks["prompt_requires_images_first"] = b"first tool call must be images()" in prompt_for(task, config)
    checks["prompt_requires_actual_repair_and_honest_retention"] = b"Attempt a meaningful local repair" in prompt_for(task, config) and b"repair as incomplete" in prompt_for(task, config)
    checks["prompt_has_matched_cameras_and_compact_records"] = b"share pose, camera, scale, material and lighting" in prompt_for(task, config) and b"full arrays and detailed metric tables" in prompt_for(task, config)
    checks["public_prompt_contains_no_construction_hints"] = all(word not in prompt_for(task, config).lower()
        for word in (b"m6_degrid", b"seed", b"noise", b"grid", b"4096", b"8192", b"source_spec"))
    bridge = Bridge(SimpleNamespace(case=case, session=session, audit=output / "bridge", route="facts", max_tool_calls=12,
        python_timeout_s=45, python_output_chars=16000, fact_output_chars=50000))
    bridge.api = MockAPI(state)
    image_reply = bridge.call(dict(name="images", arguments={}))
    images = [block for block in image_reply["content"] if block["type"] == "image"]
    checks["native_MCP_image_blocks_have_original_bytes"] = len(images) == len(rows) and all(
        block["mimeType"] == "image/png" and hashlib.sha256(base64.b64decode(block["data"])).hexdigest() == row["sha256"] for block, row in zip(images, rows))
    checks["relative_image_metadata_verifies_original_sources"] = verify_image_response(output / "bridge/tool_01", task, rows, session)["exact_source_PNG_bytes"]
    checks["image_metadata_has_no_condition_path"] = "m6_degrid" not in image_reply["content"][0]["text"].lower()
    event = dict(server="task_geometry", tool="images", status="completed", error=None, result=image_reply)
    checks["CLI_image_event_joins_every_metadata_SHA256"] = verify_cli_image_event(event, output / "bridge/tool_01")["metadata_SHA256_verified"]
    clipped = dict(event, result=dict(content=[dict(type="text", text=image_reply["content"][0]["text"] + " ... 100 chars truncated")]))
    checks["CLI_clipped_base64_preserves_metadata_SHA256_binding"] = verify_cli_image_event(clipped, output / "bridge/tool_01")["serialized_result_clipped"]
    try:
        verify_cli_image_event(dict(event, result={}), output / "bridge/tool_01")
        checks["CLI_image_event_with_missing_SHA256_is_rejected"] = False
    except ValueError:
        checks["CLI_image_event_with_missing_SHA256_is_rejected"] = True
    code = """import json, math
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.sparse.linalg import spsolve
print(type(V), repr(V[:2]), version)
A=csr_matrix(np.array([[2.,-1.],[-1.,2.]]))
print(cKDTree(V).query(V[2],k=2),dijkstra(abs(A),directed=False),spsolve(A,np.ones(2)))
eigenvalues, _ = np.linalg.eigh(A.toarray())
assert np.isfinite(eigenvalues).all()
assert np.isfinite(np.linalg.svd(V,full_matrices=False)[1]).all()
assert np.array_equal(I_ids,np.array([2,3])) and np.array_equal(protected_ids,np.array([0,1]))
assert np.array_equal(V,V0) and np.array_equal(n0,np.tile([0.,0.,1.],(4,1)))
assert ':' not in packet_path and ':' not in payload_folder
assert 'm6_degrid' not in packet_path and 'm6_degrid' not in payload_folder
with np.load(packet_path,allow_pickle=False) as packet:
    assert np.array_equal(packet['initial_vertices'],V0)
print('current_packet_read_verified')
print(save_edit(I_ids,np.array([[.023,-.014,.007],[-.004,.005,.002]]),mode='displacements_world'))
"""
    result = get(bridge.call(dict(name="execute_python", arguments=dict(code=code))))
    checks["bounded_NumPy_SciPy_repr_namespace_and_packet_read"] = result["error"] is None
    if result["error"]:
        raise AssertionError(str(result))
    item = result["created_payloads"][0]
    with np.load(session / "payloads" / (item["payload_id"] + ".npz")) as package:
        checks["consumer_computed_payload_is_unmodified"] = np.array_equal(package["displacements_world"], np.array([[.023,-.014,.007],[-.004,.005,.002]]))
    second = get(bridge.call(dict(name="execute_python", arguments=dict(code="print(version, V.shape, protected_ids.tolist())"))))
    checks["warm_NPZ_packet_hit_same_version"] = second["error"] is None and bridge.calls[-1]["snapshot"]["cache_hit"]
    from python_executor import execute
    snapshot, safe_task = bridge.snapshot()
    forbidden = HERE.parent / "m6_shape_pairs_001/private/reference_vertices.npy"
    probes = {
        "np_load_absolute_old_clean": "np.load(" + repr(str(forbidden)) + ")",
        "open_absolute_old_clean": "open(" + repr(str(forbidden)) + ",'rb').read()",
        "np_fromfile_absolute_old_clean": "np.fromfile(" + repr(str(forbidden)) + ",dtype=np.uint8)",
        "np_memmap_absolute_old_clean": "np.memmap(" + repr(str(forbidden)) + ",dtype=np.uint8,mode='r')",
        "Path_absolute_old_clean": "from pathlib import Path\nPath(" + repr(str(forbidden)) + ").read_bytes()",
        "importlib_bypass": "import importlib\nimportlib.import_module('os')",
        "os_bypass": "import os\nprint(os.listdir('.'))",
        "reflection_bypass": "print(save_edit.__globals__)",
        "dynamic_reflection_bypass": "print(getattr(save_edit,'__globals__'))",
        "format_reflection_bypass": "print('{0.__globals__}'.format(save_edit))",
        "numpy_native_bypass": "print(np.ctypeslib)",
        "numpy_module_os_bypass": "print(np.lib.npyio.os)",
    }
    for label, code in probes.items():
        probe, record = execute(code, snapshot, safe_task, session / "payloads", output / "security" / label)
        checks["denied_" + label] = bool(probe.get("error")) and record["status"] == "execution_error"
        if label in ("np_load_absolute_old_clean", "open_absolute_old_clean", "np_fromfile_absolute_old_clean", "np_memmap_absolute_old_clean"):
            checks["audited_denied_" + label] = bool(record.get("worker", {}).get("access_policy", {}).get("denied_accesses"))
    payload_code = "with np.load(payload_folder + '/" + item["payload_id"] + ".npz',allow_pickle=False) as packet:\n    print(packet['source_ids'].tolist())"
    probe, record = execute(payload_code, snapshot, safe_task, session / "payloads", output / "security/payload_read")
    checks["own_saved_payload_is_readable"] = probe.get("error") is None
    applied = get(bridge.call(dict(name="submit_edit", arguments=dict(payload_id=item["payload_id"], expected_version=0, operation_id="local_probe"))))
    checks["submit_shared_API_fields"] = applied["version"] == 1
    repeated = get(bridge.call(dict(name="submit_edit", arguments=dict(payload_id=item["payload_id"], expected_version=0, operation_id="local_probe"))))
    checks["same_operation_mock_receipt_recovery"] = repeated["idempotent_receipt"]
    focus = get(bridge.call(dict(name="focus", arguments={})))
    resolved = get(bridge.call(dict(name="resolve_ref", arguments=dict(reference=focus["reference"]))))
    checks["facts_focus_and_versioned_resolve_adapter"] = resolved["source_ids"] == [2, 3] and "geometry_packet" in resolved
    public_state = get(bridge.call(dict(name="state", arguments={})))
    checks["state_hides_server_paths_and_initial_handles"] = all(key not in public_state for key in ("source_spec", "source_original", "initial_npz", "current_npz"))
    snapshot, _ = bridge.snapshot()
    checks["snapshot_invalidates_after_version_change"] = snapshot["version"] == 1 and not snapshot["snapshot_cost"]["cache_hit"]
    returned_path = resolved["geometry_packet"]["path"]
    ref_code = "assert reference_packets[0]['path'] == " + repr(returned_path) + "\nwith np.load(" + repr(returned_path) + ",allow_pickle=False) as packet:\n    print(packet['source_ids'].tolist())"
    ref_result = get(bridge.call(dict(name="execute_python", arguments=dict(code=ref_code))))
    checks["delivered_current_reference_packet_is_readable"] = ref_result["error"] is None and "[2, 3]" in ref_result["stdout"]
    from python_executor import validate_read_only_packet
    descriptor = resolved["geometry_packet"]
    reference_snapshot, safe_task = bridge.snapshot()
    overwrite_code = "open(" + repr(descriptor["path"]) + ",'wb').write(b'changed')"
    overwrite_result, overwrite_record = execute(overwrite_code, reference_snapshot, safe_task, session / "payloads", output / "security/reference_write")
    checks["reference_packet_is_read_only_and_write_is_audited"] = bool(overwrite_result.get("error")) and overwrite_record.get("worker", {}).get("access_policy", {}).get("denied_accesses", 0) == 1
    fields = bridge.snapshot_fields(state)
    invalid_descriptors = {
        "other_session": dict(descriptor, binding=dict(descriptor["binding"], session_key="0" * 64)),
        "stale_version": dict(descriptor, binding=dict(descriptor["binding"], session_version=0)),
        "wrong_current_geometry": dict(descriptor, binding=dict(descriptor["binding"], current_geometry_sha256="0" * 64)),
        "arbitrary_path": dict(descriptor, path=str(forbidden)),
        "wrong_SHA256": dict(descriptor, sha256="0" * 64),
    }
    for label, candidate in invalid_descriptors.items():
        try:
            validate_read_only_packet(candidate, session, 1, fields)
            checks["reference_packet_denied_" + label] = False
        except ValueError:
            checks["reference_packet_denied_" + label] = True
    bridge.api.state["version"] = 2
    stale_snapshot, safe_task = bridge.snapshot()
    checks["old_reference_descriptor_is_removed_from_next_version"] = stale_snapshot["read_only_packets"] == []
    stale_code = "np.load(" + repr(descriptor["path"]) + ",allow_pickle=False)"
    stale_result, stale_record = execute(stale_code, stale_snapshot, safe_task, session / "payloads", output / "security/stale_reference_access")
    checks["stale_reference_path_is_audited_and_denied"] = bool(stale_result.get("error")) and stale_record.get("worker", {}).get("access_policy", {}).get("denied_accesses", 0) == 1
    bridge.save(True)
    requests = [dict(jsonrpc="2.0", id=1, method="initialize", params=dict(protocolVersion="2025-03-26")),
        dict(jsonrpc="2.0", id=2, method="tools/list", params={}),
        dict(jsonrpc="2.0", id=3, method="tools/call", params=dict(name="images", arguments={}))]
    raw = ("\n".join(json.dumps(row) for row in requests) + "\n").encode()
    python = HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe"
    process = subprocess.run([str(python), "-I", "-B", "-X", "utf8", str(HERE / "consumer_bridge.py"),
        "--case", str(case), "--session", str(session), "--route", "native", "--audit", str(output / "stdio")],
        input=raw, capture_output=True, timeout=60)
    (output / "STDIO_STDOUT.bin").write_bytes(process.stdout)
    (output / "STDIO_STDERR.bin").write_bytes(process.stderr)
    replies = [json.loads(row) for row in process.stdout.splitlines()]
    checks["actual_fresh_stdio_process_three_protocol_replies"] = process.returncode == 0 and [row["id"] for row in replies] == [1, 2, 3]
    checks["stdio_initialize_and_tool_schema"] = replies[0]["result"]["protocolVersion"] == "2025-03-26" and len(replies[1]["result"]["tools"]) == 5
    blocks = [block for block in replies[2]["result"]["content"] if block["type"] == "image"]
    checks["actual_stdio_image_blocks_decode_original_PNGs"] = len(blocks) == len(rows) and all(
        hashlib.sha256(base64.b64decode(block["data"])).hexdigest() == row["sha256"] for block, row in zip(blocks, rows))
    checks["all_original_image_bytes_unchanged"] = all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in before.items())
    source_names = ("consumer_runner.py", "consumer_bridge.py", "python_executor.py", "image_inputs.py", "consumer_preflight.py", "analyze_consumers.py")
    for name in source_names:
        ast.parse((HERE / name).read_text(encoding="utf8"))
    result = dict(status="pass" if all(checks.values()) else "fail", checks=checks, count=len(checks),
        actual_Pro_sessions=0, actual_Blender_calls=0, protocol_fixture_image_inputs=rows,
        image_delivery="Single MCP images() delivery selected. Actual fresh local stdio image blocks decode to all original PNG bytes. CLI attachment construction is separately checked as an optional capability.",
        actual_mock_scope="Protocol fixtures contain eight synthetic 1-pixel PNGs and four synthetic vertices. Submit, focus and resolve facts use a mock API. Root performs actual image, Blender/edit/quality preflight before source freeze.",
        CLI_help_wall_s=help_wall, wall_s=time.perf_counter()-started, parent_CPU_s=time.process_time()-cpu,
        source_identities=[dict(path=name, bytes=(HERE / name).stat().st_size, sha256=hashlib.sha256((HERE / name).read_bytes()).hexdigest())
            for name in source_names],
        private_evidence=str(output.relative_to(HERE)))
    write(output / "RESULT.json", result)
    write(HERE / "CONSUMER_PREFLIGHT.json", result)
    print(result["status"], len(checks), result["wall_s"], flush=True)
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    failure_started, failure_cpu = time.perf_counter(), time.process_time()
    try:
        main()
    except BaseException as exception:
        import traceback
        write(HERE / "private/consumer_preflight" / ("FAILURE_" + uuid.uuid4().hex[:10] + ".json"),
            dict(error=dict(type=type(exception).__name__, message=str(exception)), traceback=traceback.format_exc(),
                wall_s=time.perf_counter()-failure_started, parent_CPU_s=time.process_time()-failure_cpu,
                actual_Pro_sessions=0, actual_Blender_calls=0))
        raise
