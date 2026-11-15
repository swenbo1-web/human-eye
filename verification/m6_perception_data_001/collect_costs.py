"""Collect measured process-tree costs, acquisition failures and storage."""

import datetime
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read, write


def collect():
    phases={}
    for path in sorted((HERE/"private/processes").glob("*.controller.json")):
        controller=read(path.relative_to(HERE))
        worker=read("private/processes/"+controller["label"]+".json")
        phases[controller["label"]]=dict(controller=controller,worker=worker)
    counted=sum(row["controller"]["wall_s"] for row in phases.values() if row["controller"]["compute_budget_counted"])
    acquisition=read("ACQUISITION.json")
    registered=datetime.datetime.fromtimestamp(1794746076.0267653,datetime.timezone.utc)
    now=datetime.datetime.now(datetime.timezone.utc)
    measured=sum(row["controller"]["wall_s"] for row in phases.values())
    # Shell envelopes include the reconstruction CLI and read-only metadata arithmetic.
    ad_hoc_envelopes=[1.3150734,.2345168,.087863,.3237855]
    return dict(cycle_id="M6-PERCEPTION-DATA-001",snapshot_utc=now.isoformat(),task_registered_utc=registered.isoformat(),
        elapsed_task_wall_s=(now-registered).total_seconds(),phases=phases,
        numerical_monitored_wall_s=counted,ad_hoc_readonly_shell_envelope_upper_sum_s=sum(ad_hoc_envelopes),
        numerical_budget_accounting_upper_s=counted+sum(ad_hoc_envelopes),numerical_budget_s=1800,
        all_monitored_phase_wall_s=measured,monitored_tree_CPU_s=sum(row["worker"]["tree_cpu_s"] for row in phases.values()),
        max_sampled_simultaneous_tree_RSS_bytes=max(row["worker"]["tree_sampled_peak_working_set_bytes"] for row in phases.values()),
        max_observed_process_lifetime_peak_bytes=max(p["peak_working_set_bytes"] for row in phases.values() for p in row["worker"]["process_tree"]),
        acquisition_wall_s=sum(row["controller"]["wall_s"] for row in phases.values() if row["controller"]["phase"]=="acquire"),
        HTTP_body_transfer_wall_s=sum(r["wall_s"] for r in acquisition["network_requests"]),
        archive_HTTP_body_bytes=acquisition["archive_http_bytes"],source_page_HTTP_body_bytes=8827,archive_budget_bytes=256*1024**2,
        new_disk_bytes_snapshot=sum(path.stat().st_size for path in HERE.rglob("*") if path.is_file()),new_disk_budget_bytes=2*1024**3,
        failures=[dict(label=key,returncode=row["controller"]["returncode"],wall_s=row["controller"]["wall_s"]) for key,row in phases.items() if row["controller"]["returncode"]],
        recovery="acquire reference .pose extension and codec spelling, original scripts/reports/logs retained, downloaded horse/page reused without re-download. Single dent matrix and single sampling simulation.",
        authoring_reading_inspection_and_tool_wait_residual_wall_s=max(0,(now-registered).total_seconds()-measured),
        residual_scope="inclusive elapsed remainder, not process CPU, overlaps network browser inspection and agent latency, no exact per-activity attribution",
        visual_inspection="12 source and12 paired real-geometry views inspected by root, view tool wall included in elapsed remainder",
        readonly_agent_review="old assignments current=false, three helpers supplied read-only design/code review. Root performed all new task writes and numerical execution. No new assignment borrowed.",
        unmeasured="pre-registration contract reads and administration CPU, short undiscovered process descendants, API internal inference cost, filesystem cache effects",
        measurement_scope="single-thread nonexclusive correctness run, process discovery50ms, launcher CPU separated from descendants, formal performance window absent",
        training_runs=0,model_forwards=0,repair_outputs=0,blender_actions=0,product_changes=0,paid_calls=0)


if __name__=="__main__":
    write("COSTS.json",collect())
