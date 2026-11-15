"""Plot frozen reference contours against actual independently read saved models."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read,write,identity
import numpy as np
from PIL import Image,ImageDraw,ImageFont

specification=importlib.util.spec_from_file_location("_consume002_overlay_reference",HERE.parent/"m6_reference_refine_001/reference_geometry.py")
REFERENCE=importlib.util.module_from_spec(specification)
specification.loader.exec_module(REFERENCE)

EXPECTED=("v1_forearm_native","v1_forearm_facts","v2_forearm_facts","v2_forearm_native")
COLORS=dict(reference=(213,94,0),before=(0,91,161),saved=(0,135,105),axis=(80,80,80),station=(135,135,135))


def absolute(value):
    path=Path(value)
    return path if path.is_absolute() else HERE/path


def packet(path):
    with np.load(path,allow_pickle=False) as archive:
        return {key:archive[key] for key in archive.files}


def fingerprint_image(path):
    with Image.open(path) as image:
        result=identity(path)
        result.update(width=image.width,height=image.height,pixel_sha256=hashlib.sha256(image.convert("RGB").tobytes()).hexdigest())
        return result


def final_records(session,state):
    candidates=[]
    for path in sorted((session/"readbacks").glob("*/READBACK.json")):
        receipt=read(path)
        if receipt["version"]==state["version"] and receipt["saved_blend"]["sha256"]==state["current_blend_identity"]["sha256"]:
            candidates.append((absolute(receipt["readback"]["path"]),absolute(receipt["quality_record"]),path))
    if candidates:
        return candidates[-1]
    for operation in reversed(state["operations"]):
        if operation.get("status")=="saved_and_independently_read" and operation["version"]==state["version"]:
            return absolute(operation["readback"]["path"]),absolute(operation["quality_record"]),None
    raise ValueError("actual_final_saved_model_readback_required")


def font(size):
    for path in (Path("C:/Windows/Fonts/arial.ttf"),Path("C:/Windows/Fonts/segoeui.ttf")):
        if path.exists():
            return ImageFont.truetype(str(path),size)
    return ImageFont.load_default(size=size)


def dashed(draw,points,color,width=2,on=7.,off=5.):
    distance=0.
    for start,end in zip(points[:-1],points[1:]):
        start,end=np.asarray(start),np.asarray(end)
        length=float(np.linalg.norm(end-start))
        if not length:
            continue
        subdivisions=max(1,int(np.ceil(length)))
        for index in range(subdivisions):
            first_fraction,second_fraction=index/subdivisions,(index+1)/subdivisions
            midpoint=distance+.5*(first_fraction+second_fraction)*length
            if midpoint%(on+off)<on:
                first=start+(end-start)*first_fraction
                second=start+(end-start)*second_fraction
                draw.line([tuple(first),tuple(second)],fill=color,width=width)
        distance+=length


def as_pixels(records,field,anchors):
    E,tangent,outward,length=REFERENCE.axis_frame(anchors["E"],anchors["W"])
    return np.array([E+length*(row["t"]*tangent+row[field]*outward) for row in records])


def model_sections(data,projection,anchors,stations):
    projected=data["vertices"] @ np.asarray(projection["affine_2_by_3"]).T+projection["offset"]
    return REFERENCE.measure_projected_sections(projected,data["faces"],anchors["E"],anchors["W"],stations)


def draw_overlay(image_path,anchors,reference,before,after,quality,definition,label,destination,changed):
    with Image.open(image_path) as image:
        canvas=Image.new("RGB",(800,800),(248,249,250))
        canvas.paste(image.convert("RGB"),(64,108))
    draw=ImageDraw.Draw(canvas)
    draw.text((24,15),label+"  |  correspondence "+definition,fill=(25,28,32),font=font(20))
    outer=quality["contours"]["definitions"]["primary" if definition=="A" else "alternative"]["improvements"]["outer"]
    draw.text((24,45),f"Outer MAE / EW   before {outer['MAE_before']:.6f}   saved {outer['MAE_after']:.6f}",fill=(25,28,32),font=font(15))
    text="Changed vertices 0; saved geometry matches initial" if changed==0 else f"Changed vertices {changed}; actual saved geometry"
    draw.text((24,67),text,fill=(45,48,52),font=font(15))
    offset=np.array([64.,108.])
    for field in ("inner","outer"):
        points=as_pixels(reference,field,anchors)+offset
        draw.line([tuple(value) for value in points],fill=COLORS["reference"],width=3)
        points=as_pixels(before,field,anchors)+offset
        draw.line([tuple(value) for value in points],fill=COLORS["before"],width=3)
        dashed(draw,as_pixels(after,field,anchors)+offset,COLORS["saved"],width=2)
    E,tangent,outward,length=REFERENCE.axis_frame(anchors["E"],anchors["W"])
    dashed(draw,[E+offset,np.asarray(anchors["W"])+offset],COLORS["axis"],1,4.,5.)
    for name,point in (("E",anchors["E"]),("W",anchors["W"])):
        point=np.asarray(point)+offset
        draw.ellipse([tuple(point-3),tuple(point+3)],fill=(35,35,35),outline=(250,250,250),width=1)
        draw.text(tuple(point+[6,-14]),name,fill=(35,35,35),font=font(14),stroke_width=1,stroke_fill=(245,245,245))
    for fraction in (.15,.35,.55,.75,.9):
        rows=[records[np.argmin([abs(row["t"]-fraction) for row in records])] for records in (reference,before,after)]
        low=min(row["inner"] for row in rows)
        high=max(row["outer"] for row in rows)
        first=E+length*(fraction*tangent+low*outward)+offset
        second=E+length*(fraction*tangent+high*outward)+offset
        dashed(draw,[first,second],COLORS["station"],1,2.,4.)
        draw.text(tuple(second+[6,-6]),f"{fraction:.0%}",fill=(30,30,30),font=font(12),stroke_width=1,stroke_fill=(245,245,245))
    x=30
    for name,key in (("Reference","reference"),("Before","before"),("Actual saved","saved")):
        if key=="saved":
            dashed(draw,[(x,769),(x+35,769)],COLORS[key],2)
        else:
            draw.line([(x,769),(x+35,769)],fill=COLORS[key],width=3)
        draw.text((x+43,759),name,fill=(30,30,30),font=font(14))
        x+=230
    canvas.save(destination)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",choices=("v1","v2","all"),required=True)
    parser.add_argument("--attempt",default="contour_overlays")
    args=parser.parse_args()
    if not args.attempt.replace("_","").replace("-","").isalnum():
        raise ValueError("safe_output_attempt_required")
    started,cpu=time.perf_counter(),time.process_time()
    views=read("VIEWABLES.json")
    order=list(EXPECTED)
    random.Random(20261116).shuffle(order)
    labels={name:"pair_"+str(index+1).zfill(2) for index,name in enumerate(order)}
    mapping_path=HERE/"private/contour_blind_mapping.json"
    mapping=dict(seed=20261116,session_order=order,labels=labels,blinded_attributes=["consumer route","stage"],
        unblinded_attributes=["correspondence A/B","before versus saved","actual changed-vertex count"])
    if mapping_path.exists() and read(mapping_path)!=mapping:
        raise ValueError("blind_session_mapping_changed")
    write(mapping_path,mapping)
    results=[]
    selected=[row for row in views["sessions"] if args.stage=="all" or row["stage"]==args.stage]
    if not selected:
        raise ValueError("no_completed_rendered_sessions_for_selected_stage")
    for view in sorted(selected,key=lambda row:labels[row["session"]]):
        session=HERE/"private/sessions"/view["session"]
        state_path=session/"session.json"
        state_bytes=state_path.read_bytes()
        state=json.loads(state_bytes)
        if state.get("pending"):
            raise ValueError("saved_edit_pending")
        if identity(Path(state["current_blend"]))["sha256"]!=view["after_blend"]["sha256"]:
            raise ValueError("render_does_not_match_current_saved_model")
        current_path,quality_path,read_receipt=final_records(session,state)
        current,initial=packet(current_path),packet(state["initial_npz"])
        quality=read(quality_path)
        changed=int(np.any(initial["vertices_local"].view(np.uint32)!=current["vertices_local"].view(np.uint32),axis=1).sum())
        if changed!=quality["displacement"]["changed_vertices"]:
            raise ValueError("saved_readback_quality_changed_vertex_count_mismatch")
        spec=read(Path(state["source_spec"]))
        annotation,observation=read(Path(spec["annotation_path"])),read(Path(spec["observation_path"]))
        image_record=next(row for row in view["after_images"] if row["specification"]["name"]=="forearm_front")
        if identity(absolute(image_record["image"]["path"]))["sha256"]!=image_record["image"]["sha256"]:
            raise ValueError("actual_saved_model_render_changed")
        projection=annotation["source_projection"]
        if not np.allclose(image_record["world_to_image_affine_2_by_3"],projection["affine_2_by_3"],rtol=0,atol=1e-9) or not np.allclose(image_record["world_to_image_offset"],projection["offset"],rtol=0,atol=1e-9):
            raise ValueError("render_camera_differs_from_frozen_measurement_projection")
        output=Path(view["artifact_directory"])/args.attempt
        output.mkdir(parents=True,exist_ok=False)
        stations=np.unique(np.r_[np.linspace(0.,1.,121),annotation["stations"]])
        for definition,key,name in (("A","primary_anchors","primary"),("B","alternative_anchors","alternative")):
            anchors=observation[key]
            reference=REFERENCE.measure_polyline_sections(annotation["reference_foreground"]["inner_polyline"],annotation["reference_foreground"]["outer_polyline"],
                anchors["reference"]["E"],anchors["reference"]["W"],stations)
            before=model_sections(initial,projection,anchors["model"],stations)
            after=model_sections(current,projection,anchors["model"],stations)
            for fraction in annotation["stations"]:
                row=after[np.argmin([abs(value["t"]-fraction) for value in after])]
                measured=next(value for value in quality["contours"]["definitions"][name]["after"]["stations"] if value["t"]==fraction)
                if abs(row["outer"]-measured["model"]["outer"])>1e-10 or abs(row["inner"]-measured["model"]["inner"])>1e-10:
                    raise ValueError("overlay_curve_differs_from_actual_saved_quality")
            destination=output/(labels[view["session"]]+"_"+definition+".png")
            draw_overlay(absolute(image_record["image"]["path"]),anchors["model"],reference,before,after,quality,definition,labels[view["session"]],destination,changed)
            record=dict(session=view["session"],blind_label=labels[view["session"]],definition=definition,
                image=fingerprint_image(destination),changed_vertices=changed,quality_status=quality["status"],
                outer_errors=quality["contours"]["definitions"][name]["improvements"]["outer"],
                current_packet=identity(current_path),initial_packet=identity(Path(state["initial_npz"])),quality_record=identity(quality_path),
                saved_blend=identity(Path(state["current_blend"])),source_render=image_record["image"],
                annotation=identity(Path(spec["annotation_path"])),observation=identity(Path(spec["observation_path"])),
                read_receipt=identity(read_receipt) if read_receipt else None,
                pixel_geometry_scale=1.,displacement_scale=1.,interpretation="Fixed reference hypothesis and actual saved geometry; no artistic preference score")
            write(destination.with_suffix(".json"),record)
            write(output/(labels[view["session"]]+"_"+definition+"_CURVES.json"),dict(stations=stations.tolist(),reference=reference,before=before,actual_saved=after))
            results.append(record)
        if state_path.read_bytes()!=state_bytes:
            raise ValueError("session_changed_during_readonly_contour_render")
    result=dict(stage=args.stage,attempt=args.attempt,images=results,image_count=len(results),
        wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu,Pro_calls=0,Blender_calls=0,
        source=identity(Path(__file__)),blind_mapping=identity(mapping_path),
        scope="readonly post-render scientific contours; routes/stages have fixed random labels, required reference/before/saved identities remain visible")
    write("private/results/"+args.attempt+"_"+args.stage+"_SUMMARY.json",result)
    print(json.dumps(dict(stage=args.stage,images=len(results),wall_s=result["wall_s"])),flush=True)


if __name__=="__main__":
    main()
