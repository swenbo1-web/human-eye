"""Summarize independent recovery of the six original scan display packets."""

import hashlib
import json
from pathlib import Path
import sys
import time
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from verification.m4_surface_scan_compact_facts_001.semantics.test_compact_semantics import (
    SEALED, check_projection, text_result,
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    rows = []
    test = unittest.TestCase()
    for cell, value, old_text in SEALED:
        outputs = {}
        for name, options in (("default", {}), ("brief", {"response_detail": "brief"}),
                              ("full", {"response_detail": "full"})):
            start = time.perf_counter_ns()
            wire, body = text_result(value, **options)
            elapsed = time.perf_counter_ns() - start
            text = wire["content"][0]["text"]
            if name == "full":
                assert text == old_text
            else:
                check_projection(test, value, body)
                assert len(text.encode("utf8")) <= 10 * 1024
            outputs[name] = dict(utf8_bytes=len(text.encode("utf8")), sha256=sha(text.encode("utf8")),
                                 projection_and_encoding_local_sample_ns=elapsed)
        assert outputs["default"]["sha256"] == outputs["brief"]["sha256"]
        rows.append(dict(cell=cell, trace_id=value["trace_id"], matches=len(value["matches"]),
                         source_text_utf8_bytes=len(old_text.encode("utf8")),
                         source_text_sha256=sha(old_text.encode("utf8")), outputs=outputs))
    record = dict(schema="surface_scan_compact_sealed_packet_recovery_v1", original_packets=6,
                  match_rows_recovered=6 * 71, source_product_file_sha256=sha((ROOT / "human_eye_plugin/live_spatial_mcp.py").read_bytes()),
                  scope="Offline pure display projections only, one timed sample per packet/mode; no host or model calls.",
                  timing_limit="Local projection/encoding samples include the independent JSON parse used by this verifier; they are not standalone production span or task latency.",
                  new_Blender_model_business_API_runs=0, rows=rows)
    (HERE / "SEALED_RESPONSES.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps(dict(packets=6, rows_recovered=426,
                         default_bytes=[row["outputs"]["default"]["utf8_bytes"] for row in rows],
                         full_bytes=[row["outputs"]["full"]["utf8_bytes"] for row in rows])))


if __name__ == "__main__":
    main()
