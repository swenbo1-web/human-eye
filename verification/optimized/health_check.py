"""Human-Eye source or explicitly targeted installed-package health checks.

在 P0 修复之后做一次覆盖性体检，确认没有影响既有功能与边界情况。

覆盖 5 组、16 项；跳过项不计为通过：
  A 产物与环境    A1 清单校验 / A2 类身份唯一 / A3 版本一致
  B 功能主线      B1 16 场景处方达标 / B2 六个工具 / B3 MCP 协议 / B4 冒烟脚本
  C 稳定性        C1 确定性 / C2 场景隔离 / C3 边界错误 / C4 无效几何与标架门禁
  D 性能          D1 关键路径分位耗时 / D2 缓存不无界增长
  E 兼容          E1 响应详略 / E2 旧字段保留 / E3 单元测试

用法：
    python -B verification/optimized/health_check.py --mode source --json out.json
    python -B verification/optimized/health_check.py --installed --installed-target <directory>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import importlib
import importlib.metadata
import importlib.machinery
import os
import pathlib
import re
import statistics
import subprocess
import sys
import time
import tempfile
import traceback

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT
MODE = "source"
EXPECTED_VERSION = ""
IMPORT_ORIGINS = {}
PRODUCT_MODULES = [
    "human_eye_foveated_renderer", "native_3d_spatial_scratchpad",
    "module_2_low_token_mcp_scene_bridge", "module_3_1_mcp_protocol_ipc_engine",
    "module_3_2_vlm_grounding_closed_loop_agent", "module_3_3_closed_loop_control_engine",
    "human_eye_plugin", "human_eye_plugin.plugin_facade", "human_eye_plugin.mcp_server",
    "human_eye_plugin.llm_tool_schemas", "human_eye_module1_operators",
    *["human_eye_module1_operators." + name for name in (
        "submodule_1_1_mesh_entity", "submodule_1_2_sub_frustum_gaze",
        "submodule_1_3_se3_alignment_math", "submodule_1_4_spatial_sniffer",
        "submodule_1_5_alignment_verifier", "submodule_1_6_quad_compositor",
        "native_3d_spatial_scratchpad")],
]

RESULTS = []


def _source_project_version():
    """Read this project's plain version string without a Python 3.11 dependency."""
    content = (SOURCE / "pyproject.toml").read_text(encoding="utf-8")
    sections = re.findall(
        r"(?ms)^[ \t]*\[project\][ \t]*(?:#[^\r\n]*)?\r?$\n(.*?)(?=^[ \t]*\[|\Z)", content)
    if len(sections) != 1:
        raise ValueError("Expected exactly one [project] section in selected source pyproject.toml")
    versions = re.findall(
        r'''(?m)^[ \t]*version[ \t]*=[ \t]*(["'])([^"'\\\r\n]+)\1[ \t]*(?:#[^\r\n]*)?$''',
        sections[0])
    if len(versions) != 1:
        raise ValueError("Expected exactly one plain quoted [project] version string")
    return versions[0][1]


def _scope_description():
    return f"{MODE}/runtime acceptance; no archive, wheel, MANIFEST or dist integrity acceptance"


def _module_path(target, name):
    path = pathlib.Path(target).joinpath(*name.split("."))
    return path / "__init__.py" if path.is_dir() else path.with_suffix(".py")


def _verify_import_origins():
    origins = {}
    for name in PRODUCT_MODULES:
        module = importlib.import_module(name)
        actual = pathlib.Path(module.__file__).resolve()
        expected = _module_path(SOURCE, name).resolve()
        if actual != expected:
            raise RuntimeError(f"Import outside selected {MODE} target: {name}: {actual}; expected {expected}")
        origins[name] = str(actual)
    return origins


