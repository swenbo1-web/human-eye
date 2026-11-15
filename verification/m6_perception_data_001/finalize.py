"""Check fixed identities and acceptance evidence, then inventory all artifacts."""

import ast
import datetime
import hashlib
from pathlib import Path
import subprocess
import sys
import time
import zipfile
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read,write,identity
from collect_costs import collect


def main():
    started,cpu=time.perf_counter(),time.process_time()
    checks=[]
    def check(name,passed):
        checks.append(dict(name=name,passed=bool(passed)))
        if not passed:
            raise ValueError(name)
    freeze=read("PLAN_FREEZE.json")
    freeze_commit="1d690ec2540be2ea86dc80037b2125ba63792919"
    for row in freeze["files"]:
        check("frozen_"+row["path"],identity(HERE/row["path"])["sha256"]==row["sha256"])
        committed=subprocess.check_output(["git","show",freeze_commit+":verification/m6_perception_data_001/"+row["path"]],cwd=HERE.parents[1])
        check("freeze_committed_before_generation_"+row["path"],committed==(HERE/row["path"]).read_bytes())
    planner="C:/Users/Administrator/.codex/worktrees/1212/hefe"
    for source,dest in (("docs/M6_PERCEPTION_DATA_001_TASK.md","CONTRACT.md"),("docs/M6_PERCEPTION_001_REVIEW.md","PRIOR_REVIEW.md"),("verification/m6_perception_data_001_plan/PREFLIGHT.json","PLANNER_PREFLIGHT.json")):
        raw=subprocess.check_output(["git","-C",planner,"show","9191dd8df4999ead991254a5eb4100f1c9944b0b:"+source])
        check("exact_planner_contract_"+dest,raw==(HERE/dest).read_bytes())
    for path in HERE.glob("*.py"):
        ast.parse(path.read_bytes(),filename=str(path))
    check("public_sources_parse",True)
    import numpy as np
    import scipy
    import PIL
    from sampler import PairedStateSampler
    write("RUNTIME.json",dict(python=sys.version,worker_executable=str(HERE.parent/"m6_shape_train_001/private/venv/Scripts/python.exe"),
        numpy=np.__version__,scipy=scipy.__version__,Pillow=PIL.__version__,
        numerical_dependency_target=str(HERE.parent/"m6_shape_pretrain_001/private/deps"),threads=1,
        rendering_dependency_target="C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/Lib/site-packages",
        runtime_policy="read-only reuse, no installations or model imports"))
    index=read("DATASET_INDEX.json")
    for row in read("SOURCE_INDEX.json")["archives"]:
        check("archive_bytehash_"+row["path"],identity(HERE/row["path"])["sha256"]==row["sha256"])
    archives={row["path"].split("/")[-1].split("-")[0]:row for row in read("SOURCE_INDEX.json")["archives"]}
    for row in index["sources"]:
        check("source_OBJ_bytehash_"+row["id"],identity(HERE/row["obj_path"])["sha256"]==row["obj_sha256"])
        check("source_array_bytehash_"+row["id"],identity(HERE/row["array_path"])["sha256"]==row["array_sha256"])
        with zipfile.ZipFile(HERE/archives[row["asset"]]["path"]) as package:
            check("source_exact_archive_member_"+row["id"],package.read(row["member"])==(HERE/row["obj_path"]).read_bytes())
    qa,sampling,verification=read("DATA_QA.json"),read("SAMPLER_AUDIT.json"),read("SAMPLER_VERIFY.json")
    sampler=PairedStateSampler(index)
    expected={row["pair_id"]:row["probability_per_pair_event"] for row in sampling["pair_weights"]}
    check("hardened_sampler_preserves_exact_leaf_probabilities",all(expected[index["pairs"][key]["id"]]==probability for key,probability in sampler.pair_probabilities().items()))
    check("7037_numeric_checks",qa["status"]=="passed_data_engineering_QA" and qa["checks"]==7037 and not qa["failures"])
    check("24ROI96centers600observations576attempts",qa["actual"]["rois"]==24 and qa["actual"]["centers"]==96 and qa["actual"]["unique_observations"]==600 and len(index["attempts"])==576)
    check("503usable73failed_retained",qa["actual"]["usable_pairs"]==503 and qa["actual"]["failed_dents"]==73 and qa["failure_reasons"]=={"support_minimum":54,"no_face_reversal":19})
    check("all_groups_present",set(qa["usable_pairs_by_group"])=={"horse_transfer","face_transfer","cat_transfer"})
    check("sampling_exact50_50",sampling["status"]=="passed" and sampling["normal_rows"]==sampling["damaged_rows"]==614400 and sampling["validation_rows"]==0)
    check("saved_index_independent_endpoint_lineage",verification["status"]=="passed" and verification["independent_lineage_endpoint_rows_checked"]==1228800 and not verification["failures"])
    check("simulation_index_hash",identity(HERE/sampling["index"]["path"])["sha256"]==sampling["index"]["sha256"])
    current=read("CURRENT_GEOMETRY_QA.json")
    check("576current_geometry_diagnostics_zero_new_invalid_normals",len(current["cases"])==576 and not any(r["newly_unavailable_vertex_normals"] for r in current["cases"]))
    for name,key in (("SOURCE_VIEWS.json","view"),("REPRESENTATIVE_VIEWS.json","image")):
        report=read(name)
        check("12fixed_views_"+name,len(report["cases"])==12)
        for row in report["cases"]:
            check("view_identity_"+name+row["source_id"],identity(HERE/row[key]["path"])["sha256"]==row[key]["sha256"])
    costs=collect()
    original_sources={"acquire":"private/recovery/acquire_initial.py","acquire_extension_recovery":"private/recovery/acquire_extension.py","generate":"private/recovery/generate_executed.py"}
    for label,row in costs["phases"].items():
        source=original_sources.get(label,row["controller"]["phase"]+".py")
        check("executed_worker_source_"+label,identity(HERE/source)["sha256"]==row["controller"]["worker_source_sha256"])
    check("archive_bytes_budget",costs["archive_HTTP_body_bytes"]<=costs["archive_budget_bytes"])
    check("numerical_wall_budget",costs["numerical_budget_accounting_upper_s"]<1800)
    check("disk_budget",costs["new_disk_bytes_snapshot"]<2*1024**3)
    check("all_scope_prohibited_counts_zero",not any(costs[k] for k in ("training_runs","model_forwards","repair_outputs","blender_actions","product_changes","paid_calls")))
    write("COSTS.json",costs)
    write("MANUAL_VIEW_QA.json",dict(status="completed_root_visual_inspection",source_views=12,paired_views=12,
        source_direction="Positive winding arrows visibly leave nose/muzzle/hoof exterior in all selected source views. Open-patch orientation recorded before generation.",
        paired_direction="All12 fixed normal/damaged views inspected at actual scale. Change follows the negative of blue outward arrow, with depression visible where local profile resolves it.",
        fixed_failed_representative="cat_pose1_roi0_c0_r1_a2 retained as failing face-reversal example, no replacement representative",
        limitations="Raster views support direction interpretation. Numeric QA establishes actual displacements and local face reversals. Some full-length arrow labels extend beyond crop.",
        source_view_manifest=identity(HERE/"SOURCE_VIEWS.json"),paired_view_manifest=identity(HERE/"REPRESENTATIVE_VIEWS.json")))
    write("FINAL_QA.json",dict(status="passed_data_engineering_acceptance",checks=checks,check_count=len(checks),
        plan_freeze_commit=freeze_commit,wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu,
        finalization_scope="identity/AST/archive provenance and report checks, no dent generation, sampling replay, model forward or training",
        known_limitations=qa["limitations"],post_review_code_hardening="guard source sign fallback/missing ROI and sampler identities; original executed versions retained, actual data/sampling never rerun"))
    public=[identity(path) for path in sorted(HERE.iterdir()) if path.is_file() and path.name not in {"MANIFEST.json","HANDOFF.json","callback_payload.json"}]
    private=[identity(path) for path in sorted((HERE/"private").rglob("*")) if path.is_file()]
    write("MANIFEST.json",dict(cycle_id="M6-PERCEPTION-DATA-001",public_files=public,private_files=private,
        scope="all batch files at finalization, MANIFEST self and postcommit HANDOFF/callback receipt excluded",
        raw_mesh_bytes_in_git=0,private_only="archives, original OBJ/.pose bytes, parsed meshes, local current coordinates, supervision, sampling indices, view PNGs and process evidence"))
    print("final QA passed",len(checks),"public",len(public),"private",len(private),flush=True)


if __name__=="__main__":
    main()
