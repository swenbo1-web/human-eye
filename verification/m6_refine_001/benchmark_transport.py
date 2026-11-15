"""Compare frozen inline transport with version-bound NPZ on private copies."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from consumer_bridge import Bridge, binding_digest
from python_executor import execute
from tool_preflight import prepare_session
import numpy as np

PROBE_CODE = '''import math, json, hashlib, heapq, collections, dataclasses
from scipy.spatial import cKDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.sparse.linalg import spsolve
from scipy.linalg import solve
fingerprints = {name: dict(dtype=str(value.dtype), shape=list(value.shape), sha256=hashlib.sha256(value.tobytes()).hexdigest()) for name, value in G.items()}
aliases = dict(V=V is G['vertices'], current=current is V, vertices=vertices is V, V0=V0 is G['initial_vertices'], initial_vertices=initial_vertices is V0, geometry=geometry is G, n0=n0 is G['n0'], source_ids=source_ids is G['source_ids'], faces=faces is G['faces'], F_ids=F_ids is G['F_ids'], I_ids=I_ids is G['I_ids'], C_ids=C_ids is G['C_ids'], B0_ids=B0_ids is G['B0_ids'], B1_ids=B1_ids is G['B1_ids'], independent_current_initial=not np.shares_memory(V,V0))
tree = cKDTree(V[I_ids])
graph = csr_matrix(np.array([[0.,1.,0.],[1.,0.,2.],[0.,2.,0.]]))
scipy_checks = dict(nearest=tree.query(V[center],k=2)[0].tolist(), shortest=dijkstra(graph,directed=False,indices=0).tolist(), sparse_solution=spsolve(csr_matrix(np.array([[2.,-1.],[-1.,2.]])),np.ones(2)).tolist(), dense_solution=solve(np.eye(2),np.ones(2)).tolist())
record = dataclasses.make_dataclass('Record',[('value',int)])
ordinary_python = dict(root=math.sqrt(4), heap=heapq.nsmallest(2,[3,1,2]), counts=dict(collections.Counter([1,1,2])), record=dataclasses.asdict(record(3)))
edit = save_edit(np.array([center],dtype=np.int64),np.array([[h/101.,-h/211.,h/307.]]),mode='displacements_world')
print('BENCHMARK ' + json.dumps(dict(arrays=fingerprints,aliases=aliases,scipy=scipy_checks,ordinary_python=ordinary_python,scalars=dict(h=h,ell=ell,center=center,version=version),task=task,edit=dict(observed_version=edit['observed_version'],points=edit['points'],mode=edit['mode'])),sort_keys=True))
'''


def load_frozen(name):
    frozen = read("TOOL_FREEZE.json")
    row = next(row for row in frozen["files"] if row["path"] == name)
    archive = HERE / row["archived"]["path"]
    if identity(archive)["sha256"] != row["sha256"]:
        raise ValueError("frozen_archive_identity_changed")
    original = HERE / name
    module = ModuleType("_benchmark_frozen_" + original.stem)
    module.__file__ = str(original)
    sys.modules[module.__name__] = module
    exec(compile(archive.read_bytes(), str(original), "exec"), module.__dict__)
    return module, row


class JSONTimer:
    def __init__(self):
        self.wall_s, self.CPU_s = 0., 0.

    def __getattr__(self, name):
        return getattr(json, name)

    def dumps(self, value, *arguments, **keywords):
        started, cpu = time.perf_counter(), time.process_time()
        result = json.dumps(value, *arguments, **keywords)
        if isinstance(value, dict) and "arrays" in value:
            self.wall_s += time.perf_counter()-started
            self.CPU_s += time.process_time()-cpu
        return result


def worker_fingerprint(result):
    line = next(line for line in result["stdout"].splitlines() if line.startswith("BENCHMARK "))
    return json.loads(line[len("BENCHMARK "):])


def payload_arrays(directory, result):
    payload_id = result["created_payloads"][0]["payload_id"]
    with np.load(directory / (payload_id + ".npz"), allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def main():
    began = time.perf_counter()
    if not (HERE / "OPTIMIZATION_BINDING.json").exists():
        raise ValueError("performance_change_binding_required")
    run_id = uuid.uuid4().hex[:10]
    output = HERE / "private/transport_benchmark" / run_id
    old_bridge_module, old_bridge_identity = load_frozen("consumer_bridge.py")
    old_executor, old_executor_identity = load_frozen("python_executor.py")
    formal = {case: HERE / "private/sessions" / ("v2_" + case + "_facts") / "snapshots" for case in ("s01", "s02")}
    formal_before = {case: path.exists() for case, path in formal.items()}
    checks, runs, comparison, setup, entrypoints = {}, [], [], {}, []
    last_snapshot = last_task = last_session = None
    immutable_inputs = {}
    for case_index, case in enumerate(("s01", "s02")):
        session = prepare_session("ipc_" + run_id, case, "facts")
        options = SimpleNamespace(case=HERE / "private/consumer_cases" / case, session=session,
            audit=output / case / "bridge_v2", route="facts", max_tool_calls=10,
            python_timeout_s=45, python_output_chars=16000, fact_output_chars=50000)
        new_bridge = Bridge(options)
        old_options = copy.copy(options)
        old_options.audit = output / case / "bridge_v1"
        old_bridge = old_bridge_module.Bridge(old_options)
        setup[case] = {}
        for name, bridge in (("inline", old_bridge), ("NPZ", new_bridge)):
            setup_started = time.perf_counter()
            bridge.load_api()
            setup[case][name + "_API_module_setup_wall_s"] = time.perf_counter()-setup_started
        state = read(session / "session.json")
        inputs = [session / "session.json", Path(state["current_blend"]), Path(state["current_npz"]), Path(state["source_spec"])]
        before = [identity(path) for path in inputs]
        immutable_inputs[case] = before
        for trial in range(3):
            pair, payload_pair = {}, {}
            order = ("inline", "NPZ") if (case_index+trial) % 2 == 0 else ("NPZ", "inline")
            for mode in order:
                bridge = old_bridge if mode == "inline" else new_bridge
                snapshot_started, snapshot_cpu = time.perf_counter(), time.process_time()
                snapshot, task = bridge.snapshot()
                snapshot_wall, snapshot_CPU = time.perf_counter()-snapshot_started, time.process_time()-snapshot_cpu
                payload_folder = session / ("payloads_inline" if mode == "inline" else "payloads")
                audit = output / case / (mode + "_" + str(trial))
                timer = JSONTimer()
                old_executor.json = timer
                function = old_executor.execute if mode == "inline" else execute
                result, execution = function(PROBE_CODE, snapshot, task, payload_folder, audit)
                if result.get("error"):
                    raise ValueError("benchmark_worker_failed_" + json.dumps(result["error"]))
                fingerprint = worker_fingerprint(result)
                pair[mode], payload_pair[mode] = fingerprint, payload_arrays(payload_folder, result)
                transport = (execution.get("worker") or {}).get("transport", {})
                row = dict(case_id=case, trial=trial, mode=mode, sample="cold" if trial == 0 else "warm",
                    sample_order=list(order), snapshot_wall_s=snapshot_wall, snapshot_CPU_s=snapshot_CPU,
                    snapshot_cost=snapshot.get("snapshot_cost"), execution_wall_s=execution["wall_s"],
                    sequential_component_wall_s=snapshot_wall+execution["wall_s"],
                    input_JSON_bytes=execution["input_JSON_bytes"],
                    JSON_encode_wall_s=execution.get("JSON_encode_wall_s", timer.wall_s),
                    JSON_encode_CPU_s=execution.get("JSON_encode_CPU_s", timer.CPU_s),
                    worker_wall_s=execution["worker"]["worker_wall_s_before_write"], worker_transport=transport,
                    fingerprint=fingerprint, audit_path=str(audit))
                runs.append(row)
                if mode == "NPZ":
                    checks[case + "_" + str(trial) + "_cache_hit_expected"] = snapshot["snapshot_cost"]["cache_hit"] == (trial > 0)
                    last_snapshot, last_task, last_session = snapshot, task, session
            checks[case + "_" + str(trial) + "_all_array_bits_dtypes_namespace_equal"] = pair["inline"] == pair["NPZ"]
            checks[case + "_" + str(trial) + "_raw_saved_payload_equal"] = payload_pair["inline"].keys() == payload_pair["NPZ"].keys() and all(
                payload_pair["inline"][key].dtype == payload_pair["NPZ"][key].dtype and payload_pair["inline"][key].tobytes() == payload_pair["NPZ"][key].tobytes() for key in payload_pair["inline"])
        entry_started = time.perf_counter()
        response = new_bridge.call(dict(name="execute_python", arguments=dict(code=PROBE_CODE)))
        public = json.loads(response["content"][0]["text"])
        checks[case + "_normal_bridge_entrypoint"] = not response["isError"] and worker_fingerprint(public) == pair["NPZ"] and "transport" not in public
        entrypoints.append(dict(case_id=case, wall_s=time.perf_counter()-entry_started, public_UTF8_bytes=len(response["content"][0]["text"].encode("utf8"))))
        checks[case + "_session_asset_inputs_unchanged"] = before == [identity(path) for path in inputs]
        case_rows = [row for row in runs if row["case_id"] == case]
        for sample in ("cold", "warm"):
            selected = [row for row in case_rows if row["sample"] == sample]
            totals = {mode: sum(row["sequential_component_wall_s"] for row in selected if row["mode"] == mode) for mode in ("inline", "NPZ")}
            comparison.append(dict(case_id=case, sample=sample, samples_per_mode=1 if sample == "cold" else 2,
                sequential_component_wall_s=totals, difference_inline_minus_NPZ_s=totals["inline"]-totals["NPZ"]))
    negative = {}
    for name in ("checksum", "version", "schema", "session"):
        snapshot = copy.deepcopy(last_snapshot)
        payload_folder = last_session / "payloads"
        expected = "packet_session_version_binding_mismatch"
        if name == "checksum":
            snapshot["array_packet"]["sha256"] = "0" * 64
            expected = "packet_SHA256_or_size_mismatch"
        elif name == "version":
            snapshot["version"] += 1
        elif name == "schema":
            snapshot["array_packet"]["binding"]["schema"]["vertices"]["dtype"] = "float32"
            snapshot["array_packet"]["cache_key"] = binding_digest(snapshot["array_packet"]["binding"])
            expected = "packet_array_dtype_shape_binding_mismatch"
        else:
            payload_folder = output / "other_session" / "payloads"
        audit = output / ("guard_" + name)
        result, execution = execute("print('unexpected_user_code')", snapshot, last_task, payload_folder, audit)
        stderr = (audit / "STDERR.bin").read_text(encoding="utf8", errors="replace")
        passed = result["error"] is not None and expected in stderr and "unexpected_user_code" not in result.get("stdout", "")
        checks["worker_rejects_" + name] = passed
        negative[name] = dict(passed=passed, execution_wall_s=execution["wall_s"], expected_guard=expected)
    formal_after = {case: path.exists() for case, path in formal.items()}
    checks["formal_v2_snapshots_remain_cold"] = not any(formal_before.values()) and formal_after == formal_before
    frozen_checks = {}
    for row in read("TOOL_FREEZE.json")["files"]:
        frozen_checks[row["path"]] = identity(HERE / row["archived"]["path"])["sha256"] == row["sha256"]
    checks["all_v1_archived_source_bytes_unchanged"] = all(frozen_checks.values())
    totals = {mode: dict(calls=sum(row["mode"] == mode for row in runs),
        input_JSON_bytes=sum(row["input_JSON_bytes"] for row in runs if row["mode"] == mode),
        sequential_component_wall_s=sum(row["sequential_component_wall_s"] for row in runs if row["mode"] == mode),
        JSON_encode_wall_s=sum(row["JSON_encode_wall_s"] for row in runs if row["mode"] == mode)) for mode in ("inline", "NPZ")}
    detail = dict(runs=runs, guards=negative, API_module_setup=setup, normal_entrypoints=entrypoints,
        immutable_inputs=immutable_inputs, archived_source_checks=frozen_checks)
    write(output / "DETAIL.json", detail)
    result = dict(status="pass" if all(checks.values()) else "fail", checks=checks, comparison=comparison, totals=totals,
        frozen_source_identities=[old_bridge_identity, old_executor_identity],
        current_source_identities=[identity(HERE / name) for name in ("consumer_bridge.py", "python_executor.py")],
        formal_v2_snapshot_cache_before=formal_before, formal_v2_snapshot_cache_after=formal_after,
        wall_s=time.perf_counter()-began, detail_path=str((output / "DETAIL.json").relative_to(HERE)),
        accounting="One cold packet and two warm invocations per mode per real case. API module imports are completed and separately timed before component samples. Same fresh v2 worker supports both wire formats. Frozen v1 parent and snapshot source are compiled with original __file__. Inline JSON encoding is timed by a delegating wrapper. Component timers are nested, only sequential snapshot plus executor wall is added. Order alternates, worker imports and OS cache can affect individual samples. Normal entrypoint and guard probes are additional local checks, included only in benchmark total wall.",
        geometry_probe="Consumer-independent tiny explicit displacements are saved as payloads only. No native final edit payload is read. No model edit or Pro call is performed.",
        actual_Pro_sessions=0, actual_Blender_calls=0)
    write(HERE / "TRANSPORT_BENCHMARK.json", result)
    print(json.dumps(dict(status=result["status"], checks=len(checks), totals=totals, comparison=comparison, wall_s=result["wall_s"])))
    if result["status"] != "pass":
        raise AssertionError("transport_equivalence_or_guard_failed")


if __name__ == "__main__":
    main()
