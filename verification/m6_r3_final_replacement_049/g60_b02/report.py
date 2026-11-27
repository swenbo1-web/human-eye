"""Seal the finished 049 G60/B02 receipts after the offline audit."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT/g60_b02")


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest)


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return pin(path)


def main():
    plan = read(RAW / "PLAN.json")
    release = read(RAW / "RELEASE.json")
    assert release["status"] == "released" and not release["remaining_owned"]
    audits = {family: read(RAW / family / "AUDIT.json") for family in ("G60", "B02")}
    assert all(a["status"] == "pass" for a in audits.values())
    old045 = read(RAW / "old045/AUDIT.json")
    assert old045["status"] == "pass"
    raw_results = {"G60": RAW / "G60/resume_001/RESULTS.json", "B02": RAW / "B02/main_001/RESULTS.json"}
    families = {}
    for family, audit in audits.items():
        measured = read(raw_results[family])
        arms = "ABF" if family == "G60" else "AF"
        phases, resources, paths = {}, {}, {}
        for arm in arms:
            cells = [group["cells"][arm] for group in audit["groups"]]
            phases[arm] = {}
            names = set.intersection(*(set(c["lifecycle"]["phases"]) for c in cells))
            for name in sorted(names):
                values = [c["lifecycle"]["phases"][name] for c in cells]
                phases[arm][name] = dict(values=values, median=median(v for v in values if v is not None) if any(v is not None for v in values) else None)
            cpu = [c["lifecycle"]["CPU_total_100ns"]/1e7 for c in cells]
            resources[arm] = dict(process_lifetime_CPU_s=cpu, median_CPU_s=median(cpu),
                original_process_boundary_samples=[dict(before=c["product_before"], after=c["product_after"]) for c in cells],
                interpretation="CPU uses unique held process generations. Memory is original per-interpreter boundary/peak-working-set samples; no simultaneous process-tree peak is inferred.")
            paths[arm] = {}
            for group in audit["groups"]:
                for step, row in group["cells"][arm]["steps"].items():
                    if row["work"] is None:
                        continue
                    for route, count in row["work"]["solver_paths"].items():
                        paths[arm][route] = paths[arm].get(route, 0)+count
        families[family] = dict(results=pin(raw_results[family]), audit=pin(RAW / family / "AUDIT.json"),
            hosts=6, services=audit["actual_services"], business_replies=audit["actual_business_reads"],
            business=measured["business"], actual_OS_lifetime=measured["process_lifetime"],
            client_full=measured["client_full"], lifecycle_phase_descriptive=phases, resources=resources,
            actually_recorded_solver_path_counts=paths,
            GUI_lifecycle_ns=[r["full_GUI_ns"] for r in audit["groups"]],
            GUI_CPU_business_envelope_s=[r["GUI_CPU_business_envelope_s"] for r in audit["groups"]],
            geometry_and_public_parity=True, actual_after_capture_status=[r["after_snapshot_status"] for r in audit["groups"]])
    summary = dict(schema="m6-049-G60-B02-final-summary-v1", status="complete_audited", plan=pin(RAW / "PLAN.json"),
        final_pins=plan["final_pins"], preflight=pin(RAW / "preflight_001/RESULTS.json"), release=pin(RAW / "RELEASE.json"),
        family=families, old045_lifecycle_reverification=pin(RAW / "old045/AUDIT.json"),
        counts=dict(owned_GUI_hosts=12, installed_services=30, business_replies=78, geometry_repeated_or_replaced=0),
        recovery=dict(original_G01=pin(RAW / "G60/main_001/G01-ABF/GROUP.json"),
            original_incomplete_result=pin(RAW / "G60/main_001/RESULTS.json"),
            freeze=pin(RAW / "G60/resume_001/RECOVERY_FREEZE.json"),
            supplemental=pin(RAW / "G60/resume_001/G01_REQUALIFIED.json"),
            cause="Only validated overview runtime manifest source_file_count 143 vs145; public geometry had no difference",
            qualification="Original G01 business and OS records retained without rerun. All later frozen slots entered once.",
            unresolved_evidence_gap="G01 RAM-after snapshot was not acquired because comparison failed before its capture; no substitute was created. Its before source, read-only business, normal GUI close and unchanged source/copy/addon hashes remain available."),
        limitations=["Normal installed stdio with unchanged Hook condition, no automatic host Hook dispatch claim.",
            "G60 first overview write through scan decode and B02 nearest write through scan decode are contiguous business windows.",
            "OS lifetime uses Windows creation/actual exit for wrapper and interpreter, distinct from reader/EOF/archive/client cleanup.",
            "Phase medians are not added. GUI envelopes include QA and are not the primary business window.",
            "Only actual solver_path fields count as observed routes; absent baseline path fields are not retroactively inferred.",
            "G01 missing RAM-after remains an evidence limitation; it is not silently called a complete before/after observation."],
        new_model_calls=0, product_source_changes=0, summary_source=pin(__file__))
    summary_ref = save(RAW / "SUMMARY.json", summary)
    save(HERE / "SUMMARY.json", summary)
    g, b = families["G60"], families["B02"]
    text = f"""# 049 G60 and B02 ordinary entry\n\nThe one final F installation was measured against the fixed 041 installations: A=032, B=original R3. Six G60 groups use ABF, AFB, BAF, BFA, FAB, FBA; six B02 groups use AF, FA three times each. The run created 12 independent ordinary hidden Blender GUIs, 30 fresh installed services, and 78 complete business replies. No Hook registration, model, candidate revision or public product patch was added.\n\nG60 preserves the original overview → Target nearest → 5mm scan chain. F's paired median business saving against A is {g['business']['pairs']['F_vs_A']['median_saving']*100:.4f}% (6/6 faster), with {g['business']['pairs']['F_vs_B']['median_relative_increase']*100:+.4f}% against original R3. The G60 business gate passes. Actual OS process survival saves {g['actual_OS_lifetime']['pairs']['F_vs_A']['median_saving']*100:.4f}% against A and changes {g['actual_OS_lifetime']['pairs']['F_vs_B']['median_relative_increase']*100:+.4f}% against B; its gate also passes. These are paired ratios, not ratios of the marginal medians.\n\nB02 uses the original unrotated 24-piece assembly, Obj_014 nearest → 2mm scan, with the original 041 requests and independent nearest/276-pair scan answers. F's paired median business change against A is {b['business']['pairs']['F_vs_A']['median_relative_increase']*100:+.4f}% (6/6 faster), passing the frozen maximum +5% gate. OS survival changes {b['actual_OS_lifetime']['pairs']['F_vs_A']['median_relative_increase']*100:+.4f}%. All public geometry, rounded points/directions where originally published, nearest order and scan coverage match the frozen historical answers and same-host peers.\n\nEvery successful cell retains original TX/RX, initialize/catalog identity, request traces/work and Windows process handles. The client records first write through final complete business decode separately from installed-service creation, actual wrapper/interpreter exit, reader join, wire archive and full client cleanup. Per-process CPU and observed memory samples remain in SUMMARY/AUDIT; no process-tree simultaneous peak is claimed. Original 045 receipts were independently re-audited offline with the unchanged original verifier.\n\nOne engineering recovery is explicit. G01 completed all three valid business and OS records, then the old full-body comparison rejected solely `overview.runtime_identity.source_file_count` (143 versus F's validated 145). The original failed GROUP and RESULTS remain untouched. A supplemental requalification normalizes only that verified metadata and retains G01; G02–G06 then ran once in the frozen order. G01's RAM-after snapshot was not acquired before closure and remains unmeasured. Its exact before source, read-only queries, EOF/GUI closure and unchanged disk source/copy/add-on evidence remain. No AFTER snapshot or replacement sample was invented.\n\nEntry files: `PLAN.json`, `preflight_001/RESULTS.json`, `G60/resume_001/RESULTS.json`, `B02/main_001/RESULTS.json`, both `AUDIT.json` files, `old045/AUDIT.json`, `RELEASE.json`, `SUMMARY.json`, and `INDEX.json`. The release receipt independently found no remaining owned Blender or Python process after all close receipts.\n\nSummary SHA: `{summary_ref['sha256']}`. Final F source SHA: `{plan['arms']['F']['source_sha256']}`. The scoped `run.py` and `client.py` never modify the measured installation; the original 045 Windows helper is byte-identical. `SOURCE_CUSTODY.json` documents the two client guard/count adaptations and the two-versus-three-business wire count in the offline audit.\n"""
    for path in (HERE / "README.md", RAW / "README.md"):
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    # Check every frozen input again before sealing. Runtime source and original archives remain untouched.
    for ref in (*plan["sources"].values(), *plan["support"].values(), plan["final_pins"]):
        assert pin(ref["path"]) == ref, ref["path"]
    refs = [pin(p) for p in sorted(RAW.rglob("*")) if p.is_file()]
    sources = [pin(p) for p in sorted(HERE.iterdir()) if p.is_file()]
    index = dict(schema="m6-049-G60-B02-index-v1", status="sealed", created_utc=datetime.now(timezone.utc).isoformat(),
        raw_root=str(RAW), raw_files=refs, stage_files=sources, self_excluded=True,
        summary=summary_ref, no_writes_after_seal=True)
    print(save(RAW / "INDEX.json", index))
    print(save(HERE / "INDEX.json", index))


if __name__ == "__main__":
    main()
