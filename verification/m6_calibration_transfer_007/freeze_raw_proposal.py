"""Freeze the single model proposal and current-only calibration references."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
import numpy as np


def absolute(value):
    path = Path(value)
    return path if path.is_absolute() else HERE / path


def main():
    started, cpu = time.perf_counter(), time.process_time()
    consumer_dir = HERE / "private/consumers/raw/sample_07/facts"
    consumer = read(consumer_dir / "CONSUMER.json")
    claim = read(consumer_dir / "CLAIM.json")
    if consumer["status"] == "running" or claim["launch_state"] != "launched":
        raise ValueError("sole_consumer_must_be_terminal")
    claims = list((HERE / "private/consumers").glob("*/*/*/CLAIM.json"))
    if len(claims) != 1:
        raise ValueError("exactly_one_consumer_claim_required")
    session = HERE / "private/sessions/raw_sample_07_facts"
    state = read(session / "session.json")
    if state.get("pending") or state["version"] != 1 or len(state["operations"]) != 1:
        raise ValueError("one_final_saved_proposal_required")
    operation = state["operations"][0]
    payloads = [path for path in (session / "payloads").glob("p*.npz") if identity(path)["sha256"] == operation["payload_sha256"]]
    if len(payloads) != 1:
        raise ValueError("one_exact_submitted_payload_required")
    proposal_dir = HERE / "private/proposal"
    proposal_dir.mkdir(exist_ok=False)
    original = proposal_dir / "model_original.npz"
    shutil.copyfile(payloads[0], original)
    with np.load(original, allow_pickle=False) as payload:
        ids = payload["source_ids"]
        mode = next(key for key in payload.files if key != "source_ids")
        values = payload[mode]
    source = read("SOURCE_INPUT_BINDING.json")
    with np.load(absolute(source["initial"]["packet"]["path"]), allow_pickle=False) as initial:
        V0 = initial["vertices_world"]
    canonical = proposal_dir / "world_delta.npz"
    if mode == "displacements_world":
        shutil.copyfile(original, canonical)
        conversion = "Exact original sparse world-displacement payload bytes copied."
    elif mode == "positions_world":
        np.savez_compressed(canonical, source_ids=ids, displacements_world=values - V0[ids])
        conversion = "world_delta = original_positions_world - actual_saved_V0_world[source_ids]. Original model payload bytes retained separately."
    else:
        raise ValueError("unsupported_model_payload_mode")
    raw_saved = absolute(operation["saved_blend"]["path"])
    raw_readback = absolute(operation["readback"]["path"])
    reader_receipt = HERE / "private/jobs" / operation["reader_job"] / "receipt.json"
    preview_path = session / "previews/v1/PREVIEW.json"
    preview = read(preview_path)
    if preview["binding"]["saved_blend"]["sha256"] != identity(raw_saved)["sha256"]:
        raise ValueError("raw_preview_saved_file_mismatch")
    start = read("CONSUMER_START_OBSERVATION.json")
    proposal = dict(proposal_id="raw_proposal", points=len(ids), payload=identity(canonical),
        source_payload=identity(original) if mode == "displacements_world" else identity(canonical),
        original_model_payload=identity(original), original_model_payload_mode=mode, normalization=conversion,
        source_session=identity(session / "session.json"), source_operation=operation["operation_id"],
        saved_blend=identity(raw_saved), readback=identity(raw_readback), reader_receipt=identity(reader_receipt),
        quality=identity(absolute(operation["quality_record"])), images=preview["images"],
        preview=identity(preview_path), model_response=identity(consumer_dir / "PUBLIC_FINAL.txt"),
        consumer=identity(consumer_dir / "CONSUMER.json"), consumer_started_epoch=start["creation_epoch"])
    with np.load(canonical, allow_pickle=False) as delta:
        inverse = np.linalg.inv(np.load(absolute(source["initial"]["packet"]["path"]), allow_pickle=False)["matrix_world"])
        requested = V0[ids] + delta["displacements_world"]
        expected_native = (requested @ inverse[:3,:3].T + inverse[:3,3]).astype(np.float32)
    with np.load(raw_readback, allow_pickle=False) as actual:
        if actual["vertices_local"][ids].tobytes() != expected_native.tobytes():
            raise ValueError("canonical_delta_must_reproduce_actual_raw_native")
    source.update(cycle_id="M6-CALIBRATION-TRANSFER-007", proposals=[proposal], alphas=[0,.5,1],
        consumer_started_epoch=start["creation_epoch"], new_Pro_consumers=1,
        source_input_binding=identity(HERE / "SOURCE_INPUT_BINDING.json"))
    write("SOURCE_BINDING.json", source)
    frozen_epoch = time.time()
    write("PROPOSAL_FREEZE.json", dict(cycle_id="M6-CALIBRATION-TRANSFER-007", status="frozen_before_calibration_and_private_scoring",
        frozen_epoch=frozen_epoch, frozen_UTC=datetime.fromtimestamp(frozen_epoch,timezone.utc).isoformat(),
        proposal=proposal, source_binding=identity(HERE / "SOURCE_BINDING.json"),
        raw_session=identity(session / "session.json"), input_source=identity(HERE / "SOURCE_INPUT_BINDING.json"),
        consumer=identity(consumer_dir / "CONSUMER.json"), consumer_started_epoch=start["creation_epoch"],
        new_Pro_consumers=1, new_Blender_calls=0, exact_original_payload_preserved=True,
        canonical_delta_reproduces_actual_raw_native=True, private_geometry_scoring="pending_after_image_selection_freeze",
        wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu))
    print(dict(proposal="raw_proposal", points=len(ids), mode=mode, original_sha256=identity(original)["sha256"],canonical_sha256=identity(canonical)["sha256"], raw_technical_status=operation["quality"]["status"]))


if __name__ == "__main__":
    main()
