"""Archive exact pre-model execution sources and fixed asset observations once."""

import difflib
import hashlib
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write

RUNTIME = ("common.py", "background.py", "run_measured.py", "blender_common.py", "blender_edit.py", "blender_read.py", "blender_render.py", "session_api.py", "evaluate.py", "quality.py", "image_inputs.py", "image_metric.py", "calibrator.py", "calibration_batch.py", "batch_worker.py", "calibration_protocol.py", "protocol_client.py")
CONSUMER = ("consumer_runner.py", "consumer_bridge.py", "correspondence.py", "localized_support.py", "facts_api.py", "python_executor.py")


def main():
    if (HERE / "PRE_PRO_FREEZE.json").exists():
        raise FileExistsError("pre_model_freeze_already_exists")
    sources = []
    diffs = []
    for group, names, prior in (("calibration", RUNTIME, "m6_image_calibration_006"), ("consumer", CONSUMER, "m6_image_correspondence_005")):
        for name in names:
            path = HERE / name
            original = HERE.parent / prior / name
            archive = HERE / "private/source_archive" / name
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(path.read_bytes())
            same = path.read_bytes() == original.read_bytes()
            sources.append(dict(group=group, current=identity(path), archived=identity(archive), original=identity(original), exact_same_bytes=same))
            if not same:
                diff = "".join(difflib.unified_diff(original.read_text(encoding="utf8").splitlines(True), path.read_text(encoding="utf8").splitlines(True), fromfile=prior+"/"+name, tofile="007/"+name))
                output = HERE / "private/source_diff" / (name+".diff")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(diff, encoding="utf8")
                diffs.append(identity(output))
    extra = [identity(path) for path in sorted(HERE.glob("*.py")) if path.name not in RUNTIME+CONSUMER]
    input_binding = identity(HERE / "SOURCE_INPUT_BINDING.json")
    write("PRE_PRO_FREEZE.json", dict(cycle_id="M6-CALIBRATION-TRANSFER-007", frozen_epoch=time.time(),
        sources=sources, source_diffs=diffs, additional_support_sources=extra, source_inputs=input_binding,
        calibration_alphas=[0,.5,1], image_samples=3686400, new_started_Pro_at_freeze=0,
        scope="Frozen 005 correspondence and 006 V2 algorithm sources with explicit asset/reference/object/unit adaptation. Final new proposal is frozen separately after the only model session."))
    print(dict(sources=len(sources), exact=sum(row["exact_same_bytes"] for row in sources), diffs=len(diffs)))


if __name__ == "__main__":
    main()
