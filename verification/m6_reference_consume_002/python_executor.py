"""Ordinary bounded Python over a versioned isolated geometry snapshot."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

HERE = Path(__file__).resolve().parent
DEPS = HERE.parent / "m6_shape_pretrain_001/private/deps"
spec = importlib.util.spec_from_file_location("_refine_process_metrics", HERE.parent / "m6_task_perception_001/python_sandbox.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def worker():
    started = time.perf_counter()
    decode_started, decode_cpu = time.perf_counter(), time.process_time()
    payload = json.loads(sys.stdin.buffer.read())
    transport = dict(input_JSON_decode_wall_s=time.perf_counter()-decode_started,
        input_JSON_decode_CPU_s=time.process_time()-decode_cpu, mode="inline_arrays")
    sys.path.insert(0, str(DEPS))
    import numpy as np
    import scipy
    if "array_packet" in payload:
        packet_started, packet_cpu = time.perf_counter(), time.process_time()
        descriptor = payload["array_packet"]
        session = Path(payload["payload_folder"]).resolve().parent
        packet_path = Path(descriptor["path"]).resolve()
        binding = descriptor["binding"]
        cache_key = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")).hexdigest()
        session_key = hashlib.sha256(str(session).casefold().encode("utf8")).hexdigest()
        if binding["session_key"] != session_key or binding["version"] != payload["version"] or cache_key != descriptor["cache_key"]:
            raise ValueError("packet_session_version_binding_mismatch")
        if packet_path.parent != session / "snapshots" / ("v" + str(payload["version"])):
            raise ValueError("packet_outside_session_version_snapshot_directory")
        raw = packet_path.read_bytes()
        if len(raw) != descriptor["bytes"] or hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
            raise ValueError("packet_SHA256_or_size_mismatch")
        with np.load(io.BytesIO(raw), allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in archive.files}
        schema = {key: dict(dtype=str(value.dtype), shape=list(value.shape)) for key, value in arrays.items()}
        if schema != binding["schema"]:
            raise ValueError("packet_array_dtype_shape_binding_mismatch")
        transport.update(mode="NPZ_packet", packet_bytes=len(raw),
            packet_validate_load_wall_s=time.perf_counter()-packet_started,
            packet_validate_load_CPU_s=time.process_time()-packet_cpu)
    else:
        arrays = {key: np.asarray(value) for key, value in payload["arrays"].items()}
    for key in ("faces", "F_ids", "I_ids", "protected_ids", "source_ids"):
        if key in arrays:
            arrays[key] = arrays[key].astype(np.int64)
    for key in ("vertices", "initial_vertices"):
        arrays[key] = arrays[key].astype(np.float64)
    created = []
    output_folder = Path(payload["payload_folder"])
    output_folder.mkdir(parents=True, exist_ok=True)

    def save_edit(source_ids, values, mode="positions_world"):
        ids = np.asarray(source_ids)
        values = np.asarray(values, dtype=np.float64)
        if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer) or not len(ids):
            raise ValueError("source_ids_must_be_nonempty_integer_vector")
        ids = ids.astype(np.int64)
        if len(np.unique(ids)) != len(ids) or not np.isin(ids, arrays["I_ids"]).all():
            raise ValueError("submitted_source_ids_must_be_unique_and_inside_I")
        if values.shape != (len(ids), 3) or not np.isfinite(values).all():
            raise ValueError("submitted_values_must_be_finite_N_by3")
        if mode not in ("positions_world", "displacements_world"):
            raise ValueError("mode_must_be_positions_world_or_displacements_world")
        ident = "p" + uuid.uuid4().hex
        np.savez_compressed(output_folder / (ident + ".npz"), source_ids=ids, **{mode: values})
        item = dict(payload_id=ident, observed_version=payload["version"], points=len(ids), mode=mode)
        write(output_folder / (ident + ".json"), item)
        created.append(item)
        return item

    task = payload["task"]
    namespace = dict(np=np, scipy=scipy, V=arrays["vertices"], current=arrays["vertices"], vertices=arrays["vertices"],
        V0=arrays["initial_vertices"], initial_vertices=arrays["initial_vertices"], faces=arrays["faces"],
        F_ids=arrays["F_ids"], I_ids=arrays["I_ids"], protected_ids=arrays["protected_ids"],
        source_ids=arrays.get("source_ids", np.arange(len(arrays["vertices"]))), version=payload["version"],
        task=task, save_edit=save_edit, G=arrays, geometry=arrays)
    stdout, stderr = io.StringIO(), io.StringIO()
    error = None
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(compile(payload["code"], "<refine-consumer-python>", "exec"), namespace, namespace)
    except BaseException as exception:
        error = dict(type=type(exception).__name__, message=str(exception))
    result = dict(stdout=stdout.getvalue(), stderr=stderr.getvalue(), error=error, created_payloads=created,
        observed_version=payload["version"], worker_wall_s_before_write=time.perf_counter() - started, process=legacy.lifetime_metrics(),
        transport=transport)
    sys.stdout.write(json.dumps(result, ensure_ascii=True, allow_nan=False) + "\n")


def execute(code, snapshot, task, payload_folder, audit_path, python=None, timeout_s=45, output_chars=16000):
    started = time.perf_counter()
    audit_path = Path(audit_path)
    audit_path.mkdir(parents=True, exist_ok=False)
    payload = dict(code=code, version=snapshot["version"], task=task, payload_folder=str(payload_folder))
    if "array_packet" in snapshot:
        payload["array_packet"] = snapshot["array_packet"]
        shapes = {key: value["shape"] for key, value in snapshot["array_packet"]["binding"]["schema"].items()}
    else:
        payload["arrays"] = snapshot["arrays"]
        shapes = {key: [len(value)] for key, value in snapshot["arrays"].items()}
    encode_started, encode_cpu = time.perf_counter(), time.process_time()
    raw = (json.dumps(payload, ensure_ascii=True, allow_nan=False) + "\n").encode("utf8")
    encode_wall, encode_CPU = time.perf_counter()-encode_started, time.process_time()-encode_cpu
    write(audit_path / "REQUEST.json", dict(code=code, observed_version=snapshot["version"], task=task,
        input_JSON_bytes=len(raw), array_shapes=shapes))
    python = Path(python or HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe")
    command = [str(python), "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()), "--worker"]
    record = dict(command=command, timeout_s=timeout_s, observed_version=snapshot["version"], input_JSON_bytes=len(raw),
        status="running", returncode=None, worker=None, error=None, JSON_encode_wall_s=encode_wall, JSON_encode_CPU_s=encode_CPU,
        input_transport="NPZ_packet" if "array_packet" in snapshot else "inline_arrays")
    process = None
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=audit_path, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        record["pid"] = process.pid
        stdout, stderr = process.communicate(raw, timeout=timeout_s)
        (audit_path / "STDOUT.bin").write_bytes(stdout)
        (audit_path / "STDERR.bin").write_bytes(stderr)
        record["returncode"] = process.returncode
        if process.returncode:
            raise RuntimeError("python_worker_exit_" + str(process.returncode))
        complete = json.loads(stdout)
        record["worker"] = complete
        write(audit_path / "COMPLETE_RESULT.json", complete)
        public = dict(complete)
        public.pop("transport", None)
        for key in ("stdout", "stderr"):
            public[key] = complete[key][:output_chars]
        record["public_truncated"] = any(len(complete[key]) > output_chars for key in ("stdout", "stderr"))
        public["truncated"] = record["public_truncated"]
        record["status"] = "completed" if complete["error"] is None else "execution_error"
    except subprocess.TimeoutExpired:
        if process is not None and process.poll() is None:
            stop = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            record["timeout_tree_kill_returncode"] = stop.returncode
            if process.poll() is None:
                process.kill()
        stdout, stderr = process.communicate(timeout=5)
        (audit_path / "STDOUT.bin").write_bytes(stdout)
        (audit_path / "STDERR.bin").write_bytes(stderr)
        record.update(status="timeout", returncode=process.returncode, error=dict(type="TimeoutExpired", message="python_execution_deadline"))
        public = dict(stdout="", stderr="", error=record["error"], created_payloads=[])
    except BaseException as exception:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        record.update(status="failed", error=dict(type=type(exception).__name__, message=str(exception)))
        public = dict(stdout="", stderr="", error=record["error"], created_payloads=[])
    record["wall_s"] = time.perf_counter() - started
    write(audit_path / "EXECUTION.json", record)
    return public, record


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("use_module_execute_or_worker_protocol")
    worker()
