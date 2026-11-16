"""Saved-only three-scope geometry, camera and outcome qualification.

No product imports or execution. Full pixel/source-buffer checks are separately
owned by checks/saved_frames.py. This file verifies their pins and independently
binds current raw/captured geometry to the frozen fixture and exact oracle.
"""
from __future__ import annotations

import argparse
from fractions import Fraction as F
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
spec = importlib.util.spec_from_file_location("_global_local_exact_oracle", HERE / "static_oracle.py")
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
LABELS = ("global","local_open","local_covered")
PRODUCT = "7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


class Audit:
    def __init__(self):
        self.pins = {}
        self.checks = []

    def file(self,path,expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected is not None and expected!=digest:
            raise ValueError("input_sha256_changed/"+str(path))
        self.pins[str(path)] = dict(path=str(path),sha256=digest,bytes=len(raw))
        return raw

    def read(self,path,expected=None):
        return json.loads(self.file(path,expected))

    def require(self,condition,name):
        if not condition:
            raise ValueError(name)
        self.checks.append(dict(check=name,passed=True))


def interval_contains(interval,value):
    value = F(value)
    return interval.lo<=value<=interval.hi


def ordered_geometry(vertices,faces):
    preimage = dict(vertices=[[str(F(x)) for x in p] for p in vertices],triangles=faces)
    return fingerprint(preimage)


def prove_open_view_unobstructed(view_name,fixture,target_name):
    """Exclude all positive rays from the whole target against other AABBs.

    The interval in t admits every ray origin in the target rectangle's AABB.
    An empty intersection proves no original triangle can block that view.
    """
    target = next(row for row in fixture if row["name"]==target_name)
    direction = oracle.VIEWS[view_name]
    low = [min(p[a] for p in target["vertices"]) for a in range(3)]
    high = [max(p[a] for p in target["vertices"]) for a in range(3)]
    exclusions = []
    for obj in fixture:
        if obj["name"]==target_name:
            continue
        interval_low,interval_high = F(0),None
        separation = None
        for axis,d in enumerate(direction):
            obj_low = min(p[axis] for p in obj["vertices"])
            obj_high = max(p[axis] for p in obj["vertices"])
            if d==0:
                if obj_high<low[axis] or obj_low>high[axis]:
                    separation = dict(axis=axis,reason="parallel_strictly_separated")
                    break
            else:
                endpoints = ((obj_low-high[axis])/d,(obj_high-low[axis])/d)
                t_low,t_high = min(endpoints),max(endpoints)
                interval_low = max(interval_low,t_low)
                interval_high = t_high if interval_high is None else min(interval_high,t_high)
                if interval_high<interval_low or interval_high<=0:
                    separation = dict(axis=axis,reason="no_common_positive_ray_parameter",t_lower=interval_low,t_upper=interval_high)
                    break
        if separation is None:
            raise ValueError("open_witness_view_not_proven_unobstructed/"+view_name+"/"+obj["name"])
        exclusions.append(dict(object_name=obj["name"],**separation))
    return dict(view_name=view_name,target_object_name=target_name,whole_rectangle_unobstructed=True,
                method="exact positive-ray parameter interval exclusion against all other object AABBs",exclusions=exclusions)


def camera_review(label,cameras,fixture,selected,audit):
    all_vertices = [p for obj in fixture for p in obj["vertices"]]
    target_vertices = all_vertices if label=="global" else selected["vertices"]
    center = tuple((min(p[a] for p in target_vertices)+max(p[a] for p in target_vertices))/2 for a in range(3))
    audit.require([view["name"] for view in cameras["views"]]==list(oracle.VIEWS),"fixed_six_view_order/"+label)
    audit.require(tuple(map(F,cameras["common_center_world_m"]))==center,"actual_fitted_center/"+label)
    rows = []
    for pose in cameras["views"]:
        name = pose["name"]
        direction = oracle.VIEWS[name]
        audit.require(pose["direction_rational"]==list(direction),"actual_direction/"+label+"/"+name)
        view,projection = pose["view_matrix"],pose["projection_matrix"]
        audit.require(view[3]==[0,0,0,1] and projection[3]==[0,0,0,1]
                      and projection[0][1:]==[0,0,0] and [projection[1][i] for i in (0,2,3)]==[0,0,0]
                      and projection[0][0]==projection[1][1]>0,"actual_orthographic_XY/"+label+"/"+name)
        if label=="global":
            expected = oracle.camera_intervals(all_vertices,direction,center)
        else:
            d = oracle.inormalize(tuple(oracle.Interval(x) for x in direction))
            seed = tuple(oracle.Interval(x) for x in ((0,1,0) if name=="TOP" else (0,0,1)))
            right = oracle.inormalize(oracle.icross(tuple(-x for x in d),seed))
            up = oracle.icross(right,tuple(-x for x in d))
            relative = [tuple(oracle.Interval(x)-oracle.Interval(c) for x,c in zip(p,center)) for p in target_vertices]
            half_unpadded = oracle.imax([oracle.idot(p,axis).abs() for p in relative for axis in (right,up)])
            half_span = half_unpadded*oracle.Interval(F.from_float(1.1))
            eye = tuple(oracle.Interval(x) for x in pose["eye"])
            translations = tuple(-oracle.idot(axis,eye) for axis in (right,up))
            expected = dict(right=right,up=up,translation=translations,scale=oracle.Interval(1)/half_span,half_span=half_span)
        audit.require(all(interval_contains(expected[key][axis],view[row][axis])
                          for row,key in enumerate(("right","up")) for axis in range(3)),
                      "published_XY_basis_inside_independent_rounding_intervals/"+label+"/"+name)
        audit.require(all(interval_contains(expected["translation"][axis],view[axis][3]) for axis in (0,1)),
                      "published_XY_translation_inside_independent_rounding_intervals/"+label+"/"+name)
        audit.require(interval_contains(expected["half_span"],pose["half_span_m"])
                      and interval_contains(expected["scale"],projection[0][0]),
                      "published_fit_scale_inside_independent_rounding_intervals/"+label+"/"+name)
        depths = []
        for point in all_vertices:
            camera_z = sum(F(view[2][i])*point[i] for i in range(3))+F(view[2][3])
            ndc_z = F(projection[2][2])*camera_z+F(projection[2][3])
            depths.append(-camera_z)
            audit.require(-camera_z>0 and -1<=ndc_z<=1,"all_scene_source_inside_positive_camera_depth/"+label+"/"+name)
        rows.append(dict(view_name=name,view_matrix=view,projection_matrix=projection,
                         actual_half_span_m=pose["half_span_m"],independent_half_span_interval_m=expected["half_span"].pair(),
                         all_scene_depth_range_m=[min(depths),max(depths)]))
    return rows


def check_session(label,runtime,static,fixture,asset,requests,audit):
    session = runtime/"sessions"/label
    result = audit.read(session/"SLOT_RESULT.json")
    publication = audit.read(session/"SLOT_PUBLICATION.json")
    audit.require(result["label"]==label and result["status"]=="completed" and result["errors"]==[],"original_completed_without_errors/"+label)
    audit.require(publication["label"]==label and publication["status"]=="completed" and publication["owned_budget_passed"] is True
                  and publication["result_sha256"]==oracle.pin(session/"SLOT_RESULT.json")["sha256"],"published_original_result/"+label)
    audit.require(result["model_consumers"]==0 and result["paid_API_calls"]==0 and result["public_requests_attempted"]==1,"zero_consumer_one_public_request/"+label)
    audit.require(result["request_arguments"]==requests[label],"fixed_public_arguments/"+label)
    audit.require(result["source"]["asset_sha256"]==asset["asset_sha256"] and result["source"]["product_sha256"]==PRODUCT,"accepted_asset_and_product/"+label)
    clocks = result["clocks"]
    audit.require(clocks["public_started_ns"]<clocks["public_returned_ns"]<clocks["public_deadline_ns"]
                  and clocks["public_deadline_ns"]<=clocks["owned_deadline_ns"]
                  and clocks["public_deadline_ns"]-clocks["public_started_ns"]<=30_000_000_000
                  and clocks["owned_deadline_ns"]-clocks["slot_started_ns"]==600_000_000_000,"original_request_and_owned_deadlines/"+label)
    frames = audit.read(NS/"checks"/(label+"_FRAMES.json"))
    audit.require(frames["passed_checked_scope"] is True and Path(frames["session"]).resolve()==session.resolve(),"independent_frame_checker_current_slot/"+label)
    for item in frames["input_pins"]:
        audit.file(item["path"],item["sha256"])
    capture = frames["current_capture"]
    evidence = audit.read(session/"SAVED_EVIDENCE.json")
    audit.require(evidence["asset_sha256"]==asset["asset_sha256"] and evidence["product_source_sha256"]==PRODUCT
                  and len(evidence["sources"])==1,"one_fresh_current_raw_scene/"+label)
    source_entry = evidence["sources"][0]
    raw = audit.read(source_entry["path"],source_entry["sha256"])
    audit.require(raw["source"]["asset_sha256"]==asset["asset_sha256"] and raw["source"]["frame"]==1
                  and raw["source"]["subframe"]==0 and raw["source"]["scale_length"]==1,"current_raw_frame_units/"+label)
    fixture_by_name = {obj["name"]:obj for obj in fixture}
    raw_by_name = {obj["name"]:obj for obj in raw["objects"]}
    audit.require(len(raw_by_name)==len(raw["objects"])==9 and set(raw_by_name)==set(fixture_by_name),"raw_whole_scene_nine_objects/"+label)
    for name,expected in fixture_by_name.items():
        actual = raw_by_name[name]
        audit.require([oracle.rational_vector(p) for p in actual["vertices"]]==expected["vertices"]
                      and [tuple(face) for face in actual["triangles"]]==expected["triangles"],"current_raw_matches_frozen_point_and_face_order/"+label+"/"+name)
    full = audit.read(session/"product_full/call_001/SERVICE_RESULT.json")
    response = audit.read(session/"product_calls/call_001/RESPONSE.json")
    texts = [json.loads(block["text"]) for block in response["result"]["content"] if block["type"]=="text"]
    audit.require(response["result"]["isError"] is False and len(texts)==1 and texts[0]["facts"]==full["facts"],"actual_public_full_facts_delivered/"+label)
    binding = full["binding"]
    audit.require(binding["capture_state"]==capture["capture_state"] and binding["document_epoch"]==capture["host_identity"]["document_epoch"],"own_capture_epoch_and_generation/"+label)
    correspondence = []
    for index,mesh in enumerate(capture["meshes"]):
        name = mesh["name"]
        expected,raw_object = fixture_by_name[name],raw_by_name[name]
        audit.require([oracle.rational_vector(p) for p in mesh["vertices"]]==expected["vertices"]
                      and [tuple(face) for face in mesh["faces"]]==expected["triangles"],"actual_capture_matches_frozen_point_and_face_order/"+label+"/"+name)
        host = binding["objects"][index]
        audit.require(host["object_index"]==index and host["object_name"]==name and host["host_id"]==mesh["object_id"]==raw_object["object_id"]
                      and str(host["instance_id"])==str(raw_object["instance_id"]),"own_raw_capture_host_instance_mapping/"+label+"/"+name)
        correspondence.append(dict(asset_sha256=asset["asset_sha256"],object_name=name,document_epoch=binding["document_epoch"],
            host_id=host["host_id"],instance_id=host["instance_id"],object_index=index,
            source_triangle_indices=list(range(len(mesh["faces"]))),
            independent_ordered_geometry_sha256=ordered_geometry(mesh["vertices"],mesh["faces"])))
    audit.require(len({row["object_name"] for row in correspondence})==len(correspondence),"unique_current_capture_names/"+label)
    if label=="global":
        audit.require(binding["capture_scope"]=="complete_scene_meshes" and len(correspondence)==9 and "observation_target" not in capture,"true_global_capture_without_target/"+label)
        selected = None
        expected_components = [row for row in static["components"] if row["rectangle_supported"]]
    else:
        name = "Obj_02" if label=="local_open" else "Obj_06"
        selected = fixture_by_name[name]
        target = capture["observation_target"]
        audit.require(binding["capture_scope"]=="target_observation_meshes" and target["selector"]=={"name":name}
                      and capture["meshes"][target["target_object_index"]]["name"]==name,"true_local_target_scope/"+label)
        expected_components = [row for row in static["components"] if row["object_name"]==name and row["rectangle_supported"]]
    cameras = camera_review(label,binding["camera_specification"],fixture,selected,audit)
    support = full["facts"]["scope"]["patch_support"]
    region_mappings = support["regions"]
    facts = {row["roi_id"]:row for row in full["facts"]["regions"]}
    audit.require(len(facts)==len(full["facts"]["regions"])==len(region_mappings)==len(expected_components),"complete_supported_region_denominator/"+label)
    actual_components = {}
    for row in region_mappings:
        name = capture["meshes"][row["object_index"]]["name"]
        key = (name,tuple(sorted(row["triangle_indices"])))
        audit.require(key not in actual_components,"no_duplicate_source_region/"+label)
        actual_components[key] = row["roi_id"]
    expected_keys = {(row["object_name"],tuple(row["source_triangle_indices"])) for row in expected_components}
    audit.require(set(actual_components)==expected_keys,"independent_maximal_rectangle_partition/"+label)
    by_expected = {(row["object_name"],tuple(row["source_triangle_indices"])):row for row in expected_components}
    for key,roi in actual_components.items():
        expected,fact = by_expected[key],facts[roi]
        audit.require(tuple(map(F,fact["center_world_m"]))==tuple(expected["center_world_m"]),"exact_region_center/"+label+"/"+roi)
        normal = oracle.inormalize(tuple(oracle.Interval(x) for x in expected["plane_normal_integer"]))
        audit.require(all(interval_contains(axis,value) for axis,value in zip(normal,fact["front_direction_world"])),"oriented_unit_normal_rounding_enclosure/"+label+"/"+roi)
        center,u,v = [tuple(map(F,fact[field])) for field in ("center_world_m","half_edge_u_world_m","half_edge_v_world_m")]
        actual_corners = {tuple(c+su*a+sv*b for c,a,b in zip(center,u,v)) for su,sv in itertools.product((-1,1),repeat=2)}
        expected_corners = {fixture_by_name[key[0]]["vertices"][i] for i in expected["boundary_loops"][0]}
        audit.require(actual_corners==expected_corners,"actual_region_geometry_matches_source_corners/"+label+"/"+roi)
    evidence_rows = {row["roi_id"]:row for row in full["facts"]["region_evidence"]}
    covered_ids = full["facts"]["coverage"]["covered_roi_ids"]
    outcome_rows = []
    for expected in static["eligible"]:
        key = (expected["object_name"],tuple(expected["source_triangle_indices"]))
        if key not in actual_components:
            continue
        roi = actual_components[key]
        fact,evidence_row = facts[roi],evidence_rows[roi]
        if label=="local_open":
            audit.require(fact["status"]=="covered" and fact["reason"]=="observed_readable" and roi in covered_ids
                          and evidence_row["complete_witness"] is not None,"local_open_actual_complete_readable_witness")
            witness = evidence_row["complete_witness"]
            view_name = witness["view_name"]
            frame = next(row for row in full["facts"]["observations"] if row["view_name"]==view_name)
            pixel = frame["pixel_rows"][witness["pixel_row_index"]]
            audit.require(pixel["roi_id"]==roi and pixel["readable"] is True and pixel["visible_surface_pixels"]>=16
                          and pixel["contrasting_boundary_pixels"]>=4,"local_witness_actual_pixel_row_and_source")
            geometric_proof = prove_open_view_unobstructed(view_name,fixture,"Obj_02")
        else:
            reason = "positive_area_occlusion_all_front_views" if expected["object_name"]=="Obj_06" else "pixel_evidence_insufficient"
            public_reason = "finite_camera_pool_uncovered" if expected["object_name"]=="Obj_06" else reason
            audit.require(fact["status"]=="unknown" and fact["reason"]==public_reason and evidence_row["unobserved_reason"]==reason
                          and evidence_row["complete_witness"] is None and roi not in covered_ids,"honest_unknown_without_witness/"+label+"/"+roi)
            witness = None
            geometric_proof = "static exact six-direction strict cover proof" if expected["object_name"]=="Obj_06" else "static six-view pixel upper bound plus actual constructed-view pixels"
        outcome_rows.append(dict(object_name=expected["object_name"],source_triangle_indices=expected["source_triangle_indices"],roi_id=roi,
                                 status=fact["status"],reason=fact["reason"],unobserved_reason=evidence_row["unobserved_reason"],
                                 complete_witness=witness,independent_proof=geometric_proof))
    if label=="global":
        audit.require(len(outcome_rows)==3,"global_all_three_task_targets_accounted")
        unsupported_rows = [row for obj in support["objects"] for row in obj["unsupported_components"]]
        actual_unsupported = {(capture["meshes"][obj["object_index"]]["name"],tuple(sorted(row["triangle_indices"])))
                              for obj in support["objects"] for row in obj["unsupported_components"]}
        expected_unsupported = {(row["object_name"],tuple(row["source_triangle_indices"])) for row in static["unsupported"]}
        audit.require(actual_unsupported==expected_unsupported and sum(len(row["triangle_indices"]) for row in unsupported_rows)==12,"ring_and_L_remain_unknown_source_denominator")
        for frame in frames["frames"]:
            for pixel in frame["pixels"]:
                if pixel["roi_id"] in {row["roi_id"] for row in outcome_rows}:
                    audit.require(pixel["surface_pixels"]<=2 and not pixel["readable"],"actual_global_small_surface_respects_static_bound")
    return dict(label=label,passed_checked_scope=True,capture_scope=binding["capture_scope"],
                document_epoch=binding["document_epoch"],capture_state=binding["capture_state"],binding_sha256=binding["binding_sha256"],
                source_binding_sha256=binding["source_binding_sha256"],source_correspondence=correspondence,cameras=cameras,
                outcomes=outcome_rows,rendered_views=frames["rendered_views"],unrendered_views=frames["unrendered_views"],
                frame_report_pin=oracle.pin(NS/"checks"/(label+"_FRAMES.json")),
                product_parent_child_binding_claim=False)


def evaluate(runtime):
    audit = Audit()
    audit.file(__file__)
    audit.file(HERE/"static_oracle.py")
    static = audit.read(HERE/"STATIC_QUALIFICATION.json")
    audit.read(HERE/"EXPECTATIONS.json")
    geometry = audit.read(NS/"fixture/GEOMETRY.json")
    fixture = oracle.read_objects(geometry)
    asset = audit.read(NS/"fixture/ASSET_BINDING.json")
    requests = audit.read(NS/"REQUESTS.json")
    audit.require(static["passed"] is True and static["status"]=="qualified","static_qualification_precedes_actual")
    for item in static["input_pins"]:
        audit.file(item["path"],item["sha256"])
    audit.file(asset["asset_path"],asset["asset_sha256"])
    records = []
    for label in LABELS:
        try:
            records.append(check_session(label,runtime,static,fixture,asset,requests,audit))
        except Exception as error:
            records.append(dict(label=label,passed_checked_scope=False,error=dict(type=type(error).__name__,message=str(error))))
    passed = all(row["passed_checked_scope"] for row in records)
    return dict(schema="global-local-saved-independent-qualification-v1",passed_checked_scope=passed,passed=passed,
                status="qualified" if passed else "not_realized",denominator=3,qualified_count=sum(row["passed_checked_scope"] for row in records),
                records=records,check_count=len(audit.checks),checks=audit.checks,input_pins=list(audit.pins.values()),
                source_correspondence_basis="Same fixed asset SHA and independently verified actual evaluated ordered geometry. Fresh-host compound identities and per-scope cameras/indexes remain distinct.",
                source_face_contract="current per-object evaluated capture triangle rows",product_parent_child_binding_claim=False,
                new_operations=dict(Blender=0,MCP=0,raster=0,model=0,paid_API=0))


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime",type=Path,default=Path("D:/he_m4_global_local_001"))
    parser.add_argument("--output",type=Path,default=NS/"QUALIFICATION.json")
    args = parser.parse_args()
    result = evaluate(args.runtime)
    with args.output.open("x",encoding="utf-8") as stream:
        json.dump(oracle.rational_json(result),stream,ensure_ascii=False,indent=2)
        stream.write("\n")
    print(json.dumps(dict(passed=result["passed"],qualified_count=result["qualified_count"],denominator=3,
                          output=str(args.output),sha256=oracle.pin(args.output)["sha256"])))
