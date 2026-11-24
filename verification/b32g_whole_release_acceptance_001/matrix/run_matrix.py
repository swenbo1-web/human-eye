"""Same requests through the two existing installed release launchers."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
ARCHIVED = Path("D:/hefe/verification/fixes/20261110_local_upgrade/ENTRY_CHECK.py")
ARCHIVED_SHA = "ead39eff6582abb2a2feca96d6e2f342b510257e699fe18389b23e8adedecfbd"
DIAG = Path("C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/scale_diag_001")
B_ROOT = Path("D:/he_m3_bvh032_private_654c1f69/.human-eye/releases/9.7.2+b32g")
RELEASES = {
    "A": ("df016079b0265ee327f884c90dd4815c392016b6", Path("D:/hefe/.human-eye/releases/9.7.2+20261110.scale.opt.r1"),
          "3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd", 137),
    "B": ("6c93f2375d1073b33e721a168f1fcf610ac6dbdc", B_ROOT,
          "0f9e6336ec54adf9e7b9a5379b02d2c2cab9f6d1f734138c3fde29e08ccee241", 143),
}
SCENES = (
    ("A", "G60_D12", "G"),
    ("B", "G60_D12", "G"),
    ("B", "D48", "D"),
    ("A", "D48", "D"),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archived_entry():
    assert sha(ARCHIVED) == ARCHIVED_SHA
    spec = importlib.util.spec_from_file_location("_historical_entry", ARCHIVED)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    entry = archived_entry()
    freeze = entry.load(DIAG / "FREEZE.json")
    input_paths = ["driver.py", "session.py", "ORACLE.json"] + [
        f"fixtures/{scene}{suffix}" for scene in ("G60_D12", "D48") for suffix in (".blend", ".json")
    ]
    for path in input_paths:
        assert sha(DIAG / path) == freeze["files"][path], path
    assert sha(DIAG / "ORACLE.json") == entry.ORACLE_SHA
    helper = entry.fixed_module("release_owned_session", DIAG / "session.py", entry.HELPER_SHA)
    scorer = entry.fixed_module("release_pure_scorer", DIAG / "quality_review.py", entry.SCORER_SHA)
    tree = ast.parse((DIAG / "driver.py").read_bytes())
    snapshot = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "SNAPSHOT" for target in node.targets))
    oracle = {row["id"]: row for row in entry.load(DIAG / "ORACLE.json")["snapshots"]}
    bindings = {}
    for arm, (commit, release, digest, count) in RELEASES.items():
        bind_path = release / "admin/RUNTIME_BINDING.json"
        binding = entry.load(bind_path)
        launcher = release / "admin/target_runtime_entry.py"
        version = binding["identity"]["distribution_version"]
        assert binding["identity"]["source_sha256"] == digest
        assert len(binding["source_files"]) == count
        assert sha(launcher) == binding["launcher_sha256"]
        bindings[arm] = dict(commit=commit, source_sha256=digest, source_count=count,
                             release=version, launcher=str(launcher), binding_sha256=sha(bind_path),
                             launcher_sha256=sha(launcher), python=binding["dependency_python"])
    contract = dict(arms=bindings, order=SCENES, input_sha256={path: sha(DIAG / path) for path in input_paths},
                    script_sha256=sha(Path(__file__).resolve()), archived_harness_sha256=ARCHIVED_SHA,
                    scorer_sha256=entry.SCORER_SHA, budget_s=30,
                    logical_geometry=12, logical_overview=4,
                    workload="Three identical geometry observations, then one same-scene overview per lane",
                    measure="Owned fresh start, identical initial and final worldmesh audit, actual line RTT and complete close",
                    model_calls=0, default_configuration_changed=False)
    frozen = ROOT / "FROZEN.json"
    if frozen.exists():
        assert entry.load(frozen) == json.loads(json.dumps(contract))
    else:
        entry.save(frozen, contract)
    if args.freeze_only:
        return 0

    mcp_class = entry.MCP
    rows = []
    for arm, scene, mode in SCENES:
        binding = bindings[arm]
        entry.COMMIT = binding["commit"]
        entry.BUILD = binding["source_sha256"]
        entry.RELEASE = binding["release"]
        fixture = entry.load(DIAG / "fixtures" / (scene + ".json"))
        names = {obj["name"] for obj in fixture["objects"]}
        overview = {}

        def check_identity(value):
            count = len(value["source_files"]) if "source_files" in value else value.get("source_file_count")
            assert value.get("source_sha256") == binding["source_sha256"]
            assert count == binding["source_count"]
            assert value.get("source_kind") == "installed_distribution"
            assert value.get("distribution_version") == binding["release"]

        class LiveMCP(mcp_class):
            def call(self, method, params=None, label=None):
                if label == "ping_after":
                    result, cost = super().call("tools/call", dict(
                        name="human_eye_scene_observe", arguments=dict(session_id="scale-entry-task",
                        include_image=False, query=dict(mode="overview"))), "readonly_overview")
                    value = entry.metadata(result)
                    check_identity(value["runtime_identity"])
                    actual_names = {obj["name"] for obj in value["objects"]}
                    ok = (value["status"] == "overview" and value["observation_status"] == "complete"
                          and value["execution_status"] == "not_requested" and names == actual_names)
                    overview.update(complete=ok, names=sorted(actual_names),
                                    expected_names=sorted(names), status=value["status"],
                                    execution_status=value["execution_status"],
                                    rtt_ns=cost["rtt_ns"], response_bytes=cost["response_bytes"])
                    entry.save(self.folder / "OVERVIEW_SCORE.json", overview)
                    assert ok, overview
                return super().call(method, params, label)

        entry.check_identity = check_identity
        entry.MCP = LiveMCP
        lane = entry.lane(SimpleNamespace(output=ROOT, diag=DIAG, entry=Path(binding["launcher"]),
                                          python=Path(binding["python"])),
                          f"{arm}_{scene}", scene, mode, helper, scorer, snapshot, freeze, oracle)
        lane["overview"] = overview
        rows.append(lane)
        print(json.dumps(dict(arm=arm, scene=scene, status=lane["status"],
                              overview=overview.get("complete"), error=lane.get("error", {}).get("message"),
                              ms=[row["rtt_ns"] / 1e6 for row in lane["observations"]]),
                         ensure_ascii=False), flush=True)
    success = all(row["status"] == "passed" and row["overview"].get("complete") for row in rows)
    entry.save(ROOT / "SUMMARY.json", dict(status="passed" if success else "failed", lanes=rows,
              geometry_pass=sum(observation["score"]["task_success"] for row in rows for observation in row["observations"]),
              geometry_denominator=12, overview_pass=sum(row["overview"].get("complete", False) for row in rows),
              overview_denominator=4, model_calls=0, default_configuration_changed=False))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
