"""Retain V1 by default after the full-task optimization comparison."""

import difflib
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import identity,read,write


def main():
    if (HERE/"API_SELECTION.json").exists():
        raise ValueError("final_default_already_selected")
    versions=[]
    for stage,name in (("v1","TOOL_FREEZE.json"),("v2","TOOL_FREEZE_v2.json")):
        row=next(row for row in read(name)["files"] if row["path"]=="session_api.py")
        archive=HERE/row["archived"]["path"]
        if identity(archive)["sha256"]!=row["sha256"]:
            raise ValueError("archived_API_changed")
        versions.append((stage,archive,row["sha256"]))
    active=HERE/"session_api.py"
    if identity(active)["sha256"]!=versions[1][2]:
        raise ValueError("expected_executed_v2_API_before_selection")
    before,after=(row[1].read_bytes() for row in versions)
    patch="".join(difflib.unified_diff(before.decode().splitlines(keepends=True),after.decode().splitlines(keepends=True),
        fromfile="a/verification/m6_reference_consume_002/session_api.py",tofile="b/verification/m6_reference_consume_002/session_api.py"))
    (HERE/"OPTIMIZATION_DIFF.patch").write_text(patch,encoding="utf8",newline="\n")
    active.write_bytes(before)
    write("API_SELECTION.json",dict(default="v1",default_API=identity(active),
        executed_v1_source=identity(versions[0][1]),executed_v2_source=identity(versions[1][1]),candidate_patch=identity(HERE/"OPTIMIZATION_DIFF.patch"),
        evidence=dict(v1_session_wall_s=178.703435,v2_session_wall_s=199.64238,actual_readback_text_v1_bytes=46547,actual_readback_text_v2_bytes=29877,
            reference_geometry_improvement_established=False,formal_consumers_edited=0),
        decision="Keep the first-version default and preserve the compact candidate experiment. The repeated readback text was reduced, while the complete second-stage sessions were slower and used extra preceding tools.",
        attribution="Each second-stage extra Python tool occurred before its last readback response, so those added calls cannot be caused by that response deduplication. No general causal timing conclusion from this single task.",
        historical_freeze_policy="Validate each executed stage using its exact archived source bytes. Current default intentionally matches V1; V2 source and patch retain the actual experiment.",
        restored_after_actual_consumers_and_final_Blender_validation=True,additional_Pro=0,additional_Blender=0))
    print("default V1 restored, executed V2 and exact patch retained")


if __name__=="__main__":
    main()
