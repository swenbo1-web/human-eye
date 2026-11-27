"""Recheck the full H3 diagnostic event ledgers without loading a kernel."""
from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

from common import dump, pin, read

PINS = {
    "A-native": (559, 10, 11445, 0),
    "B-native": (1571, 32, 14311, 439),
    "B-zero": (1572, 16, 12405, 75),
    "B-positive": (1571, 32, 14311, 439),
    "B-leaf4": (861, 35, 10795, 123),
    "B-median": (1341, 22, 12638, 446),
    "B-seed": (1571, 29, 14182, 527),
    "C-native": (1572, 16, 12405, 75),
}


def compare(folder):
    rows = {key: read(folder / (key + ".json")) for key in PINS}
    fields = ("node_pair_visits", "narrow_phase_pairs", "work_units", "witness_projection_tests")
    final = {"native_pair": [49114, 0], "square_m2":
             "1706210241885292920107310683649/81129638414606681695789005144064"}
    facts = {}
    for key, row in rows.items():
        work = row["counters"]
        assert tuple(work.get(field, 0) for field in fields) == PINS[key]
        assert row["final"] == final and row["root"]["strict_inclusion"] and row["root"]["shift"] == 0
        assert work.get("witness_projection_pruned_pairs", 0) == 0
        facts[key] = {"trace": pin(folder / (key + ".json")), "counters": dict(zip(fields, PINS[key])),
            "tree_build_units": work["tree_build_units"], "first_final_upper": row["first_final_upper"],
            "first_final_canonical": row["first_final_canonical"],
            "accepted_counts": {name: sum(x["kind"] == name for x in row["accepted"])
                                for name in ("first_upper", "strict_improvement", "equal_distance_earlier_witness")}}
    b, c, zero, positive = (rows[key] for key in ("B-native","C-native","B-zero","B-positive"))
    assert c["events"] == zero["events"] and c["counters"] == zero["counters"]
    def pop_rows(row):
        return [x["entry"] for x in row["events"] if x["event"]=="pop"]
    def pop_shape(entry):
        return entry["left"], entry["right"]
    orig, changed, positive_only = map(pop_rows, (b, c, positive))
    assert list(map(pop_shape, orig)) == list(map(pop_shape, positive_only))
    divergent = next(i for i,(l,r) in enumerate(zip(orig,changed)) if pop_shape(l)!=pop_shape(r))
    assert divergent == 0 and orig[0]["key"]==changed[0]["key"]==0
    seed_b,seed_c=([x for x in row["events"] if x["event"]=="exact_start" and x["pops"]==0] for row in (b,c))
    assert seed_b==seed_c and len(seed_b)==2
    return {"status": "pass", "evidence": "instrumented deterministic execution, separate from timing",
        "final": final, "conditions": facts, "changed_first_distinct_heap_index": divergent+1,
        "first_B_pop": orig[0], "first_C_pop": changed[0],
        "same_greedy_seed_native_pairs": [x["native_pair"] for x in seed_b],
        "candidate_equals_zero_control_events_and_counts": True, "positive_control_leaves_pop_order_and_counts": True}


if __name__=="__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    print(dump(args.output, compare(args.folder)))
