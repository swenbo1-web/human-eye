"""Render the already-computed, fixed-matrix descriptive results."""

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ms(value):
    return f"{value / 1e6:.5f}"


def interval(distribution):
    return f"{ms(distribution['minimum'])}–{ms(distribution['maximum'])}"


def main():
    result_path = HERE / "run_02/RESULTS.json"
    raw = result_path.read_bytes()
    result = json.loads(raw)
    sessions = result["sessions"]
    lifecycle = result["batch_lifecycle_and_control"]
    version = result["version_comparisons"]
    lines = [
        "# One controlled default-latency matrix",
        "",
        "The two matched session blocks have opposite signs for the candidate-versus-baseline difference. Attribution of the earlier regression remains unresolved. The controlled ON/OFF mode chain shows a consistent positive paired difference in these four sessions.",
        "",
        "## Integrity and scope",
        "",
        f"The saved-record analysis passed {result['check_count']} checks with zero failures. Four fixed B,C,C,B sessions completed 88 business calls, 40 warm pairs, 92 received worker RPCs and {sum(session['all_product_stdio_records'] for session in sessions)} product stdio messages. Each version contributes two independent sessions. All raw warm observations remain in the machine result under each session's rows and summary distributions.",
        "",
        "The source, exact request, facts, capture generation, profiler schedule/restoration, required kernel counters, actual process PID/exit proof and owned close gates passed. The two original product versions remain e077/53db and a81/9f28. The implementation's later schema version remains outside this experiment.",
        "",
        "## Session observations",
        "",
        "All times in the following table are milliseconds. ON and OFF each contain ten warm observations per session. The paired column is the median of ten individual ON-minus-OFF differences.",
        "",
        "| Session | ON median | ON range | OFF median | OFF range | Paired difference median | Paired difference range |",
        "| --- | ---: | --- | ---: | --- | ---: | --- |",
    ]
    for session in sessions:
        summary = session["summary"]
        on, off, paired = [summary[key]["entry_elapsed_ns"] for key in ("ON", "OFF", "paired_ON_minus_OFF")]
        lines.append(f"| {session['case']['id']} | {ms(on['median'])} | {interval(on)} | {ms(off['median'])} | {interval(off)} | {ms(paired['median'])} | {interval(paired)} |")
    lines += ["", "| Session | Cold | Warmup | ON position 1 / 2 | OFF position 1 / 2 |",
              "| --- | ---: | ---: | --- | --- |"]
    for session in sessions:
        summary = session["summary"]
        positions = {profile: " / ".join(ms(summary["position"][profile][str(position)]["entry_elapsed_ns"]["median"])
            for position in (1, 2)) for profile in ("ON", "OFF")}
        lines.append(f"| {session['case']['id']} | {ms(summary['cold']['entry_elapsed_ns']['median'])} | {ms(summary['warmup']['entry_elapsed_ns']['median'])} | {positions['ON']} | {positions['OFF']} |")
    lines += ["", "Cold and warmup values remain separate. Each position stratum has five observations per mode. Previous-mode strata and all individual paired differences remain in RESULTS.json. Their populations follow the fixed logical state chain, including repeated ON or OFF across pair boundaries.",
              "", "## Version contrasts", "",
              "| Matched baseline / candidate sessions | C minus B, ON | C minus B, OFF | Interaction |",
              "| --- | ---: | ---: | ---: |"]
    for block in version["matched_blocks"]:
        value = block["contrasts"]["entry_elapsed_ns"]
        lines.append(f"| {block['baseline_session']} / {block['candidate_session']} | {ms(value['C_minus_B_ON'])} | {ms(value['C_minus_B_OFF'])} | {ms(value['interaction'])} |")
    on = version["equal_weight_version_difference"]["ON"]["entry_elapsed_ns"]
    off = version["equal_weight_version_difference"]["OFF"]["entry_elapsed_ns"]
    lines += ["", f"Equal-weight differences of the two session medians are {ms(on)} ms under ON and {ms(off)} ms under OFF. The matched-block interactions have different signs. These descriptive results retain the session as the independent unit.",
              "", "## Complete recorded cost", "",
              f"Batch wall time is {lifecycle['batch_wall_ns'] / 1e9:.7f} seconds. It includes frozen-commit verification of {lifecycle['frozen_commit_verification_ns'] / 1e6:.4f} ms and input verification of {lifecycle['preparation_verification_elapsed_ns'] / 1e6:.4f} ms. The four session walls total {result['sum_session_wall_ns'] / 1e9:.7f} seconds. The batch endpoint precedes its final result publication and excludes interpreter import, as recorded by the frozen entry.",
              "", "| Recorded stage | Sum over four sessions, ms |", "| --- | ---: |"]
    stage_names = sorted({name for session in sessions for name in session["lifecycle_and_control"]["timing_stages_ns"]})
    for name in stage_names:
        value = sum(session["lifecycle_and_control"]["timing_stages_ns"].get(name, 0) for session in sessions)
        lines.append(f"| {name} | {ms(value)} |")
    lines += ["", "The verification sum is already included in business_loop. Stage values and nested request spans overlap. Entry, Peer, trace, host capture, content encoding, verification and inclusive QA scope distributions remain available for every mode and session.",
              "", "| Session | Stdio TX bytes | Stdio RX bytes | Product lifetime peak RSS bytes |", "| --- | ---: | ---: | ---: |"]
    for session in sessions:
        peaks = [row["lifetime_product_peak_rss"]["bytes"] for row in session["rows"] if row.get("lifetime_product_peak_rss")]
        lines.append(f"| {session['case']['id']} | {session['product_stdio_tx_bytes']} | {session['product_stdio_rx_bytes']} | {max(peaks) if peaks else 'unmeasured'} |")
    lines += ["", "Product memory records are process-lifetime OS high-water marks. Worker OS peak and isolated request allocations remain unmeasured.",
              "", "## Interpretation limits and retained correction", "",
              "The ON-minus-OFF difference includes callback execution, state checks and the natural dict-versus-null recording/publication path. The inclusive profile_scope starts with state construction and overlaps the before/after probes. New probe boundaries differ from the earlier experiment. Callback-only overhead remains unisolated, and observed bpy C-method names remain incomplete.",
              "", "The frozen analyzer's first saved-only run stopped on a KeyError for pair_calls in warm telemetry. Its original source, error and partial checks remain unchanged in run_01. A source-bound field-contract review found that warm cache-hit telemetry emits three initialized kernel counters, while pair_calls and rank_calls are absent. The derived script checks the three required keys directly and explicitly records the absent extra counters. Nine metadata regressions cover the real sparse shape and rejection of missing/nonzero required counters. SOURCE.diff and both installed source fragments remain under field_fix_001.",
              "", "The earlier sealed +3.57% observation and admission state remain part of the record. This experiment adds a controlled observation with two sessions per version. Production latency equivalence, model-task benefit and full admission remain unestablished. No additional runtime sample, image, consumer, installation or paid API call was added by analysis."]
    report = "\n".join(lines) + "\n"
    with (HERE / "run_02/REPORT.md").open("x", encoding="utf8", newline="\n") as stream:
        stream.write(report)
    metadata = {"analysis_result_sha256": sha(raw), "report_sha256": sha(report.encode()),
        "writer_source_sha256": sha(Path(__file__).read_bytes()),
        "frozen_analyzer_unchanged": sha((HERE / "analyze_saved.py").read_bytes()) == "ce877249d0cbb85ae3edfa4342af6672ebd25256f64fa9a84e747a6ae53c3dff",
        "extra_runtime_measurements": 0, "full_admission": False}
    with (HERE / "run_02/REPORT_METADATA.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(metadata, stream, indent=2, sort_keys=True)
        stream.write("\n")
    assert result_path.read_bytes() == raw
    print(json.dumps(metadata))


if __name__ == "__main__":
    main()
