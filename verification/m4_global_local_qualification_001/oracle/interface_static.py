"""Small independent-oracle regression checks. No product import or raster."""
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_independent_static_oracle", HERE / "static_oracle.py")
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
F = oracle.F


def check():
    rows = []

    def record(name, condition):
        if not condition:
            raise AssertionError(name)
        rows.append({"case":name,"passed":True})

    rectangle = [tuple(map(F,p)) for p in ((0,0,0),(1,0,0),(1,1,0),(0,1,0))]
    first = oracle.component_analysis("test",rectangle,[(0,1,2),(0,2,3)])
    record("two_triangles_make_one_rectangle",len(first)==1 and first[0]["rectangle_supported"] and first[0]["area_squared_m4"]==1)
    cyclic = oracle.component_analysis("test",rectangle,[(2,0,1),(3,0,2)])
    record("cyclic_face_start_does_not_change_geometry",cyclic==first)
    reordered = oracle.component_analysis("test",rectangle,[(0,2,3),(0,1,2)])
    record("source_face_reorder_keeps_actual_indices",reordered[0]["source_triangle_indices"]==[0,1] and reordered[0]["rectangle_supported"])
    reversed_faces = oracle.component_analysis("test",rectangle,[(2,1,0),(3,2,0)])
    record("reversed_surface_keeps_oriented_negative_normal",reversed_faces[0]["plane_normal_integer"]==[0,0,-1] and not reversed_faces[0]["normal_nz_in_domain"])
    opposite = oracle.component_analysis("test",rectangle,[(0,1,2),(3,2,0)])
    record("incoherent_winding_cannot_make_supported_rectangle",len(opposite)==2 and not any(row["rectangle_supported"] for row in opposite))
    trapezoid = [tuple(map(F,p)) for p in ((0,0,0),(2,0,0),(1,1,0),(0,1,0))]
    shape = oracle.component_analysis("test",trapezoid,[(0,1,2),(0,2,3)])
    record("rectangular_bbox_does_not_certify_trapezoid",not shape[0]["rectangle_supported"])
    duplicate_seam = rectangle+[rectangle[0],rectangle[2]]
    separated = oracle.component_analysis("test",duplicate_seam,[(0,1,2),(4,5,3)])
    record("coincident_coordinates_do_not_invent_shared_source_edge",len(separated)==2 and not any(row["rectangle_supported"] for row in separated))
    try:
        oracle.component_analysis("test",rectangle,[(0,1,2),(0,2,3),(0,2,1)])
    except ValueError as error:
        record("nonmanifold_source_edge_rejected",str(error)=="nonmanifold source edge")
    else:
        raise AssertionError("nonmanifold_source_edge_rejected")
    try:
        oracle.component_analysis("test",rectangle,[(0,1,1)])
    except ValueError as error:
        record("repeated_source_vertex_rejected",str(error)=="invalid triangle")
    else:
        raise AssertionError("repeated_source_vertex_rejected")
    record("barycentric_error_envelope_independently_bounded",oracle.barycentric_envelope()["envelope_sufficient"])
    static = json.loads((HERE / "STATIC_QUALIFICATION.json").read_bytes())
    record("fixed_static_checks_all_true",static["passed"] and all(static["checks"].values()))
    record("all_18_fixed_projection_rows_have_strict_integer_bound",sum(len(view["regions"]) for view in static["pixels"]["projection_by_view"])==18 and
           all(row["pixel_center_bbox_upper"]<16 for view in static["pixels"]["projection_by_view"] for row in view["regions"]))
    return {"schema":"global-local-oracle-interface-v1","passed":True,"case_count":len(rows),"cases":rows,
            "scope":"Oracle sanity checks and fixed scene certificate structure. No new scene, product execution, raster or qualification sample.",
            "input_pins":[oracle.pin(__file__),oracle.pin(HERE/"static_oracle.py"),oracle.pin(HERE/"STATIC_QUALIFICATION.json")]}


if __name__=="__main__":
    output = HERE / "INTERFACE_STATIC.json"
    result = check()
    with output.open("x",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write("\n")
    print(json.dumps({"passed":result["passed"],"case_count":result["case_count"],"sha256":oracle.pin(output)["sha256"]}))
