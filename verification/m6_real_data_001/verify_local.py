"""Independent stdlib checks against the retained local native geometry."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def record(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    start = time.perf_counter()
    manifest = json.loads((OUT / "SOURCE_MANIFEST.json").read_bytes())
    checks = []

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)

    check("original file still matches dispatch", record(Path(manifest["source"]["path"])) == manifest["source"])
    check("isolated copy still matches original", record(Path(manifest["isolated_copy"]["path"])) == manifest["isolated_copy"])
    for capture in manifest["captures"]:
        check(f"{capture['capture_id']} exited successfully", capture["status"] == "collected" and capture["returncode"] == 0)
        for item in capture["export_files"]:
            check(f"frozen native file {Path(item['path']).name} {capture['capture_id']}", record(Path(item["path"])) == item)
    inventory = json.loads((OUT / "INVENTORY.json").read_bytes())
    region_record = inventory["arm_region"]["private_patch"]
    check("patch hash", record(Path(region_record["path"])) == region_record)
    patch = json.loads(Path(region_record["path"]).read_bytes())
    capture = next(row for row in reversed(manifest["captures"]) if row["selected_object"] is not None)
    raw = json.loads((OUT / "private" / capture["capture_id"] / "raw_selected.json").read_bytes())
    evaluated = json.loads((OUT / "private" / capture["capture_id"] / "evaluated_selected.json").read_bytes())
    check("raw/evaluated equality from saved arrays", raw["vertices_object"] == evaluated["vertices_object"] and raw["triangles"] == evaluated["triangles"])
    bounds = patch["selection"]["bounds_xyz_minmax"]
    ids = [i for i, point in enumerate(raw["vertices_world"])
           if all(bounds[2 * axis] <= point[axis] <= bounds[2 * axis + 1] for axis in range(3))]
    check("all and only spatial-box vertices retained", ids == patch["source_vertex_ids"])
    check("world and object coordinates preserve source indices",
          [raw["vertices_world"][i] for i in ids] == patch["vertices_world"] and
          [raw["vertices_object"][i] for i in ids] == patch["vertices_object"])
    selected = set(ids)
    triangle_ids = [i for i, triangle in enumerate(raw["triangles"]) if selected.issuperset(triangle)]
    check("all and only induced source triangles retained", triangle_ids == patch["source_triangle_ids"])
    check("source connectivity preserved", [[ids[i] for i in triangle] for triangle in patch["triangles_local"]] ==
          [raw["triangles"][i] for i in triangle_ids])
    check("source polygon IDs preserved", patch["source_polygon_ids"] == [raw["polygon_ids_by_triangle"][i] for i in triangle_ids])
    check("no correction or rig labels manufactured", all(patch[key] is None for key in
          ("bone_chain", "weights", "sections", "paired_reference", "supervision_label")))
    native = inventory["native"]
    check("absence of rig and shape-key data directly recorded", native["armature_datablocks"] == [] and native["shape_key_datablocks"] == [])
    product = []
    for suffix in ("expert", "weights", "source", "correction"):
        relative = f"human_eye_plugin/arm_twist_{suffix}.py"
        path = ROOT / relative
        fixed = subprocess.check_output(["git", "show", f"12d46730b94e758c3c426f5c0d3122a40eecad9e:{relative}"], cwd=ROOT)
        check(f"unchanged product {suffix}", path.read_bytes().replace(b"\r\n", b"\n") == fixed.replace(b"\r\n", b"\n"))
        product.append(record(path))
    reference = Path("D:/Projects/fps/outputs/character-design/Yanyite/Yanyite_Front_v1.png")
    manifest["appearance_reference"] = (record(reference) | {"role": "2D appearance only; not paired 3D correction truth"}
                                        if reference.exists() else {"path": str(reference), "missing": True})
    history = Path("D:/codex data/2026-10-02/fps-blender-models/Yanyite/work/readview_002_20261103/attempt_01")
    manifest["historical_evidence"] = [record(history / name) for name in
                                       ("RUN_RESULT.json", "NORMAL_RESPONSE.json", "config.json", "STALE_EVIDENCE.json", "HEAD_FRONT.png")]
    manifest["historical_evidence_scope"] = "Source identity and static appearance provenance. No reusable vertex/triangle/weight arrays in the normal response. Stale evidence is an intentional old negative case."
    manifest["product_sources_read_only"] = product
    manifest["current_replay_scripts"] = [record(OUT / name) for name in ("acquire.py", "collect_native.py", "analyze.py", "verify_local.py")]
    (OUT / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    result = {"cycle_id": "M6-REAL-DATA-001", "status": "passed", "checks": checks,
              "python": sys.version, "platform": platform.platform(),
              "scope": "Independent stdlib readback against retained native files; no new Blender process",
              "wall_s_before_final_publication": time.perf_counter() - start}
    (OUT / "LOCAL_VERIFICATION.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"status": "passed", "checks": len(checks), "private_patch_vertices": len(ids), "private_patch_triangles": len(triangle_ids)}))


if __name__ == "__main__":
    main()
