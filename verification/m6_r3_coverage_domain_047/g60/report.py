"""Final raw-only G60 cache/phase report and immutable evidence index."""
from hashlib import file_digest
from itertools import combinations
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
RAW=Path("D:/HumanEye/runs/M6-047-R3-COVERAGE-DOMAIN/g60")


def read(path):return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    with path.open("rb") as stream:digest=file_digest(stream,"sha256").hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)


def save(path,value):
    with Path(path).open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write("\n")
    return pin(path)


def main():
    result=read(RAW/"RESULTS.json")
    requests=read(RAW/"REQUESTS.json");calls=read(RAW/"PAIR_CALLS.json");duplicates=read(RAW/"CROSS_MODE_DUPLICATES.json")
    verifier=read(RAW/"VERIFY_045_RECOMPUTED.json")
    archive=read(RAW/"ARCHIVE_FREEZE.json")
    old=Path(archive["archive_root"])
    original_verifier=read(old/"g60/verification/ATTEMPT_002.json")
    assert verifier["verifier"]==original_verifier["verifier"]
    cache_rows=[]
    for row in requests:
        if row["step"]!="scan":continue
        before,after=row["measurement_cache_before"],row["measurement_cache_after"]
        cache_rows.append(dict(group=row["group"],arm=row["arm"],entry_count_before=before["measurement_entries"],
            entry_count_after=after["measurement_entries"],computations_before=before["measurement_computations"],
            computations_after=after["measurement_computations"],hits_before=before["measurement_hits"],hits_after=after["measurement_hits"],
            misses_before=before["measurement_misses"],misses_after=after["measurement_misses"],
            max_bytes=after["max_bytes"],accounted_bytes_before=before["accounted_bytes"],accounted_bytes_after=after["accounted_bytes"],
            entry_change_scope="Observed entry growth only; actual nearest key digest was not archived",
            source_cell=row["cell"]))
    assert len(cache_rows)==18 and all((r["entry_count_before"],r["entry_count_after"],r["computations_before"],r["computations_after"],
                                      r["hits_before"],r["hits_after"])==(11,77,11,77,0,0) for r in cache_rows)
    scan_calls=[c for c in calls if c["step"]=="scan"];nearest_calls=[c for c in calls if c["step"]=="nearest"]
    assert len(scan_calls)==1188 and len(nearest_calls)==198 and len(duplicates)==198
    assert all(c["cache_key_digest_observed"] and c["scan_dependency_used"] and c["scan_dependency_cache_hit"] is False for c in scan_calls)
    assert all(c["cache_key_digest"] is None for c in nearest_calls)
    assert all(c["per_call_compute_ns"] is None and c["shared_trees"] is False for c in calls)
    assert all(c["validated_faces"]==c["prepared_triangles"]==120 and c["tree_builds"]==2 for c in calls)
    geometry=read(RAW/"NATIVE_GEOMETRY.json")
    boxes={name:([min(v[a] for v in mesh["vertices_world_m"]) for a in range(3)],
                 [max(v[a] for v in mesh["vertices_world_m"]) for a in range(3)]) for name,mesh in geometry["objects"].items()}
    aabb_rows=[dict(names=[a,b],closed_AABB_overlap=all(boxes[a][0][axis]<=boxes[b][1][axis] and
                                                    boxes[b][0][axis]<=boxes[a][1][axis] for axis in range(3)))
               for a,b in combinations(sorted(boxes),2)]
    assert len(aabb_rows)==66 and all(row["closed_AABB_overlap"] for row in aabb_rows)
    cache=dict(schema="m6-047-g60-cache-evidence-v1",source=pin(Path(__file__)),request_table=pin(RAW/"REQUESTS.json"),
        pair_table=pin(RAW/"PAIR_CALLS.json"),duplicate_table=pin(RAW/"CROSS_MODE_DUPLICATES.json"),
        observed_entry_progress=cache_rows,nearest_pair_calls=198,scan_pair_calls=1188,
        scan_actual_dependency_key_digests=1188,nearest_actual_key_digests_unmeasured=198,
        same_unordered_source_geometry_repeated_across_modes=198,same_order=18,reversed_order=180,
        actual_cross_mode_pair_hits=0,
        actual_digest_equality_comparisons_measured=0,per_call_timing_measured=0,
        key_scope="Both paths retain exact rank. Ordered pair and ordinary read/full-mesh versus scan resource-dependency key representations remain distinct; no key/routing change is implemented.")
    cache_ref=save(RAW/"CACHE_EVIDENCE.json",cache)
    phase_rows=[]
    for name in ("business","process_lifetime","client_full","workflow"):
        data=verifier[name]
        phase_rows.append(dict(phase=name,status=data["status"],original_rounds=data["rounds"],
            arm_medians_ns=data["medians_ns"],B_vs_A=data["pairs"]["B_vs_A"],C_vs_A=data["pairs"]["C_vs_A"],
            C_vs_B=data["pairs"]["C_vs_B"]))
    report=dict(schema="m6-047-g60-final-evidence-v1",status="pass",raw_result=pin(RAW/"RESULTS.json"),
        cache_evidence=cache_ref,original_verifier_exact_source=verifier["verifier"],
        original_verifier_recomputed=pin(RAW/"VERIFY_045_RECOMPUTED.json"),
        ordinary_host_count=6,services=18,all_three_version_replies=54,primary_A_C_replies=36,
        actual_kernel_calls_all_versions=1386,actual_kernel_calls_A_C=924,
        per_service=dict(nearest_possible_object_pairs=11,nearest_actual_kernel_calls=11,scan_possible_object_pairs=66,
                         scan_actual_kernel_calls=66,distinct_unordered_pairs=66,repeated_nearest_scan_geometry=11,
                         same_order_repeat=1,reversed_order_repeat=10,cache_hits=0,strict_skips=0,unknown=0,deferred=0),
        by_arm=result["by_arm"],observed_limits=result["observed_limits"],historical_complete_phases=phase_rows,
        native_object_AABB_pair_overlaps=aabb_rows,native_AABB_overlap_count=66,
        AABB_scope="All 66 source-world object AABBs overlap in the hash-bound geometry common to all six actual host snapshots; this is a min/max array check, not a surface solve",
        new_calls=result["newly_run"],coverage_unknowns=result["coverage_and_timing_gaps"],
        no_hybrid_speed_estimate=True,no_full_contract_sufficiency_claim=True,
        preparation_scope="All original per-call validation/prepared/tree counters are reported. Each archived call reports 120 validated/prepared triangles and 2 new trees, shared_trees=false. Counter equality is not time equality or a proof that normalization is free.")
    final_ref=save(RAW/"FINAL_REPORT.json",report)
    print(final_ref)
    with (HERE/"FINAL_REPORT.json").open("x",encoding="utf-8",newline="\n") as stream:
        json.dump({key:report[key] for key in ("schema","status","raw_result","cache_evidence","original_verifier_exact_source",
            "ordinary_host_count","services","all_three_version_replies","primary_A_C_replies","actual_kernel_calls_all_versions",
            "actual_kernel_calls_A_C","per_service","observed_limits","new_calls","coverage_unknowns","no_hybrid_speed_estimate",
            "no_full_contract_sufficiency_claim","preparation_scope")}|{"raw_final_report":final_ref},stream,indent=2,ensure_ascii=False)
        stream.write("\n")
    raw_refs=[pin(path) for path in sorted(RAW.rglob("*")) if path.is_file() and path.name!="INDEX.json"]
    sources=[pin(path) for path in sorted(HERE.rglob("*")) if path.is_file() and path.name!="INDEX.json"]
    raw_index=save(RAW/"INDEX.json",dict(schema="m6-047-g60-raw-index-v1",files=raw_refs,source_files=sources,
        raw_file_count=len(raw_refs),raw_bytes=sum(row["bytes"] for row in raw_refs),original_archives_modified=False,
        Blender=0,product=0,kernel=0,timing_runs=0))
    with (HERE/"INDEX.json").open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(dict(schema="m6-047-g60-delivery-v1",status="complete",raw_index=raw_index,source_files=sources,
            raw_file_count=len(raw_refs),raw_bytes=sum(row["bytes"] for row in raw_refs)),stream,indent=2,ensure_ascii=False)
        stream.write("\n")
    print(pin(HERE/"INDEX.json"))


if __name__=="__main__":main()
