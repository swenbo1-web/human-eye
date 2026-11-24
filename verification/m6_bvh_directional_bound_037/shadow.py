"""Non-pruning shadow probe for the fixed 032 dual-tree loop."""
from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
from time import perf_counter_ns


SCRATCH_BITS = 512
WORK_KEYS = ("work_units", "node_pair_visits", "queue_pushes", "leaf_pair_visits",
             "subtree_pruned_pairs", "aabb_pruned_pairs", "plane_pruned_pairs",
             "witness_projection_pruned_pairs", "narrow_phase_pairs",
             "witness_projection_credit_node_units", "witness_projection_credit_narrow_units",
             "witness_projection_credit_spent_units")


def dot_bound(box, axis):
    lower, upper = box[:2]
    low = high = 0
    for lo, hi, n in zip(lower, upper, axis):
        if n >= 0:
            low += n * lo
            high += n * hi
        else:
            low += n * hi
            high += n * lo
    return low, high


def enclosed(node, axis):
    if node[3] is not None:
        return dot_bound(node, axis)
    a, b = dot_bound(node[4],axis), dot_bound(node[5],axis)
    return min(a[0],b[0]), max(a[1],b[1])


def interval_gap(a,b):
    return max(a[0]-b[1],b[0]-a[1],0)


def members(node):
    if node[3] is not None:
        return list(node[3])
    return members(node[4]) + members(node[5])


def work_read(budget):
    return tuple(budget.counts.get(k,0) for k in WORK_KEYS)


def work_diff(before,budget):
    return {key:after-old for key,old,after in zip(WORK_KEYS,before,work_read(budget))}


class Shadow:
    """Observe A's actual order. A successful root only tags A's descendants."""
    def __init__(self, prepared, roots, shift):
        self.prepared = prepared
        self.shift = shift
        self.coord_bits = max(abs(v).bit_length() for node in roots for corner in node[:2] for v in corner)
        self.count = Counter()
        self.cost_ns = Counter()
        self.roots = []
        self.tags = {}
        self.active = None
        self.descendant = False
        self.parent_work = defaultdict(Counter)
        self.parent_ns = Counter()
        self.saved_work = defaultdict(Counter)
        self.saved_ns = Counter()

    def begin(self, serial, budget, cursor):
        self.active = self.tags.pop(serial,None)
        self.descendant = self.active is not None
        if self.descendant:
            self.before = cursor
            self.before_work = work_read(budget)

    def consider(self, serial, left, right, best, projection, budget):
        if self.descendant:
            return
        self.count["original_AABB_passed"] += 1
        if not projection or (left[3] is not None and right[3] is not None):
            return
        assert projection.best is best and best[0] > 0
        self.count["valid_direction_internal"] += 1
        started = perf_counter_ns()
        axis = projection.axis
        if sum(n != 0 for n in axis) <= 1:
            self.count["single_axis_skipped"] += 1
            self.cost_ns["check"] += perf_counter_ns()-started
            return
        axis_bits = max(abs(n).bit_length() for n in axis)
        # Three products per dot and one interval subtraction add at most three bits.
        if self.coord_bits+axis_bits+3 > SCRATCH_BITS:
            self.count["local_bits_skipped"] += 1
            self.cost_ns["check"] += perf_counter_ns()-started
            return
        self.count["projected_nodes"] += 1
        self.count["projected_boxes"] += 2 + int(left[3] is None) + int(right[3] is None)
        la, rb = enclosed(left,axis), enclosed(right,axis)
        gap = interval_gap(la,rb)
        excluded = gap > projection.cutoff
        self.cost_ns["candidate_proof_including_checks"] += perf_counter_ns()-started
        if not excluded:
            return
        started = perf_counter_ns()
        ag,bg = dot_bound(left,axis),dot_bound(right,axis)
        parent_gap = interval_gap(ag,bg)
        self.cost_ns["diagnostic_parent_comparison"] += perf_counter_ns()-started
        assert parent_gap <= gap
        tag = len(self.roots)
        self.active = tag
        self.roots.append((serial,left,right,best,axis,projection.cutoff,gap,parent_gap,projection.epoch,
                           budget.counts["work_units"],budget.counts["narrow_phase_pairs"]))
        self.count["new_root_exclusions"] += 1
        self.count["proved_cartesian_triangle_pairs"] += left[2] * right[2]
        label = "also_strict_parent_projection" if parent_gap > projection.cutoff else "strict_only_child_envelope"
        self.count[label] += 1

    def before_push(self, serial, budget):
        if self.active is None:
            return None
        self.tags[serial] = self.active
        if self.descendant:
            return None
        return perf_counter_ns(), work_read(budget)

    def after_push(self, token, budget):
        if token is not None:
            start,before = token
            self.parent_ns[self.active] += perf_counter_ns()-start
            self.parent_work[self.active].update(work_diff(before,budget))

    def end(self, budget):
        if self.descendant:
            self.saved_ns[self.active] += perf_counter_ns()-self.before
            delta = work_diff(self.before_work,budget)
            # begin() runs after the existing node tick and heap dequeue.
            delta["node_pair_visits"] += 1
            delta["work_units"] += 1
            self.saved_work[self.active].update(delta)

    def receipt(self):
        assert not self.tags
        witnesses=[]
        for j,row in enumerate(self.roots):
            serial,left,right,best,axis,cutoff,gap,parent_gap,epoch,at_work,at_narrow = row
            left_rows,right_rows=members(left),members(right)
            assert len(set(left_rows))==len(left_rows)==left[2] and len(set(right_rows))==len(right_rows)==right[2]
            n2 = sum(n*n for n in axis)
            assert gap*gap*best[1] > n2*best[0]
            intervals=[]
            for node,faces,side in ((left,left_rows,0),(right,right_rows,1)):
                samples=[sum(v*n for v,n in zip(pt,axis)) for face in faces for pt in self.prepared[side][face][0]]
                low,high=enclosed(node,axis)
                assert low <= min(samples) <= max(samples) <= high
                intervals.append({"outer":[low,high],"exact_members":[min(samples),max(samples)]})
            assert interval_gap(*(r["exact_members"] for r in intervals))>=gap
            work = self.saved_work[j]+self.parent_work[j]
            tail_stats = {key: work[key] for key in WORK_KEYS}
            later_pruned=sum(tail_stats[k] for k in (
                "subtree_pruned_pairs","aabb_pruned_pairs","plane_pruned_pairs","witness_projection_pruned_pairs"))
            assert later_pruned+tail_stats["narrow_phase_pairs"]==left[2]*right[2]
            # Every descendant leaf box remains outside the exact current
            # upper bound, so A must already prune before any leaf branch.
            assert tail_stats["subtree_pruned_pairs"]==left[2]*right[2]
            assert tail_stats["leaf_pair_visits"]==tail_stats["narrow_phase_pairs"]==0
            witnesses.append({"queue_serial":serial,"projection_epoch":epoch,"axis":axis,"integer_cutoff":cutoff,
                "best_local_sq":str(Fraction(best[0],best[1])),
                "pair_members":[sorted(left_rows),sorted(right_rows)],"intervals":intervals,
                "parent_gap":parent_gap,"child_gap":gap,
                "at_original_units":at_work,"at_original_narrow_calls":at_narrow,
                "baseline_descendants":tail_stats,"baseline_later_pruned_pairs":later_pruned,
                "baseline_inclusive_spans_ns":self.saved_ns[j]+self.parent_ns[j]})
        checked=sum(self.cost_ns.values())
        return {"stats":dict(self.count),"shift":self.shift,"frame_coord_bits":self.coord_bits,
                "probe_cost_ns":dict(self.cost_ns),"all_instrumented_proof_and_parent_cost_ns":checked,
                "root_receipts":witnesses}


