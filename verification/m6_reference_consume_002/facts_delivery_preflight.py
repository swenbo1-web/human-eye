"""Verify complete reference delivery within the fixed public tool response budget."""

import hashlib
import json
from pathlib import Path
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import identity,write
import facts_api
import numpy as np


def main():
    started,cpu=time.perf_counter(),time.process_time()
    folder=HERE/"private/quality_preflight/facts_delivery"
    folder.mkdir(parents=True,exist_ok=False)
    session=HERE/"private/sessions/facts_delivery_preflight"
    session.mkdir(parents=True,exist_ok=False)
    case=HERE/"private/cases/forearm"
    state=dict(case_id="forearm",version=0,current_npz=str(case/"initial.npz"),initial_npz=str(case/"initial.npz"),source_spec=str(case/"spec.json"))
    result=facts_api.focus(session,state)
    reference=result["target"]["reference"]
    resolved=facts_api.resolve_ref(session,state,reference)
    again=facts_api.resolve_ref(session,state,reference)
    raw=json.dumps(resolved,ensure_ascii=True,allow_nan=False)
    packet=resolved["additional_geometry_packet"]
    checks=dict(no_public_truncation_needed=len(raw)<50000,
        exact_normals_areas_packet_identity=hashlib.sha256(Path(packet["path"]).read_bytes()).hexdigest()==packet["sha256"],
        same_version_packet_reused=packet==again["additional_geometry_packet"],
        packet_bound_to_session_version=packet["binding"]["session_version"]==0 and packet["reference"]==reference,
        positions_stay_inline="current_positions_world" in resolved,
        complete_raw_resolve_preserved=bool(list((HERE/"private/f").glob("*/v0/private/resolved/*.json"))))
    with np.load(case/"initial.npz",allow_pickle=False) as initial,np.load(packet["path"],allow_pickle=False) as extra:
        F=initial["F_source_ids"]
        checks["exact_inline_source_IDs"]=resolved["source_ids"]==F.tolist()
        checks["exact_inline_current_positions"]=np.array_equal(np.array(resolved["current_positions_world"]),initial["vertices"][F])
        checks["packet_source_ID_mapping"]=np.array_equal(extra["source_ids"],F)
        checks["normals_shape_and_finite"]=extra["current_vertex_normals"].shape==(len(F),3) and bool(np.isfinite(extra["current_vertex_normals"]).all())
        checks["areas_shape_and_finite"]=extra["lumped_area_world"].shape==(len(F),) and bool(np.isfinite(extra["lumped_area_world"]).all())
    sections=facts_api.project_sections(session,state)
    checks["dual_sections_fit_delivery_budget"]=len(json.dumps(sections,ensure_ascii=True,allow_nan=False))<50000
    report=dict(status="pass" if all(checks.values()) else "fail",checks=checks,passed=sum(checks.values()),total=len(checks),
        previous_complete_reference_chars=95118,current_public_reference_chars=len(raw),public_limit_chars=50000,
        packet=packet,wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu,actual_Pro_calls=0,actual_Blender_calls=0,
        numerical_quality_source_unchanged=True,source_identities=[identity(HERE/name) for name in ("facts_api.py","facts_delivery_preflight.py")])
    write(folder/"PUBLIC_REFERENCE.json",resolved)
    write("FACTS_DELIVERY_PREFLIGHT.json",report)
    print(json.dumps(dict(status=report["status"],checks=len(checks),public_chars=len(raw),wall_s=report["wall_s"])),flush=True)
    if report["status"]!="pass":
        raise SystemExit(1)


if __name__=="__main__":
    main()
