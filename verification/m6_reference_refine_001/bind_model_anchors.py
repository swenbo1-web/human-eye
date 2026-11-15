"""Bind manual model-image landmarks to visible triangles and source vertices."""

import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import numpy as np
from PIL import Image,ImageDraw,ImageFont


def identity(path):
    raw=Path(path).read_bytes()
    return dict(path=str(Path(path).resolve()),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def main():
    started,cpu=time.perf_counter(),time.process_time()
    draft_path=HERE/"ANNOTATION_DRAFT.json"
    draft_identity=identity(draft_path)
    draft=json.loads(draft_path.read_bytes())
    views=json.loads((HERE/"BASE_VIEWS.json").read_bytes())["views"]
    front=next(row for row in views if row["specification"]["name"]=="forearm_front")
    whole=next(row for row in views if row["specification"]["name"]=="whole_front")
    with np.load(HERE/"private/cases/s01/baseline_readback.npz",allow_pickle=False) as packet:
        vertices,faces=packet["vertices"],packet["faces"]
    initial=HERE.parent/"m6_refine_001/private/cases/s01/initial.npz"
    with np.load(initial,allow_pickle=False) as packet:
        seed=packet["F_source_ids"]
    projection=np.asarray(front["world_to_image_affine_2_by_3"])
    offset=np.asarray(front["world_to_image_offset"])
    uv=vertices@projection.T+offset
    backward=np.asarray(front["camera_matrix_world"])[:3,2]
    depth=vertices@backward
    triangle=uv[faces]
    first=triangle[:,1]-triangle[:,0]
    second=triangle[:,2]-triangle[:,0]
    denominator=first[:,0]*second[:,1]-first[:,1]*second[:,0]

    def front_hit(point):
        delta=point-triangle[:,0]
        a=np.divide(delta[:,0]*second[:,1]-delta[:,1]*second[:,0],denominator,out=np.zeros(len(faces)),where=np.abs(denominator)>1e-12)
        b=np.divide(first[:,0]*delta[:,1]-first[:,1]*delta[:,0],denominator,out=np.zeros(len(faces)),where=np.abs(denominator)>1e-12)
        mask=(np.abs(denominator)>1e-12)&(a>=-1e-7)&(b>=-1e-7)&(a+b<=1+1e-7)
        rows=np.flatnonzero(mask)
        if not len(rows):
            raise ValueError("landmark_ray_has_no_mesh_intersection")
        weights=np.column_stack((1-a[rows]-b[rows],a[rows],b[rows]))
        positions=np.einsum("ij,ijk->ik",weights,vertices[faces[rows]])
        chosen=int(np.argmax(positions@backward))
        return int(rows[chosen]),weights[chosen],positions[chosen]

    landmarks={}
    for name in ("E","W"):
        point=np.asarray(draft["anchors"]["model_local"][name])
        face,weights,surface=front_hit(point)
        distances=np.linalg.norm(uv-point,axis=1)
        for source_id in np.argsort(distances):
            if distances[source_id]>30:
                raise ValueError("no_visible_vertex_close_to_landmark")
            ray_face,ray_weights,ray_position=front_hit(uv[source_id])
            gap=float(ray_position@backward-depth[source_id])
            if gap<=2e-6:
                break
        landmarks[name]=dict(annotation_pixel=point.tolist(),visible_surface_triangle=face,
            visible_surface_triangle_source_ids=faces[face].tolist(),barycentric_weights=weights.tolist(),surface_world=surface.tolist(),
            nearest_visible_source_id=int(source_id),nearest_visible_world=vertices[source_id].tolist(),
            source_vertex_projected_pixel=uv[source_id].tolist(),source_vertex_pixel_distance=float(distances[source_id]),
            visibility_depth_gap_world=gap,visibility_tolerance_world=2e-6,
            visibility_definition="frontmost ray intersection of the full source mesh at the source vertex's projected location, along actual saved orthographic camera backward direction")
    font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf",16)
    outputs=[]
    for view in (whole,front):
        image=Image.open(view["image"]["path"]).convert("RGB")
        draw=ImageDraw.Draw(image)
        p=vertices@np.asarray(view["world_to_image_affine_2_by_3"]).T+np.asarray(view["world_to_image_offset"])
        for x,y in p[seed]:
            draw.ellipse((x-1.5,y-1.5,x+1.5,y+1.5),fill=(245,55,70))
        for name,row in landmarks.items():
            point=np.asarray(row["nearest_visible_world"])@np.asarray(view["world_to_image_affine_2_by_3"]).T+np.asarray(view["world_to_image_offset"])
            x,y=point
            draw.ellipse((x-5,y-5,x+5,y+5),fill=(255,190,0),outline=(0,0,0),width=1)
            draw.text((x+8,y-14),name+" #"+str(row["nearest_visible_source_id"]),fill=(255,125,0),font=font,stroke_width=1,stroke_fill=(255,255,255))
        path=HERE/"private/annotation"/(view["specification"]["name"]+"_source_mapping.png")
        image.save(path)
        outputs.append(identity(path))
    result=dict(status="pass",landmarks=landmarks,old_spatial_seed=dict(points=len(seed),source_ids=seed.tolist(),
        bbox_world_min=vertices[seed].min(axis=0).tolist(),bbox_world_max=vertices[seed].max(axis=0).tolist(),
        mapping_images=outputs),annotation_bytes_unchanged=draft_identity==identity(draft_path),
        projection=identity(HERE/"BASE_VIEWS.json"),baseline=identity(HERE/"private/cases/s01/baseline_readback.npz"),
        world_X_semantics="+X is the camera-facing side of this original mesh in the fixed front view",
        wall_s=time.perf_counter()-started,CPU_s=time.process_time()-cpu)
    (HERE/"MODEL_ANCHOR_BINDING.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8",newline="\n")
    print(json.dumps({key:result[key] for key in ("landmarks","wall_s","CPU_s")}))


if __name__=="__main__":
    main()
