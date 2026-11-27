"""048 bind the old closed-family arrays/oracle/public receipts, without a solver."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct

HERE=Path(__file__).resolve().parent
VER=HERE.parents[1]
RAW=Path("D:/HumanEye/runs/M6-048-R3-WITNESS-PARITY/closed_archive")
OLD=RAW.parent.parent/"M6-044-R3-FRESH-BUDGET"
NAMES=("Object_01","Object_02")
SOURCES={"A":"a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d",
         "C":"b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e"}
FIXED={"oracle/GEOMETRY.json":"c7a9d2962fd4d44564cbd6b7da9cff5d2bca63012bf9904942b7d4c791ce4448",
       "oracle/TRUTH.json":"cbe74dc227148cc60fd04c95e0f8adc221a053b6b6e005be148990e4cd78b97f",
       "oracle/INPUTS.json":"d00bcaedecc3783e7f2a7f5c6653fe2dea39ad12c4007451144e8b41eeb10d7a",
       "live_family/PLAN_02.json":"d606250a593d0940658e412ba65f6e0029895cbdba5299563d9fa403416d7abb",
       "live_family/attempt_002/RESULTS.json":"ef098918421965d962e8a34af3e4be80b9a69697ead1cbbd2536e1864d18431e",
       "live_family/attempt_002/BEFORE.json":"03f144cb84355712a3a3337578b2de5154498dc0212a6e64922cc182be85a874"}


def need(value,reason):
    if not value:raise ValueError("048_closed_archive_"+reason)


def read(path):return json.loads(Path(path).read_bytes())


def pin(path):
    path=Path(path).resolve(strict=True)
    with path.open("rb") as stream:digest=hashlib.file_digest(stream,"sha256").hexdigest()
    return dict(path=str(path),bytes=path.stat().st_size,sha256=digest)


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write("\n")
    return pin(path)


def copy_bytes(source,target):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("xb") as stream:stream.write(Path(source).read_bytes())
    need(pin(source)["sha256"]==pin(target)["sha256"],"copy_exact")
    return dict(original=pin(source),copy=pin(target))


def binary(value):
    if type(value) is float:return {"f64":value.hex()}
    if isinstance(value,list):return [binary(x) for x in value]
    if isinstance(value,dict):return {k:binary(x) for k,x in value.items()}
    return value


def array_sha(rows,kind):
    return hashlib.sha256(b"".join(struct.pack("<"+kind,v) for row in rows for v in row)).hexdigest()


def freeze():
    RAW.mkdir(parents=True,exist_ok=True)
    refs={name:pin(OLD/name) for name in FIXED}
    need(all(ref["sha256"]==FIXED[name] for name,ref in refs.items()),"fixed_old_anchors")
    for name in ("live_family/attempt_002/AFTER.json","oracle/PROVENANCE.json","oracle/ORIGINAL_CALL.json",
                 "live_family/CLOSEOUT.json","live_family/POST_PROCESS_CHECK_02.json"):
        refs[name]=pin(OLD/name)
    actual=OLD/"live_family/attempt_002"
    for arm in ("A","C"):
        for name in ("CELL.json","client/004.TX.bin","client/004.RX.bin","client/AUDIT.jsonl",
                     "client/STARTUP.json","client/CONFIG.json","client/CLOSE.json"):
            refs[f"ordinary/{arm}/{name}"]=pin(actual/arm/name)
        for name in ("RESULT.json","POP_EVENTS.json"):
            refs[f"offline_shared/{arm}/{name}"]=pin(OLD/"family_diagnostic_001"/arm/name)
    plan=read(OLD/"live_family/PLAN_02.json")
    originals={name:ref for name,ref in plan["inputs"].items()}
    for ref in originals.values():need(pin(ref["path"])==ref,"original_044_asset")
    source=pin(Path(__file__))
    print(save(RAW/"ARCHIVE_FREEZE.json",dict(schema="m6-048-closed-archive-freeze-v1",status="frozen_before_audit",
        frozen_utc=datetime.now(timezone.utc).isoformat(),contract="fc36530cdedd3db65ee55010b7f2a90a89fa87d6",
        old_refs=refs,original_inputs=originals,script=source,pair=list(NAMES),source_rows=[96,12],versions=SOURCES,
        interpretation=dict(
            arrays="Copy the actual evaluated world-binary64 vertex and triangle row arrays, keep native/local/matrix and triangle-polygon maps separately. No re-transform, deduplication or sorting.",
            truth="Bind the existing 1152-pair independent rational oracle: 14 minimizing face pairs, canonical[90,2], its exact canonical witness. Do not rerun or generalize point uniqueness from the tie count.",
            ordinary="A/C historical ordinary query requested relation then surface and used closed shared preparation. Preserve original task form; native pair/exact rational points are not public fields.",
            diagnostic="Old offline shared-tree queue native pair is separately measured diagnostic evidence, not a field of the ordinary public reply.",
            regular="The same world arrays can be given to the original regular distance kernel by the parent; no regular kernel measurement is performed or substituted here."),
        kernel_calls=0,Blender_calls=0,new_assets=0)))


def ordinary(arm,frozen,truth):
    folder=OLD/"live_family/attempt_002"/arm;cell=read(folder/"CELL.json")
    need(cell["valid"] and not cell["errors"],"historical_valid_cell")
    body=cell["answer"]["result"];request=read(folder/"client/004.TX.bin");response=read(folder/"client/004.RX.bin")
    need(request["params"]["arguments"]==read(OLD/"live_family/PLAN_02.json")["request"]["arguments"] and
         request["id"]==response["id"]==cell["answer"]["timing"]["id"],"original_ordered_query")
    need(len(response["result"]["content"])==1 and response["result"]["content"][0]["type"]=="text" and
         not response["result"].get("isError") and json.loads(response["result"]["content"][0]["text"])==body,"original_public_form")
    need(body["result_kind"]=="task_query" and body["pair_order"]=="A_to_B" and body["unit"]=="m" and
         body["coordinate_frame"]=="world" and body["binding"]["runtime_source_sha256"]==SOURCES[arm],"source_unit_order")
    need([row["name"] for row in body["binding"]["objects"]]==list(NAMES),"public_pair_identity")
    startup=read(folder/"client/STARTUP.json");config=read(folder/"client/CONFIG.json")
    identity=startup["hello"]["result"]["_meta"]["human_eye"]
    need(identity["source_sha256"]==SOURCES[arm] and identity["source_file_count"]==143 and identity["production_mode"],"actual_installed_identity")
    need(config["expected_identity"]=={"source_sha256":SOURCES[arm]} and config["request_budget_s"]==30.0,"original_fresh_budget")
    logs=[json.loads(line) for line in (folder/"client/AUDIT.jsonl").read_bytes().splitlines() if line]
    trace_event,=[row for row in logs if row.get("event")=="request_trace" and
                  str(row["trace"]["annotations"].get("mcp_request_id"))==cell["answer"]["timing"]["id"]]
    trace=trace_event["trace"]
    need(trace_event["pid"]==trace["pid"]==cell["product_pid"]==startup["actual_pid"] and
         body["trace_id"]==trace["trace_id"] and trace_event["runtime_identity"]["build_id"]=="sha256:"+SOURCES[arm] and
         trace_event["identity_check"]["compatible"],"actual_request_trace")
    observe,=[row for row in logs if row.get("event")=="observe" and row.get("request_id")==trace["request_id"]]
    need(observe["scene_revision"]==body["binding"]["scene_revision"] and observe["task_work"]==cell["work"],"source_work_binding")
    facts=body["facts"];sf=facts["surface_proximity"];relation=facts["closed_solid_relation"]
    expected=[[float(Fraction(x)) for x in point] for point in truth["exact_points_world_m"]]
    witness=sf["value"]["nearest_witness"]
    need(sf["status"]=="measured" and binary(sf["value"]["distance_m"])==binary(truth["distance_m"]) and
         binary([witness["a"],witness["b"]])==binary(expected),"historical_exact_published_point_pair")
    need(relation["status"]=="measured" and relation["value"]==truth["relation"]=="separated","historical_relation")
    work=cell["work"];surface=work["surface_work"]
    need(work["surface_pair_count"]==work["closed_solid_pair_count"]==1 and work["surface_pair_cache_hit"] is False and
         work["closed_solid_pair_cache_hit"] is False and work["result_cache_hit"] is False and surface["shared_preparation"] and
         surface["shared_trees"] and surface["tree_builds"]==surface["prepared_triangles"]==0,"measured_shared_path")
    close=read(folder/"client/CLOSE.json");need(close["method"]=="eof" and close["exit_code"]==0,"historical_EOF")
    original_wires={name:copy_bytes(folder/"client"/name,RAW/"ordinary"/arm/name) for name in ("004.TX.bin","004.RX.bin")}
    return dict(schema="m6-048-closed-historical-public-v1",arm=arm,source_sha256=SOURCES[arm],
        original_query=request["params"],original_public=body,ordinary_surface_fact=sf,ordinary_relation_fact=relation,
        original_cell=pin(folder/"CELL.json"),original_audit=pin(folder/"client/AUDIT.jsonl"),
        wires=original_wires,work=work,trace=trace,
        path="ordinary task closed_solid_relation followed by surface_proximity with shared preparation/trees",
        missing_public_fields=["exact squared distance","exact rational witness coordinates","canonical native triangle pair","internal witness feature/descriptor"],
        canonical_pair_publicly_exposed=False,exact_rational_points_publicly_exposed=False,
        original_product_pid=cell["product_pid"],original_GUI_pid=cell["host_pid"],
        original_descriptive_business_ns=cell["business_ns"])


def run():
    frozen=read(RAW/"ARCHIVE_FREEZE.json");need(pin(Path(__file__))==frozen["script"],"frozen_audit_source")
    for ref in (*frozen["old_refs"].values(),*frozen["original_inputs"].values()):need(pin(ref["path"])==ref,"unchanged_archive")
    before=read(OLD/"live_family/attempt_002/BEFORE.json");after=read(OLD/"live_family/attempt_002/AFTER.json")
    need(binary(before)==binary(after),"actual_full_scene_preserved")
    oracle=read(OLD/"oracle/GEOMETRY.json");truth=read(OLD/"oracle/TRUTH.json")
    original_author=read(frozen["original_inputs"]["author_mesh_snapshots.json"]["path"])["initial"]
    author={row["name"]:row for row in original_author["objects"]}
    objects={row["name"]:row for row in before["objects"] if row["type"]=="MESH"}
    need(before["source"]["background"] is False and before["source"]["main_thread"] and before["source"]["scale_length"]==1.0 and
         before["source"]["frame"]==1 and before["source"]["subframe"]==0.0,"actual_ordinary_world_source")
    public={arm:ordinary(arm,frozen,truth) for arm in ("A","C")}
    logical={row["name"]:row["object_id"] for row in public["A"]["original_public"]["binding"]["objects"]}
    geometry=dict(schema="m6-048-closed-ordered-world-input-v1",unit="m",coordinate_frame="world",scale_length=1.0,
        pair=list(NAMES),source_capture=frozen["old_refs"]["live_family/attempt_002/BEFORE.json"],
        original_scene=frozen["original_inputs"]["scene.blend"],
        use_note="vertices_world already contains the actual world-metres coordinates. Do not apply matrix_world a second time.")
    for side,name in zip(("left","right"),NAMES):
        row=objects[name];data=row["evaluated"];old=oracle["objects"][name]
        need(binary(data)==binary(row["native"]),"native_evaluated_identity")
        for key,archive_key in (("vertices_world_m","vertices_world_m"),("vertices_local","vertices_local"),("triangles","triangles")):
            need(binary(data[key])==binary(old[archive_key]),"old_independent_array_binding:"+name)
        need(binary(data["vertices_world_m"])==binary(author[name]["world_vertices"]) and data["triangles"]==author[name]["faces"] and
             binary(row["matrix_world"])==binary(author[name]["matrix_world"])==binary(old["matrix_world"]),"original_author_binding")
        count=len(data["triangles"])
        need(data["source_triangle_rows"]==data["triangle_polygons"]==list(range(count)) and
             data["native_polygon_vertices"]==data["triangles"],"actual_original_native_mapping")
        geometry[side]=dict(name=name,object_id=logical[name],native_instance_id=row["instance_id"],
            vertices_world=deepcopy(data["vertices_world_m"]),faces=deepcopy(data["triangles"]),
            vertices_local=deepcopy(data["vertices_local"]),matrix_world=deepcopy(row["matrix_world"]),
            source_triangle_rows=data["source_triangle_rows"],triangle_polygons=data["triangle_polygons"],
            original_native_polygon_vertices=data["native_polygon_vertices"],
            array_hashes=dict(vertices_world_f64_le=array_sha(data["vertices_world_m"],"d"),
                vertices_local_f64_le=array_sha(data["vertices_local"],"d"),faces_i32_le=array_sha(data["triangles"],"i")))
    need([len(geometry[side]["faces"]) for side in ("left","right")]==[96,12],"fixed_face_count")
    geometry_ref=save(RAW/"GEOMETRY.json",geometry)
    ties=truth["all_minimizing_source_triangle_pairs"]
    need(len(ties)==len({tuple(p) for p in ties})==14 and ties==truth["enumeration"]["minimizing_input_pairs"] and
         min(ties)==truth["canonical_source_triangle_pair"]==[90,2],"old_oracle_canonical_tie_set")
    need(truth["enumeration"]["full_pair_count"]==truth["enumeration"]["exact_feature_pairs"]==1152,"old_oracle_full_denominator")
    exact=[[Fraction(x) for x in p] for p in truth["exact_points_world_m"]]
    need(sum((b-a)**2 for a,b in zip(*exact))==Fraction(truth["exact_distance_squared_world_m2"]),"old_exact_witness_square_consistency")
    need([geometry[side]["faces"][idx] for side,idx in zip(("left","right"),(90,2))]==truth["canonical_face_source_vertices"],"canonical_original_source_vertices")
    for side,idx,expected in zip(("left","right"),(90,2),truth["canonical_face_world_triangles"]):
        actual=[geometry[side]["vertices_world"][v] for v in geometry[side]["faces"][idx]]
        need(binary(actual)==binary(expected),"canonical_face_geometry")
    bound_truth=deepcopy(truth)
    bound_truth.update(schema="m6-048-bound-existing-closed-oracle-v1",geometry=geometry_ref,
        original_independent_oracle=frozen["old_refs"]["oracle/TRUTH.json"],computed_this_task=False,
        original_triangle_polygons_for_canonical_pair=[geometry["left"]["triangle_polygons"][90],geometry["right"]["triangle_polygons"][2]],
        point_uniqueness_scope="No independent uniqueness proof over all 14 face pairs was recomputed here; bind the existing exact canonical witness only")
    truth_ref=save(RAW/"CANONICAL_TRUTH.json",bound_truth)
    public_refs={arm:save(RAW/"ordinary"/arm/"PUBLIC.json",value) for arm,value in public.items()}
    diag={}
    for arm in ("A","C"):
        path=OLD/"family_diagnostic_001"/arm/"RESULT.json";row=read(path)
        need(row["identity"]["source_sha256"]==SOURCES[arm] and row["scope"]=="shared_task_facts_offline_diagnostic","old_diagnostic_scope")
        need(row["input"]==frozen["old_refs"]["oracle/GEOMETRY.json"] and row["independent_truth"]==frozen["old_refs"]["oracle/TRUTH.json"],"diagnostic_same_inputs")
        surface=row["result"]["surface"];observed=public[arm]["ordinary_surface_fact"]["value"]
        need(surface["distance_m"]==observed["distance_m"] and binary(surface["point_a_world"])==binary(observed["nearest_witness"]["a"]) and
             binary(surface["point_b_world"])==binary(observed["nearest_witness"]["b"]) and surface["work"]==public[arm]["work"]["surface_work"],
             "diagnostic_public_binding")
        pairs=[tree["returned_native_face_pair"] for tree in row["queue"]["trees"]]
        need(pairs==[[90,2]],"separate_diagnostic_native_pair")
        diag[arm]=dict(original_result=pin(path),phase=row["phase"],scope=row["scope"],instrumented=row["instrumented"],
            returned_native_face_pairs=pairs,public_points_match=True,work_matches_ordinary=True,
            queue=row["queue"],not_a_public_native_pair_field=True,not_a_regular_distance_measurement=True)
    ordinary_equal=binary(public["A"]["ordinary_surface_fact"])==binary(public["C"]["ordinary_surface_fact"])
    need(ordinary_equal and public["A"]["ordinary_relation_fact"]==public["C"]["ordinary_relation_fact"],"historical_fact_parity")
    originals={name:copy_bytes(ref["path"],RAW/"originals"/name) for name,ref in frozen["original_inputs"].items()}
    inputs=dict(schema="m6-048-closed-archive-inputs-v1",status="bound",pair=list(NAMES),geometry=geometry_ref,truth=truth_ref,
        ordinary_public=public_refs,historical_shared_diagnostics=diag,originals=originals,source_freeze=pin(RAW/"ARCHIVE_FREEZE.json"),
        regular_distance=dict(status="not_measured_by_this_archive_task",same_ordered_world_input=geometry_ref,
                              source="Actual 044 source, not a replayed answer. Parent may run original A/C regular kernels separately.",
                              not_equated_to_shared_preparation=True),
        original_query=public["A"]["original_query"],kernel_calls=0,Blender_calls=0,new_assets=0)
    inputs_ref=save(RAW/"INPUTS.json",inputs)
    result=dict(schema="m6-048-closed-archive-audit-v1",status="pass",inputs=inputs_ref,
        source_rows=[96,12],source_vertices=[48,8],possible_triangle_pairs=1152,old_independent_oracle_pair_count=1152,
        old_minimizing_pair_count=14,canonical_source_triangle_pair=[90,2],
        canonical_source_vertices=truth["canonical_face_source_vertices"],
        actual_triangle_polygon_mapping_present=True,historical_A_C_surface_facts_equal=ordinary_equal,
        historical_A_C_distance_m=truth["distance_m"],historical_A_C_relation="separated",
        observed_paths=dict(ordinary_shared_preparation=["A","C"],separate_old_offline_shared_diagnostic=["A","C"],
                            regular_distance_new_or_archived_in_this_scope=[]),
        missing_public_fields=public["A"]["missing_public_fields"],
        limitations=["No regular distance run is substituted for the shared original public fact.",
            "The public task never exposed [90,2]; that pair is independent oracle plus separately matched old diagnostic evidence.",
            "Fourteen minimizing face pairs do not alone prove global point uniqueness or a general witness feature contract.",
            "No new pair search, exact kernel, Blender, source mutation, timing, or installation change was performed."],
        checked_new_arithmetic="Only exact squared length of the already supplied rational witness and byte/row identities; no numerical search/predicate kernel",
        archive_mismatches=[],analytical_source=pin(Path(__file__)),new_calls=dict(kernel=0,Blender=0,timing=0,asset_generation=0))
    print(save(RAW/"RESULTS.json",result))
    with (HERE/"RESULTS.json").open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(result,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write("\n")
    print(pin(HERE/"RESULTS.json"))


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("mode",choices=("freeze","run"));args=parser.parse_args()
    freeze() if args.mode=="freeze" else run()
