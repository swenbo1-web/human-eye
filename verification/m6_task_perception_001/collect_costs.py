"""Keep research preparation, consumer execution and cached-runtime costs explicit."""

import datetime
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read,write,identity


def collect():
    phases={}
    for path in sorted((HERE/"private/processes").glob("*.controller.json")):
        controller=read(path.relative_to(HERE))
        worker=read("private/processes/"+controller["label"]+".json")
        phases[controller["label"]]=dict(controller=controller,worker=worker)
    consumers=[]
    for path in sorted((HERE/"private/consumers").glob("t*/*/CONSUMER.json")):
        value=read(path.relative_to(HERE))
        consumers.append(dict(task_id=value["task_id"],route=value["route"],status=value["status"],valid_completion=value["valid_completion"],
            wall_s=value.get("wall_s"),tool_calls=value.get("tool_count"),usage=value.get("usage"),fees=value.get("fees"),
            record=identity(path),provider_retry_observations=value.get("provider_retry_observations",[])))
    routes={}
    for route in ("native","facts","learned"):
        rows=[row for row in consumers if row["route"]==route]
        tokens={}
        for row in rows:
            for key,value in (row["usage"] or {}).items():
                tokens[key]=tokens.get(key,0)+value
        routes[route]=dict(attempted=len(rows),completed=sum(row["valid_completion"] for row in rows),
            consumer_wall_sum_s=sum(row["wall_s"] or 0 for row in rows),tool_calls=sum(row["tool_calls"] or 0 for row in rows),
            actual_usage_sum=tokens,monetary_fees=None,usage_scope="actual public CLI counts, cached input is a subset of input, fee not exposed")
    now=datetime.datetime.now(datetime.timezone.utc)
    registered=datetime.datetime.fromtimestamp(1794750697.961201,datetime.timezone.utc)
    walls=sum(row["controller"]["wall_s"] for row in phases.values())
    features=read("FEATURES.json")
    stage_names=set(name for case in features["cases"] for name in case["timings"])
    stages={name:{key:sum(case["timings"].get(name,{}).get(key,0) for case in features["cases"]) for key in ("wall_s","cpu_s","calls")} for name in sorted(stage_names)}
    files=[path for path in HERE.rglob("*") if path.is_file()]
    categories={name:sum(path.stat().st_size for path in (HERE/"private"/name).rglob("*") if path.is_file()) for name in ("current","features","model","predictions","request_cache","consumers")}
    runtime=read("RUNTIME_QA.json") if (HERE/"RUNTIME_QA.json").exists() else None
    consumer_summary=read("CONSUMERS.json") if (HERE/"CONSUMERS.json").exists() else None
    smoke=read("private/smoke/RESULT.json") if (HERE/"private/smoke/RESULT.json").exists() else None
    recovery_path=HERE/"private/consumers/recovery/RECOVERY.json"
    recovery=read(recovery_path.relative_to(HERE)) if recovery_path.exists() else None
    return dict(cycle_id="M6-TASK-PERCEPTION-001",snapshot_utc=now.isoformat(),task_registered_utc=registered.isoformat(),
        elapsed_task_wall_s=(now-registered).total_seconds(),phases=phases,numerical_controller_wall_sum_s=walls,numerical_budget_wall_s=7200,
        worker_tree_CPU_sum_s=sum(row["worker"]["tree_cpu_s"] for row in phases.values()),
        maximum_sampled_simultaneous_tree_RSS_bytes=max(row["worker"]["tree_sampled_peak_working_set_bytes"] for row in phases.values()),
        maximum_observed_process_lifetime_peak_bytes=max(p["peak_working_set_bytes"] for row in phases.values() for p in row["worker"]["process_tree"]),
        target_memory_bytes=4*1024**3,phase_failures=[dict(label=key,wall_s=value["controller"]["wall_s"],returncode=value["controller"]["returncode"]) for key,value in phases.items() if value["controller"]["returncode"]],
        shared_feature_preparation=dict(observations=600,F_points=230400,shape=[384,5,16],controller_wall_s=phases["features"]["controller"]["wall_s"],stages=stages,
            unassigned_wall_s=phases["features"]["controller"]["wall_s"]-sum(row["wall_s"] for row in stages.values()),
            scope="full600 current-descriptor/context cache setup, includes baseline geometry statistic and learned input, one shared actual preparation. Unassigned includes context-cache compression, process startup/index/loop/write overhead."),
        training=dict(versions=2,steps_each=1200,parameters=11969,wall_s=sum(row["controller"]["wall_s"] for row in phases.values() if row["controller"]["phase"] in ("train_v1","train_v2")),
            feature_preparation_separately_above=True,verification_optimizer_step_replays=0),
        runtime_entrypoints=runtime,cache_storage_bytes=categories,total_new_disk_bytes_snapshot=sum(path.stat().st_size for path in files),
        consumers=consumers,by_route=routes,consumer_task_count=len(consumers),consumer_task_cap=24,
        consumer_complete_summary=consumer_summary,local_protocol_smoke=smoke,
        consumer_sessions_wall_sum_s=sum(row["wall_s"] or 0 for row in consumers),
        full_comparison_accounting="Actual shared600-observation data/descriptor/cache setup is charged once above, training and batch inference separate, consumer session wall includes tool execution/reference/cache/fallback time. These nested component times are not added a second time. Single-observation cold/warm/focus subprocess measurements separate. Route-only cached-read times do not represent full cold preparation.",
        per_task_exclusive_preparation_attribution="unmeasured for8-case subset, full600 actual preparation and measured stages retained instead of inventing exclusive cold task costs",
        consumer_infrastructure_recovery=recovery,provider_replacement=False,paid_API_restored=False,new_mesh_download_bytes=0,original_asset_changes=0,product_changes=0,blender_actions=0,
        authoring_and_waiting_scope="elapsed task wall includes authoring, source/contract reads, compilation and failure recovery, consumer waits and tool/model latency. Consumer calls overlap later read-only verification. Exclusive per-activity residual is not inferred by subtracting overlapping sums.",
        unmeasured=["monetary fees", "provider-internal requests and retries", "resolved reasoning effort if absent", "complete consumer CLI tree CPU/RSS", "graceful bridge EOF close receipts", "CPU of read-only authoring shell commands and administration", "short descendants missed by50ms discovery", "pre-registration contract read cost"],
        measurement="single-thread research and local Python workers, nonexclusive host. CPU/RSS from process tree, CLI login transport reuse is read-only. No formal plugin startup or OS-isolation certification.")


if __name__=="__main__":
    write("COSTS.json",collect())