class _TargetImportGuard:
    """Fail before executing product code from outside the selected target."""
    def find_spec(self, fullname, path=None, target=None):
        if (fullname in PRODUCT_MODULES or fullname.startswith("human_eye_plugin.")
                or fullname.startswith("human_eye_module1_operators.")):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            expected = _module_path(SOURCE, fullname).resolve()
            if spec is None or spec.origin is None or pathlib.Path(spec.origin).resolve() != expected:
                raise ImportError(f"Refusing {fullname} outside explicit target {SOURCE}")
            return spec
        return None


def _child_environment():
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONPATH"] = str(SOURCE)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_child(code, *, input_text=None, timeout=180):
    """No inherited PYTHONPATH and no repository cwd in installed mode."""
    bootstrap = (
        "import importlib,importlib.machinery,pathlib,sys\n"
        f"target=pathlib.Path({str(SOURCE)!r}).resolve()\n"
        f"names={PRODUCT_MODULES!r}\n"
        "class TargetGuard:\n"
        " def find_spec(self,name,path=None,target_arg=None):\n"
        "  if name in names or name.startswith('human_eye_plugin.') or name.startswith('human_eye_module1_operators.'):\n"
        "   spec=importlib.machinery.PathFinder.find_spec(name,path)\n"
        "   candidate=target.joinpath(*name.split('.'))\n"
        "   expected=(candidate/'__init__.py' if candidate.is_dir() else candidate.with_suffix('.py')).resolve()\n"
        "   if spec is None or spec.origin is None or pathlib.Path(spec.origin).resolve()!=expected:\n"
        "    raise ImportError(f'Refusing child import outside explicit target: {name}')\n"
        "   return spec\n"
        "  return None\n"
        "sys.meta_path.insert(0,TargetGuard())\n"
        "for name in names:\n"
        " module=importlib.import_module(name)\n"
        " path=target.joinpath(*name.split('.'))\n"
        " expected=(path/'__init__.py' if path.is_dir() else path.with_suffix('.py')).resolve()\n"
        " actual=pathlib.Path(module.__file__).resolve()\n"
        " if actual!=expected: raise RuntimeError(f'Wrong child import origin: {name}: {actual}; expected {expected}')\n"
    )
    with tempfile.TemporaryDirectory(prefix="human_eye_health_") as child_cwd:
        return subprocess.run([sys.executable, "-B", "-c", bootstrap + "\n" + code],
                              input=input_text, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout,
                              cwd=child_cwd, env=_child_environment())


def check(section, name, fn):
    t0 = time.perf_counter()
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"{type(exc).__name__}: {exc}"
        if "--trace" in sys.argv:
            traceback.print_exc()
    status = "skipped" if ok is None else ("passed" if ok else "failed")
    RESULTS.append({"section": section, "name": name, "ok": None if ok is None else bool(ok), "status": status,
                    "detail": detail, "ms": round((time.perf_counter() - t0) * 1000, 1)})
    return ok


# --------------------------------------------------------------------------
# A 产物与环境
# --------------------------------------------------------------------------
def a1_bundle():
    return None, (f"SKIPPED: {MODE}/runtime acceptance only; no release archive, wheel, "
                  "MANIFEST or dist integrity is certified by this run")


def a2_identity():
    IMPORT_ORIGINS.update(_verify_import_origins())
    import human_eye_foveated_renderer as mono
    import human_eye_module1_operators as pkg
    pairs = [("MeshEntity3D", pkg.MeshEntity3D, mono.MeshEntity3D),
             ("SpatialClearanceProbeResult", pkg.SpatialClearanceProbeResult, mono.SpatialClearanceProbeResult),
             ("ClosedLoopRecheckReport", pkg.ClosedLoopRecheckReport, mono.ClosedLoopRecheckReport)]
    bad = [n for n, a, b in pairs if a is not b]
    return (not bad), f"{len(IMPORT_ORIGINS)} imports from {SOURCE}; distinct classes: {bad or 'none'}"


