"""Local multimodal wire and ordinary-Python checks, with zero Pro sessions."""

import ast
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from consumer_bridge import Bridge, write
from consumer_runner import EXE, argv_for, prompt_for
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
        return dict(source_ids=[2, 3], current_positions_world=[[1., 1., 0.], [0., 1., 0.]])

    def project_sections(self, directory):
        return dict(version=self.state["version"], stations=[.15, .35, .55, .75, .90], scope="mock_schema_only")


def main():
    started, cpu = time.perf_counter(), time.process_time()
    output = HERE / "private/consumer_preflight" / uuid.uuid4().hex[:10]
    case, session = output / "case", output / "session"
    case.mkdir(parents=True, exist_ok=False)
    session.mkdir()
    reference = Path("D:/Projects/fps/outputs/character-design/Yanyite/Yanyite_Front_v1.png")
    previous = HERE.parent / "m6_reference_refine_001"
    visual = previous / "private/views/before"
    task = dict(task_id="forearm", images=[dict(role="reference", path=str(reference))] +
        [dict(role=name, path=str(visual / (name + ".png"))) for name in ("whole_front", "forearm_front", "forearm_side", "forearm_45")] +
        [dict(role=role, path=str(previous / folder / filename)) for role, folder, filename in (
            ("primary reference annotation", "private/annotation", "reference_annotated.png"),
            ("primary model annotation", "private/annotation", "model_annotated.png"),
            ("independent reference annotation", "private/independent_anchors", "reference_anchors.png"),
            ("independent model annotation", "private/independent_anchors", "model_front_anchors.png"))],
        contour=dict(stations=[.15, .35, .55, .75, .90], frame="fixed_elbow_wrist", target_outer=[.1, .09, .08, .07, .06]))
    write(case / "task.json", task)
    vertices = np.array([[0., 0., 0.], [1., 0., 0.], [1., 1., 0.], [0., 1., 0.]])
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    np.savez_compressed(case / "input.npz", vertices=vertices, vertices_world=vertices, faces=faces,
        source_ids=np.arange(4), F_source_ids=np.arange(4), I_ids=np.array([2, 3]), protected_ids=np.array([0, 1]))
    state = dict(version=0, current_npz=str(case / "input.npz"), initial_npz=str(case / "input.npz"), source_spec={})
    write(session / "session.json", state)
    rows = image_inputs(case)
    before = {row["path"]:row["sha256"] for row in rows}
    config = dict(model="gpt-6.1-sol", reasoning_effort="medium", max_tool_calls=12, max_session_seconds=600,
        image_transport="mcp",
        answer_schema=dict(task_id="forearm", status="pass/fail/unknown", image_observations="actual visual comparison", operation_id="record ID"))
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
    temporary_session = output / "private/sessions/v1_forearm_native/session.json"
    write(temporary_session, state)
    write(output / "private/sessions/v1_forearm_facts/session.json", state)
    try:
        command, native_tools = argv_for(case, "native", output / "private/consumers/v1/forearm/native", config)
        facts_command, facts_tools = argv_for(case, "facts", output / "private/consumers/v1/forearm/facts", config)
    finally:
        consumer_runner.HERE = runner_here
    attachments = [command[index + 1] for index, item in enumerate(command) if item == "--image"]
    checks["MCP_transport_avoids_duplicate_CLI_images"] = attachments == []
    checks["both_routes_same_attachment_bytes"] = attachments == [facts_command[index + 1] for index, item in enumerate(facts_command) if item == "--image"]
    cli_config = dict(config, image_transport="cli")
    consumer_runner.HERE = output
    try:
        cli_command, _ = argv_for(case, "native", output / "private/consumers/v1/forearm/native", cli_config)
    finally:
        consumer_runner.HERE = runner_here
    checks["optional_CLI_argument_construction_preserves_exact_PNGs"] = [cli_command[index+1] for index,item in enumerate(cli_command) if item=="--image"] == [row["path"] for row in rows]
    checks["native_shared_tools"] = native_tools == ["images", "execute_python", "submit_edit", "state", "save_readback"]
    checks["facts_only_additional_observation_tools"] = facts_tools == native_tools + ["focus", "resolve_ref", "project_sections"]
    checks["one_shared_prompt_without_route_name"] = prompt_for(task, config) == prompt_for(dict(task), config) and b"h,ell" not in prompt_for(task, config)
    checks["prompt_requires_images_first"] = b"first tool call must be images()" in prompt_for(task, config)
    checks["prompt_allows_evidenced_no_edit_with_readback"] = b"zero-edit decision" in prompt_for(task, config) and b"still call save_readback" in prompt_for(task, config)
    checks["prompt_preserves_both_existing_definitions"] = b"only these two existing correspondence definitions" in prompt_for(task, config)
    bridge = Bridge(SimpleNamespace(case=case, session=session, audit=output / "bridge", route="facts", max_tool_calls=12,
        python_timeout_s=45, python_output_chars=16000, fact_output_chars=50000))
    bridge.api = MockAPI(state)
    image_reply = bridge.call(dict(name="images", arguments={}))
    images = [block for block in image_reply["content"] if block["type"] == "image"]
    checks["native_MCP_image_blocks_have_original_bytes"] = len(images) == len(rows) and all(
        block["mimeType"] == "image/png" and hashlib.sha256(base64.b64decode(block["data"])).hexdigest() == row["sha256"] for block, row in zip(images, rows))
    code = """import json, math
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.sparse.linalg import spsolve
print(type(V), repr(V[:2]), task['contour']['stations'], version)
A=csr_matrix(np.array([[2.,-1.],[-1.,2.]]))
print(cKDTree(V).query(V[2],k=2),dijkstra(abs(A),directed=False),spsolve(A,np.ones(2)))
assert np.array_equal(I_ids,np.array([2,3])) and np.array_equal(protected_ids,np.array([0,1]))
assert np.array_equal(V,V0) and 'h' not in globals() and 'n0' not in globals()
print(save_edit(I_ids,np.array([[.023,-.014,.007],[-.004,.005,.002]]),mode='displacements_world'))
"""
    result = get(bridge.call(dict(name="execute_python", arguments=dict(code=code))))
    checks["ordinary_NumPy_SciPy_repr_and_namespace"] = result["error"] is None
    item = result["created_payloads"][0]
    with np.load(session / "payloads" / (item["payload_id"] + ".npz")) as package:
        checks["consumer_computed_payload_is_unmodified"] = np.array_equal(package["displacements_world"], np.array([[.023,-.014,.007],[-.004,.005,.002]]))
    second = get(bridge.call(dict(name="execute_python", arguments=dict(code="print(version, V.shape, protected_ids.tolist())"))))
    checks["warm_NPZ_packet_hit_same_version"] = second["error"] is None and bridge.calls[-1]["snapshot"]["cache_hit"]
    applied = get(bridge.call(dict(name="submit_edit", arguments=dict(payload_id=item["payload_id"], expected_version=0, operation_id="local_probe"))))
    checks["submit_shared_API_fields"] = applied["version"] == 1
    repeated = get(bridge.call(dict(name="submit_edit", arguments=dict(payload_id=item["payload_id"], expected_version=0, operation_id="local_probe"))))
    checks["same_operation_mock_receipt_recovery"] = repeated["idempotent_receipt"]
    focus = get(bridge.call(dict(name="focus", arguments={})))
    resolved = get(bridge.call(dict(name="resolve_ref", arguments=dict(reference=focus["reference"]))))
    sections = get(bridge.call(dict(name="project_sections", arguments={})))
    checks["facts_focus_resolve_and_fixed_projection_adapter"] = resolved["source_ids"] == [2, 3] and len(sections["stations"]) == 5
    snapshot, _ = bridge.snapshot()
    checks["snapshot_invalidates_after_version_change"] = snapshot["version"] == 1 and not snapshot["snapshot_cost"]["cache_hit"]
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
    for name in ("consumer_runner.py", "consumer_bridge.py", "python_executor.py", "image_inputs.py"):
        ast.parse((HERE / name).read_text(encoding="utf8"))
    result = dict(status="pass" if all(checks.values()) else "fail", checks=checks, count=len(checks),
        actual_Pro_sessions=0, actual_Blender_calls=0, real_image_inputs=rows,
        image_delivery="Single MCP images() delivery selected. Actual fresh local stdio image blocks decode to all original PNG bytes. CLI attachment construction is separately checked as an optional capability.",
        actual_mock_scope="Submit, focus, resolve and section facts use a mock API. Root performs the actual Blender/edit/quality API preflight before source freeze.",
        CLI_help_wall_s=help_wall, wall_s=time.perf_counter()-started, parent_CPU_s=time.process_time()-cpu,
        source_identities=[dict(path=name, bytes=(HERE / name).stat().st_size, sha256=hashlib.sha256((HERE / name).read_bytes()).hexdigest())
            for name in ("consumer_runner.py", "consumer_bridge.py", "python_executor.py", "image_inputs.py")],
        private_evidence=str(output.relative_to(HERE)))
    write(output / "RESULT.json", result)
    write(HERE / "CONSUMER_PREFLIGHT.json", result)
    print(result["status"], len(checks), result["wall_s"], flush=True)
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
