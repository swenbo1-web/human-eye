"""Persistent experiment limits, retaining attempts and unresolved reservations."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import time
import uuid


LIMITS = {"Blender_start_attempts": 24, "qualification_rasters": 48,
          "formal_rasters": 72, "all_rasters": 120}


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode()


def save(path, value):
    path = Path(path)
    with path.open("xb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


class Budget:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.claims = self.root / "claims"
        self.settlements = self.root / "settlements"
        self.claims.mkdir(exist_ok=True)
        self.settlements.mkdir(exist_ok=True)
        with self.lock():
            plan = self.root / "LIMITS.json"
            if plan.exists():
                if json.loads(plan.read_bytes()) != LIMITS:
                    raise ValueError("experiment_budget_limits_changed")
            else:
                save(plan, LIMITS)

    @contextmanager
    def lock(self):
        # The kernel releases this lock if the process exits. No stale-owner
        # directory or a new persistent service is introduced.
        with (self.root / "LOCK").open("a+b") as stream:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                deadline = time.monotonic() + 5
                while True:
                    try:
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("experiment_budget_lock")
                        time.sleep(.01)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _snapshot(self):
        claims = [json.loads(path.read_bytes()) for path in sorted(self.claims.glob("*.json"))]
        records = []
        counts = {"Blender_start_attempts": 0, "Blender_spawned_confirmed": 0,
                  "Blender_spawned_unknown": 0, "qualification_raster_actual": 0,
                  "formal_raster_actual": 0, "qualification_raster_upper": 0,
                  "formal_raster_upper": 0, "pending_raster_reservations": 0}
        for claim in claims:
            path = self.settlements / (claim["token"] + ".json")
            settlement = json.loads(path.read_bytes()) if path.exists() else None
            records.append({"claim": claim, "settlement": settlement})
            if claim["kind"] == "Blender_start":
                counts["Blender_start_attempts"] += 1
                counts["Blender_spawned_confirmed"] += bool(settlement and settlement.get("pid"))
                counts["Blender_spawned_unknown"] += settlement is None or settlement.get("spawn_status") == "unknown"
                continue
            phase = claim["phase"]
            actual = None if settlement is None else settlement.get("actual_attempts")
            lower = 0 if settlement is None else settlement.get("confirmed_attempts_lower_bound", 0)
            counts[phase + "_raster_actual"] += actual if actual is not None else lower
            counts[phase + "_raster_upper"] += actual if actual is not None else claim["reserved_upper_bound"]
            counts["pending_raster_reservations"] += settlement is None
        counts["all_raster_actual"] = counts["qualification_raster_actual"] + counts["formal_raster_actual"]
        counts["all_raster_upper"] = counts["qualification_raster_upper"] + counts["formal_raster_upper"]
        return {"limits": LIMITS, "counts": counts, "records": records,
                "semantics": "Reservations are bounds. Confirmed attempts include failures. Unconfirmed outcomes retain the reserved upper bound."}

    def snapshot(self):
        with self.lock():
            return self._snapshot()

    def reserve(self, kind, label, phase="qualification", upper=1):
        if kind not in ("Blender_start", "raster_request") or phase not in ("qualification", "formal"):
            raise ValueError("experiment_budget_claim_kind")
        if type(upper) is not int or not 0 <= upper <= 6:
            raise ValueError("experiment_budget_request_bound")
        with self.lock():
            counts = self._snapshot()["counts"]
            if kind == "Blender_start":
                if counts["Blender_start_attempts"] >= LIMITS["Blender_start_attempts"]:
                    raise RuntimeError("Blender_start_budget_exhausted")
            elif (counts[phase + "_raster_upper"] + upper > LIMITS[phase + "_rasters"]
                  or counts["all_raster_upper"] + upper > LIMITS["all_rasters"]):
                raise RuntimeError("raster_phase_or_total_budget_exhausted")
            token = uuid.uuid4().hex
            claim = {"token": token, "kind": kind, "phase": phase, "label": label,
                     "reserved_upper_bound": upper, "claimed_ns": time.perf_counter_ns()}
            save(self.claims / (token + ".json"), claim)
            return token

    def settle_start(self, token, *, pid, spawn_status, outcome):
        self._settle(token, {"pid": pid, "spawn_status": spawn_status, "outcome": outcome})

    def settle_rasters(self, token, *, actual, lower_bound, evidence, outcome):
        claim = json.loads((self.claims / (token + ".json")).read_bytes())
        if (type(lower_bound) is not int or not 0 <= lower_bound <= claim["reserved_upper_bound"]
                or actual is not None and (type(actual) is not int or not lower_bound <= actual <= claim["reserved_upper_bound"])):
            raise ValueError("raster_settlement_outside_reserved_bound")
        self._settle(token, {"actual_attempts": actual,
                             "confirmed_attempts_lower_bound": lower_bound,
                             "evidence": evidence, "outcome": outcome,
                             "released_proven_unconstructed_reservation":
                             None if actual is None else claim["reserved_upper_bound"] - actual})

    def _settle(self, token, value):
        with self.lock():
            claim = self.claims / (token + ".json")
            if not claim.is_file():
                raise ValueError("unknown_budget_claim")
            value.update(token=token, settled_ns=time.perf_counter_ns(),
                         claim_sha256=hashlib.sha256(claim.read_bytes()).hexdigest())
            save(self.settlements / (token + ".json"), value)