def a3_version():
    import human_eye_plugin
    from human_eye_plugin import HumanEyeLLMPlugin
    if MODE == "source":
        declared = _source_project_version()
        basis = "selected source pyproject.toml"
    else:
        distributions = [d for d in importlib.metadata.distributions(path=[str(SOURCE)])
                         if d.metadata["Name"].lower().replace("_", "-") == "human-eye-spatial-plugin"]
        if len(distributions) != 1:
            return False, f"Expected one distribution metadata record in explicit target; found {len(distributions)}"
        declared = distributions[0].version
        basis = "explicit installed-target distribution metadata"
    versions = {human_eye_plugin.__version__, HumanEyeLLMPlugin.VERSION, declared}
    return len(versions) == 1, f"versions={sorted(versions)}; basis={basis}; no old release metadata used"


# --------------------------------------------------------------------------
# B 功能主线
# --------------------------------------------------------------------------
def _scenarios():
    from human_eye_plugin import HumanEyeLLMPlugin
    p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
    return {row[0]: list(row[1]) for row in p.vlm_agent._get_or_build_benchmark_scenarios()}


def b1_scenarios():
    import numpy as np
    from human_eye_plugin import HumanEyeLLMPlugin
    from human_eye_module1_operators import SE3AlignmentMath, SpatialAnomalySniffer
    fails = []
    table = _scenarios()
    for name, meshes in table.items():
        p = HumanEyeLLMPlugin(meshes=list(meshes), enable_zero_copy_ipc=False)
        args = dict(p.build_llm_observation_bundle(meshes=p.meshes)["prompt_bundle"].canonical_mcp_tool_call["arguments"])
        focal = next(m for m in meshes if m.is_focal_target)
        ref = next(m for m in meshes if m.object_id != focal.object_id)
        R = SE3AlignmentMath.euler_xyz_to_matrix(*args["rotation_euler_deg_xyz"])
        piv = np.array(args["pivot_world"], dtype=np.float64) if "pivot_world" in args else None
        al = focal.rotated_around_pivot(R, pivot=piv).translated(tuple(args["translation_xyz_m"]))
        pr = SpatialAnomalySniffer.probe_closest_clearance(al, ref, yaw_symmetry_order=2)
        if (abs(pr.signed_clearance_m) > 0.0005 or pr.is_penetrating
                or not pr.measurement_valid or not pr.axes_valid
                or pr.contact_normal_angle_deg > 1.0 or pr.tangent_yaw_mismatch_deg > 1.0):
            fails.append(f"{name}({pr.signed_clearance_m*1000:.1f}mm,pen={pr.is_penetrating},"
                         f"measurement={pr.measurement_valid},axes={pr.axes_valid},"
                         f"tilt={pr.contact_normal_angle_deg},yaw={pr.tangent_yaw_mismatch_deg})")
    return (not fails), f"{len(table)} scenarios, fails={fails or 'none'}"


def b2_tools():
    from human_eye_plugin import HumanEyeLLMPlugin
    p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
    expect = {
        "human_eye_inspect_scene_quad_canvas": ("mcp_image_content", "som_anchor_table", "total_tokens"),
        "human_eye_probe_spatial_clearance": ("alignment_state", "signed_clearance_mm", "rotation_euler_deg_xyz"),
        "human_eye_sync_low_token_scene_delta": ("status", "dsl_text", "dsl_tokens"),
        "human_eye_unproject_2d_click_to_3d": ("focal_pixel_uv", "mcp_tool_call"),
        "human_eye_issue_digital_twin_certificate": ("certificate_sha256", "overall_certified"),
    }
    missing = []
    for tool, keys in expect.items():
        out = p.dispatch_tool_call(tool, {"focal_click_or_box": [560, 560]} if "unproject" in tool else {})
        for k in keys:
            if k not in out:
                missing.append(f"{tool}.{k}")
    obs = p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {})
    act = obs["canonical_mcp_tool_call"]
    res = p.dispatch_tool_call(act["tool"], act["arguments"])
    for k in ("verification_passed", "post_recheck_metrics", "fsm_state", "applied_se3_action"):
        if k not in res:
            missing.append(f"apply.{k}")
    return (not missing), f"6 tools, missing={missing or 'none'}"


