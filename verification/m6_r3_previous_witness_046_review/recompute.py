"""Check the fixed transaction log and independently replay the unchanged 046 kernel once."""
import hashlib
import itertools
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time
import types


HERE = Path(__file__).resolve().parent
last = runpy.run_path(str(HERE.parent / "m6_r3_replacement_entry_045_review" / "recompute.py"))
read, sha, bound, work = (last[k] for k in ("read", "sha", "bound", "WORK"))
raw = Path("D:/HumanEye/runs/M6-046-R3-PREVIOUS-WITNESS")
scope = "verification/m6_r3_previous_witness_046"
commit = "c010b07be6352b1f15e39fd2c8227a05bb7690cd"
prior = "83897bc2fa626bc86a141e3e63fff3c9f59ab75a"
limit, pair_limit = 1179648, 16384
candidate = "e432607752b6756e67815fe56fd088278d1e8063bb2dbf34b5b5cece7ae19dee"


def provenance():
    proc = ["git", "-C", str(work)]
    assert subprocess.check_output(proc + ["rev-parse", commit + "^"]).decode().strip() == prior
    changes = subprocess.check_output(proc + ["diff", "--name-status", prior, commit]).decode().splitlines()
    assert changes and all(row.startswith("A\t" + scope + "/") for row in changes)
    for row in subprocess.check_output(proc + ["ls-tree", "-r", commit, "--", scope]).splitlines():
        data, name = row.split(b"\t")
        blob = (work / name.decode()).read_bytes()
        assert hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest() == data.split()[-1].decode()
    index = raw / "RAW_EVIDENCE.json"
    assert sha(index) == "4f0d3790c8a62ea5d43ae6b01946434c0fa63f1cce7e9f3612049fc1558f107f"
    inv = read(index)
    members = {r["path"] for r in inv["files"]}
    assert members == {p.relative_to(raw).as_posix() for p in raw.rglob("*") if p.is_file() and p != index}
    assert len(members) == len(inv["files"]) == inv["file_count"]
    for item in inv["files"]:
        bound(dict(item, path=raw / item["path"]))
    assert sum(r["bytes"] for r in inv["files"]) == inv["bytes"]

    new = read(raw / "candidate/PINS.json")
    assert new["source_sha256"] == candidate
    for k in ("design", "patch", "launcher", "startup", "changed_kernel"):
        bound(new[k])
    old = read(last["RAW"] / "g60/PLAN.json")
    installations = dict(old["release_bindings"], D=new["binding"])
    pins = dict(last["PINS"], D=candidate)
    for arm, ref in installations.items():
        binding = read(bound(ref))
        assert binding["identity"]["source_sha256"] == pins[arm] and len(binding["source_files"]) == 143
        for row in binding["source_files"]:
            assert sha(Path(binding["site_packages"]) / row["path"]) == row["sha256"]
    close = read(raw / "TERMINAL_INVENTORY.json")
    assert close["status"] == "pass" and not close["matching_processes"]
    return dict(raw_members=len(members), raw_bytes=inv["bytes"], git_files=len(changes), installed_sources=572)


def ledger(observation):
    diag = read(raw / "numeric/same_input_diagnostic_02/RESULT.json")
    rows = read(bound(diag["credit_attempts"]))
    spent, last_earned, work_after = 0, 0, 0
    phases = {}
    proof_requests = []
    for i, row in enumerate(rows):
        role, ask, initial = row["role"], row["upper"], row["credit_before"]
        assert row["earned"] >= last_earned and row["spent_before"] == spent
        assert initial == row["earned"] - spent and row["work_before"] >= work_after
        admitted = initial >= ask and limit - row["work_before"] >= ask
        assert row["admitted"] == admitted
        paid = row["work_after"] - row["work_before"]
        assert 0 <= paid <= (ask if admitted else 0) and paid == row["actual"]
        assert initial - paid == row["credit_after"]
        if role == "previous_test":
            selection = rows[i - 1]
            assert selection["role"] == "previous_selection" and selection["admitted"]
            assert selection["credit_after"] == initial and selection["work_after"] == row["work_before"]
            assert ask > initial and ask <= limit - row["work_before"] and paid == 0
            proof_requests.append(row)
        bucket = phases.setdefault(role, dict(requests=0, accepted=0, work=0))
        bucket["requests"] += 1
        bucket["accepted"] += admitted
        bucket["work"] += paid
        spent += paid
        last_earned, work_after = row["earned"], row["work_after"]
    w = observation["result"]["work"]
    assert spent == w["witness_projection_credit_spent_units"] == last_earned
    assert w["witness_projection_credit_balance"] == 0
    p = phases["previous_test"]
    assert p["accepted"] == 0 and p["requests"] == phases["previous_selection"]["accepted"]
    assert w["previous_witness_work_units"] == phases["previous_build"]["work"] + phases["previous_selection"]["work"]
    assert not w.get("previous_witness_tests", 0) and not w.get("previous_witness_pruned_pairs", 0)
    old = read(last["RAW"] / "boundary_diagnostic/C/RESULT.json")["work"]
    shared = [k for k in old if k in w and not k.startswith(("witness_projection_", "previous_witness_"))]
    assert all(old[k] == w[k] for k in shared)
    assert (diag["capture"]["past_pair"], diag["capture"]["new_pair"]) == ([127,128], [128,128])
    assert diag["activation"]["axis"] == [3,1,-4] and diag["activation"]["current_axis"] == [1,1,-2]
    assert diag["narrow_cap"]["already_completed"] == w["narrow_phase_pairs"] == pair_limit
    assert w["leaf_pair_visits"] == pair_limit + 1
    return dict(rows=len(rows), phases=phases, shared_counters=len(shared), current_tests_C=old["witness_projection_tests"],
                current_tests_D=w["witness_projection_tests"], work_remaining=limit-w["work_units"],
                first_need=proof_requests[0]["upper"], first_available=proof_requests[0]["credit_before"],
                min_need=min(x["upper"] for x in proof_requests), max_available=max(x["credit_before"] for x in proof_requests),
                smallest_same_attempt_shortfall=min(x["upper"]-x["credit_before"] for x in proof_requests),
                zero_credit_attempts=sum(x["credit_before"] == 0 for x in proof_requests),
                minimum_remaining_global_work_at_application=min(limit-x["work_before"] for x in proof_requests))


