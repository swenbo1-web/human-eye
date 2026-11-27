"""Freeze original source bytes and fixed directed cases before numerical replay."""
from collections import Counter, defaultdict
from hashlib import file_digest, sha256
from pathlib import Path
import json
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-048-R3-WITNESS-PARITY")
PREVIOUS = RAW.parent / "M6-047-R3-COVERAGE-DOMAIN"
CONTRACT = "fc36530cdedd3db65ee55010b7f2a90a89fa87d6"
PARENT = "568cbf023125cea2a7c2e57270cec31956435458"
BASE = "6c93f2375d1073b33e721a168f1fcf610ac6dbdc"
CYCLE = RAW.name
LIMITS = {"total_faces": 4096, "narrow": 16384, "work": 1179648, "pair_deadline_s": 30}
IDENTITIES = {
    "A": "a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d",
    "C": "b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e",
}


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as file:
        return {"path": str(path), "bytes": path.stat().st_size,
                "sha256": file_digest(file, "sha256").hexdigest()}


def check(expected):
    path = Path(expected["path"])
    assert ref(path) == expected, path
    return path


def save(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(doc, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return ref(path)


def git_file(name, revision=CONTRACT):
    return subprocess.check_output(["git", "show", f"{revision}:{name}"], cwd=HERE)


def world_hash(values, width):
    return sha256(b"".join(struct.pack("<" + width * len(row), *row) for row in values)).hexdigest()


def g60_references():
    inputs = PREVIOUS / "g60"
    roots = {name: ref(inputs / name) for name in (
        "ARCHIVE_FREEZE.json", "NATIVE_GEOMETRY.json", "REQUESTS.json",
        "PAIR_CALLS.json", "CACHE_PATHS.json", "VERIFY_045_RECOMPUTED.json")}
    previous = read(PREVIOUS / "RAW_EVIDENCE.json")
    previous_refs = {item["path"]: item for item in previous["files"]}
    for name, file in roots.items():
        earlier = previous_refs["g60/" + name]
        assert (file["bytes"], file["sha256"]) == (earlier["bytes"], earlier["sha256"])
    archive = read(check(roots["ARCHIVE_FREEZE.json"]))
    for item in archive["archive_files"]:
        check(item)
    samples = read(check(roots["REQUESTS.json"]))
    for row in samples:
        for field in ("request", "response", "cell"):
            check(row[field])
        if row["step"] != "overview":
            assert row["result_cache_hit"] is False and row["pair_cache_hits"] == 0
    geometry = read(check(roots["NATIVE_GEOMETRY.json"]))
    assert geometry["frame"] == 1 and geometry["subframe"] == 0 and geometry["scale_length"] == 1
    assert len(geometry["matched_actual_ordinary_snapshots"]) == 6 and len(geometry["objects"]) == 12
    for row in geometry["objects"].values():
        assert row["triangle_count"] == 60 and row["source_triangle_rows"] == list(range(60))
        assert row["native_polygon_ids"] is None
    options = read(check(roots["CACHE_PATHS.json"]))
    for arm in "AC":
        assert options[arm]["nearest"]["keywords"]["retain_exact_rank"] == "True"
        assert options[arm]["scan"]["keywords"]["retain_exact_rank"] == "True"
        for step in ("nearest", "scan"):
            check(options[arm][step]["source"])
            check(options[arm]["cache_key"]["source"])
    groups, directions = defaultdict(list), defaultdict(list)
    ids_to_name = {}
    for row in read(check(roots["PAIR_CALLS.json"])):
        if row["arm"] not in "AC":
            continue
        groups[(row["arm"], row["group"], row["step"])].append(row)
        ordered = tuple(row["ordered_names"])
        for oid, name, native in zip(row["ordered_object_ids"], ordered, row["source_endpoints"]):
            assert ids_to_name.setdefault(oid, name) == name
            obj = geometry["objects"][name]
            assert world_hash(obj["vertices_world_m"], "d") == native["world_f64_sha256"]
            assert world_hash(obj["triangles"], "i") == native["triangles_i32_sha256"]
        assert row["actual_compute_calls"] == 1 and row["pair_cache_hit"] is False
        work = row["surface_work"]
        assert row["prepared_triangles"] == row["validated_faces"] == 120
        assert row["tree_builds"] == 2 and row["shared_trees"] is False
        assert "witness_triangle_checks" not in work and not work.get("shared_preparation")
        directions[ordered].append({key: row[key] for key in
            ("id", "step", "arm", "group", "ordered_object_ids", "surface_work")})
    assert len(groups) == 24 and len(directions) == 76 and len(ids_to_name) == 12
    for arm in "AC":
        for group in range(1, 7):
            near = groups[(arm, group, "nearest")]
            scan = groups[(arm, group, "scan")]
            assert len(near) == 11 and len(scan) == 66
            assert len({tuple(row["ordered_names"]) for row in near+scan}) == 76
    cases = []
    for ordinal, (ordered, history) in enumerate(sorted(directions.items()), 1):
        assert len({tuple(x["ordered_object_ids"]) for x in history}) == 1
        cases.append({
            "id": f"g60-{ordinal:02d}", "label": "g60",
            "ordered_names": list(ordered), "ordered_object_ids": history[0]["ordered_object_ids"],
            "geometry": roots["NATIVE_GEOMETRY.json"], "matrix_shape": [60, 60],
            "kernel_args": {"retain_exact_rank": True}, "history": history,
            "account": "fresh original surface Work, no pair/cache reuse, no closed contact",
        })
    counts = Counter(item["step"] for case in cases for item in case["history"])
    assert dict(counts) == {"scan": 792, "nearest": 132}, counts
    return roots, cases


def runtime_references():
    runtime = read(PREVIOUS / "FREEZE.json")["runtime"]
    git_checks = []
    for arm in "AC":
        item = runtime[arm]
        binding_path = check(item["binding"])
        binding = read(binding_path)
        assert binding["identity"] == item["identity"]
        assert item["identity"]["source_sha256"] == IDENTITIES[arm]
        site = binding_path.parent.parent / "site-packages"
        assert len(binding["source_files"]) == 143
        for row in binding["source_files"]:
            assert ref(site / row["path"])["sha256"] == row["sha256"]
        item["site"] = str(site)
        for name, file in item["source"].items():
            path = check(file)
            if arm == "A":
                git_path = "human_eye_plugin/" + name
                got = git_file(git_path, BASE).replace(b"\r\n", b"\n")
                assert got == path.read_bytes().replace(b"\r\n", b"\n"), name
                git_checks.append({"git_path": git_path, "sha256_lf": sha256(got).hexdigest()})
    return runtime, git_checks


def main():
    controls = Path(sys.argv[1]).resolve(strict=True)
    family = Path(sys.argv[2]).resolve(strict=True)
    family_truth = Path(sys.argv[3]).resolve(strict=True)
    runtime, git_checks = runtime_references()
    g60, cases = g60_references()
    print(save(RAW / "FREEZE.json", {
        "cycle_id": CYCLE, "parent": PARENT, "contract": CONTRACT, "base_git": BASE,
        "contract_sha256": sha256(git_file("docs/M6_R3_WITNESS_PARITY_048_TASK.md")).hexdigest(),
        "g60_independent_review": {
            "path": "verification/m6_r3_coverage_domain_047_review/RESULTS.json",
            "git": CONTRACT,
            "sha256": sha256(git_file("verification/m6_r3_coverage_domain_047_review/RESULTS.json")).hexdigest(),
            "use": "evaluation only; original separation certificate not an input to the kernels",
        },
        "g60_material": g60, "g60_cases": cases, "runtime": runtime, "baseline_git_checks": git_checks,
        "family": {"geometry": ref(family), "truth": ref(family_truth),
                   "archive_inputs": ref(family.parent / "INPUTS.json"),
                   "ordered_names": ["Object_01", "Object_02"], "shape": [96, 12],
                   "original_shared_path": "use actual 044 public archive",
                   "offline_path": "fresh ordinary distance, exact rank retained for evaluation"},
        "controls": ref(controls), "limits": LIMITS,
        "order": ["G60 case order by directed name pair", "044 family", "controls in frozen file order"],
        "stop": ("Persist both arms and cease new cases at first material geometry or available-field "
                 "difference, preserving earliest witness/fields and failed receipts. "
                 "Only same-input diagnostic reobservation can follow a material difference."),
        "replay": ref(HERE / "replay.py"),
        "deduplication": ("Same native rows/world binary64, ordered identities, exact-rank option, fresh original "
                          "account and no shared state. Nearest/scan reducers or cache identity are not conflated."),
        "diagnostics": ("First matching original-options kernel output, then read-only profiling and documented "
                        "witness-retention flag on the same input, bound by equal ordinary semantic fields."),
        "original_129": ref(RAW.parent / "M6-045-R3-REPLACEMENT-ENTRY" / "oracle" / "FINAL_FREEZE.json"),
    }))


if __name__ == "__main__":
    main()

