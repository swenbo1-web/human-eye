"""Prepare one shared editable forearm task and four independent source copies."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "m6_reference_refine_001"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "m6_shape_pretrain_001/private/deps"))
import numpy as np


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf8", newline="\n")


def identity(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def session(stage, route, directory):
    destination = HERE / "private/sessions" / (stage + "_forearm_" + route)
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(directory / "before.blend", destination / "before.blend")
    state = dict(stage=stage,case_id="forearm",route=route,version=0,case_dir=str(directory),
        current_blend=str(destination / "before.blend"),current_npz=str(directory / "initial.npz"),
        initial_npz=str(directory / "initial.npz"),current_scene=str(directory / "baseline_scene.json"),
        source_spec=str(directory / "spec.json"),current_blend_identity=identity(destination / "before.blend"),operations=[],pending=None)
    write(destination / "session.json",state)
    return destination


def main():
    started,cpu=time.perf_counter(),time.process_time()
    directory=HERE / "private/cases/forearm"
    directory.mkdir(parents=True,exist_ok=False)
    for source,target in (("docs/M6_REFERENCE_CONSUME_002_TASK.md","CONTRACT.md"),("docs/M6_REFERENCE_REFINE_001_REVIEW.md","PRIOR_REVIEW.md")):
        raw=subprocess.check_output(["git","-C","C:/Users/Administrator/.codex/worktrees/1212/hefe","show","7dbcc26e0cdc0bbe8ae984f9d56f00e43300d93d:"+source])
        (HERE/target).write_bytes(raw)
    for name,source in (("before.blend",OLD/"private/cases/s01/before.blend"),("baseline_scene.json",OLD/"private/cases/s01/baseline_scene.json")):
        shutil.copyfile(source,directory/name)
    with np.load(OLD/"private/cases/s01/observation.npz",allow_pickle=False) as source:
        arrays={key:source[key] for key in source.files}
    F=arrays["F_source_ids"].astype(np.int64)
    if len(F)!=599:
        raise AssertionError("fixed599point_source_scope_required")
    observation=read(OLD/"OBSERVATION.json")
    annotation=read(OLD/"ANNOTATION_DRAFT.json")
    geometry_path=OLD/"reference_geometry.py"
    import importlib.util
    spec_loader=importlib.util.spec_from_file_location("_consume_fixed_projection",geometry_path)
    geometry=importlib.util.module_from_spec(spec_loader)
    spec_loader.loader.exec_module(geometry)
    P=arrays["projected_pixels"]
    normalized=[]
    for name in ("primary_anchors","alternative_anchors"):
        anchors=observation[name]["model"]
        normalized.append(geometry.normalized_coordinates(P,anchors["E"],anchors["W"]))
    # Both supplied landmark definitions get endpoint guards. Consumers choose
    # the remaining active patch and transition themselves within the599 scope.
    endpoint=np.zeros(len(P),dtype=bool)
    for coordinates in normalized:
        endpoint |= (coordinates[:,0] <= .05) | (coordinates[:,0] >= .95)
    anchor_guard=np.intersect1d(F,np.flatnonzero(endpoint))
    I=np.setdiff1d(F,anchor_guard)
    protected=np.setdiff1d(np.arange(len(P)),I)
    if len(I)==0:
        raise AssertionError("consumer_edit_domain_must_be_nonempty")
    faces=arrays["faces"]
    local_faces=faces[np.isin(faces,F).all(axis=1)]
    edges=np.unique(np.sort(np.concatenate((local_faces[:,[0,1]],local_faces[:,[1,2]],local_faces[:,[2,0]])),axis=1),axis=0)
    interior_edges=edges[np.isin(edges,I).all(axis=1)]
    ell=float(np.median(np.linalg.norm(arrays["vertices"][interior_edges[:,0]]-arrays["vertices"][interior_edges[:,1]],axis=1)))
    limit=.11*ell
    arrays["I_ids"]=I
    arrays["protected_ids"]=protected
    arrays["anchor_guard_ids"]=anchor_guard
    np.savez_compressed(directory/"initial.npz",**arrays)
    original=read(OLD/"SOURCES.json")["cases"][0]
    specification=dict(case_id="forearm",unit="m",object_name=original["object_name"],source_original=original["source_original"],
        base_blend_path=str(directory/"before.blend"),initial_npz=str(directory/"initial.npz"),baseline_scene=str(directory/"baseline_scene.json"),
        annotation_path=str(OLD/"ANNOTATION_DRAFT.json"),observation_path=str(OLD/"OBSERVATION.json"),
        max_cumulative_displacement_m=limit,max_operation_displacement_m=limit,max_displacement=limit,
        world_preservation_tol=1e-6,require_scene_preservation=True,ell=ell,
        protection_definition="Fixed599 source domain, with both given EW definitions protected for axial coordinates t<=0.05 or t>=0.95; full source complement of I protected. Inner contour and depth are evaluated and preserved by the consumer's task choice.",
        quality_gate=dict(max_gradient=.2,max_normal_change_deg=5.),
        reference_definition="Five fixed stations for both existing EW anchor definitions, measuring inner/outer/width/centerline. Technical status and reference improvement are separate.",
        uncertainty_policy="Give both existing definitions and uncertainty to actual visual consumers. They decide with explicit evidence; uncertainty never skips consumption.")
    write(directory/"spec.json",specification)
    for stage,route in (("v1","native"),("v1","facts"),("v2","facts"),("v2","native")):
        session(stage,route,directory)
    case=HERE/"private/consumer_cases/forearm"
    case.mkdir(parents=True,exist_ok=False)
    np.savez_compressed(case/"input.npz",**arrays)
    write(HERE/"CASE_BINDING.json",dict(F_points=len(F),editable_points=len(I),anchor_guard_points=len(anchor_guard),protected_points=len(protected),
        I_source_identity=dict(sha256=hashlib.sha256(np.ascontiguousarray(I).tobytes()).hexdigest(),dtype=str(I.dtype),shape=list(I.shape)),
        ell_m=ell,max_cumulative_displacement_m=limit,max_operation_displacement_m=limit,
        originals=[identity(Path(original["source_original"])),identity(Path(read(OLD/"INPUT_BINDING.json")["inputs"][0]["path"]))],
        reused_initial=identity(OLD/"private/cases/s01/observation.npz"),new_initial=identity(directory/"initial.npz"),source_spec=identity(directory/"spec.json"),
        contract_commit="7dbcc26e0cdc0bbe8ae984f9d56f00e43300d93d",baseline_commit="9a759efd7d4acdbc7917fad709d350bd86b33ae2",
        wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu,reference_fields_changed=False))
    print("fixed F",len(F),"editable I",len(I),"endpoint guard",len(anchor_guard),"max displacement m",limit,flush=True)


if __name__=="__main__":
    main()
