"""Reconcile existing S0 receipts with independent frozen IDs and arm pins."""
from copy import deepcopy
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from consumer_controls import BENCH, BENCH_HASH, EXPECTED_SCAN, OPTIONS, PEER_IDS, POSITIONS, coords, sha
import historical_replay as h


def sem(row):
    return {key: value for key, value in row.items() if key != "work"}


def seal_comparator():
    assert h.digest(BENCH) == BENCH_HASH
    sys.path.insert(0, str(ROOT / "source_R3"))
    bench = h.module("_s0_comparator", BENCH)
    ins_path = ROOT.parent / "install/PINS.json"
    assert h.digest(ins_path) == h.PIN_DIGEST
    pin_data = h.read(ins_path)["arms"]
    files = [ROOT / "CONSUMER_installed_032.json", ROOT / "CONSUMER_installed_r3.json"]
    receipts = list(map(h.read, files))
    pins = {"baseline": pin_data["032"]["identity"]["source_sha256"],
            "current": pin_data["r3"]["identity"]["source_sha256"]}
    external_ids = ["a/" + x for x in PEER_IDS]
    hashes = [sha(coords(POSITIONS[obj])) for obj in ("a", *PEER_IDS)]
    docs = []
    for receipt, arm in zip(receipts, pins, strict=True):
        assert receipt["identity"]["source_sha256"] == pins[arm]
        assert receipt["frozen_geometry_sha256"] == sha(POSITIONS)
        assert list(receipt["pairs"]) == external_ids
        for key in external_ids:
            assert receipt["pairs"][key]["input_sha256"] == sha(tuple(coords(POSITIONS[obj])
                                                                      for obj in key.split("/")))
        batch = dict(input_sha256=hashes, batch_ids=external_ids,
                     signatures=[bench._surface_sig(receipt["pairs"][key]["raw"]) for key in external_ids])
        docs.append(dict(schema="m3-bvh-eval-v4", runtime_identity_sha256=pins[arm],
                         solver_options=OPTIONS, options_sha256=bench._stable_hash(OPTIONS),
                         inputs_sha256={"fixture": sha(POSITIONS)}, surface_single={}, spatial_relation={},
                         closed_solid={}, surface_analyze={}, e2e_entries={}, surface_batch={"S0_tied_peers": batch}))
    manifests = dict(expected_batch_manifest={"S0_tied_peers": external_ids},
                     expected_workload_manifest={"surface_batch": ["S0_tied_peers"]},
                     expected_arm_pins=pins)
    assert not bench._compare_signatures(*docs, **manifests)
    ends_near = [bench._nearest_sig(r["normal_nearest"]) for r in receipts]
    ends_scan = [bench._scan_sig(r["normal_scan"], r["scan_diagnostics"]) for r in receipts]
    pins_entry = dict(ref_runtime_sha=pins["baseline"], cand_runtime_sha=pins["current"])
    bench.assert_entry_receipts_equal(*ends_near, **pins_entry, entry_kind="nearest")
    bench.assert_entry_receipts_equal(*ends_scan, **pins_entry, entry_kind="scan")
    assert [row["object_ids"] for row in ends_scan[0]["dispositions"]] == [list(pair) for pair in EXPECTED_SCAN]

    negatives = {}
    values = deepcopy(docs)
    for row in values:
        # Do not allow two self-consistent receipts to omit the same pair.
        row["surface_batch"]["S0_tied_peers"]["batch_ids"].pop()
        row["surface_batch"]["S0_tied_peers"]["input_sha256"].pop()
        row["surface_batch"]["S0_tied_peers"]["signatures"].pop()
    negatives["mutual_prefix_truncation"] = bench._compare_signatures(*values, **manifests)
    assert any("expected_batch_manifest" in err for err in negatives["mutual_prefix_truncation"])

    impostor = deepcopy(docs[1])
    impostor["runtime_identity_sha256"] = pins["baseline"]
    negatives["well_formed_wrong_external_arm"] = bench._compare_signatures(docs[0], impostor, **manifests)
    assert any("expected external pin" in err for err in negatives["well_formed_wrong_external_arm"])

    wrong_scan = deepcopy(ends_scan[1])
    wrong_scan["dispositions"][0]["distance_m"] = 0.25
    negatives["wrong_scan_distance"] = bench.check_entry_receipts(ends_scan[0], wrong_scan, **pins_entry, entry_kind="scan")
    assert negatives["wrong_scan_distance"]

    return {"external_pins": pins, "expected_ids": ["a/b", "a/c"], "scan_denominator": len(EXPECTED_SCAN),
            "expected_geometry_sha256": sha(POSITIONS), "validated_negative_controls": negatives,
            "positive_controls": ["actual installed pair receipts", "actual installed nearest", "actual installed scan"],
            "input_receipts": [{"path": str(f), "sha256": h.digest(f)} for f in files]}


