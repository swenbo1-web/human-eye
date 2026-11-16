"""Archive exact calibration inputs and per-stage executable sources."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import BLENDER, PYTHON, identity, read, write

RUNTIME = ("common.py", "background.py", "blender_common.py", "blender_edit.py", "blender_read.py",
    "blender_render.py", "session_api.py", "quality.py", "evaluate.py", "image_inputs.py", "image_metric.py",
    "calibrator.py", "calibration_protocol.py", "protocol_client.py")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2"), required=True)
    stage = parser.parse_args().stage
    if (HERE / ("TOOL_FREEZE_" + stage + ".json")).exists():
        raise RuntimeError("stage_already_frozen")
    for name in ("CALIBRATION_PREFLIGHT.json", "IMAGE_METRIC_PREFLIGHT.json", "MIDPOINT_QA.json"):
        if read(name)["status"] != "pass":
            raise RuntimeError("required_preflight_not_passed_" + name)
    if stage == "v1":
        if (HERE / "PLAN_FREEZE.json").exists():
            raise RuntimeError("common_inputs_already_frozen")
        source = read("SOURCE_BINDING.json")
        files = [HERE / name for name in ("PLAN.json", "CONTRACT.md", "PRIOR_REVIEW.md", "SOURCE_BINDING.json",
            "SCORING_BINDING.json", "MIDPOINT_PLAN.json", "MIDPOINT_IMAGE_RESULT.json", "MIDPOINT_RESULT.json",
            "MIDPOINT_MANIFEST.json", "MIDPOINT_SOURCE_BINDING.json", "midpoint.py")]
        files += [HERE / row["path"] for row in source["initial"].values()]
        files += [HERE / row["payload"]["path"] for row in source["proposals"]]
        files += [HERE / row["path"] for group in source["images"].values() for row in group]
        files += [Path(source["original"]["path"]), Path(read("SCORING_BINDING.json")["target"]["path"])]
        write("PLAN_FREEZE.json", dict(UTC=datetime.now(timezone.utc).isoformat(), files=[identity(path) for path in files],
            coefficients=[0, .5, 1], new_Pro_before_freeze=0))
    else:
        for row in read("PLAN_FREEZE.json")["files"]:
            if identity(HERE / row["path"])["sha256"] != row["sha256"]:
                raise RuntimeError("fixed_input_changed_" + row["path"])
        if read("OPTIMIZATION_BINDING.json")["status"] != "ready_for_v2":
            raise RuntimeError("first_stage_and_optimization_binding_required")
    sources = [HERE / name for name in RUNTIME]
    if stage == "v2":
        sources += [HERE / "calibration_batch.py", HERE / "batch_worker.py", HERE / "OPTIMIZATION_BINDING.json"]
    sources += [HERE.parent / "m6_refine_001/quality.py", HERE.parent / "m6_coupled_probe_001/evaluate.py",
        HERE.parents[1] / "human_eye_plugin/surface_geometry.py", HERE.parent / "m6_shape_train_001/process_runner.py"]
    directory = HERE / "private/tool_versions" / stage
    directory.mkdir(parents=True, exist_ok=False)
    rows = []
    for index, path in enumerate(sources):
        archived = directory / (str(index).zfill(2) + "_" + path.name)
        shutil.copyfile(path, archived)
        rows.append(dict(identity(path), archived=identity(archived)))
    write("TOOL_FREEZE_" + stage + ".json", dict(stage=stage, UTC=datetime.now(timezone.utc).isoformat(), files=rows,
        Python=identity(PYTHON), Blender=identity(BLENDER),
        scope="Actual deterministic calibration/protocol and engine source bytes for this stage."))
    print(stage + " exact inputs/runtime frozen")


if __name__ == "__main__":
    main()
