"""Check the published M6-049 observations and optionally reproduce the tested wheel."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
R3 = "119327bbb4e645c5de3bfbc0d30259736b9a2677"
HOOK = "31792523ecb48a500b8eed0ecb531c7ecc8e767e"
BASE = "6c93f2375d1073b33e721a168f1fcf610ac6dbdc"
REVIEW = HERE.parent / "m6_r3_final_replacement_049_review" / "RESULTS.json"
PATCHES = (
    "verification/m6_r3_region_attribution_043/candidate/C.patch",
    "verification/m6_r3_final_replacement_049/candidate/F.patch",
)


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def check_records():
    public = HERE / "public"
    inventory_file = public / "RAW_FILE_INDEX.json"
    require(digest(inventory_file.read_bytes()) == "d57ff7b42bf63661c5de88c5ffd168df21b96a91198658a1563fe5983e97cc3a", "raw index")
    indexed = {row["path"].replace("\\", "/"): row["sha256"] for row in load(inventory_file)["files"]}
    require(len(indexed) == 3210, "raw index count")
    case_file = public / "CASE_RESULTS.json"
    require(digest(case_file.read_bytes()) == indexed["coverage/AUDIT_FINAL.json"], "case audit identity")
    audit = load(case_file)
    clocks = load(public / "TIMINGS.json")
    review = load(REVIEW)
    coverage = review["coverage"]
    cases = {row["case"]: row["status_by_arm"] for row in audit["rows"]}
    require(len(cases) == len(audit["rows"]) == coverage["cases"] == 84, "case count")
    compared = ("known", "reason", "distance_m", "witness_status", "native_pair_diagnostic")
    for name, arms in cases.items():
        require(all(arms["A"][key] == arms["F"][key] for key in compared), name)
    require(sum(row["F"]["known"] for row in cases.values()) == 83, "known distances")
    require(coverage["primary_and_diagnostic"] == 504 and coverage["exact_point_memberships"] == 498, "coverage counts")
    for size in (125, 129):
        row = cases[f"pressure{size}"]["F"]
        require(row["solver_path"] == "032" and row["native_pair_diagnostic"] == [size-1, size-1], "pressure witness")
        require(row["distance_m"] == (3 / 32768) ** 0.5, "pressure distance")
    require(cases["pressure129"]["C"]["reason"] == "surface_pair_budget", "previous limit")
    other = cases["original031_different_pair129"]
    require(other["F"]["reason"] == "surface_pair_budget" and other["C"]["known"], "original unknown")
    print("84 fixed cases; 83 known distances and 1 original unknown. Pressure 129: 9.568319 mm.")

    for family in ("G60", "B02"):
        result = review["host"][family]
        groups = []
        for group, reference in zip(clocks[family], result["groups"], strict=True):
            costs = {}
            for arm, row in group["cells"].items():
                require(row["sha256"] == indexed[row["source"]], row["source"])
                costs[arm] = {
                    "business": (row["last_reply_ns"] - row["first_request_ns"]) / 1e6,
                    "process": (max(row["wrapper_exit_100ns"],row["service_exit_100ns"]) - row["wrapper_created_100ns"]) / 1e4,
                    "client": (row["client_end_ns"] - row["client_start_ns"]) / 1e6,
                }
                require(all(abs(t - reference[arm][key]) < 1e-9 for key,t in costs[arm].items()), row["source"])
            groups.append(costs)
        require(len(groups) == 6, family)
        for baseline, metrics in result["comparison"].items():
            for metric, reference in metrics.items():
                ratios = [100 * (group["F"][metric] / group[baseline][metric] - 1)
                          for group in groups]
                center = statistics.median(ratios)
                wins = sum(value < 0 for value in ratios)
                require(abs(center - reference["paired_pct"]) < 1e-9 and wins == reference["faster"],
                        f"{family}/{baseline}/{metric}")
                if metric == "business":
                    print(f"{family}, F vs {baseline}: {center:+.2f}% elapsed, {wins}/6 faster.")
    warm = review["host"]["Yanyite"]["warm"]
    differences = []
    percentages = []
    for group in clocks["Yanyite"]:
        elapsed = {}
        for arm,row in group["cells"].items():
            require(row["sha256"] == indexed[row["source"]], row["source"])
            elapsed[arm] = (row["warm_decoded_ns"] - row["warm_started_ns"]) / 1e6
        differences.append(elapsed["F"] - elapsed["A"])
        percentages.append(100 * (elapsed["F"] / elapsed["A"] - 1))
    require(len(differences) == 12 and abs(statistics.median(differences) - warm["paired_ms"]) < 1e-9 and
            abs(statistics.median(percentages) - warm["paired_pct"]) < 1e-9, "Yanyite warm pairs")
    print(f"Yanyite warm: {warm['paired_ms']:+.2f} ms, {warm['paired_pct']:+.2f}% elapsed.")
    for name, slots in review["host"]["spots"].items():
        for step, value in slots["F"].items():
            print(f"{name} {step}: A {slots['A'][step]['ms']:.2f} -> F {value['ms']:.2f} ms (one observation).")


def git_blob(commit, path):
    return subprocess.check_output(["git", "-C", str(REPO), "show", f"{commit}:{path}"])


def rebuild(output):
    pins = load(HERE / "candidate" / "PINS.json")
    with tempfile.TemporaryDirectory(prefix="he049_rebuild_") as tmp:
        root = Path(tmp) / "source"
        root.mkdir()
        for row in pins["source_manifest"]:
            name = row["path"]
            if name in ("human_eye_plugin/_surface_geometry_032.py", "human_eye_plugin/_surface_proximity_032.py"):
                continue  # Both packaged 032 modules are added by F.patch.
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(git_blob(HOOK if name == "human_eye_hook.py" else R3, name))
        for name, ref in pins["packaging_sources"].items():
            data = git_blob(BASE, name)
            require(digest(data) == ref["sha256"], name)
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        # Apply Git bytes to the temporary sources, independent of checkout line-ending rules.
        patch_env = {k:v for k,v in os.environ.items() if k not in ("GIT_DIR","GIT_WORK_TREE","GIT_INDEX_FILE")}
        for name in PATCHES:
            subprocess.run(["git","-c","core.autocrlf=false","-c","core.eol=lf","apply","--whitespace=nowarn","-"], input=git_blob("HEAD",name),
                           cwd=root, env=patch_env, check=True)
        for row in pins["source_manifest"]:
            require(digest((root / row["path"]).read_bytes()) == row["sha256"], row["path"])
        build = Path(tmp) / "build"
        subprocess.run([sys.executable, "-I", "-B", str(root / "verification/build_candidate_release.py"),
                        "--output", str(build), "--version", pins["version"]], cwd=root,
                       check=True, stdout=subprocess.DEVNULL)
        name = Path(pins["wheel"]["path"].replace("\\","/")).name
        wheel = build / name
        require(digest(wheel.read_bytes()) == pins["wheel"]["sha256"], "wheel SHA-256")
        output.mkdir(parents=True, exist_ok=True)
        dest = output / name
        if dest.exists():
            require(digest(dest.read_bytes()) == pins["wheel"]["sha256"], f"different existing file: {dest}")
        else:
            with wheel.open("rb") as source, dest.open("xb") as target:
                shutil.copyfileobj(source,target)
        print(f"{dest}  SHA-256 {pins['wheel']['sha256']}")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-dir", type=Path, help="also rebuild the frozen wheel into this directory")
    args=parser.parse_args()
    check_records()
    if args.wheel_dir is not None:
        rebuild(args.wheel_dir.resolve())
