"""Check exact additional arrays and current-version reference rejection."""

import json
from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read,write,identity
import facts_api
import numpy as np


def main():
    started,cpu=time.perf_counter(),time.process_time()
    evidence=read("private/quality_preflight/facts_delivery/PUBLIC_REFERENCE.json")
    packet=evidence["additional_geometry_packet"]
    packet_path=Path(packet["path"])
    original_path=packet_path.parent.parent/"private/resolved"/(packet_path.stem[1:]+".json")
    original=read(original_path)
    checks={}
    with np.load(packet_path,allow_pickle=False) as arrays:
        for key in ("source_ids","current_vertex_normals","lumped_area_world"):
            expected=np.asarray(original[key],dtype=arrays[key].dtype)
            checks["descriptor_exact_"+key]=expected.shape==arrays[key].shape and expected.tobytes()==arrays[key].tobytes()
    session=HERE/"private/sessions/facts_delivery_preflight"
    case=HERE/"private/cases/forearm"
    state=dict(case_id="forearm",version=0,current_npz=str(case/"initial.npz"),initial_npz=str(case/"initial.npz"),source_spec=str(case/"spec.json"))
    reference=evidence["reference"]
    try:
        facts_api.resolve_ref(session,dict(state,version=1),reference)
    except ValueError as error:
        checks["stale_reference_rejected"]=str(error)=="region_reference_outside_current_session_version"
    other=HERE/"private/sessions/facts_descriptor_other"
    other.mkdir(parents=True,exist_ok=False)
    try:
        facts_api.resolve_ref(other,state,reference)
    except ValueError as error:
        checks["cross_session_reference_rejected"]=str(error)=="region_reference_outside_current_session_version"
    try:
        facts_api.focus(session,dict(state,current_npz=str(HERE/"private/quality_preflight/tiny_saved_precision.npz")))
    except ValueError as error:
        checks["geometry_change_without_version_rejected"]=str(error)=="geometry_or_scope_changed_without_session_version"
    result=dict(status="pass" if all(checks.values()) else "fail",checks=checks,passed=sum(checks.values()),total=len(checks),
        wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu,Pro_calls=0,Blender_calls=0,
        raw_resolve_identity=identity(original_path),packet_identity=identity(packet_path),sources=[identity(HERE/"facts_api.py"),identity(Path(__file__))])
    write("FACTS_DESCRIPTOR_CHECKS.json",result)
    print(result["status"],len(checks),result["wall_s"])
    if result["status"]!="pass":
        raise SystemExit(1)


if __name__=="__main__":
    main()
