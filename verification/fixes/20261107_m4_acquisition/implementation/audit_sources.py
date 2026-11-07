"""Reproduce static Git-source evidence. Never import or run product modules.

Run with an installed Python interpreter using -I -S -B and this absolute path.
Only source_index.json beside this script is written. No decision simulation.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
COMMIT = "12a6c392d66f35bbeac6854410a1784a8f60fd71"
EXPECTED = "fb5a4485c935512c1521b160c55e6034a30ae8177e2662b6a132fec5d85a4509"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def source(path):
    return git("show", COMMIT + ":" + path)


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def methods(path, class_name):
    tree = ast.parse(blobs[path].decode("utf-8-sig"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return {n.name: n.lineno for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


# All values are read as literals from the frozen source, never evaluated as code.
identity_path = "human_eye_plugin/runtime_identity.py"
identity = source(identity_path)
constants = {}
for node in ast.parse(identity.decode("utf-8-sig")).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in {"BASE_VERSION", "IMPLEMENTATION_REVISION", "_ROOT_MODULES"}:
            constants[node.targets[0].id] = ast.literal_eval(node.value)
paths = set(constants["_ROOT_MODULES"])
all_paths = git("ls-tree", "-r", "--name-only", COMMIT).decode("utf-8").splitlines()
for name in all_paths:
    parts = name.split("/")
    if len(parts) == 2 and parts[0] in {"human_eye_plugin", "human_eye_module1_operators"} and name.endswith(".py"):
        paths.add(name)
blobs = {name: source(name) for name in sorted(paths)}
manifest = [{"path": name, "sha256": digest(blob)} for name, blob in blobs.items()]
identity_input = {"base_version": constants["BASE_VERSION"],
                  "implementation_revision": constants["IMPLEMENTATION_REVISION"], "files": manifest}
source_digest = digest(json.dumps(identity_input, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))

anchors = {
    "human_eye_plugin/live_spatial_mcp.py": [(617, 635)],
    "human_eye_plugin/live_service.py": [(1021, 1026), (1044, 1071), (1220, 1238)],
    "human_eye_plugin/blender_host.py": [(329, 364), (411, 435), (437, 467), (476, 529), (574, 602), (775, 792), (1001, 1006)],
    "human_eye_plugin/blender_mcp_host.py": [(42, 48), (181, 219), (335, 341), (407, 440), (504, 516)],
    "human_eye_plugin/blender_process.py": [(196, 210)],
    "human_eye_plugin/blender_worker.py": [(148, 159)],
    "human_eye_plugin/auto_router.py": [(266, 306), (745, 757), (858, 882), (993, 1007)],
    "human_eye_plugin/query_policy.py": [(39, 66)],
    "human_eye_plugin/scene_cache.py": [(276, 318), (362, 377), (394, 410)],
    "human_eye_plugin/spatial_index.py": [(22, 47), (59, 86), (112, 145)],
    "human_eye_plugin/top1_query.py": [(13, 35), (38, 75), (79, 103)],
    "human_eye_plugin/task_query.py": [(46, 63), (176, 196), (254, 276)],
    "human_eye_plugin/surface_proximity.py": [(1, 18), (144, 162), (187, 207), (273, 315), (399, 445)],
    "module_2_low_token_mcp_scene_bridge.py": [(470, 505), (568, 587), (611, 623)],
    "human_eye_foveated_renderer.py": [(45, 62), (68, 80), (297, 322)],
    identity_path: [(19, 32), (52, 79)],
}
excerpts = []
for name, ranges in anchors.items():
    lines = blobs[name].decode("utf-8-sig").splitlines()
    for first, last in ranges:
        assert 1 <= first <= last <= len(lines), (name, first, last, len(lines))
        excerpts.append({"path": name, "blob_sha256": digest(blobs[name]), "first": first, "last": last,
                         "lines": [{"line": i, "text": lines[i-1]} for i in range(first, last+1)]})
host_methods = {
    name: methods("human_eye_plugin/" + path, name)
    for path, name in [("blender_host.py", "BlenderSceneHost"),
                       ("blender_mcp_host.py", "BlenderMCPHost"),
                       ("blender_process.py", "BlenderProcessHost")]
}
bound_box_hits = [{"path": name, "line": i, "text": line}
                  for name, blob in blobs.items()
                  for i, line in enumerate(blob.decode("utf-8-sig").splitlines(), 1) if "bound_box" in line]
result = {
    "kind": "static_source_audit_only", "commit": COMMIT,
    "runtime_source_count": len(manifest), "runtime_source_sha256": source_digest,
    "expected_source_sha256": EXPECTED,
    "source_identity_matches_assignment": source_digest == EXPECTED,
    "manifest": manifest, "anchors": excerpts, "host_methods": host_methods,
    "bound_box_literal_hits": bound_box_hits,
    "confirmed_interfaces": {
        "BlenderSceneHost.capture_task_scene": "capture_task_scene" in host_methods["BlenderSceneHost"],
        "BlenderMCPHost.capture_task_scene": "capture_task_scene" in host_methods["BlenderMCPHost"],
        "BlenderProcessHost.capture_task_scene": "capture_task_scene" in host_methods["BlenderProcessHost"],
        "worker_capture_task_command_literal": "'capture_task'" in blobs["human_eye_plugin/blender_worker.py"].decode("utf-8"),
    },
    "decision_cases_run": 0, "product_imports_or_runs": 0, "Blender_runs": 0,
    "subagents": 0, "model_consumers": 0, "model_API_calls": 0,
    "conclusion": "M4_ACQUIRE_001_DEPENDENCY",
    "limits": ["AST and byte inspection do not prove runtime behavior or performance.",
               "No bound_box literal is supporting evidence, not by itself a proof of all interface absence.",
               "No offline acquisition simulation is authorized without a reachable pre-mesh directory interface."],
}
(OUT / "source_index.json").write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
print(json.dumps({key: result[key] for key in ["kind", "commit", "runtime_source_count", "runtime_source_sha256",
    "source_identity_matches_assignment", "confirmed_interfaces", "decision_cases_run", "conclusion"]}, ensure_ascii=False, indent=2))
if len(manifest) != 131 or source_digest != EXPECTED:
    raise SystemExit("Frozen Git runtime bytes do not match the assignment source identity")