def b3_mcp():
    from human_eye_plugin.mcp_server import handle_jsonrpc_message
    init = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    if init["result"]["serverInfo"]["version"] != EXPECTED_VERSION:
        return False, "initialize version mismatch"
    tools = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    if len(tools["result"]["tools"]) != 6:
        return False, f"tools/list -> {len(tools['result']['tools'])}"
    ping = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    if ping.get("result") != {}:
        return False, "ping malformed"
    note = handle_jsonrpc_message({"jsonrpc": "2.0", "method": "notifications/initialized"})
    if note is not None:
        return False, "notification should return None"
    unk = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 4, "method": "no/such"})
    if unk.get("error", {}).get("code") != -32601:
        return False, "unknown method code"
    call = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                   "params": {"name": "human_eye_probe_spatial_clearance", "arguments": {}}})
    if "content" not in call.get("result", {}):
        return False, "tools/call content"
    # 真实 stdio 子进程
    lines = "\n".join(json.dumps(m) for m in [
        {"jsonrpc": "2.0", "id": 10, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 11, "method": "tools/list"},
    ]) + "\n"
    proc = _run_child("from human_eye_plugin.mcp_server import run_stdio_mcp_server\nrun_stdio_mcp_server()",
                      input_text=lines, timeout=120)
    if proc.returncode:
        return False, f"stdio failed: {proc.stderr[-1000:]}"
    outs = [json.loads(x) for x in proc.stdout.strip().splitlines() if x.strip()]
    if len(outs) != 2 or outs[0]["id"] != 10 or outs[1]["id"] != 11:
        return False, f"stdio handshake mismatch (lines={len(outs)})"
    return True, "in-process 5 methods + stdio 2 round-trips OK"


def b4_smoke():
    code = '''
import json
from human_eye_plugin import HumanEyeLLMPlugin, __version__
p=HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
obs=p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {"yaw_symmetry_order":2})
image=obs.get("mcp_image_content") or {}
if image.get("type")!="image" or image.get("mimeType")!="image/png" or not image.get("data"):
    raise RuntimeError("SDK smoke observation missing PNG")
if not obs.get("som_anchor_table"):
    raise RuntimeError("SDK smoke observation missing anchors")
action=obs["canonical_mcp_tool_call"]
result=p.dispatch_tool_call(action["tool"],action["arguments"])
probe=p.dispatch_tool_call("human_eye_probe_spatial_clearance",{"yaw_symmetry_order":2})
if not result["verification_passed"] or result["post_recheck_metrics"]["is_penetrating"]:
    raise RuntimeError("SDK smoke final pose failed")
print(json.dumps({"version":__version__,"verification_passed":result["verification_passed"],
                  "final_state":probe["alignment_state"],"anchor_count":len(obs["som_anchor_table"])}))
'''
    proc = _run_child(code, timeout=180)
    if proc.returncode != 0:
        return False, proc.stderr.strip().splitlines()[-1:] or "smoke failed"
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    ok = bool(data.get("verification_passed")) and data.get("final_state") == "ALIGNED_FLUSH"
    return ok, json.dumps(data, ensure_ascii=False)


# --------------------------------------------------------------------------
# C 稳定性
# --------------------------------------------------------------------------
def c1_determinism():
    import dataclasses
    from human_eye_plugin import HumanEyeLLMPlugin
    from human_eye_module1_operators import SpatialAnomalySniffer
    table = _scenarios()
    name = "S13_U_Channel_Slot"
    sigs = []
    for _ in range(3):
        meshes = [type(m).from_dict(m.to_dict()) for m in table[name]]
        focal = next(m for m in meshes if m.is_focal_target)
        ref = next(m for m in meshes if m.object_id != focal.object_id)
        pr = SpatialAnomalySniffer.probe_closest_clearance(focal, ref, yaw_symmetry_order=2)
        d = dataclasses.asdict(pr)
        d.pop("compute_time_ms", None)
        d.pop("roi_vertices_world", None)
        d.pop("intersection_seam_segments", None)
        sigs.append(hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16])
    return len(set(sigs)) == 1, f"3 runs signatures={sigs}"


