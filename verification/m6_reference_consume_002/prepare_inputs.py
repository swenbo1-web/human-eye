"""Bind one shared image-bearing task from the two existing annotations."""

import hashlib
import json
from pathlib import Path
import struct
import time
from PIL import Image

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/"m6_reference_refine_001"


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf8",newline="\n")


def image_identity(path):
    raw=Path(path).read_bytes()
    width,height=struct.unpack(">II",raw[16:24])
    return dict(path=str(Path(path).resolve()),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),width=width,height=height)


def main():
    started,cpu=time.perf_counter(),time.process_time()
    case=HERE/"private/consumer_cases/forearm"
    annotation=read(OLD/"ANNOTATION_DRAFT.json")
    observation=read(OLD/"OBSERVATION.json")
    alternative=read(OLD/"INDEPENDENT_ANCHORS.json")
    binding=read(HERE/"CASE_BINDING.json")
    derived=HERE/"private/images"
    derived.mkdir(parents=True,exist_ok=False)
    records=[]
    crop=(650,470,930,745)
    for name,path in (("A_reference_annotation",OLD/"private/annotation/reference_annotated.png"),("B_reference_annotation",OLD/"private/independent_anchors/reference_anchors.png")):
        destination=derived/(name+".png")
        with Image.open(path) as original:
            original.crop(crop).save(destination)
        records.append(dict(role=name,**image_identity(destination),source_image=image_identity(path),source_crop_xyxy=list(crop),
            coordinate_note="Viewport crop of existing annotation pixels. Numeric landmark coordinates remain in the original1056x1490 frame."))
    art=read(OLD/"INPUT_BINDING.json")["inputs"][0]["path"]
    images=[dict(role="original_reference_full",**image_identity(art))]
    for role in ("whole_front","forearm_front","forearm_side","forearm_45"):
        images.append(dict(role="original_model_"+role,**image_identity(OLD/"private/views/before"/(role+".png"))))
    images += [records[0],dict(role="A_model_annotation",**image_identity(OLD/"private/annotation/model_annotated.png")),
        records[1],dict(role="B_model_annotation",**image_identity(OLD/"private/independent_anchors/model_front_anchors.png"))]
    definitions=[]
    for label,key in (("A","primary_anchors"),("B","alternative_anchors")):
        rows=observation["primary_stations" if label=="A" else "alternative_stations"]
        definitions.append(dict(name=label,anchors=observation[key],
            wrist_definition="Near the wrist protrusion and entry-to-palm transition" if label=="A" else "Narrow distal forearm shaft proximal to the wrist protrusion and palm expansion",
            reference_sections=[dict(t=row["t"],inner=row["reference_inner"],outer=row["reference_outer"],width=row["reference_width"]) for row in rows]))
    task=dict(task_id="forearm",intent="Use the original art to assess and, when supported, refine the continuous elbow-to-wrist contour taper of the image-right/model-positive-Y forearm.",
        images=images,image_delivery="Call images() first to receive these actual PNG image blocks. Subsequent image viewing is available through the same tool.",
        observed_region=dict(F_points=599,editable_points=binding["editable_points"],endpoint_guard_points=binding["anchor_guard_points"],
            source_mapping="Source IDs index the27304-vertex complete source mesh. F is the fixed existing599-point forearm observation region. I is its nonempty editable subset after both supplied elbow/wrist endpoint guards."),
        two_existing_correspondences=definitions,reference_contours=annotation["reference_foreground"],projection=annotation["source_projection"],
        manual_uncertainty=dict(A_reference_E_radius_px=6,A_reference_W_radius_px=5,A_model_E_radius_px=8,A_model_W_radius_px=6,
            B_reference={key:alternative["reference"][key]["manual_uncertainty_plus_minus_xy_px"] for key in ("E","W")},
            B_model={key:alternative["model_front"][key]["manual_uncertainty_plus_minus_xy_px"] for key in ("E","W")},
            interpretation="Existing agent landmark assumptions and finite sensitivity cases, without a statistical confidence or user-approved anatomical truth. The two W definitions refer to different structural levels."),
        edit_budget=dict(unit="m",ell_m=binding["ell_m"],maximum_operation_displacement_m=binding["max_operation_displacement_m"],
            maximum_cumulative_displacement_m=binding["max_cumulative_displacement_m"],
            behavior="Exact consumer-submitted values, with explicit rejection outside I, nonfinite input, stale version or displacement budget. No automatic clipping or substituted displacement."),
        preservation="Preserve elbow/wrist guards, hand, domain-exterior local float32 coordinates, source mapping, native polygon topology, matrices, UV/material/packed images and other scene objects. Preserve inner contour and thickness, and evaluate side/45 views. Choose an actual active patch and transition inside I if you edit.",
        analysis_requirements=["Identify the correct forearm in whole and local views, supported by the actual images.",
            "Explain the two existing wrist structure levels and your adopted interpretation, without making a third manual landmark set.",
            "Distinguish centerline/pose offset from width and inner/outer shape difference using images and geometry.",
            "Give a specific local recommendation, direction and evidence. With sufficient support calculate your own sparse values, submit, save and independently read back.",
            "If current evidence does not support a shape edit, provide concrete visual/geometric reasons and actual follow-up needs, then independently read back your preserved model copy. Shape improvement is unestablished in that case."],
        evaluation=dict(stations=[.15,.35,.55,.75,.9],metrics="Both A and B inner/outer/width/centerline residuals and average/maximum errors are always reported. Your adopted correspondence is a task convention, not anatomical truth.",
            technical_status="Separate geometry/scene preservation from reference metrics and visual/artistic judgement.",
            gradient_limit=.2,template_normal_angle_limit_deg=5.,fixed_anchors_and_source=True),
        scope="Original asset and formal plugin are read-only. Each session starts from a separate original-model copy. Uncertainty is input for your real visual decision and never cancels the session.")
    write(case/"task.json",task)
    write(HERE/"IMAGE_BINDING.json",dict(image_transport="MCP ImageContent only",images=images,count=len(images),PNG_bytes=sum(row["bytes"] for row in images),
        pixels=sum(row["width"]*row["height"] for row in images),derived_viewports=records,existing_landmarks_changed=False,
        task_sha256=hashlib.sha256((case/"task.json").read_bytes()).hexdigest(),wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu))
    print("shared task and MCP images",len(images),"PNG bytes",sum(row["bytes"] for row in images),flush=True)


if __name__=="__main__":
    main()
