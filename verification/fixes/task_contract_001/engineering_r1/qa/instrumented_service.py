"""Existing owned P entry with in-memory counters for this acceptance only."""
import json
from pathlib import Path
import sys
import time

from human_eye_plugin import geometry_safety as geometry
from human_eye_plugin import task_query
from human_eye_plugin import live_spatial_mcp
from human_eye_plugin.blender_mcp_host import BlenderMCPHost
from verification import visual004_session
from verification.perf010_qualification import main

workspace = Path(sys.argv[sys.argv.index("--workspace") + 1])
counts = dict(pair_measurements=0, scalar_surface_traversals=0,
              witness_surface_traversals=0, paired_sat_calls=0,
              fallback_sat_calls=0, selected_captures=0, full_captures=0,
              task_content_encodings=0)
publish_ns = 0


def counted(function, name):
    def call(*args, **kwargs):
        counts[name] += 1
        return function(*args, **kwargs)
    return call


geometry._surface_distance = counted(geometry._surface_distance, "scalar_surface_traversals")
geometry._surface_distance_with_witness = counted(
    geometry._surface_distance_with_witness, "witness_surface_traversals")
geometry._single_convex_collision_and_zero = counted(
    geometry._single_convex_collision_and_zero, "paired_sat_calls")
geometry._certified_solid_collision = counted(geometry._certified_solid_collision, "fallback_sat_calls")
geometry.measure_pair_geometry = counted(geometry.measure_pair_geometry, "pair_measurements")
task_query.measure_pair_geometry = geometry.measure_pair_geometry
BlenderMCPHost.capture_task_scene = counted(BlenderMCPHost.capture_task_scene, "selected_captures")
BlenderMCPHost.capture_scene = counted(BlenderMCPHost.capture_scene, "full_captures")
original_tool_result = live_spatial_mcp._tool_result


def tool_result(value, **kwargs):
    if isinstance(value, dict) and value.get('result_kind') == 'task_query':
        counts['task_content_encodings'] += 1
    return original_tool_result(value, **kwargs)


live_spatial_mcp._tool_result = tool_result
original_handle = visual004_session.OwnerBroker.handle


def handle(self, request):
    global publish_ns
    try:
        return original_handle(self, request)
    finally:
        started = time.perf_counter_ns()
        if workspace.exists():
            (workspace / "QA_COUNTS.json").write_text(json.dumps(dict(
                counts=counts, counter_publish_ns_before_this_write=publish_ns,
                scope="actual calls to wrapped original entry points; no numeric changes"),
                indent=2) + "\n", encoding="utf8")
        publish_ns += time.perf_counter_ns() - started


visual004_session.OwnerBroker.handle = handle
main()