def c2_isolation():
    from human_eye_plugin import HumanEyeLLMPlugin
    table = _scenarios()

    def run(name, args_key):
        p = HumanEyeLLMPlugin(meshes=list(table[name]), enable_zero_copy_ipc=False)
        obs = p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {})
        act = obs["canonical_mcp_tool_call"]
        if args_key:
            act = dict(act); act["arguments"] = dict(act["arguments"], **args_key)
        r = p.dispatch_tool_call(act["tool"], act["arguments"])
        return r["verification_passed"], round(r["post_recheck_metrics"]["residual_clearance_mm"], 4)

    a1 = run("S01_Horizontal_Table", None)
    run("S13_U_Channel_Slot", None)
    a2 = run("S01_Horizontal_Table", None)
    return a1 == a2, f"S01 first={a1} after S13={a2}"


def c3_edges():
    from human_eye_plugin import HumanEyeLLMPlugin
    p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
    detail = []
    try:
        p.dispatch_tool_call("no_such_tool", {})
    except ValueError as exc:
        detail.append(f"unknown tool -> ValueError({str(exc)[:24]})")
    else:
        return False, "unknown tool did not raise"
    obs = p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {})
    act = obs["canonical_mcp_tool_call"]
    bad = dict(act["arguments"], translation_xyz_m=[5.0, 5.0, 5.0])
    res = p.dispatch_tool_call(act["tool"], bad)
    if res.get("verification_passed"):
        return False, "absurd translation accepted"
    detail.append("absurd translation -> not passed")
    from human_eye_plugin.mcp_server import handle_jsonrpc_message
    r = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                                "params": {"name": "no_such_tool", "arguments": {}}})
    if not r["result"].get("isError"):
        return False, "mcp tool error not flagged"
    detail.append("mcp error isError=True")
    return True, "; ".join(detail)


def c4_non_watertight():
    import numpy as np
    from human_eye_module1_operators import MeshEntity3D, SpatialAnomalySniffer, SpatialAlignmentVerifier
    from module_3_3_closed_loop_control_engine import ClosedLoopActionController
    table = _scenarios()
    meshes = table["S04_Deep_Penetration"]
    ref = next(m for m in meshes if not m.is_focal_target)
    open_ref = MeshEntity3D(ref.object_id, ref.mark_label, ref.name, ref.vertices.copy(),
                            ref.faces[:-2].copy(), ref.edges.copy(), ref.color_rgb, False,
                            local_axes=ref.local_axes.copy())
    focal = next(m for m in meshes if m.is_focal_target)
    cosine = float(np.sqrt(.5))
    bad_axes_ref = MeshEntity3D(
        ref.object_id, ref.mark_label, ref.name, ref.vertices.copy(), ref.faces.copy(),
        ref.edges.copy(), ref.color_rgb, False,
        local_axes=ref.local_axes @ np.array([[cosine, -cosine, 0.],
                                             [cosine, cosine, 0.], [0., 0., 1.]]))
    detail = []
    rejected = 0
    for case, candidate, flag in (("open_hull", open_ref, "measurement_valid"),
                                  ("wrong_axes", bad_axes_ref, "axes_valid")):
        probe = SpatialAnomalySniffer.probe_closest_clearance(focal, candidate, yaw_symmetry_order=2)
        if getattr(probe, flag) or probe.is_aligned_flush:
            return False, (f"{case} did not invalidate {flag}: measurement={probe.measurement_valid}, "
                           f"axes={probe.axes_valid}, flush={probe.is_aligned_flush}")
        if case == "open_hull" and candidate.is_closed_hull:
            return False, "Open reference unexpectedly marked closed"
        before = focal.vertices.copy()
        for strict in (False, True):
            moved, report = SpatialAlignmentVerifier.execute_alignment_and_recheck(
                focal, candidate, strict_recheck=strict, yaw_symmetry_order=2)
            controller = ClosedLoopActionController(enable_zero_copy_ipc=False)
            controlled, controlled_report, fsm = controller.apply_se3_prescription_and_recheck(
                focal, candidate, strict_recheck=strict,
                mcp_arguments={"rotation_euler_deg_xyz": [0., 0., 0.],
                               "translation_xyz_m": [0., 0., .01],
                               "yaw_symmetry_order": 2, "enable_ecbf_safety_shield": True})
            if (report.verification_passed or controlled_report.verification_passed
                    or fsm.locked_certified or not np.array_equal(moved.vertices, before)
                    or not np.array_equal(controlled.vertices, before)
                    or not np.array_equal(report.posed_se3_4x4, np.eye(4))
                    or not np.array_equal(controlled_report.posed_se3_4x4, np.eye(4))):
                return False, f"{case}: strict={strict} invalid input passed or changed actual/reported pose"
            rejected += 2
        detail.append(f"{case}: {flag}=False, flush=False, method={probe.measurement_method}")
    return True, "; ".join(detail) + f"; {rejected} nominal/controller strict/fast actions rejected with identity pose"


