"""Read official source as text only; never import or execute downloaded code."""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
REF = "v5.2.1"
PINNED_COMMIT = "9e2066aef7ef7e20c142ad7bd3303138a4304c93"
FILES = {
    "rna_object.cc": ("source/blender/makesrna/intern/rna_object.cc", ["rna_Object_boundbox_get", "rna_Object_data_get", "rna_Object_to_mesh"]),
    "object.cc": ("source/blender/blenkernel/intern/object.cc", ["BKE_object_boundbox_get", "BKE_object_boundbox_eval_cached_get", "BKE_object_to_mesh", "BKE_object_get_evaluated_mesh"]),
    "mesh.cc": ("source/blender/blenkernel/intern/mesh.cc", ["Mesh::bounds_min_max", "tag_positions_changed"]),
    "mesh_convert.cc": ("source/blender/blenkernel/intern/mesh_convert.cc", ["BKE_mesh_new_from_object", "mesh_new_from_mesh"]),
}
FOLLOWUP = {
    "object_update.cc": ("source/blender/blenkernel/intern/object_update.cc", ["BKE_object_eval_boundbox", "bounds_eval"]),
    "mesh_runtime.cc": ("source/blender/blenkernel/intern/mesh_runtime.cc", ["tag_positions_changed", "bounds_cache.tag_dirty"]),
    "rna_object_api.cc": ("source/blender/makesrna/intern/rna_object_api.cc", ["rna_Object_to_mesh", "preserve_all_data_layers"]),
    "BLI_bounds.hh": ("source/blender/blenlib/BLI_bounds.hh", ["min_max(Span", "math::min", "math::max", "parallel_reduce"]),
}


def fetch(item):
    name, (path, patterns) = item
    url = "https://raw.githubusercontent.com/blender/blender/" + REF + "/" + path
    row = {"file": name, "repository_path": path, "url": url, "requested_ref": REF, "execution": "text_only"}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "HumanEye-static-source-audit/1.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(2_000_001)
            row.update(status=response.status, final_url=response.geturl(), bytes=len(raw))
        if len(raw) > 2_000_000:
            raise ValueError("source_text_budget_exceeded")
        source = raw.decode("utf-8")
        lines = source.splitlines()
        matches = []
        for pattern in patterns:
            for index, line in enumerate(lines):
                if pattern in line:
                    start, end = max(0, index - 2), min(len(lines), index + 44)
                    matches.append({"pattern": pattern, "match_line": index + 1,
                                    "start_line": start + 1, "end_line": end})
        row.update(sha256=hashlib.sha256(raw).hexdigest(), total_lines=len(lines), excerpts=matches)
    except Exception as error:
        row.update(error_type=type(error).__name__, error=str(error))
    return row


if __name__ == "__main__":
    pinned = sys.argv[1:] == ["--pinned"]
    followup = sys.argv[1:] == ["--followup"]
    if pinned:
        REF = PINNED_COMMIT
    files = FILES | FOLLOWUP if pinned else FOLLOWUP if followup else FILES
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result = list(pool.map(fetch, files.items()))
    if pinned:
        previous = {}
        for name in ("OFFICIAL_SOURCE_PROBE.json", "OFFICIAL_SOURCE_CHAIN_PROBE.json"):
            for item in json.loads((ROOT / name).read_bytes()):
                previous[item["file"]] = item
        for item in result:
            item["same_sha256_as_tag_read"] = item.get("sha256") == previous[item["file"]].get("sha256") and "sha256" in item
            item["symbol_locations"] = [{key: value for key, value in section.items() if key != "lines"}
                                        for section in item.pop("excerpts", [])]
        record = {"captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "tag": "v5.2.1", "official_tag_commit": PINNED_COMMIT,
                  "all_eight_tag_commit_hashes_equal": all(item["same_sha256_as_tag_read"] for item in result),
                  "local_binary_build_commit_verified": False, "files": result}
        path = ROOT / "OFFICIAL_SOURCE_INDEX.json"
        path.write_bytes((json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        print(json.dumps({key: value for key, value in record.items() if key != "files"}))
        raise SystemExit(0 if record["all_eight_tag_commit_hashes_equal"] else 1)
    path = ROOT / ("OFFICIAL_SOURCE_CHAIN_PROBE.json" if followup else "OFFICIAL_SOURCE_PROBE.json")
    path.write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps([{key: value for key, value in row.items() if key != "excerpts"} | {"excerpt_count": len(row.get("excerpts", []))} for row in result], ensure_ascii=False))