def suites():
    logs = [ROOT / f"PORTABLE_{arm}.stderr.txt" for arm in ("032", "R3")]
    traces = list(map(lambda path: path.read_text(encoding="utf8", errors="replace"), logs))
    identities = [sorted(re.findall(r"^(?:FAIL|ERROR):[^\n]*", text, re.M)) for text in traces]
    assert len(identities[0]) == len(identities[1]) == 41 and identities[0] == identities[1]
    assert all("Ran 3203 tests" in text and "FAILED (failures=23, errors=18, skipped=13)" in text for text in traces)
    return {"modules_per_arm": 187, "tests_per_arm": 3203, "passed_per_arm": 3149,
            "known_failures_per_arm": 23, "known_errors_per_arm": 18, "skipped_per_arm": 13,
            "same_failure_ids": identities[0], "candidate_only_failure_ids": []}


def compare_history():
    out = {}
    for case in h.CASES:
        rows = {arm: h.read(ROOT / ("historical_" + arm) / (case + ".json"))
                for arm in ("source_032", "source_r3", "installed_032", "installed_r3")}
        assert len({row["input_sha256"] for row in rows.values()}) == 1
        for arm in ("032", "r3"):
            assert rows["source_" + arm]["default"] == rows["installed_" + arm]["default"]
        src, r3 = rows["source_032"], rows["source_r3"]
        assert r3["exact_truth_agrees"]
        expect_g = h.read(h.OLD31 / f"private/controls/attempt_003_Gmain/{case}_G.json")
        assert src["default"]["result"]["work"] == expect_g["work"]
        assert sem(r3["default"]["result"]) == sem(r3["off_paid_dequeue_ref"]["result"]) == sem(r3["off"]["result"])
        if case == "pair129":
            assert src["default"]["result"]["reason"] == "surface_pair_budget"
        else:
            assert src["exact_truth_agrees"]
            assert sem(src["default"]["result"]) == sem(r3["default"]["result"])
        out[case] = {arm: rows["source_" + arm]["default"]["result"] for arm in ("032", "r3")}
    for arm in ("032", "r3"):
        for layout in ("source", "installed"):
            closed = h.read(ROOT / f"historical_{layout}_{arm}/crossed-box-040.json")
            assert closed["exact_source_witness_equal"]
    out["040_crossed_box"] = {"original_032_source_rows": [27, 1],
                              "r3_source_rows": [27, 1], "full_local_evidence_equal": True}
    return out


def main():
    out = {"schema": "M6-041-S0-evaluation-v1",
           "comparator": seal_comparator(), "portable": suites(), "historical": compare_history()}
    h.save(ROOT / "S0_RESULTS.json", out)
    print(json.dumps({"status": "summary_pass", "file": str(ROOT / "S0_RESULTS.json"),
                      "sha256": h.digest(ROOT / "S0_RESULTS.json")}), flush=True)


if __name__ == "__main__":
    main()
