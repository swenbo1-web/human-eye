"""Freeze the actual archive metadata, immutable lineage split and selector rules."""

import datetime
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import read, write, identity


def main():
    if (HERE / "PLAN.json").exists():
        raise RuntimeError("plan_already_exists")
    acquisition = read("ACQUISITION.json")
    assert len(acquisition["archives"]) == 6 and len(acquisition["selected"]) == 12 and not acquisition["errors"]
    assert len({row["sha256"] for row in acquisition["documents"]}) == 1
    groups = {"horse": "horse_transfer", "camel": "horse_transfer", "face": "face_transfer",
              "head": "face_transfer", "cat": "cat_transfer", "lion": "cat_transfer"}
    selected = []
    for row in acquisition["selected"]:
        selected.append(dict(row, group=groups[row["asset"]], split="validation" if groups[row["asset"]] == "cat_transfer" else "development"))
    write("SOURCE_INDEX.json", dict(cycle_id="M6-PERCEPTION-DATA-001", primary_page=acquisition["source_page"],
                                    archives=acquisition["archives"], documents=acquisition["documents"], meshes=selected,
                                    actual_metadata_selection="one -reference OBJ-syntax file (.pose accepted), first other natural-sorted pose filename, no geometry-based reselection",
                                    package_terms_review=dict(status="read_all_six_identical_READMEs_and_mesh_comment_headers",
                                        additional_restriction_conflict=False, attribution="Robert W. Sumner and Jovan Popovic, MIT Computer Graphics Group, Deformation Transfer for Triangle Meshes, TOG 23(3), 2004",
                                        caveat_discrepancy="README calls pierced camel genus three, current web page genus two, both original texts retained, topology measured independently",
                                        permission_scope="public research access with attribution, commercial/redistribution permission unestablished, local private meshes only"),
                                    pretraining_overlap="unknown", independent_final_test=False))
    write("SPLIT.json", dict(development_groups=["horse_transfer", "face_transfer"], validation_groups=["cat_transfer"],
                            mesh_membership=[dict(id=row["id"], mesh_id=row["asset"], group=row["group"], split=row["split"]) for row in selected],
                            known_derived_groups=3, mesh_identities=6, posture_observations=12, research_collections=1,
                            excluded="flamingo, elephant, gallop, collapse, all other sources, historical Armadillo and untouched Bunny",
                            limitations=["No independent final test", "head and face coverage only for human geometry", "Pointfilter pretraining overlap unknown"]))
    cases = []
    for view in read("SOURCE_VIEWS.json")["cases"]:
        cases.append(dict(view, outward_sign=1, evidence_type="visual_source_orientation",
                          observed="Positive source winding normal leaves the visible nose/muzzle or extended hoof outer surface in orthographic views. Negative normal points into the represented external surface.",
                          scope="only the inspected largest consistent face patch, propagation across opposite-wound two-face edges, other patches unknown",
                          reviewer="root visual inspection of actual triangle renders before generation"))
    write("ORIENTATION_SOURCE.json", dict(cases=cases, closed_components="use centered signed volume with recorded roundoff tolerance",
                                         open_components="source winding plus recorded external-surface visual anchor, no closed-volume claim",
                                         raw_vn="agreement and opposite corners recorded, displacement uses geometric area normal, source vn is not an inside/outside proof",
                                         limitations=["self-intersection not globally certified", "visual source orientation is interpretive geometric evidence"]))
    write("PLAN.json", dict(cycle_id="M6-PERCEPTION-DATA-001", frozen_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            contract_commit="9191dd8df4999ead991254a5eb4100f1c9944b0b", baseline_commit="38fa3e2d01300498aabd43a051876a6f779dab68", seed=1729,
                            roi=dict(target_vertices=384, per_posture=2,
                                selection="source order in SOURCE_INDEX, one global PCG64 seed1729. First seed drawn by lumped triangle area on eligible vertices. Nearest384 via eligible induced edge-length Dijkstra, (distance, sourceID) ordering. ROI1 seed maximizes distance to ROI0, disconnected eligible vertex lowestID has priority. Remove ROI0 from graph and candidate set. Shortfall retained, no extra seeds.",
                                eligible="finite coordinates, all incident triangles crossnorm>64eps*bboxdiag^2, finite nonzero area-weighted geometric normal",
                                shortfall="save actual count, ROI unusable unless exactly384", overlaps="second ROI always excludes first, disconnected coverage prioritized"),
                            centers=dict(per_roi=4, boundary="F vertices adjacent to outside F plus source boundary/nonmanifold edge endpoints in F",
                                interior="full source edge-geodesic D to boundary, finite D>64eps*bboxdiag and D>=0.5maxD",
                                selection="first maxD then geodesic farthest-point among remaining candidates, ties lower sourceID, stop if none or separation<=length tolerance, no filling"),
                            matrix=dict(radius_over_D=[.35,.55], depth_over_radius=[.05,.15,.30], displacement="-a*(1-(d_G/r)^2)^2*n_center_undamaged_outward for d_G<r, zero outside",
                                loop_order="source, ROI, center, radius, depth", minimum_true_support=6, maximum_roi=24, maximum_centers=96, maximum_dents=576, maximum_unique_observations=600),
                            validity=dict(pair="same source/topology/sourcepoint mapping, current geometry reconstructed exactly, outside true changed domain bitwise identical, labels from actual coordinate delta",
                                geometry="finite, no new crossnorm<=64eps*bboxdiag^2, no original nondegenerate face with cross_new dot cross_old<=0, support>=6 and wholly inside F",
                                direction="all affected incident faces inside confirmed consistent patch or reliable closed component, remaining unknown excluded from dent training",
                                usable_roi="exact384 points and at least2 distinct centers each with>=1 numerically valid and direction-confirmed combination. All otherwise valid combos of that ROI are sampling members, failures remain indexed",
                                scope="local reversal is cross dot original, global self-intersection unverified"),
                            sampling=dict(seed=1729, steps=1200, rows_per_step=1024, pair_events_per_step=512,
                                hierarchy=["development_group", "mesh", "pose", "usable_ROI", "usable_damaged_combination", "uniform_F_row"],
                                state="emit normal and damaged row for each pair event, randint(2) swaps within pair, no additional shuffle, exact512/512 each step",
                                expected="normal physical observation probability=P(ROI)/2, each dent=P(ROI)/(2*usable_combo_count). Positive-label fraction recorded independently, normalization and pos_weight deferred"),
                            audit=dict(natural_concavity="mean neighbor offset dot outward normal, signed threshold64eps*bboxdiag, report concave/convex/flat incidence and per-point damage frequency. Synthetic normal labels remain zero",
                                encoder_radius="0.05*undamaged posture bboxdiag, record r/R and a/R plus true damaged fraction among Euclidean vertices within R of center, no model forwards",
                                representative="first ROI/first center/.55 radius/.30 depth in every selected posture, retained whether valid or failing, normal/damaged local geometry and arrows"),
                            input_contract="return only full current vertices, source topology, F mapping and source IDs. Source baseline used internally for compact reconstruction, reference/delta/mask files belong to separate supervision domain",
                            budgets=dict(archive_http_bytes=256*1024**2, new_disk_bytes=2*1024**3, numerical_compute_wall_s=1800, threads=1),
                            prohibited_counts=dict(training=0, model_forwards=0, repair_outputs=0, blender_changes=0, product_changes=0, paid_calls=0),
                            continuation="fixed result commit, one callback then end awaiting independent review"))
    files = ["PLAN.json", "SOURCE_INDEX.json", "SPLIT.json", "ORIENTATION_SOURCE.json", "SOURCE_GEOMETRY.json", "SOURCE_VIEWS.json", "geometry.py", "common.py", "CONTRACT.md", "PRIOR_REVIEW.md", "PLANNER_PREFLIGHT.json"]
    write("PLAN_FREEZE.json", dict(files=[identity(HERE / name) for name in files], actual_source_inputs=[identity(HERE / row["array_path"]) for row in selected]))
    print("frozen metadata and rules before any ROI/dent generation", flush=True)


if __name__ == "__main__":
    main()
