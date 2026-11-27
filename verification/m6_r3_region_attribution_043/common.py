"""Pins and immutable JSON helpers for the 043 fixed-input experiment."""
from __future__ import annotations

from hashlib import file_digest
import json
from pathlib import Path
import sys

ROOT = Path("D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION")
PIN_041 = ROOT.parent / "M6-041-KERNEL-HOOK/install/PINS.json"
PLAN_042 = ROOT.parent / "M6-042-ENTRY-WARM-REGION/replay/PLAN_02.json"
CAPTURE_SHA = "6f6274e27ce2a3a1137a1dc817aca2413362d31027416bff3aff45fb831090b9"
SOURCE_041 = {"A": "a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d",
              "B": "ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e"}
PYTHON = Path("D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe")
CYCLE = ROOT.name


def read(p):
    return json.loads(Path(p).read_bytes())


def pin(p):
    p = Path(p).resolve(strict=True)
    with p.open("rb") as f:
        return {"path": str(p), "bytes": p.stat().st_size, "sha256": file_digest(f, "sha256").hexdigest()}


def check(ref):
    if pin(ref["path"]) != ref:
        raise ValueError("fixed artifact changed: " + ref["path"])
    return Path(ref["path"])


def dump(path, value):
    path = Path(path)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write("\n")
    return pin(path)


def installation(binding):
    p = Path(binding)
    data = read(p)
    site = Path(data["site_packages"])
    assert len(data["source_files"]) == 143 and Path(data["dependency_python"]).resolve() == PYTHON.resolve()
    for source in data["source_files"]:
        actual = pin(site / source["path"])
        assert actual["sha256"] == source["sha256"], source["path"]
    return {"site": str(site), "identity": data["identity"], "binding": pin(p), "verified_files": 143}


def base_install(arm):
    refs = read(PIN_041)["binding"]
    p = check(refs[{"A": "032", "B": "r3"}[arm]])
    value = installation(p)
    assert value["identity"]["source_sha256"] == SOURCE_041[arm]
    return value


def replay_inputs():
    assert pin(PLAN_042)["sha256"] == "e4052259504ee5b15f1a4315b294d91ac8759b8e6301673c1057e7433902743d"
    old = read(PLAN_042)
    capture = check(old["capture"])
    assert pin(capture)["sha256"] == CAPTURE_SHA and old["request_budget_s"] == 30.0
    return old, capture


def activate(installed):
    assert Path(sys.executable).resolve() == PYTHON.resolve()
    sys.path.insert(0, installed["site"])
