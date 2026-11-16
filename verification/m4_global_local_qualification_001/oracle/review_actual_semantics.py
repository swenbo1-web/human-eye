"""Preserve precise per-view reasons and original witness rows from saved data."""
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
NS = HERE.parent
RUNTIME = Path("D:/he_m4_global_local_001/sessions")
ORDER = ["SCENE","TOP","LEFT","RIGHT","FRONT","BACK"]


def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))


def main():
    pins,records = [pin(Path(__file__))],[]
    for label in ("global","local_open","local_covered"):
        path = RUNTIME/label/"product_full/call_001/SERVICE_RESULT.json"
        pins.append(pin(path))
        full = json.loads(path.read_bytes())
        evidences = {row["roi_id"]:row for row in full["facts"]["region_evidence"]}
        facts = [row for row in full["facts"]["regions"] if row["object_name"] in ("Obj_02","Obj_06","Obj_09")]
        for fact in facts:
            evidence = evidences[fact["roi_id"]]
            if fact["object_name"]=="Obj_06":
                assert fact["status"]=="unknown" and fact["reason"]=="finite_camera_pool_uncovered"
                assert evidence["unobserved_reason"]=="positive_area_occlusion_all_front_views"
                assert evidence["complete_witness"] is None
                assert evidence["view_reasons"]=={"positive_area_occlusion":ORDER}
            elif label=="global":
                assert fact["reason"]==evidence["unobserved_reason"]=="pixel_evidence_insufficient"
                assert evidence["view_reasons"]=={"pixel_evidence_insufficient":ORDER}
                assert evidence["complete_witness"] is None
            row = dict(label=label,original_region_fact=fact,original_region_evidence=evidence,
                       runtime_rendered_views=[frame["view_name"] for frame in full["frames"]])
            if label=="local_open":
                witness = evidence["complete_witness"]
                observation = next(item for item in full["facts"]["observations"] if item["view_name"]==witness["view_name"])
                pixel = observation["pixel_rows"][witness["pixel_row_index"]]
                assert pixel["roi_id"]==fact["roi_id"] and pixel["readable"] is True
                row["original_witness_pixel_row"] = pixel
                row["original_witness_frame"] = next(item for item in full["frames"] if item["view_name"]==witness["view_name"])
            records.append(row)
    result = dict(schema="global-local-saved-semantic-review-v1",passed_checked_scope=True,records=records,input_pins=pins,
        findings=[
            "The covered region's public main reason is finite_camera_pool_uncovered. The original precise attached evidence names positive-area occlusion in all six directions.",
            "The inclined region's public front_direction_world is the oriented rational vector [0,-1/3,1]. The independent unit normal is [0,-1,3]/sqrt(10), with nz squared 9/10.",
            "Global/local maps are independently source-bound fixture counterparts. This batch adds no product parent-child witness association.",
            "Per-view geometric classifications cover the fixed pool. Actual images exist only for the recorded rendered views."],
        new_actual_operations=0)
    output = HERE/"ACTUAL_SEMANTIC_REVIEW.json"
    with output.open("x",encoding="utf8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
        stream.write("\n")
    print(json.dumps(dict(passed=True,record_count=len(records),sha256=pin(output)["sha256"])))


if __name__=="__main__":
    main()
