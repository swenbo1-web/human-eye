# 精简支撑面发现与执行入口

## 作用与流程

明确 focal/reference 对象对后，调用者可显式请求少量当前支撑面选择器，无需先传完整网格给模型或手算三角面索引。流程是 fresh 捕获 → 精确支撑面发现 → 回填完整 selector → 预览／有界执行段 → 每步重新门检、提交和读回。引擎负责已授权目标内的局部纠偏；调用者仍明确给出对象对、移动方向、目标和预算。

算法只接受既有闭合凸体和原始有限三角面的受支持情形。两网格只准备一次精确有理表示，参考原面按精确有向平面分组，每组保留确有有限三角垂足见证的最小原面索引，并与严格几何距离核对。不以拟合面或凸包替换原几何，不扩展为任意凹体、多壁语义或连续路径认证。

## 显式查询

通过现有 human_eye_scene_observe 工具调用，不增加工具或 Hook 数量：

~~~json
{
  "session_id": "caller-session",
  "focal_id": "current-focal-full-id",
  "reference_id": "current-reference-full-id",
  "include_image": false,
  "response_detail": "brief",
  "query": {
    "alignment_evidence": false,
    "support_plane_discovery": {
      "direction_world": [0, 0, 1],
      "max_candidates": 4
    }
  }
}
~~~

support_plane_discovery 是可选对象，只接受 direction_world 和 max_candidates。上限必须是整数 1—6，默认 4；布尔值不作为整数。方向可省略，省略时只做几何发现，不推断动作方向；提供时须为三个有限数字且范数有限非零。方向用于判定支撑面是否适合所给移动方向，不代表已批准动作。

默认查询不增加发现计算，默认原生 PNG 行为保持；include_image:false 才显式关闭图片。省略 scene_delta 可避免传完整网格；确实需要完整几何时仍可另行显式请求，但不是使用 selector 的前置要求。

结果位于 support_plane_discovery。检查 status、measurement_valid、enumeration_complete、all_candidates_returned、ambiguous、候选数量和 reason_codes。没有候选、截断、歧义、资源不足或 unknown 时，不猜一个“上表面”。局部可用 selector 也不覆盖全场 unknown 或执行门的拒绝。

## 完整 selector 与失效规则

每个候选的 selector 保持完整直接可读：

~~~json
{
  "reference_triangle_index": 2,
  "selection_binding": {
    "scene_revision": "current-captured-revision",
    "scene_fingerprint": "current-64-lowercase-hex-digest",
    "focal_id": "current-focal-full-id",
    "reference_id": "current-reference-full-id"
  }
}
~~~

2 仅展示返回值形状，不是通用面号。应直接回填所选候选的完整 selector；不要只复制面索引、丢掉绑定或手写绑定值。绑定覆盖当前完整场景 revision/fingerprint 和对象对，不是授权、人类意图证明或跨重建的语义面身份。

以下 Python 只构造请求；observed_metadata 代表刚收到的当前工具 metadata：

~~~python
discovery = observed_metadata["support_plane_discovery"]
assert discovery["status"] == "complete"
assert discovery["all_candidates_returned"] and not discovery["ambiguous"]
assert len(discovery["candidates"]) == 1
selector = discovery["candidates"][0]["selector"]

segment_arguments = {
    "session_id": "caller-session",
    "request_id": "unique-reviewed-goal",
    "execute": False,
    "include_image": False,
    "request": {
        "solver": "support_plane",
        "focal_id": discovery["focal_id"],
        "reference_id": discovery["reference_id"],
        **selector,
        "direction_world": [0, 0, 1],
        "target_clearance_m": 0.001,
        "clearance_tolerance_m": 0.0000005,
        "max_steps": 8,
        "max_step_translation_m": 0.005,
        "max_total_translation_m": 0.04,
        "max_duration_s": 20.0,
    },
}
~~~

调用现有 human_eye_clearance_segment 预览；目标、方向和预算经调用者确认后，再按同一意图执行。多候选时需要明确选择依据，不能把返回顺序当作意图。

新请求 ID 在首次 fresh 捕获后、规划和创建新账本前核对绑定；场景改变时返回 support_plane_selection_stale_revision 等明确拒绝，executed:false、requires_reobserve:true，不预留新执行回执。执行段自身的受控移动不反复要求最初 revision，但每步的全场、宿主实例、精度、提交版本和读回门保持。恢复目标须先重新发现当前 selector。

相同请求 ID、相同参数优先返回历史回执，即使当前场景已变化；这是防止重复执行的幂等性。检查 replayed:true、historical_receipt:true 和 current_scene_revalidated:false，不能把历史成功当作当前目标仍满足的证据。同 ID、不同参数拒绝；不明提交不自动重试。旧手工原面索引和世界轴箱体请求继续兼容；使用发现结果时应保留完整绑定。执行合同见 [SUPPORT_PLANE_SEGMENTS.md](SUPPORT_PLANE_SEGMENTS.md)。
