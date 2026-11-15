"""Copy the two authorized sources and prepare source-ID seed arrays."""

from pathlib import Path
import shutil
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import ROOT,identity,read,write
import numpy as np


def main():
    started,cpu=time.perf_counter(),time.process_time()
    if (HERE/"SOURCES.json").exists():
        raise RuntimeError("source_preparation_already_completed")
    planning="C:/Users/Administrator/.codex/worktrees/1212/hefe"
    for source,dest in (("docs/M6_REFINE_001_TASK.md","CONTRACT.md"),("verification/m6_refine_001_plan/PREFLIGHT.json","PLANNING_PREFLIGHT.json")):
        (HERE/dest).write_bytes(subprocess.check_output(["git","-C",planning,"show","2ef3ce26d1e7a821170eecefcd22714a65a06e40:"+source]))
    original=Path("D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend")
    old=HERE.parent/"m6_real_data_001"
    expected="614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d"
    current_identity=identity(original)
    historical=old/"private/Yanyite_Appearance.blend"
    if identity(historical)["sha256"]!=expected:
        raise ValueError("historical_verified_source_changed")
    chosen=original if current_identity["sha256"]==expected else historical
    raw=__import__("json").loads((old/"private/capture_02/raw_selected.json").read_bytes())
    region=__import__("json").loads((old/"private/ARM_REGION.json").read_bytes())
    if region["source_sha256"]!=expected:
        raise ValueError("source_region_identity_mismatch")
    source_cases=[]
    for case_id in ("s01","s02"):
        (HERE/"private/cases"/case_id).mkdir(parents=True,exist_ok=True)
    ydir=HERE/"private/cases/s01"
    shutil.copyfile(chosen,ydir/"before.blend")
    np.savez_compressed(ydir/"seed.npz",vertices=np.asarray(raw["vertices_world"],dtype=np.float64),
        vertices_local=np.asarray(raw["vertices_object"],dtype=np.float32),faces=np.asarray(raw["triangles"],dtype=np.int64),
        F_source_ids=np.asarray(region["source_vertex_ids"],dtype=np.int64),matrix_world=np.asarray(raw["matrix_world"],dtype=np.float64))
    source_cases.append(dict(case_id="s01",source_type="Yanyite",unit="m",object_name=raw["object_name"],
        source_original=str(original),source_identity=current_identity,source_used=identity(chosen),base_blend_path=str(ydir/"before.blend"),
        initial_seed=str(ydir/"seed.npz"),F_points=410,center_source_id=24205,region_source=identity(old/"private/ARM_REGION.json"),
        native_source_arrays=identity(old/"private/capture_02/raw_selected.json")))
    fdir=HERE/"private/cases/s02"
    packet=HERE.parent/"m6_task_perception_001/private/current/o0002.npz"
    if identity(packet)["sha256"]!="43fd6c95e7339a11ec0a8e8e7d0020165e927896da3cdf62f098b641a1d52939":
        raise ValueError("face_current_packet_changed")
    with np.load(packet) as data:
        np.savez_compressed(fdir/"seed.npz",vertices=data["vertices"],vertices_local=data["vertices"].astype(np.float32),
            faces=data["faces"],F_source_ids=data["F_source_ids"].astype(np.int64),matrix_world=np.eye(4))
    source_cases.append(dict(case_id="s02",source_type="face",unit="native_unknown",object_name="refinement_surface",source_original=str(packet),
        source_identity=identity(packet),source_used=identity(packet),base_blend_path=str(fdir/"before.blend"),
        initial_seed=str(fdir/"seed.npz"),F_points=384,center_source_id=None,source_alias="o0002",roi_alias="r006"))
    write("SOURCES.json",dict(cycle_id="M6-REFINE-001",cases=source_cases,original_source_changed_since_contract=current_identity["sha256"]!=expected,
        source_changes=0,source_before=current_identity,source_after=identity(original),
        wall_s_before_write=time.perf_counter()-started,cpu_s_before_write=time.process_time()-cpu))
    print("two source seeds and isolated baseline paths prepared",flush=True)


if __name__=="__main__":
    main()
