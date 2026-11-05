"""Run from the checkout with python -B verification/benchmark_resident_bridge.py."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter_ns

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from human_eye_fast.resident_bridge import ResidentBridge


WARMUP = 5
SAMPLES = 31
PROCESSES = 3
MODES = ("add", "full", "dirty", "transform", "unchanged")
THREAD_ENV = {
    name: "1"
    for name in (
        "BLIS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    )
}


@dataclass(frozen=True, slots=True)
class Fixture:
    object_id: str
    full_states: tuple
    dirty_states: tuple
    dirty_indices: np.ndarray
    triangles: np.ndarray
    transforms: tuple


def make_fixture(side, rng):
    axis = np.linspace(-0.5, 0.5, side)
    x, y = np.meshgrid(axis, axis, indexing="xy")
    base = np.column_stack((x.ravel(), y.ravel(), np.zeros(side * side)))
    corners = np.arange(side * side, dtype=np.int64).reshape(side, side)[:-1, :-1].ravel()
    triangles = np.empty((2 * len(corners), 3), dtype=np.int64)
    triangles[0::2] = np.column_stack((corners, corners + 1, corners + side + 1))
    triangles[1::2] = np.column_stack((corners, corners + side + 1, corners + side))

    indices = rng.choice(len(base), size=len(base) // 100, replace=False)
    edited = base.copy()
    edited[indices] += np.array([0.001, -0.002, 0.003])
    moved = base + np.array([-0.004, 0.005, 0.006])
    first = np.array(
        [[1.10, -0.27, 0.14, 1.1], [0.38, 0.78, -0.09, -2.0],
         [0.08, 0.24, 1.28, 0.5], [0.0, 0.0, 0.0, 1.0]]
    )
    first[:3, 3] *= side / 100
    second = first.copy()
    second[0, 1] = 0.15
    second[1, 3] += 0.3
    return Fixture(
        f"grid_{side}x{side}", (base, moved), (base, edited), indices,
        triangles, (first, second),
    )


def readonly(array):
    return np.asarray(memoryview(array).toreadonly())


@dataclass(frozen=True, slots=True)
class BaselineView:
    local_m: np.ndarray
    world_m: np.ndarray
    triangles: np.ndarray
    world_from_local: np.ndarray
    appearance: object = None


@dataclass(slots=True)
class BaselineBuffers:
    local_m: np.ndarray
    world_m: np.ndarray
    world_from_local: np.ndarray
    linear: np.ndarray
    translation: np.ndarray
    view: BaselineView

    def refresh_world(self):
        np.matmul(self.local_m, self.linear, out=self.world_m)
        self.world_m += self.translation


class FullRefreshBaseline:
    """Own the same cache and refresh all coordinate rows on an edit."""

    def __init__(self):
        self._objects = {}

    def add(self, object_id, local_m, triangles, world_from_local):
        local = local_m.copy()
        world = np.empty_like(local)
        matrix = world_from_local.copy()
        view = BaselineView(
            readonly(local), readonly(world), readonly(triangles.copy()), readonly(matrix)
        )
        buffers = BaselineBuffers(local, world, matrix, matrix[:3, :3].T, matrix[:3, 3], view)
        buffers.refresh_world()
        self._objects[object_id] = buffers
        return view

    def get(self, object_id):
        return self._objects[object_id].view

    def remove(self, object_id):
        del self._objects[object_id]

    def update_full(self, object_id, local_m):
        buffers = self._objects[object_id]
        np.copyto(buffers.local_m, local_m)
        buffers.refresh_world()
        return buffers.view

    def update_transform(self, object_id, world_from_local):
        buffers = self._objects[object_id]
        np.copyto(buffers.world_from_local, world_from_local)
        buffers.refresh_world()
        return buffers.view


def prepare(factory, fixture, peer, mode):
    bridge = factory()
    bridge.add(peer.object_id, peer.full_states[0], peer.triangles, peer.transforms[0])
    if mode == "add":
        return bridge
    local = fixture.full_states[0]
    transform = fixture.transforms[0]
    if mode == "dirty":
        local = fixture.dirty_states[1]
    elif mode == "full":
        local = fixture.full_states[1]
    elif mode == "transform":
        transform = fixture.transforms[1]
    bridge.add(fixture.object_id, local, fixture.triangles, transform)
    return bridge


def update_selected_rows(update_dirty, object_id, indices, incoming):
    return update_dirty(object_id, indices, incoming[indices])


def operation(bridge, fixture, mode, state, candidate):
    object_id = fixture.object_id
    if mode == "add":
        return bridge.add, (
            object_id, fixture.full_states[state], fixture.triangles, fixture.transforms[0],
        )
    if mode == "full":
        return bridge.update_full, (object_id, fixture.full_states[state])
    if mode == "dirty":
        incoming = fixture.dirty_states[state]
        if candidate:
            return update_selected_rows, (bridge.update_dirty, object_id, fixture.dirty_indices, incoming)
        return bridge.update_full, (object_id, incoming)
    if mode == "transform":
        return bridge.update_transform, (object_id, fixture.transforms[state])
    return bridge.get, (object_id,)


def expected_state(fixture, mode, state):
    if mode == "dirty":
        return fixture.dirty_states[state], fixture.transforms[0]
    if mode in ("add", "full"):
        return fixture.full_states[state], fixture.transforms[0]
    if mode == "transform":
        return fixture.full_states[0], fixture.transforms[state]
    return fixture.full_states[0], fixture.transforms[0]


def check_state(view, local, triangles, transform):
    homogeneous = np.column_stack((local, np.ones(len(local))))
    expected = np.einsum("ij,nj->ni", transform, homogeneous)[:, :3]
    np.testing.assert_allclose(view.world_m, expected, rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(view.local_m, local)
    np.testing.assert_array_equal(view.triangles, triangles)
    np.testing.assert_array_equal(view.world_from_local, transform)
    assert not np.shares_memory(view.local_m, local)
    assert not np.shares_memory(view.triangles, triangles)
    assert not np.shares_memory(view.world_from_local, transform)
    return float(np.max(np.abs(view.world_m - expected)))


def verify_fixture(fixture, peer):
    errors = {}
    for label, factory in (("candidate", ResidentBridge), ("baseline", FullRefreshBaseline)):
        errors[label] = {}
        for mode in MODES:
            bridge = prepare(factory, fixture, peer, mode)
            if mode != "add":
                before = bridge.get(fixture.object_id)
            worst = 0.0
            for state in (0, 1):
                method, args = operation(bridge, fixture, mode, state, label == "candidate")
                view = method(*args)
                local, transform = expected_state(fixture, mode, state)
                worst = max(worst, check_state(view, local, fixture.triangles, transform))
                if mode == "unchanged":
                    assert view.local_m is before.local_m
                    assert view.world_m is before.world_m
                    assert view.triangles is before.triangles
                peer_view = bridge.get(peer.object_id)
                check_state(peer_view, peer.full_states[0], peer.triangles, peer.transforms[0])
                if mode == "add":
                    bridge.remove(fixture.object_id)
            errors[label][mode] = worst
    return errors


def measure_fixture(fixture, peer, worker):
    results = {}
    factories = {"candidate": ResidentBridge, "baseline": FullRefreshBaseline}
    labels = tuple(factories)
    for mode in MODES:
        warmups = {label: [] for label in labels}
        samples = {label: [] for label in labels}
        bridges = {
            label: prepare(factory, fixture, peer, mode)
            for label, factory in factories.items()
        }
        for step in range(WARMUP + SAMPLES):
            order = labels if (step + worker) % 2 == 0 else labels[::-1]
            for label in order:
                method, args = operation(
                    bridges[label], fixture, mode, step % 2, label == "candidate"
                )
                started = perf_counter_ns()
                method(*args)
                elapsed = perf_counter_ns() - started
                if mode == "add":
                    bridges[label].remove(fixture.object_id)
                (warmups if step < WARMUP else samples)[label].append(elapsed)
        results[mode] = {"warmups_ns": warmups, "samples_ns": samples}
    return results


def payload_writes(fixture):
    """Count unique bytes written in each owned buffer."""
    local = fixture.full_states[0].nbytes
    rows = len(fixture.dirty_indices) * fixture.full_states[0].itemsize * 3
    topology = fixture.triangles.nbytes
    transform = fixture.transforms[0].nbytes
    return {
        "add": {"local": local, "world_unique": local, "topology": topology, "transform": transform},
        "full": {"local": local, "world_unique": local, "topology": 0, "transform": 0},
        "dirty_candidate": {"local": rows, "world_unique": rows, "topology": 0, "transform": 0},
        "dirty_baseline": {"local": local, "world_unique": local, "topology": 0, "transform": 0},
        "transform": {"local": 0, "world_unique": local, "topology": 0, "transform": transform},
        "unchanged": {"local": 0, "world_unique": 0, "topology": 0, "transform": 0},
    }


def run_worker(seed, worker):
    rng = np.random.default_rng(seed)
    fixtures = (make_fixture(100, rng), make_fixture(300, rng))
    pairs = ((fixtures[0], fixtures[1]), (fixtures[1], fixtures[0]))
    correctness = {fixture.object_id: verify_fixture(fixture, peer) for fixture, peer in pairs}
    return {
        "pid": os.getpid(),
        "worker": worker,
        "numpy_version": np.__version__,
        "blas_build": np.__config__.CONFIG["Build Dependencies"].get("blas"),
        "thread_environment": {name: os.environ.get(name) for name in THREAD_ENV},
        "meshes": {
            fixture.object_id: {
                "vertices": len(fixture.full_states[0]),
                "faces": len(fixture.triangles),
                "dirty_indices": fixture.dirty_indices.tolist(),
                "owned_payload_write_bytes_per_call": payload_writes(fixture),
                "max_abs_world_error_m": correctness[fixture.object_id],
                "timings": measure_fixture(fixture, peer, worker),
            }
            for fixture, peer in pairs
        },
    }


def summarize(workers):
    summary = {}
    for mesh in workers[0]["meshes"]:
        results = {}
        for mode in MODES:
            rows = [worker["meshes"][mesh]["timings"][mode]["samples_ns"] for worker in workers]
            process_medians = [
                {label: statistics.median(values) for label, values in pair.items()}
                for pair in rows
            ]
            pooled_p95 = {
                label: float(np.percentile([t for pair in rows for t in pair[label]], 95))
                for label in ("candidate", "baseline")
            }
            results[mode] = {"process_medians_ns": process_medians, "pooled_p95_ns": pooled_p95}
        dirty_ratios = [
            row["baseline"] / row["candidate"] for row in results["dirty"]["process_medians_ns"]
        ]
        full_ratios = [
            row["candidate"] / row["baseline"] for row in results["full"]["process_medians_ns"]
        ]
        full_p95 = results["full"]["pooled_p95_ns"]
        p95_ratio = full_p95["candidate"] / full_p95["baseline"]
        summary[mesh] = {
            "timings": results,
            "gates": {
                "dirty_process_median_speedups": dirty_ratios,
                "dirty_process_median_pass": all(ratio >= 2.0 for ratio in dirty_ratios),
                "full_process_median_ratios": full_ratios,
                "full_process_median_pass": all(ratio <= 1.20 for ratio in full_ratios),
                "full_pooled_p95_ratio": p95_ratio,
                "full_pooled_p95_pass": p95_ratio <= 1.20,
                "unchanged_returns_same_arrays": True,
            },
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=59137)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/rb_a/resident_bridge.json")
    parser.add_argument("--worker", type=int, choices=range(PROCESSES), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker is not None:
        print(json.dumps(run_worker(args.seed, args.worker)))
        return 0

    env = os.environ | THREAD_ENV
    workers = []
    for worker in range(PROCESSES):
        command = [
            sys.executable, "-B", str(Path(__file__).resolve()), "--seed", str(args.seed),
            "--worker", str(worker),
        ]
        result = subprocess.run(command, env=env, check=True, stdout=subprocess.PIPE, text=True)
        workers.append(json.loads(result.stdout))

    summary = summarize(workers)
    report = {
        "seed": args.seed,
        "warmups_per_case_per_variant": WARMUP,
        "samples_per_case_per_variant": SAMPLES,
        "processes": PROCESSES,
        "order": "paired candidate and baseline, alternating which goes first",
        "timer": "perf_counter_ns",
        "p95": "linear percentile over pooled per-variant samples",
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "python": sys.version,
        "payload_counts": "Unique bytes written in owned buffers, excluding temporaries and repeated writes.",
        "baseline": "Preallocated local/world/topology, copyto(local), matmul(out=world), in-place translation.",
        "dirty_candidate": "Timed gather of selected rows from the shared full input, then sparse update.",
        "workers": workers,
        "summary": summary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "summary": summary}, indent=2))
    return int(any(
        not passed
        for mesh in summary.values()
        for gate, passed in mesh["gates"].items()
        if gate.endswith("_pass")
    ))


if __name__ == "__main__":
    raise SystemExit(main())
