"""Verify all contour artifacts and provide route-free image paths for viewing."""

import hashlib
from pathlib import Path
import shutil
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read,write,identity
import numpy as np
from PIL import Image


def absolute(value):
    path=Path(value)
    return path if path.is_absolute() else HERE/path


def packet(path):
    with np.load(path,allow_pickle=False) as archive:
        return {key:archive[key] for key in archive.files}


def main():
    started,cpu=time.perf_counter(),time.process_time()
    stages=[read("private/results/contour_overlays_"+stage+"_SUMMARY.json") for stage in ("v1","v2")]
    records=[record for summary in stages for record in summary["images"]]
    mapping=read("private/contour_blind_mapping.json")
    checks=dict(eight_images=len(records)==8, four_sessions=len({record["session"] for record in records})==4,
        two_definitions_each=all({record["definition"] for record in records if record["session"]==session}=={"A","B"} for session in mapping["session_order"]))
    output=HERE/"private/contour_blind"
    output.mkdir(parents=True,exist_ok=True)
    public,details=[],[]
    for record in sorted(records,key=lambda row:(row["blind_label"],row["definition"])):
        name=record["blind_label"]+"_"+record["definition"]
        source=absolute(record["image"]["path"])
        checks[name+"_PNG_SHA"]=identity(source)["sha256"]==record["image"]["sha256"]
        with Image.open(source) as image:
            checks[name+"_PNG_dimensions"]=[image.width,image.height]==[record["image"]["width"],record["image"]["height"]]
            checks[name+"_PNG_pixels"]=hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()==record["image"]["pixel_sha256"]
        for field in ("current_packet","initial_packet","quality_record","saved_blend","source_render","annotation","observation"):
            value=record[field]
            checks[name+"_source_"+field]=identity(absolute(value["path"]))["sha256"]==value["sha256"]
        checks[name+"_blind_mapping"]=record["blind_label"]==mapping["labels"][record["session"]]
        initial,current=packet(absolute(record["initial_packet"]["path"])),packet(absolute(record["current_packet"]["path"]))
        changed=int(np.any(initial["vertices_local"].view(np.uint32)!=current["vertices_local"].view(np.uint32),axis=1).sum())
        checks[name+"_changed_count"]=changed==record["changed_vertices"]
        quality=read(absolute(record["quality_record"]["path"]))
        key="primary" if record["definition"]=="A" else "alternative"
        checks[name+"_QA_outer_stats"]=record["outer_errors"]==quality["contours"]["definitions"][key]["improvements"]["outer"]
        curves=read(source.with_name(source.stem+"_CURVES.json"))
        for field in ("before","actual_saved"):
            for station in quality["contours"]["definitions"][key]["before" if field=="before" else "after"]["stations"]:
                row=next(value for value in curves[field] if value["t"]==station["t"])
                checks[name+"_"+field+"_station_"+str(station["t"])]=all(abs(row[metric]-station["model"][metric])<1e-10 for metric in ("inner","outer","width"))
        if changed==0:
            checks[name+"_zero_edit_curves_match"]=curves["before"]==curves["actual_saved"]
            checks[name+"_zero_edit_improvement_false"]=quality["contours"]["definitions"][key]["improvement_established"] is False
        destination=output/(name+".png")
        if destination.exists() and destination.read_bytes()!=source.read_bytes():
            raise ValueError("existing_blind_PNG_has_other_bytes")
        if not destination.exists():
            shutil.copyfile(source,destination)
        checks[name+"_blind_copy_exact"]=destination.read_bytes()==source.read_bytes()
        public.append(dict(label=record["blind_label"],correspondence=record["definition"],image=identity(destination),
            width=record["image"]["width"],height=record["image"]["height"],pixel_sha256=record["image"]["pixel_sha256"],
            changed_vertices=changed,outer_errors=record["outer_errors"],artistic_rating=None))
        details.append(dict(record=record,public_image=identity(destination)))
    report=dict(status="pass" if all(checks.values()) else "fail",checks=checks,passed=sum(checks.values()),total=len(checks),
        image_count=len(records),stage_overlay_wall_s={row["stage"]:row["wall_s"] for row in stages},
        stage_overlay_CPU_s={row["stage"]:row["cpu_s"] for row in stages},
        verification_and_copy_wall_s=time.perf_counter()-started,verification_and_copy_CPU_s=time.process_time()-cpu,
        Pro_calls=0,Blender_calls=0,source=identity(Path(__file__)),details=details)
    write("private/contour_audit/VERIFICATION.json",report)
    write("CONTOUR_OVERLAYS.json",dict(status=report["status"],images=public,image_count=len(public),
        fixed_geometry_and_camera_scale=1.,image_order="fixed randomized session order; A/B definitions and before/saved legend shown",
        private_source_audit=identity(HERE/"private/contour_audit/VERIFICATION.json"),
        overlay_total_wall_s=sum(row["wall_s"] for row in stages),overlay_total_CPU_s=sum(row["cpu_s"] for row in stages),
        verification_and_copy_wall_s=report["verification_and_copy_wall_s"],verification_and_copy_CPU_s=report["verification_and_copy_CPU_s"],
        no_artistic_acceptance_score=True))
    print(report["status"],report["passed"],report["total"],len(public),report["verification_and_copy_wall_s"])
    if report["status"]!="pass":
        raise SystemExit(1)


if __name__=="__main__":
    main()
