"""Independent visual elbow/wrist annotation, with no contour targets loaded."""

from pathlib import Path
import hashlib
import json
import time
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REFERENCE = Path("D:/Projects/fps/outputs/character-design/Yanyite/Yanyite_Front_v1.png")
WHOLE = HERE / "private/views/before/whole_front.png"
FRONT = HERE / "private/views/before/forearm_front.png"


def grid_crop(path, box, output):
    with Image.open(path) as original:
        view = original.convert("RGB").crop(box).resize(((box[2]-box[0])*2, (box[3]-box[1])*2))
    draw = ImageDraw.Draw(view)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 15)
    for x in range((box[0]//20+1)*20, box[2], 20):
        pixel = 2*(x-box[0])
        draw.line((pixel,0,pixel,view.height), fill=(180,80,90), width=1)
        draw.text((pixel+2,2),str(x),font=font,fill=(220,20,30))
    for y in range((box[1]//20+1)*20, box[3], 20):
        pixel = 2*(y-box[1])
        draw.line((0,pixel,view.width,pixel),fill=(180,80,90),width=1)
        draw.text((2,pixel+2),str(y),font=font,fill=(220,20,30))
    output.parent.mkdir(parents=True,exist_ok=True)
    view.save(output)


def annotated(path, anchors, output):
    with Image.open(path) as original:
        view = original.convert("RGB")
    draw = ImageDraw.Draw(view)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 16)
    centers = [anchors[name]["pixel_xy"] for name in ("E", "W")]
    draw.line(tuple(tuple(point) for point in centers), fill=(190,80,190), width=2)
    for name, color in (("E", (220,35,30)), ("W", (25,75,220))):
        row = anchors[name]
        x,y = row["pixel_xy"]
        dx,dy = row["manual_uncertainty_plus_minus_xy_px"]
        draw.ellipse((x-dx,y-dy,x+dx,y+dy), outline=color, width=2)
        draw.line((x-5,y,x+5,y),fill=color,width=2)
        draw.line((x,y-5,x,y+5),fill=color,width=2)
        label = f"{name} ({x:.1f}, {y:.1f})"
        position = (x+15,y-22)
        bounds = draw.textbbox(position,label,font=font)
        if bounds[2] > view.width-3:
            position = (x-15-(bounds[2]-bounds[0]),y-22)
            bounds = draw.textbbox(position,label,font=font)
        draw.rectangle((bounds[0]-2,bounds[1]-2,bounds[2]+2,bounds[3]+2),fill=(245,245,245))
        draw.text(position,label,font=font,fill=color)
    output.parent.mkdir(parents=True,exist_ok=True)
    view.save(output)


def save_independent():
    started, cpu = time.perf_counter(), time.process_time()
    directory = HERE / "private/independent_anchors"
    reference = dict(
        E=dict(pixel_xy=[708.,524.],manual_uncertainty_plus_minus_xy_px=[8.,12.],
            basis="Center of the elbow-level arm section at the visible medial bend/crease, between the arm silhouette boundaries. The crease helps locate the level, while its dark shading is excluded from the silhouette."),
        W=dict(pixel_xy=[751.,678.],manual_uncertainty_plus_minus_xy_px=[7.,12.],
            basis="Center of the narrow distal forearm shaft immediately proximal to the outward wrist bump and the broadening hand. The exact transition extends along several rows."))
    model = dict(
        E=dict(pixel_xy=[274.,140.],manual_uncertainty_plus_minus_xy_px=[10.,15.],
            basis="Center of the projected elbow section at the upper-arm to forearm bend visible around the medial elbow crease. The faceted shading and gradual outer silhouette transition leave the joint-center level ambiguous."),
        W=dict(pixel_xy=[350.,393.],manual_uncertainty_plus_minus_xy_px=[8.,18.],
            basis="Center of the narrow distal forearm shaft above the wrist's outward bump and the hand/thenar expansion. A short slanted segment is plausibly the pre-wrist minimum, so longitudinal uncertainty is wider than a crisp pixel edge."))
    # Orthographic camera specifications are from the supplied real-view script.
    # This mapping only transfers the independent local annotations to the whole
    # view for an anatomical context check.
    ratio = (.285/640)/(1.07/800)
    whole = {}
    for name, row in model.items():
        x,y = row["pixel_xy"]
        dx,dy = row["manual_uncertainty_plus_minus_xy_px"]
        whole[name] = dict(pixel_xy=[240+.155/(1.07/800)+(x-320)*ratio,
            400-.065/(1.07/800)+(y-320)*ratio],
            manual_uncertainty_plus_minus_xy_px=[dx*ratio,dy*ratio], basis="Projection of independently chosen local anchor through the supplied orthographic camera specifications")
    inputs = []
    for path in (REFERENCE,WHOLE,FRONT):
        raw = path.read_bytes()
        with Image.open(path) as view:
            size = list(view.size)
        inputs.append(dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),size=size))
    annotated(REFERENCE,reference,directory / "reference_anchors.png")
    annotated(FRONT,model,directory / "model_front_anchors.png")
    annotated(WHOLE,whole,directory / "model_whole_anchors.png")
    result = dict(observer="reference_consumer independent visual annotation", status="independent_manual_annotation_complete",
        inputs=inputs, pixel_convention="continuous image coordinates, top-left edge origin, x right, y down",
        reference=reference, model_front=model, model_whole_projected=whole,
        uncertainty_interpretation="Manual plausible location intervals based on visible anatomical transitions and silhouette ambiguity. These are per-axis plus/minus bounds, not statistical confidence intervals.",
        independence=dict(other_annotation_or_target_numbers_read=False, desired_edit_sign_used=False,
            prior_information="Root noted that another annotator's measurements may fall within uncertainty, but supplied no landmark values or edit sign. The observer inspected the three raw real images and coordinate-grid crops before fixing these points."),
        visual_context="The target is the arm on the reference image's right and the model's positive-Y arm. Elbow and pre-wrist locations were selected on the arm between sleeve and hand, supported by the whole-body view.",
        limitation="The visible elbow crease and wrist shaft transition occupy a range. A tighter joint correspondence would require additional independently marked views or author-provided anatomical landmarks.",
        images=[str((directory/name).relative_to(HERE)) for name in ("reference_anchors.png","model_front_anchors.png","model_whole_anchors.png","reference_grid.png","model_grid.png")],
        annotation_wall_s=time.perf_counter()-started, parent_CPU_s=time.process_time()-cpu,
        source_probe=dict(matplotlib_available=False, resolution="Pillow coordinate plots and overlays",probe_wall_s=None),
        root_model_or_reference_file_edits=0, Pro_sessions=0, Blender_calls=0, training_runs=0)
    (HERE / "INDEPENDENT_ANCHORS.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8",newline="\n")
    print(json.dumps(dict(reference=reference,model_front=model,annotation_wall_s=result["annotation_wall_s"])),flush=True)


if __name__ == "__main__":
    directory = HERE / "private/independent_anchors"
    grid_crop(REFERENCE,(630,420,805,765),directory / "reference_grid.png")
    grid_crop(FRONT,(180,80,425,470),directory / "model_grid.png")
    save_independent()
