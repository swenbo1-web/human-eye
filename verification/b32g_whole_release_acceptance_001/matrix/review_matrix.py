"""Independently pair normalized raw replies and their own trace receipts."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_bytes())


def read_payload(folder, call):
    response = load(folder / "mcp" / f"{call}_RESPONSE.json")
    assert not response["result"].get("isError")
    rows = response["result"]["content"]
    assert len(rows) == 1 and rows[0]["type"] == "text"
    return json.loads(rows[0]["text"])


def stage_spans(trace):
    return [{"name": span["name"], "ms": span["duration_ns"] / 1e6}
            for span in trace["spans"]]


def witness_checks(witness, distance):
    displacement = [right - left for left, right in zip(witness["a"], witness["b"])]
    assert math.isclose(math.hypot(*displacement), distance, abs_tol=1e-16)
    assert all(math.isclose(d / distance, component, abs_tol=1e-12)
               for d, component in zip(displacement, witness["direction_a_to_b"]))


def main():
    summary = load(ROOT / "SUMMARY.json")
    assert summary["status"] == "passed"
    assert summary["geometry_pass"] == 12 and summary["overview_pass"] == 4
    lane_stats = {}
    comparison = {}
    first_g = read_payload(ROOT / "A_G60_D12", "05_observe_0")
    witness = first_g["pairs"][0]["facts"]["surface_proximity"]["value"]["nearest_witness"]
    for scene in ("G60_D12", "D48"):
        folders = {arm: ROOT / f"{arm}_{scene}" for arm in ("A", "B")}
        copy_source = [load(folder / "INITIAL.json") for folder in folders.values()]
        assert copy_source[0] == copy_source[1]
        for arm, folder in folders.items():
            lane = load(folder / "RESULT.json")
            assert lane["status"] == "passed"
            assert load(folder / "FINAL.json") == copy_source[0]
            assert all(lane[field]["exit_code"] == 0 and lane[field]["process_reaped"]
                       for field in ("mcp_close", "blender_close"))
            audit = [json.loads(row) for row in (folder / "audit.jsonl").read_bytes().splitlines()]
            traces = {row["trace_id"]: row["trace"] for row in audit if row["event"] == "request_trace"}
            work = {row["trace_id"]: row.get("task_work") for row in audit if row["event"] == "observe"}
            measurements = []
            for repeat in range(3):
                rec = lane["observations"][repeat]
                payload = read_payload(folder, f"{repeat + 5:02d}_observe_{repeat}")
                traced = traces[payload["trace_id"]]
                counters = work[payload["trace_id"]]
                measurements.append(dict(rtt_ms=rec["rtt_ns"] / 1e6,
                                         response_bytes=rec["response_bytes"],
                                         span_ns=traced["duration_ns"], spans=stage_spans(traced),
                                         pair_calls=counters.get("pair_calls"),
                                         result_cache_hit=counters.get("result_cache_hit")))
            overview_score = load(folder / "mcp/OVERVIEW_SCORE.json")
            overview_row = next(r for r in lane["protocol_calls"] if r["label"] == "readonly_overview")
            overview = read_payload(folder, f'{overview_row["id"]:02d}_readonly_overview')
            lane_stats[lane["cell"]] = dict(geometry=measurements, source_objects=len(copy_source[0]["objects"]),
                                           geometry_unchanged=True, overview=overview_score,
                                           overview_spans=stage_spans(traces[overview["request_trace"]["trace_id"]]),
                                           first_answer_ms=lane["owned_chain_start_to_first_answer_ns"] / 1e6,
                                           spawn_to_init_ms=lane["mcp_spawn_to_initialized_ns"] / 1e6,
                                           lifecycle_ms=lane["whole_owned_chain_ns"] / 1e6,
                                           mcp_exit=lane["mcp_close"]["exit_code"],
                                           blender_exit=lane["blender_close"]["exit_code"])
        for repeat in range(3):
            call = f"{repeat + 5:02d}_observe_{repeat}"
            left_request, right_request = [(folder / "mcp" / f"{call}_REQUEST.json").read_bytes()
                                           for folder in folders.values()]
            assert left_request == right_request
            a, b = [read_payload(folder, call) for folder in folders.values()]
            if scene == "G60_D12":
                x, y = (payload["pairs"][0]["facts"] for payload in (a, b))
                assert x == y and x["closed_solid_relation"]["value"] == "separated"
                fact = x["surface_proximity"]["value"]
                witness_checks(fact["nearest_witness"], fact["distance_m"])
                comparison[scene] = dict(gap_m=fact["distance_m"], relation="separated",
                                         published_witness_equal=True)
            else:
                for field in ("distance_m", "best_known_distance_m", "coverage",
                              "unresolved", "nearest_objects"):
                    assert a[field] == b[field], field
                assert a["coverage"]["distance_valid"] == 47 and a["unresolved"] == []
                evidence = b["best_known_evidence"]
                assert len(evidence) == 1
                extra = evidence[0]
                assert b["nearest_objects"] == [extra["candidate"]]
                assert extra["point_a_world"] == witness["a"] and extra["point_b_world"] == witness["b"]
                assert extra["direction_a_to_b"] == witness["direction_a_to_b"]
                witness_checks(witness, b["distance_m"])
                comparison[scene] = dict(nearest=b["nearest_objects"][0]["name"], targets=47,
                                         gap_m=b["distance_m"], extra_witness_consistent=True)
    result = dict(status="passed", factual_pairs=6, matched_readonly_overviews=4, observations=comparison,
                  lane_stats=lane_stats, cold_rtt_delta_pct={
                      scene: 100 * (lane_stats[f"B_{scene}"]["geometry"][0]["rtt_ms"]
                                    / lane_stats[f"A_{scene}"]["geometry"][0]["rtt_ms"] - 1)
                      for scene in ("G60_D12", "D48")})
    result_file = ROOT / "RAW_COMPARISON.json"
    result_file.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    indexed = {str(path.relative_to(ROOT)).replace("\\", "/"):
               dict(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
               for path in sorted(ROOT.rglob("*")) if path.is_file() and path.name != "RAW_INDEX.json"}
    (ROOT / "RAW_INDEX.json").write_text(json.dumps(indexed, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(results=comparison, indexed=len(indexed), cold_pct=result["cold_rtt_delta_pct"])))


if __name__ == "__main__":
    main()
