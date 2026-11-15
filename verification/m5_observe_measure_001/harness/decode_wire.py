"""Expand closed actual host packets and retain each real transmission boundary."""

import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import zlib

from budget import save


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def forward(points, matrix, scale):
    return [[(((matrix[axis][0] * point[0] + matrix[axis][1] * point[1])
                + matrix[axis][2] * point[2]) + matrix[axis][3]) * scale
             for axis in range(3)] for point in points]


def decode(folder, binding):
    folder = Path(folder)
    manifest = {row["path"]: row["sha256"] for row in binding["source_manifest"]}
    resources, steps, captures, source_payloads = {}, [], [], []
    for directory in sorted((folder / "native/WIRE").glob("[0-9]*")):
        request_path, response_path = directory / "REQUEST.bin", directory / "RESPONSE.bin"
        request = json.loads(request_path.read_bytes())
        response = json.loads(response_path.read_bytes())
        row = {"sequence": int(directory.name), "type": request["type"],
               "request": str(request_path), "request_sha256": sha(request_path),
               "response": str(response_path), "response_sha256": sha(response_path),
               "actual_TCP_TX_bytes": request_path.stat().st_size,
               "actual_TCP_RX_bytes": response_path.stat().st_size,
               "host_response_status": response.get("status")}
        steps.append(row)
        if request["type"] != "execute_code":
            row["fixture_response"] = response
            continue
        code = request["params"]["code"]
        row["script_sha256"] = hashlib.sha256(code.encode()).hexdigest()
        for node in ast.walk(ast.parse(code)):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "compile" and len(node.args) >= 2):
                continue
            expression = node.args[0]
            if not (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                    and expression.func.attr == "decompress"):
                continue
            blob = zlib.decompress(base64.b64decode(ast.literal_eval(expression.args[0].args[0]), validate=True))
            loaded = Path(ast.literal_eval(node.args[1]))
            relative = loaded.relative_to(Path(binding["install_root"])).as_posix()
            actual = hashlib.sha256(blob).hexdigest()
            if actual != manifest[relative] or sha(loaded) != actual:
                raise ValueError("actual_TCP_product_source_changed")
            source_payloads.append({"path": relative, "sha256": actual, "bytes": len(blob),
                                    "wire_sequence": row["sequence"]})
        match = re.search(r"_request = _json.loads\((.+)\)\n", code)
        if match is None:
            row["kind"] = "fixture_or_other_original_script"
            continue
        command = json.loads(ast.literal_eval(match.group(1)))
        row["command"] = command
        stdout = response.get("result", {}).get("result", "")
        marked = [line for line in stdout.splitlines() if line.startswith("HUMAN_EYE_BLENDER_MCP:")]
        if len(marked) != 1:
            row["marker_count"] = len(marked)
            continue
        packet = json.loads(marked[0].split(":", 1)[1])
        row["host_error"] = packet.get("error")
        value = packet.get("result", {})
        if not isinstance(value, dict):
            continue
        forwarded = value.get("resources", [])
        row.update(resources_forwarded=len(forwarded),
                   resource_vertices_forwarded=sum(len(item.get("vertices_local", [])) for item in forwarded),
                   resource_faces_forwarded=sum(len(item.get("faces", [])) for item in forwarded),
                   marked_stdout_UTF8_bytes=len(marked[0].encode("utf-8")))
        for resource in forwarded:
            resources[(resource["id"], resource["revision"])] = resource
        capture = value.get("capture", value)
        if not isinstance(capture, dict) or not capture.get("meshes"):
            continue
        capture = copy.deepcopy(capture)
        for mesh in capture["meshes"]:
            reference = mesh.pop("_scene_resource", None)
            if reference is None:
                continue
            resource = resources[(reference["id"], reference["revision"])]
            mesh.update(vertices=forward(resource["vertices_local"], reference["matrix"], reference["scale"]),
                        faces=resource["faces"], edges=resource["edges"])
        path = folder / ("CAPTURE_" + str(row["sequence"]).zfill(3) + ".json")
        save(path, capture)
        entry = {"wire_sequence": row["sequence"], "path": str(path), "sha256": sha(path),
                 "command": command, "capture_scope": capture.get("capture_scope"),
                 "capture_state": capture.get("capture_state"), "host_identity": capture.get("host_identity"),
                 "object_ids": [mesh["object_id"] for mesh in capture["meshes"]],
                 "object_names": [mesh["name"] for mesh in capture["meshes"]],
                 "vertices": sum(len(mesh["vertices"]) for mesh in capture["meshes"]),
                 "triangles": sum(len(mesh["faces"]) for mesh in capture["meshes"])}
        captures.append(entry)
    value = {"schema": "m5-closed-actual-host-wire-v1", "steps": steps,
             "captures": captures, "loaded_source_payloads": source_payloads,
             "source_sha256": binding["source_sha256"],
             "new_host_calls": 0, "new_rasters": 0,
             "scope": "Actual original packet expansion. Returned selected geometry, forwarded resources and whole-scene wrapper guard work remain distinct."}
    save(folder / "SAVED_WIRE.json", value)
    return value