def overlay(source):
    """Prepare an isolated shadow module. Original statements are kept in place."""
    begin=source.index("def _nearest_tree(")
    stop=source.index("\ndef _nearest(",begin)
    head, tree, tail=source[:begin],source[begin:stop],source[stop:]

    def insert(old,new):
        nonlocal tree
        assert tree.count(old)==1,old
        tree=tree.replace(old,new)

    insert("    pending = []\n", "    pending = []\n    monitor = Shadow(prepared, roots, shift)\n")
    insert("        key = _queue_distance(left, right, shift, budget)\n",
           "        token = monitor.before_push(serial, budget)\n"
           "        key = _queue_distance(left, right, shift, budget)\n")
    insert("        serial += 1\n", "        serial += 1\n        monitor.after_push(token, budget)\n")
    # Only include timestamps for actual removed-baseline descendants. The
    # active tag is looked up by the original serial, preserving heap content.
    insert("        key, _, left, right = heapq.heappop(pending)\n",
           "        key, _, left, right = heapq.heappop(pending)\n"
           "        if monitor.tags:\n"
           "            monitor.begin(_, budget, perf_counter_ns())\n"
           "        else:\n"
           "            monitor.active = None\n"
           "            monitor.descendant = False\n")
    insert("                continue\n        if left[3] is not None and right[3] is not None:",
           "                continue\n"
           "            monitor.consider(_, left, right, best, projection, budget)\n"
           "        if left[3] is not None and right[3] is not None:")
    start=tree.index("        if best is not None:\n")
    end=tree.index("    if witness_pair is not None",start)
    body=tree[start:end]
    tree=tree[:start]+"        try:\n"+"".join("    "+line if line.strip() else line for line in body.splitlines(True))+(
        "        finally:\n"
        "            if monitor.descendant:\n"
        "                monitor.end(budget)\n"
        "    _shadow_037_collect.append(monitor)\n")+tree[end:]
    return head+tree+tail