# --------------------------------------------------------------------------
# D 性能
# --------------------------------------------------------------------------
def d1_perf():
    from human_eye_plugin import HumanEyeLLMPlugin
    from human_eye_module1_operators import SpatialAnomalySniffer
    inits = []
    for _ in range(5):
        t0 = time.perf_counter()
        p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
        inits.append((time.perf_counter() - t0) * 1000)
    p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {})   # 预热
    renders = []
    for _ in range(5):
        t0 = time.perf_counter()
        p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {})
        renders.append((time.perf_counter() - t0) * 1000)
    focal = next(m for m in p.meshes if m.is_focal_target)
    ref = next(m for m in p.meshes if m.object_id != focal.object_id)
    probes = []
    for _ in range(100):
        t0 = time.perf_counter()
        SpatialAnomalySniffer.probe_closest_clearance(focal, ref, yaw_symmetry_order=2)
        probes.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(probes, n=20)[-1]
    ok = statistics.median(inits) < 500 and statistics.median(renders) < 80 and p95 < 20
    return ok, (f"init p50={statistics.median(inits):.1f}ms render p50={statistics.median(renders):.1f}ms "
                f"probe p50={statistics.median(probes):.2f}ms p95={p95:.2f}ms")


def d2_cache():
    from human_eye_plugin import HumanEyeLLMPlugin
    from human_eye_module1_operators import SpatialAnomalySniffer
    p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
    focal = next(m for m in p.meshes if m.is_focal_target)
    ref = next(m for m in p.meshes if m.object_id != focal.object_id)
    focal._probe_cache = None
    peak = 0
    refs = [ref.translated((i*.001, 0.0, 0.0)) for i in range(600)]
    for changed in refs:
        SpatialAnomalySniffer.probe_closest_clearance(focal, changed, yaw_symmetry_order=2)
        peak = max(peak, len(focal._probe_cache or {}))
    size = len(focal._probe_cache or {})
    first_retained = any(entry[0] is refs[0] for entry in focal._probe_cache.values())
    last_probe = SpatialAnomalySniffer.probe_closest_clearance(focal, refs[-2], yaw_symmetry_order=2)
    same_probe = SpatialAnomalySniffer.probe_closest_clearance(focal, refs[-2], yaw_symmetry_order=2)
    last_entry = next(reversed(list(focal._probe_cache.values())))
    ok = peak <= 128 and size <= 128 and not first_retained and same_probe is last_probe and last_entry[0] is refs[-2]
    return ok, (f"600 distinct reference states; peak={peak}; retained={size}; limit=128; "
                f"oldest_evicted={not first_retained}; hit_promoted={last_entry[0] is refs[-2]}")


