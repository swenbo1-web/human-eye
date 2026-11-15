"""Record actual foreground contour, fixed EW annotations and source projection."""

import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from reference_geometry import (axis_frame, normalized_coordinates, align_similarity,
    front_pixel_to_world_yz, measure_polyline_sections, measure_projected_sections)

REFERENCE = Path("D:/Projects/fps/outputs/character-design/Yanyite/Yanyite_Front_v1.png")
STATIONS = [.15, .35, .55, .75, .90]
REFERENCE_E, REFERENCE_W = [707.,520.], [752.,695.]
MODEL_E, MODEL_W = [282.,126.], [354.,421.]


def identity(path):
    raw = Path(path).read_bytes()
    return dict(path=str(Path(path).resolve()), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf8", newline="\n")


def foreground_polylines(image):
    values = np.asarray(image.convert("RGB"), dtype=np.int16)
    roi = values[480:721,650:801]
    red, green, blue = roi[:,:,0], roi[:,:,1], roi[:,:,2]
    mask = (red-green >= 10) & (green-blue >= 8) & (red-blue >= 35)
    inner, outer = [], []
    for row in range(len(mask)):
        columns = np.flatnonzero(mask[row])
        if len(columns):
            inner.append([float(650+columns[0]), 480+row+.5])
            outer.append([float(650+columns[-1]+1), 480+row+.5])
    return np.asarray(inner), np.asarray(outer)


def station_points(stations, elbow, wrist):
    origin, tangent, normal, length = axis_frame(elbow, wrist)
    return [dict(t=row["t"], inner=(origin+length*(row["t"]*tangent+row["inner"]*normal)).tolist(),
        outer=(origin+length*(row["t"]*tangent+row["outer"]*normal)).tolist()) for row in stations]


def annotate(image, elbow, wrist, stations, polylines=None):
    image = image.convert("RGB").copy()
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
    if polylines:
        for line in polylines:
            draw.line([tuple(point) for point in line], fill=(20,170,255), width=2)
    draw.line([tuple(elbow),tuple(wrist)], fill=(255,185,0), width=3)
    for name, point in (("E",elbow),("W",wrist)):
        x,y = point
        draw.ellipse((x-5,y-5,x+5,y+5), fill=(255,185,0), outline=(0,0,0), width=1)
        draw.text((x+8,y-10),name, font=font, fill=(255,100,20), stroke_width=1, stroke_fill=(255,255,255))
    for row in station_points(stations, elbow, wrist):
        draw.line([tuple(row["inner"]),tuple(row["outer"])], fill=(240,40,90), width=2)
        x,y = row["outer"]
        draw.text((x+6,y-8),str(round(100*row["t"]))+"%", font=font, fill=(240,40,90), stroke_width=1, stroke_fill=(255,255,255))
    return image


def main():
    started, cpu = time.perf_counter(), time.process_time()
    folder = HERE / "private/annotation"
    folder.mkdir(parents=True, exist_ok=True)
    views = json.loads((HERE / "BASE_VIEWS.json").read_bytes())
    front = next(row for row in views["views"] if row["specification"]["name"] == "forearm_front")
    model_image = Path(front["image"]["path"])
    inputs_before = [identity(path) for path in (REFERENCE,model_image,HERE / "private/cases/s01/baseline_readback.npz")]
    original = Image.open(REFERENCE)
    inner, outer = foreground_polylines(original)
    with np.load(HERE / "private/cases/s01/baseline_readback.npz", allow_pickle=False) as source:
        vertices, faces = source["vertices"], source["faces"]
    affine = np.asarray(front["world_to_image_affine_2_by_3"])
    offset = np.asarray(front["world_to_image_offset"])
    projected = vertices @ affine.T + offset
    reference = measure_polyline_sections(inner,outer,REFERENCE_E,REFERENCE_W,STATIONS)
    model = measure_projected_sections(projected,faces,MODEL_E,MODEL_W,STATIONS)
    residual = np.array([b["outer"]-a["outer"] for a,b in zip(reference,model)])
    yz = front_pixel_to_world_yz([MODEL_E,MODEL_W])
    draft = dict(status="draft_before_consumer_freeze", pixel_convention=front["pixel_convention"],
        anchors=dict(reference=dict(E=REFERENCE_E,W=REFERENCE_W, E_radius_pixels=6.,W_radius_pixels=5.),
            model_local=dict(E=MODEL_E,W=MODEL_W,E_radius_pixels=8.,W_radius_pixels=6.),model_world_yz_ideal_camera=yz.tolist()),
        anchor_basis=dict(E="Visible elbow articulation/crease center between upper-arm shaft and proximal forearm mass, identified with full body context",
            W="Narrow forearm immediately before palm expansion, identified with full forearm and hand context",
            uncertainty="Localization radii reflect anatomical center and wrist station ambiguity. Foreground contour boundary uncertainty is separately three original-reference pixels."),
        source_projection=dict(affine_2_by_3=affine.tolist(),offset=offset.tolist(), ideal_formula="u=320+(Y-.155)*640/.285; v=320-(Z-.565)*640/.285; actual measurements use exported affine including tiny camera rotation terms"),
        reference_foreground=dict(ROI_pixel_edges=[650,480,801,721], threshold="R-G>=10 and G-B>=8 and R-B>=35", inner_polyline=inner.tolist(),outer_polyline=outer.tolist(), boundary_uncertainty_pixels=3., rationale="Distinct actual arm skin/background foreground in this fixed ROI; all silhouettes are visible exterior boundaries"),
        stations=STATIONS, reference_sections=reference, model_sections=model,
        reference_intersections_pixel=station_points(reference,REFERENCE_E,REFERENCE_W),model_intersections_pixel=station_points(model,MODEL_E,MODEL_W),
        signed_residual_model_minus_reference=residual.tolist(), baseline_outer_MAE=float(np.mean(np.abs(residual))), baseline_outer_max_abs=float(np.max(np.abs(residual))),
        inputs=inputs_before, statistical_label="Single geometric annotation, anatomical localization and projected reference pose have recorded uncertainty")
    write(HERE / "ANNOTATION_DRAFT.json",draft)
    print(json.dumps(dict(reference=reference,model=model,residual=residual.tolist(),MAE=draft["baseline_outer_MAE"])),flush=True)
    annotate(original,REFERENCE_E,REFERENCE_W,reference,[inner,outer]).save(folder / "reference_annotated.png")
    annotate(Image.open(model_image),MODEL_E,MODEL_W,model).save(folder / "model_annotated.png")
    overlay = annotate(Image.open(model_image),MODEL_E,MODEL_W,model)
    draw = ImageDraw.Draw(overlay)
    for polyline in (inner,outer):
        aligned = align_similarity(polyline,REFERENCE_E,REFERENCE_W,MODEL_E,MODEL_W)
        draw.line([tuple(point) for point in aligned], fill=(20,170,255), width=3)
    overlay.save(folder / "similarity_contour_overlay.png")
    dense_stations = np.linspace(.25,.8,56)
    dense_ref = measure_polyline_sections(inner,outer,REFERENCE_E,REFERENCE_W,dense_stations)
    dense_model = measure_projected_sections(projected,faces,MODEL_E,MODEL_W,dense_stations)
    dense_residual = np.array([b["outer"]-a["outer"] for a,b in zip(dense_ref,dense_model)])
    angles = np.linspace(0,2*np.pi,8,endpoint=False)
    directions = np.vstack(([0.,0.],np.column_stack((np.cos(angles),np.sin(angles)))))
    bounds = {}
    for name, E, W, er, wr in (("reference",REFERENCE_E,REFERENCE_W,6.,5.),("model",MODEL_E,MODEL_W,8.,6.)):
        samples = []
        for de in directions:
            for dw in directions:
                moved_E,moved_W = np.asarray(E)+er*de,np.asarray(W)+wr*dw
                result = measure_polyline_sections(inner,outer,moved_E,moved_W,STATIONS) if name == "reference" else measure_projected_sections(projected,faces,moved_E,moved_W,STATIONS)
                samples.append([row["outer"] for row in result])
        bounds[name] = dict(scenarios=len(samples), minimum=np.min(samples,axis=0).tolist(),maximum=np.max(samples,axis=0).tolist())
    lower = np.asarray(bounds["model"]["minimum"])-np.asarray(bounds["reference"]["maximum"])
    upper = np.asarray(bounds["model"]["maximum"])-np.asarray(bounds["reference"]["minimum"])
    contour_uncertainty = 3./axis_frame(REFERENCE_E,REFERENCE_W)[3]
    draft["sensitivity"] = dict(anchor_scenarios=bounds, residual_minimum=(lower-contour_uncertainty).tolist(),residual_maximum=(upper+contour_uncertainty).tolist(),
        contour_uncertainty_normalized=contour_uncertainty, interpretation="Independent anchor-radius scenarios and three-pixel reference silhouette uncertainty. These are sensitivity envelopes, with no probabilistic confidence claim.")
    draft["dense_25_to_80"] = dict(stations=dense_stations.tolist(),residual=dense_residual.tolist())
    draft["input_bytes_unchanged"] = inputs_before == [identity(path) for path in (REFERENCE,model_image,HERE / "private/cases/s01/baseline_readback.npz")]
    draft["cost"] = dict(wall_s=time.perf_counter()-started,CPU_s=time.process_time()-cpu,source="ordinary local image annotation and mesh projection, no model calls or Blender rendering")
    write(HERE / "ANNOTATION_DRAFT.json",draft)
    print(json.dumps(dict(status="draft_complete",sensitivity=draft["sensitivity"],cost=draft["cost"])),flush=True)


if __name__ == "__main__":
    main()
