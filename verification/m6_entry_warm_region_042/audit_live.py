"""Recompute 042 live Yanyite results from frozen plan, GUI and stdio receipts."""
from __future__ import annotations

import argparse
from hashlib import file_digest
import json
from pathlib import Path
from statistics import median

ORDERS = [("AB", "BA", "AB", "BA"), ("BA", "AB", "BA", "AB"), ("BA", "AB", "AB", "BA")]
ARMS = {"A": "032", "B": "r3"}


def read(p):
    return json.loads(p.read_bytes())


def pin(p):
    p = p.resolve(strict=True)
    with p.open("rb") as stream:
        return {"path": str(p), "sha256": file_digest(stream, "sha256").hexdigest(), "bytes": p.stat().st_size}


def check_ref(ref):
    path = Path(ref["path"])
    assert pin(path) == ref
    return path


def body_from_wire(response):
    result = response["result"]
    assert not result.get("isError")
    value = result.get("structuredContent")
    if value is None:
        value = json.loads(result["content"][0]["text"])
    return value


def check_answer(body, plan, before):
    truth = plan["expected_geometry"]
    assert body["status"] == "complete" and body["read_only"] and body["unit"] == "m"
    expected = {"world_box_m": truth["box_m"], "selected_triangle_count": 262, "source_triangle_a": 49114,
        "source_triangle_b": 0, "distance_m": truth["distance_m"], "point_a_m": truth["source_point_world_m"],
        "point_b_m": truth["reference_point_world_m"], "direction_a_to_b": plan["direction_a_to_b"],
        "source_triangle_index_domain": "zero_based_object_local_current_evaluated_capture_triangle_rows"}
    assert all(body[k] == v for k, v in expected.items())
    query = plan["request"]["arguments"]["query"]
    for field, name in (("region_object", query["region"]["object"]["name"]), ("reference_object", "Cube")):
        assert body[field]["name"] == name
        assert body[field]["instance_id"] == before["geometry"][name]["instance"]


def check_cell(folder, arm, plan, before, host):
    report = read(folder / "CELL.json")
    assert report["valid"] and not report["errors"] and report["arm"] == arm
    assert report["host_pid"] == host["pid"]
    client = folder / "client"
    opening = read(client / "STARTUP.json")
    configured = read(client / "CONFIG.json")
    assert opening["actual_pid"] == report["product_pid"]
    assert configured["blender"]["port"] == host["close"]["released_port"]["port"]
    assert opening["hello"]["result"]["_meta"]["human_eye"]["source_sha256"] == plan["arms"][arm]["source_sha256"]
    assert configured["expected_identity"]["source_sha256"] == plan["arms"][arm]["source_sha256"]
    closing = read(client / "CLOSE.json")
    assert closing["method"] == "eof" and closing["exit_code"] == 0
    assert [r["step"] for r in report["rows"]] == ["first_high", "warm_high"]
    facts = []
    for row in report["rows"]:
        tx, rx = (check_ref(row[k]) for k in ("request", "response"))
        params, response = read(tx), read(rx)
        t = row["timing"]
        assert params["params"] == plan["request"] and params["id"] == response["id"] == t["id"]
        assert params["method"] == "tools/call"
        body = body_from_wire(response)
        assert body == row["result"]
        check_answer(body, plan, before)
        assert (t["wire_wait_ns"] + t["client_decode_ns"] == t["client_full_ns"] ==
                t["closed_ns"] - t["started_ns"])
        assert row["business_ns"] == row["end_ns"] - t["started_ns"]
        assert row["business_ns"] >= t["client_full_ns"] > 0
        assert (t["tx_bytes"], t["rx_bytes"]) == (tx.stat().st_size, rx.stat().st_size)
        trace = row["telemetry"]
        a = trace["annotations"]
        assert trace["pid"] == opening["actual_pid"] and a["mcp_request_id"] == t["id"]
        assert a["include_image"] is False and a["mcp_native_image_block_count"] == 0 and not trace["image_events"]
        assert a["delivery"] == "stdio_write_completed"
        host_spans = [s["duration_ns"] for s in trace["spans"] if s["name"] == "host.capture_source_region_pair"]
        assert len(host_spans) == 1
        facts.append({"business_ns": row["business_ns"], "host_capture_span_ns": host_spans[0],
                      "wire_wait_ns": t["wire_wait_ns"], "trace_ns": trace["duration_ns"],
                      "request_bytes": t["tx_bytes"], "response_bytes": t["rx_bytes"], "body": body})
    assert facts[0]["body"] == facts[1]["body"]
    return report, facts