# --------------------------------------------------------------------------
# E 兼容
# --------------------------------------------------------------------------
def e1_detail_level():
    from human_eye_plugin import HumanEyeLLMPlugin
    p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
    act = p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {})["canonical_mcp_tool_call"]
    compact = p.dispatch_tool_call(act["tool"], act["arguments"])
    if "posed_se3_4x4" in compact["applied_se3_action"] or "verification" in compact:
        return False, "compact leaked full fields"
    if "verify_mode" not in compact["post_recheck_metrics"]:
        return False, "compact missing verify_mode"
    p2 = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
    act2 = p2.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {})["canonical_mcp_tool_call"]
    full = p2.dispatch_tool_call(act2["tool"], dict(act2["arguments"], detail_level="full"))
    if "posed_se3_4x4" not in full["applied_se3_action"] or not full.get("verification"):
        return False, "full missing pose matrix"
    return True, "compact/full fields correct"


def e2_backward_compat():
    from human_eye_plugin import HumanEyeLLMPlugin
    p = HumanEyeLLMPlugin(enable_zero_copy_ipc=False)
    obs = p.dispatch_tool_call("human_eye_inspect_scene_quad_canvas", {})
    act = obs["canonical_mcp_tool_call"]
    res = p.dispatch_tool_call(act["tool"], act["arguments"])
    legacy = ["mcp_tool", "verification_passed", "fsm_state", "locked_certified",
              "recommended_next_action", "pair", "stateTransition", "applied_se3_action", "post_recheck_metrics"]
    missing = [k for k in legacy if k not in res]
    sub = [("applied_se3_action", "rotation_euler_deg_xyz"), ("applied_se3_action", "translation_xyz_m"),
           ("post_recheck_metrics", "residual_clearance_mm"), ("post_recheck_metrics", "is_aligned_flush")]
    missing += [f"{a}.{b}" for a, b in sub if b not in res.get(a, {})]
    return (not missing), f"legacy keys missing={missing or 'none'}"


def e3_unit_tests():
    if MODE == "installed":
        return None, "SKIPPED: source-tree regression fixtures are not installed-package acceptance; runtime checks A2-E2 target only the explicit install"
    code = f'''
import json,unittest
suite=unittest.TestSuite()
suite.addTests(unittest.TestLoader().discover({str(ROOT/'verification')!r},pattern="test*.py"))
suite.addTests(unittest.TestLoader().discover({str(ROOT/'verification/optimized')!r},pattern="test_regression.py"))
result=unittest.TextTestRunner(verbosity=1).run(suite)
print(json.dumps({{"tests_run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
                  "skipped":len(result.skipped),"successful":result.wasSuccessful()}}))
sys.exit(0 if result.wasSuccessful() else 1)
'''
    proc = _run_child(code, timeout=300)
    if not proc.stdout.strip():
        return False, proc.stderr[-2000:] or "unit-test child produced no results"
    try:
        summary = json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return False, f"unit-test output malformed: {proc.stderr[-1000:]}"
    if proc.returncode:
        summary["error_tail"] = proc.stderr[-2000:]
    return proc.returncode == 0, summary


CHECKS = [
    ("A 产物", "A1 清单哈希校验", a1_bundle),
    ("A 产物", "A2 类身份唯一（单一真源）", a2_identity),
    ("A 产物", "A3 版本号一致", a3_version),
    ("B 功能", "B1 16 场景处方达标", b1_scenarios),
    ("B 功能", "B2 六个工具契约", b2_tools),
    ("B 功能", "B3 MCP 协议（进程内 + stdio）", b3_mcp),
    ("B 功能", "B4 SDK 冒烟子进程", b4_smoke),
    ("C 稳定", "C1 探针确定性（3 次位级一致）", c1_determinism),
    ("C 稳定", "C2 场景间状态隔离", c2_isolation),
    ("C 稳定", "C3 边界错误处理", c3_edges),
    ("C 稳定", "C4 无效几何与标架门禁", c4_non_watertight),
    ("D 性能", "D1 关键路径分位耗时", d1_perf),
    ("D 性能", "D2 缓存不无界增长", d2_cache),
    ("E 兼容", "E1 响应详略档位", e1_detail_level),
    ("E 兼容", "E2 旧字段向后兼容", e2_backward_compat),
    ("E 兼容", "E3 当前项目及优化版回归套件", e3_unit_tests),
]


