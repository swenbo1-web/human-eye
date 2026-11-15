"""Bind zero-change readback deduplication to two actual initial sessions."""

from datetime import datetime, timezone
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from common import read,write,identity


def main():
    if (HERE/"OPTIMIZATION_BINDING.json").exists():
        raise ValueError("one_optimization_already_bound")
    initial=[]
    for route in ("native","facts"):
        consumer=HERE/"private/consumers/v1/forearm"/route/"CONSUMER.json"
        state=HERE/"private/sessions"/("v1_forearm_"+route)/"session.json"
        receipt=read(consumer)
        if receipt["status"]!="completed":
            raise ValueError("both_actual_initial_sessions_required")
        initial.append(dict(route=route,consumer=identity(consumer),session=identity(state),wall_s=receipt["wall_s"],usage=receipt["usage"],
            public_images=receipt["public_image_count"],PNG_bytes=receipt["public_image_bytes"]))
    write("OPTIMIZATION_BINDING.json",dict(bound_at_UTC=datetime.now(timezone.utc).isoformat(),initial_results=initial,
        initial_analysis=identity(HERE/"CONSUMER_STATS_v1.json"),initial_tools=identity(HERE/"TOOL_FREEZE.json"),
        issue="Both actual no-edit readbacks transmit identical before and after dual-definition station tables twice",
        evidence=dict(save_readback_text_bytes=46547,total_tool_text_bytes=92881,readback_share_percent=50.114,
            actual_total_initial_wall_s=178.703435,actual_readback_tool_wall_s=2.887665899994317),
        selected_change="Deduplicate exactly equal before/after contour tables only in the shared public short_quality response. Deliver one complete current table for each definition and an explicit equality marker. Preserve full raw QUALITY and all technical checks and identities.",
        invariants="Same assets, nine images, task, anchors, writable set, step budgets, model/effort, tools, saved-file reader and numerical evaluator. Changed geometry or unequal tables retain the complete original response.",
        expected_component_effect="Reduce repeated public text and associated context delivery. Whole-session timing remains an observation, without a promised speedup.",
        consumer_changes={},second_order=["facts","native"],additional_actual_Pro_sessions=2,training=0,
        image_observability="Raw bridge responses contain nine complete PNG ImageContent blocks per actual images call. CLI event serialization has a1MiB middle-truncation marker. Count delivery from complete bridge bytes and actual call events, and retain provider-internal encoding as unmeasured."))
    print("single public readback deduplication bound")


if __name__=="__main__":
    main()
