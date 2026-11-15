"""Retain each local protocol attempt and the exact source bytes it exercised."""

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from consumer_bridge import write


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    root = HERE / "private/consumer_preflight"
    shell_walls = [2.7756792, 1.1968846]
    reports = sorted(root.glob("*/RESULT.json"), key=lambda path:path.stat().st_mtime_ns)
    runs, checks = [], {}
    for index,path in enumerate(reports):
        result = json.loads(path.read_bytes())
        folder = root / "sources" / path.parent.name
        folder.mkdir(parents=True,exist_ok=False)
        identities = []
        for source in result["source_identities"]:
            raw = (HERE / source["path"]).read_bytes()
            reconstruction = None
            if sha(raw) != source["sha256"] and source["path"] == "consumer_bridge.py":
                text = raw.decode("utf8").replace("from python_executor import execute, legacy as process_metrics", "from python_executor import execute")
                text = text.replace("            process_id=os.getpid(), process_metrics=process_metrics.lifetime_metrics(),\n", "")
                raw = text.encode("utf8")
                reconstruction = "Reverse the subsequent process-id/lifetime-metrics instrumentation, verified against the original preflight SHA."
            matches = sha(raw) == source["sha256"]
            checks[path.parent.name+"_"+source["path"]] = matches
            if not matches:
                raise AssertionError("exact_preflight_source_not_reconstructed_"+source["path"])
            destination = folder / source["path"]
            destination.write_bytes(raw)
            identities.append(dict(path=str(destination.relative_to(HERE)),bytes=len(raw),sha256=sha(raw),reconstruction=reconstruction))
        runs.append(dict(run_id=path.parent.name,status=result["status"],checks=result["count"],
            script_wall_s=result["wall_s"],parent_CPU_s=result["parent_CPU_s"],observed_shell_wall_s=shell_walls[index],
            actual_Pro_sessions=0,actual_Blender_calls=0,source_archives=identities))
    current = []
    for name in ("consumer_runner.py","consumer_bridge.py","python_executor.py","image_inputs.py"):
        raw = (HERE / name).read_bytes()
        current.append(dict(path=name,bytes=len(raw),sha256=sha(raw)))
    write(root / "RUNS.json",dict(runs=runs,checks=checks,status="pass" if all(checks.values()) else "fail",
        measured_shell_wall_s=sum(row["observed_shell_wall_s"] for row in runs),
        successful_script_wall_s=sum(row["script_wall_s"] for row in runs),
        successful_parent_CPU_s=sum(row["parent_CPU_s"] for row in runs),
        accounting="Each script timer is nested inside its shell timer. Runs use local protocol clients and a mock editing API. No Pro or Blender launched.",
        current_source_identities=current))
    write(HERE / "CONSUMER_SOURCE_IDENTITIES.json",dict(files=current,actual_Pro_sessions=0,preflight_source_archives_verified=True))
    print("source archives verified",len(checks),"runs",len(runs))


if __name__ == "__main__":
    main()