def audit(live):
    plan = read(live / "PLAN.json")
    plan_orders = [tuple(x) for x in plan["orders"]]
    assert plan_orders == ORDERS
    check_ref(plan["asset"])
    check_ref(plan["source_geometry"])
    assert plan["asset"]["sha256"] == "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d"
    recorded = read(live / "main/RESULTS.json")
    hosts, products, pairs = [], [], []
    for i, orders in enumerate(ORDERS, 1):
        h = live / "main" / ("H" + str(i))
        host = read(h / "HOST.json")
        ownership = read(h / "native/OWNERSHIP.json")
        before, after = read(h / "BEFORE.json"), read(h / "AFTER.json")
        assert host["valid"] and host["geometry_preserved"]
        assert ownership["normal_queue_roundtrip_verified"] and ownership["normal_addon_unmodified"]
        assert not ownership["business_relay"] and not ownership["business_monkeypatch"]
        assert not before["background"] and before["pid"] == host["pid"] == after["pid"]
        assert all(before[k] == after[k] == plan[k] for k in ("frame", "subframe", "scale"))
        assert before["geometry"] == after["geometry"]
        assert pin(Path(before["asset"]))["sha256"] == plan["asset"]["sha256"]
        exit_proof = host["close"]
        assert exit_proof["status"] == "pass" and exit_proof["process_reaped"] and exit_proof["exit_code"] == 0
        assert exit_proof["forced"] is None and not exit_proof["released_port"]["owned_listener"]
        assert exit_proof["source_unchanged"] and exit_proof["owned_copy_unchanged"]
        hosts.append(host["pid"])
        for group, order in enumerate(orders, 1):
            arms = {}
            entries = []
            for letter in order:
                arm = ARMS[letter]
                result, facts = check_cell(h / f"H{i}-P{group}-{arm}", arm, plan, before, host)
                entries.append(result)
                products.append(result["product_pid"])
                arms[letter] = facts
            assert entries[0]["end_ns"] <= entries[1]["start_ns"]
            a, b = arms["A"], arms["B"]
            assert a[0]["body"] == b[0]["body"]
            ca, cb, aa, bb = a[0]["business_ns"], b[0]["business_ns"], a[1]["business_ns"], b[1]["business_ns"]
            row = {"host": i, "pair": group, "order": order, "a_first_ns": ca, "b_first_ns": cb,
                   "a_warm_ns": aa, "b_warm_ns": bb, "delta_ms": (bb-aa)/1e6, "relative": bb/aa-1,
                   "a_host_capture_ns": a[1]["host_capture_span_ns"], "b_host_capture_ns": b[1]["host_capture_span_ns"],
                   "a_trace_ns": a[1]["trace_ns"], "b_trace_ns": b[1]["trace_ns"]}
            pairs.append(row)
    assert len(set(hosts)) == 3 and len(set(products)) == 24
    delta = median(p["delta_ms"] for p in pairs)
    relative = median(p["relative"] for p in pairs)
    assert recorded["median_delta_ms"] == delta and recorded["median_relative"] == relative
    by_host = [dict(host=i, delta_ms=median(p["delta_ms"] for p in pairs if p["host"] == i),
                    relative=median(p["relative"] for p in pairs if p["host"] == i)) for i in (1, 2, 3)]
    assert by_host == recorded["by_host"]
    assert all(p["valid"] for p in recorded["pairs"])
    capture_delta_ms = median((p["b_host_capture_ns"]-p["a_host_capture_ns"])/1e6 for p in pairs)
    return {
        "verified_cold_and_warm_responses": 48, "valid_pairs": len(pairs), "distinct_ordinary_guis": len(hosts),
        "distinct_product_pids": len(products), "pairs": pairs, "median_delta_ms": delta,
        "median_relative": relative, "by_host": by_host, "material_regression": delta > 5 and relative > .05,
        "business_minus_host_capture_delta_ms": median((p["b_warm_ns"]-p["b_host_capture_ns"]-
                                                       p["a_warm_ns"]+p["a_host_capture_ns"])/1e6 for p in pairs),
        "host_capture_delta_ms": capture_delta_ms,
        "timing_scope": "observed inclusive host capture span and residual calculated within each request",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("live", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.live)
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as out:
            json.dump(result, out, ensure_ascii=False, indent=2)
            out.write("\n")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
