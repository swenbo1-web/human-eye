"""Version-bound current region references and dual-correspondence projection facts."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parent / "m6_shape_pretrain_001/private/deps"))
import numpy as np
from quality import compare_contours

specification=importlib.util.spec_from_file_location("_consume002_reused_focus",HERE.parent / "m6_task_perception_001/interfaces.py")
FOCUS=importlib.util.module_from_spec(specification)
specification.loader.exec_module(FOCUS)


def digest(*arrays):
    result=hashlib.sha256()
    for value in arrays:
        value=np.ascontiguousarray(value)
        result.update(json.dumps(dict(dtype=str(value.dtype),shape=list(value.shape)),sort_keys=True).encode())
        result.update(value.tobytes())
    return result.hexdigest()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=True,indent=2,allow_nan=False)+"\n",encoding="utf8",newline="\n")


def path_for(session,value):
    path=Path(value)
    return path if path.is_absolute() else Path(session)/path


def prepare(session,state):
    session=Path(session).resolve()
    version=state["version"]
    if type(version) is not int or version<0:
        raise ValueError("current_nonnegative_integer_session_version_required")
    with np.load(path_for(session,state["current_npz"]),allow_pickle=False) as archive:
        current={key:archive[key] for key in archive.files}
    with np.load(path_for(session,state["initial_npz"]),allow_pickle=False) as archive:
        initial={key:archive[key] for key in archive.files}
    vertices=current["vertices_world"] if "vertices_world" in current else current["vertices"]
    faces=current["faces"]
    ids=current.get("source_ids",np.arange(len(vertices),dtype=np.int64))
    if not np.array_equal(ids,np.arange(len(vertices))):
        raise ValueError("preserved_full_source_ID_indexing_required")
    F=np.asarray(initial["F_source_ids"],dtype=np.int64)
    I=np.asarray(initial["I_ids"],dtype=np.int64)
    if not len(I) or len(np.unique(I))!=len(I) or not np.isin(I,F).all():
        raise ValueError("nonempty_unique_edit_domain_within_F_required")
    protected=np.setdiff1d(F,I)
    source_spec=state["source_spec"]
    if not isinstance(source_spec,dict):
        source_spec=json.loads(path_for(session,source_spec).read_bytes())
    session_key=hashlib.sha256(str(session).casefold().encode()).hexdigest()
    logical=dict(session_key=session_key,session_version=version,case_id=state.get("case_id","forearm"),
        current_geometry_sha256=digest(vertices,faces,ids),scope_sha256=digest(F,I),unit=source_spec.get("unit","m"))
    directory=HERE / "private/f" / session_key[:10] / ("v"+str(version))
    directory.mkdir(parents=True,exist_ok=True)
    binding_path=directory/"BINDING.json"
    packet=directory/"g.npz"
    alias="rc"+session_key+"v"+str(version)
    if binding_path.exists():
        binding=json.loads(binding_path.read_bytes())
        if binding["logical"]!=logical:
            raise ValueError("geometry_or_scope_changed_without_session_version")
        if hashlib.sha256(packet.read_bytes()).hexdigest()!=binding["packet_sha256"]:
            raise ValueError("versioned_focus_packet_modified")
        expected=dict(cases=[dict(alias=alias,input=dict(path="g.npz",sha256=binding["packet_sha256"]))])
        if json.loads((directory/"INPUT_INDEX.json").read_bytes())!=expected:
            raise ValueError("versioned_focus_index_modified")
    else:
        np.savez_compressed(packet,vertices=vertices,faces=faces,F_source_ids=F)
        packet_sha=hashlib.sha256(packet.read_bytes()).hexdigest()
        write(directory/"INPUT_INDEX.json",dict(cases=[dict(alias=alias,input=dict(path="g.npz",sha256=packet_sha))]))
        write(binding_path,dict(logical=logical,packet_sha256=packet_sha))
    return FOCUS.TaskPerception(directory),directory,alias,logical,current,initial,F,I,protected,source_spec


def world_geometry(facts,unit):
    facts["coordinate_space"]="Blender_world"
    facts["physical_unit"]=unit
    facts["centroid_world"]=facts.pop("centroid_native")
    facts["bbox_world"]=facts.pop("bbox_native")
    facts["lumped_area_world"]=facts.pop("lumped_area_native")
    facts["area_unit"]=unit+"^2"


def focus(session,state):
    started,cpu=time.perf_counter(),time.process_time()
    prototype,directory,alias,logical,current,initial,F,I,protected,source_spec=prepare(session,state)
    result=prototype.focus(alias,F,protected,request="Observe the existing positive-Y forearm, its editable interior and protected elbow/wrist/hand guards.")
    for role in ("target","background","protected","context"):
        region=result[role]
        if region is not None:
            world_geometry(region["geometry"],logical["unit"])
            region["read_more"]=dict(resolver="resolve_ref",reference=region["reference"])
    result["session_binding"]=logical
    result["task_geometry_roles"]=dict(observation_F_points=len(F),editable_I_points=len(I),local_protected_points=len(protected),
        full_source_points=len(current["vertices"]),outside_I_protection="Every full-source point outside I is protected from editing",
        full_source_protected_points=len(current["vertices"])-len(I))
    result["editable_source_ids"]=I.tolist()
    result["cost"].update(wall_s=time.perf_counter()-started,CPU_s=time.process_time()-cpu,
        scope="saved current NPZ reads, full version identity validation and reused geometry focus")
    return result


def resolve_ref(session,state,reference):
    started,cpu=time.perf_counter(),time.process_time()
    prototype,directory,alias,logical,*_=prepare(session,state)
    prefix=FOCUS.REFERENCE_PREFIX
    if not isinstance(reference,str) or not reference.startswith(prefix):
        raise ValueError("invalid_region_reference")
    digest_value=reference[len(prefix):]
    if len(digest_value)!=64 or any(value not in "0123456789abcdef" for value in digest_value):
        raise ValueError("invalid_region_reference_digest")
    if not (directory/"private/references"/(digest_value+".json")).exists():
        raise ValueError("region_reference_outside_current_session_version")
    result=prototype.resolve(reference,include_geometry=True)
    if result["identity"]["observation_alias"]!=alias:
        raise ValueError("region_reference_alias_version_mismatch")
    world_geometry(result["geometry"],logical["unit"])
    result["current_positions_world"]=result.pop("current_positions_native")
    result["lumped_area_world"]=result.pop("lumped_area_native")
    result["session_binding"]=logical
    write(directory/"private/resolved"/(digest_value[:16]+".json"),result)
    arrays=dict(source_ids=np.asarray(result["source_ids"],dtype=np.int64),
        current_vertex_normals=np.asarray(result.pop("current_vertex_normals"),dtype=np.float64),
        lumped_area_world=np.asarray(result.pop("lumped_area_world"),dtype=np.float64))
    packet=directory/"arrays"/("a"+digest_value[:16]+".npz")
    packet.parent.mkdir(parents=True,exist_ok=True)
    if packet.exists():
        with np.load(packet,allow_pickle=False) as archive:
            if set(archive.files)!=set(arrays) or any(archive[key].dtype!=value.dtype or archive[key].tobytes()!=value.tobytes() for key,value in arrays.items()):
                raise ValueError("current_reference_extra_array_packet_changed")
    else:
        np.savez_compressed(packet,**arrays)
    raw=packet.read_bytes()
    result["additional_geometry_packet"]=dict(path=str(packet),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
        arrays={key:dict(dtype=str(value.dtype),shape=list(value.shape)) for key,value in arrays.items()},
        binding=logical,reference=reference,read_with="ordinary NumPy np.load(path, allow_pickle=False)")
    result["cost"].update(wall_s=time.perf_counter()-started,CPU_s=time.process_time()-cpu)
    return result


def project_sections(session,state):
    started,cpu=time.perf_counter(),time.process_time()
    prototype,directory,alias,logical,current,initial,F,I,protected,source_spec=prepare(session,state)
    changed=int(np.any(current["vertices_local"].view(np.uint32)!=initial["vertices_local"].view(np.uint32),axis=1).sum())
    result=compare_contours(initial["vertices"],initial["faces"],current["vertices"],current["faces"],source_spec,changed)
    result["session_binding"]=logical
    result["cost"]=dict(wall_s=time.perf_counter()-started,CPU_s=time.process_time()-cpu,
        scope="actual current saved geometry, frozen reference polylines and both existing EW definitions")
    return result