def main() -> int:
    global MODE, SOURCE, EXPECTED_VERSION
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--mode", choices=("source", "installed"), default=None)
    ap.add_argument("--installed", action="store_true",
                    help="仅验证显式指定的安装目录；发行包哈希和完整性另行校验")
    ap.add_argument("--installed-target", type=pathlib.Path,
                    help="Installed mode requires an explicit directory containing the package and dist-info")
    args = ap.parse_args()
    if args.installed and args.mode == "source":
        ap.error("--installed conflicts with --mode source")
    MODE = "installed" if args.installed else (args.mode or "source")
    if MODE == "installed":
        if args.installed_target is None:
            ap.error("Installed mode requires --installed-target; source fallback is forbidden")
        SOURCE = args.installed_target.resolve()
        if not SOURCE.is_dir() or SOURCE == ROOT or (SOURCE / "pyproject.toml").exists():
            ap.error("--installed-target must be an installed package directory, not this source checkout")
        declared = [d.version for d in importlib.metadata.distributions(path=[str(SOURCE)])
                    if d.metadata["Name"].lower().replace("_", "-") == "human-eye-spatial-plugin"]
        if len(declared) != 1:
            ap.error("Explicit installed target must contain exactly one human-eye-spatial-plugin dist-info record")
        EXPECTED_VERSION = declared[0]
    else:
        if args.installed_target is not None:
            ap.error("--installed-target only applies to installed mode")
        SOURCE = ROOT
        EXPECTED_VERSION = _source_project_version()

    # Product code must never inherit a source or previous release search path.
    cleaned = []
    for entry in sys.path:
        if not entry:
            continue
        path = pathlib.Path(entry).resolve()
        if path == SOURCE:
            continue
        if path == ROOT or ROOT in path.parents:
            continue
        cleaned.append(entry)
    sys.path[:] = [str(SOURCE), *cleaned]
    sys.meta_path.insert(0, _TargetImportGuard())
    os.environ.pop("PYTHONPATH", None)
    os.environ["PYTHONPATH"] = str(SOURCE)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    print(f"Health mode={MODE}; target={SOURCE}; declared_version={EXPECTED_VERSION}")
    print(f"Scope: {_scope_description()}")

    for section, name, fn in CHECKS:
        check(section, name, fn)

    width = max(len(r["name"]) for r in RESULTS)
    cur = None
    for r in RESULTS:
        if r["section"] != cur:
            cur = r["section"]
            print(f"\n[{cur}]")
        label = {"passed":"PASS","failed":"FAIL","skipped":"SKIP"}[r["status"]]
        print(f"  {label}  {r['name']:<{width}}  {r['ms']:>7.1f}ms  {r['detail']}")

    total = len(RESULTS)
    passed = sum(r["status"] == "passed" for r in RESULTS)
    failed = sum(r["status"] == "failed" for r in RESULTS)
    skipped = sum(r["status"] == "skipped" for r in RESULTS)
    print(f"\n{'='*72}\n健康度：计划 {total} 项，执行 {total-skipped} 项；通过 {passed}，失败 {failed}，跳过 {skipped}")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(
            {"mode":MODE,"root":str(ROOT),"target":str(SOURCE),"declared_version":EXPECTED_VERSION,
             "scope":_scope_description(),
             "passed": passed,"failed":failed,"skipped":skipped,"executed":total-skipped,
             "total": total,"import_origins":IMPORT_ORIGINS,"results": RESULTS}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print("报告:", args.json)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
