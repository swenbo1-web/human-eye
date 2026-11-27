"""Read and hash the original A/C source only; never import or execute it."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-047-R3-COVERAGE-DOMAIN/entry")
CONTRACT = "a303b53c8c69ef2ac24283bc515888dc5fd0cdbd"
SITES = {
    "A": Path("D:/HumanEye/runs/M6-041-KERNEL-HOOK/install/032/.human-eye/releases/9.7.2+k041hook032/site-packages"),
    "C": Path("D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/candidate/.human-eye/releases/9.7.2+k043region/site-packages"),
}
IDENTITIES = {
    "A": "a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d",
    "C": "b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e",
}
SYMBOLS = {
    "human_eye_plugin/live_service.py": [
        "_request", "LiveSpatialService._read_source_identity", "LiveSpatialService._bind_read_result",
        "LiveSpatialService._request_budget", "LiveSpatialService._check_request_budget",
        "LiveSpatialService._observation_scope", "LiveSpatialService.observe", "LiveSpatialService._observe_task",
        "LiveSpatialService._observe_surface_nearest", "LiveSpatialService._observe_surface_scan",
        "LiveSpatialService._measure_selective_source_region", "LiveSpatialService._observe_source_region"],
    "human_eye_plugin/live_spatial_mcp.py": ["_validate_arguments", "LiveSpatialMCPServer._dispatch_tool",
        "run_stdio_mcp_server"],
    "human_eye_plugin/task_query.py": ["_surface_pair_measurement", "_closed_solid_pair_measurement",
        "_spatial_pair_measurement", "_closed_surface_facts", "task_result", "surface_nearest_result"],
    "human_eye_plugin/surface_scan.py": ["_packet", "surface_scan_result"],
    "human_eye_plugin/scene_cache.py": ["_mesh_dict", "SpatialSceneCache._bind_read_meshes",
        "SpatialSceneCache._bind_surface_scan_meshes", "SpatialSceneCache._measurement_mesh", "SpatialSceneCache.pair_measurement"],
    "human_eye_plugin/read_context.py": ["capture_key", "ReadContext.reset", "ReadContext.activate",
        "ReadContext.normalized", "ReadContext.result", "ReadContext.surface_scan_progress"],
    "human_eye_plugin/auto_router.py": ["_validated_scene"],
    "human_eye_plugin/source_region.py": ["resolve_region_selection", "prepare_region", "_measure_region_surfaces",
        "_validate_selective_capture", "measure_selective_region", "measure_region", "_witness_sources"],
    "human_eye_plugin/active_observation_images.py": ["_meshes_from_objects"],
    "human_eye_foveated_renderer.py": ["MeshEntity3D.from_dict"],
    "human_eye_plugin/blender_mcp_host.py": ["BlenderMCPHost.capture_task_scene", "BlenderMCPHost.capture_nearest_candidates",
        "BlenderMCPHost.capture_surface_scan", "BlenderMCPHost.capture_source_region_pair"],
    "human_eye_plugin/blender_host.py": ["BlenderSceneHost.capture_task_scene", "BlenderSceneHost.capture_nearest_candidates",
        "BlenderSceneHost.capture_surface_scan", "BlenderSceneHost._compact_source_region_pair"],
    "human_eye_plugin/surface_proximity.py": ["_Work", "_admit", "_admit_one", "_integer_frame",
        "_nearest_linear", "_nearest_tree", "_nearest", "_distance_roots", "_ProjectionCredit",
        "_boundary_witness", "_witness_triangle_provenance", "_CacheBuildBudget", "_mesh_cache_is_immutable",
        "_ensure_cached_frame", "_pair_from_mesh_cache", "measure_surface_proximity", "_referenced_support_evidence",
        "measure_spatial_relation"],
    "human_eye_plugin/surface_geometry.py": ["_bvh", "_ClosedWork", "classify_closed_solids"],
}


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return pin(path)


def definitions(tree, prefix=""):
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = prefix+node.name
            result[name] = node
            if isinstance(node, ast.ClassDef):
                result.update(definitions(node, name+"."))
    return result


def main():
    result = {"schema": "m6-047-original-entry-source-audit-v1", "contract": CONTRACT,
        "status": "pass", "analyst": pin(__file__), "installations": {}, "files": {}, "functions": {},
        "read_only": True, "product_imports": 0, "kernel_calls": 0, "Blender": 0,
        "scope": "Static installed-source identities and exact source-line references. No fresh query, timing, cache probe or sufficient whole-work theorem is claimed."}
    manifests = {}
    for arm, site in SITES.items():
        binding_path = site.parent/"admin/RUNTIME_BINDING.json"
        binding = json.loads(binding_path.read_bytes())
        identity = binding["identity"]
        assert identity["source_sha256"] == IDENTITIES[arm]
        assert Path(binding["site_packages"]).resolve() == site.resolve()
        assert len(binding["source_files"]) == 143
        manifests[arm] = {r["path"]: r["sha256"] for r in binding["source_files"]}
        for row in binding["source_files"]:
            assert pin(site/row["path"])["sha256"] == row["sha256"]
        encoded = {"base_version": identity["base_version"], "implementation_revision": identity["implementation_revision"],
                   "files": binding["source_files"]}
        assert hashlib.sha256(json.dumps(encoded, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest() == IDENTITIES[arm]
        result["installations"][arm] = {"binding": pin(binding_path), "identity": identity, "verified_files": 143}
        for filename, symbols in SYMBOLS.items():
            path = site/filename
            raw = path.read_bytes()
            lines = raw.splitlines(keepends=True)
            tree = ast.parse(raw.decode("utf8"))
            defs = definitions(tree)
            result["files"].setdefault(filename, {})[arm] = pin(path)
            for name in symbols:
                key = filename+":"+name
                output = result["functions"].setdefault(key, {})
                if name not in defs:
                    output[arm] = {"present": False}
                    continue
                node = defs[name]
                segment = b"".join(lines[node.lineno-1:node.end_lineno])
                output[arm] = {"present": True, "path": str(path), "line": node.lineno,
                    "end_line": node.end_lineno, "bytes": len(segment), "sha256": hashlib.sha256(segment).hexdigest()}
    changed = sorted(name for name in manifests["A"] if manifests["A"][name] != manifests["C"][name])
    assert changed == ["human_eye_plugin/surface_geometry.py", "human_eye_plugin/surface_proximity.py",
                       "human_eye_plugin/surface_scan.py", "human_eye_plugin/task_query.py"]
    result["changed_A_to_C_source_files"] = changed
    for refs in result["files"].values():
        refs["equal_bytes"] = refs["A"]["sha256"] == refs["C"]["sha256"]
    for refs in result["functions"].values():
        refs["equal_bytes"] = refs["A"].get("sha256") == refs["C"].get("sha256")
    result["observed_rules"] = {
        "fresh_surface_Work": "Original _Work is constructed inside measure_surface_proximity, after request/capture/normalization/cache-key costs; it starts at zero rather than inheriting elapsed wall time.",
        "external_prior_debit": "The 043 low control's original _Work initializer is intentionally predebited; its 8356 remaining is not an ordinary caller option or a universal fresh-budget assumption.",
        "surface_limits": {"combined_faces": 4096, "narrow": 16384, "work": 1179648, "integer_bits": 4096, "linear_product_limit": 256},
        "closed_limits": {"work": 262144, "pair_tests": 16384, "ray_tests": 16384},
        "G60_reducer_limits": {"scan_max_new_kernel_pairs": 512, "max_objects": 256, "scan_delivery_bytes": 524288},
        "same_request_deadline": "Outer stdio tools/call opens _request_budget; nested service scopes reuse it, and before_stdio_write checks the original remaining time after encoding.",
        "full_work_proof": "Not supplied by this entry trace; face products and observed prior successes do not certify integer-width, preparation, support/closure, optional witness publication or wall deadline.",
        "fallback_on_paper": "Conservative whole-request choice before first version-specific geometry/preparation/cache activation, using one current validated capture and bound request identity. If any pending pair or compound tail lacks a sufficient original-contract certificate, retain A. No post-unknown retry, C-prepared-tree borrowing, cross-version result cache, deadline reset or mixed ledger is authorized or implemented.",
    }
    # Bind the measured local path's actual request, rather than substituting
    # another source_region API which happens to call the same solver.
    local_plan = Path("D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/live/yanyite/PLAN.json")
    local = json.loads(local_plan.read_bytes())
    assert local["high_request"]["arguments"]["query"]["mode"] == "source_region_measurement"
    result["actual_Yanyite"] = {"plan": pin(local_plan), "query": local["high_request"],
        "special_entry": "LiveSpatialMCPServer -> _measure_selective_source_region -> measure_selective_region -> _measure_region_surfaces",
        "warm_scope": "Host residency/lease only. This entry always reconstructs compact NumPy meshes and invokes a fresh per-pair solver with _prepared_holder; it does not use context.result or pair_measurement.",
        "selected_domain": "Use compact selected source-triangle rows, not the full source object's source_triangle_count, for the kernel face product. Host compaction/validation/mapping still cost real work outside the surface _Work ledger."}
    out = RAW/"SOURCE_AUDIT.json"
    print(json.dumps(save(out, result)))
    print(json.dumps(save(HERE/"SOURCE_REFS.json", result)))


if __name__ == "__main__":
    main()