def replay(observation):
    install = read(bound(observation["installation"]))
    site = Path(install["site"])
    source = bound(install["changed_kernel"])
    assert source == site / "human_eye_plugin/surface_proximity.py"
    # Compile the pinned source itself; sibling imports resolve in the verified installation.
    sys.path.insert(0, str(site))
    kernel = types.ModuleType("human_eye_plugin._independent_046_kernel")
    kernel.__package__ = "human_eye_plugin"
    kernel.__file__ = str(source)
    exec(compile(source.read_bytes(), str(source), "exec"), kernel.__dict__)
    frozen = read(bound(observation["frozen_geometry_and_truth"]))
    data = read(bound(frozen["geometry"]))
    def mesh(side):
        d = data[side]
        return types.SimpleNamespace(name=d["name"], object_id=d["name"], vertices=tuple(map(tuple, d["vertices_world"])),
                                     faces=tuple(map(tuple, d["faces"])))
    left, right = mesh("left"), mesh("right")
    work_codes = {kernel._Work.tick.__code__, kernel._Work.consume.__code__}
    prefixes = 0
    last_work = 0
    def observer(frame, event, arg):
        nonlocal prefixes, last_work
        if event == "return" and frame.f_code in work_codes:
            counts = frame.f_locals["self"].counts
            current = counts["work_units"]
            assert last_work <= current <= limit and counts["narrow_phase_pairs"] <= pair_limit
            prefixes += 1
            last_work = current
    deadline = time.monotonic_ns() + 30_000_000_000
    def checkpoint(stage):
        if time.monotonic_ns() >= deadline:
            raise TimeoutError(stage)
    previous = sys.getprofile()
    try:
        sys.setprofile(observer)
        result = kernel.measure_surface_proximity(left, right, checkpoint, retain_exact_rank=True, retain_witness_triangles=True)
    finally:
        sys.setprofile(previous)
    assert time.monotonic_ns() < deadline
    assert json.loads(json.dumps(result, allow_nan=False)) == observation["result"]
    assert result["reason"] == "surface_pair_budget" and not result["measurement_valid"]
    assert all(result[k] is None for k in ("distance_m", "point_a_world", "point_b_world", "direction_a_to_b"))
    diag = read(raw / "numeric/same_input_diagnostic_02/RESULT.json")
    assert prefixes == diag["observed_work_prefixes"] and last_work == result["work"]["work_units"]
    return dict(work_prefixes=prefixes, final_work=last_work, result_matches_fixed_first=True,
                scope="one independent offline source replay, instrumented and excluded from performance")


def archived_counts():
    plan = read(last["RAW"] / "g60/PLAN.json")
    fixture = read(bound(plan["snapshot_fixture"]))
    counts = {o["name"]:len(o["triangles"]) for o in fixture["objects"]}
    for group in sorted((last["RAW"] / "g60/main_001").glob("G??-*")):
        for file in ("BEFORE.json", "AFTER.json"):
            capture = read(group / file)["geometry"]
            assert {k:v["triangles"] for k,v in capture.items()} == counts
    pairs = [a*b for a,b in itertools.combinations(counts.values(), 2)]
    design = read(raw / "DESIGN.json")
    holdout = read(bound(design["holdout"]))
    assert not holdout["D_imports"] and not holdout["D_results_read"]
    source = read(bound(holdout["selected"]["geometry"]))
    assert [len(source[k]["faces"]) for k in ("left","right")] == [128,28]
    development = read(bound(read(bound(design["development"]["freeze"]))["geometry"]))
    return dict(development_pairs=len(development["left"]["faces"])*len(development["right"]["faces"]),
                G60_objects=len(counts), G60_possible_object_pairs=len(pairs), G60_products=sorted(set(pairs)),
                holdout_possible_pairs=128*28, scope="face-product arithmetic only; no dispatch or timing measured")


if __name__ == "__main__":
    observation = read(raw / "numeric/first_129/RESULT.json")
    print(json.dumps(dict(commit=commit, integrity=provenance(), archival_credit=ledger(observation),
                          independent_replay=replay(observation), archive_counts=archived_counts()),
                     indent=2, allow_nan=False))
