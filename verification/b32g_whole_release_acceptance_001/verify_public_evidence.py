"""Verify exported bytes and the release decision from the included evidence."""
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(path):
    return json.loads((ROOT / path).read_bytes())


def main():
    index = load("EVIDENCE_INDEX.json")
    published = [key for key in index["entries"] if "published_path" in key]
    assert len(index["entries"]) == index["source_rows"]
    assert len({row["published_path"] for row in published}) == len(published)
    for row in published:
        path = (ROOT / row["published_path"]).resolve()
        assert path.is_relative_to(ROOT)
        raw = path.read_bytes()
        assert len(raw) == row["published_bytes"], row["published_path"]
        assert sha256(raw).hexdigest() == row["published_sha256"], row["published_path"]
        if row["byte_exact"]:
            assert row["source_sha256"] == row["published_sha256"]
    matrix = load("matrix/SUMMARY.json")
    assert matrix["geometry_pass"] == matrix["geometry_denominator"] == 12
    assert matrix["overview_pass"] == matrix["overview_denominator"] == 4
    assert all(row["initial_and_final_worldmesh_equal"]
               and row["mcp_close"]["exit_code"] == 0
               and row["blender_close"]["exit_code"] == 0 for row in matrix["lanes"])
    hook = load("hook/live/CLOSED_HOOK_REVIEW.json")
    assert hook["passed"] and hook["arm_count"] == 2
    assert not hook["host_automatic_dispatch_tested"]
    rollback = load("rollback/verified/RESULT.json")
    assert rollback["passed"] and rollback["latest_state_retained"]
    assert rollback["stale_reverse_refused"] and rollback["audit_preserved_by_admin"]
    startup = load("startup_verified/RESULT.json")
    assert len(startup["rows"]) == 8 and startup["order"] == "ABBABAAB"
    print(f"Verified {len(published)} published bodies. Geometry 12/12, overview 4/4, "
          "live Hook 2/2, rollback verified, startup 8/8.")


if __name__ == "__main__":
    main()
