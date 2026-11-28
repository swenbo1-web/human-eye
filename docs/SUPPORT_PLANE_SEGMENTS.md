# 支撑平面有界执行段

```json
{
  "session_id": "caller-session",
  "request_id": "unique-reviewed-goal",
  "execute": false,
  "include_image": false,
  "request": {
    "solver": "support_plane",
    "focal_id": "current-focal-full-id",
    "reference_id": "current-reference-full-id",
    "reference_triangle_index": 2,
    "direction_world": [0, 0, 1],
    "target_clearance_m": 0.001,
    "clearance_tolerance_m": 0.0000005,
    "max_steps": 8,
    "max_step_translation_m": 0.005,
    "max_total_translation_m": 0.04,
    "max_duration_s": 20
  }
}
```

示例ID和面索引须由当前快照替换，2不是通用上表面。新分支没有axis；旧分支继续省略solver并使用明确的axis。execute默认为false；预览不保留回执、不移动，局部候选也不赋予执行资格。

执行时每步复用[支撑面数学合同](SUPPORT_PLANE_CANDIDATE.md)，并保留完整场景fresh检查、宿主编辑／身份／精度、提交版本、回读、累计实际位移、步数与时间预算、停滞／振荡停止和不明提交隔离。没有连续路径或运行中即时取消认证。支撑面目标签名不能代替形状、实例或外部编辑检查。

首次规划在创建running记录前完成，非法面索引／缺失对象不留下未完成账本，规划耗尽时间也不开始执行。方向原有限向量转float后持久化，仅求解时归一化，保证账本反复载入不会因归一化舍入改变参数指纹。同ID同参数是历史回执，当前场景不会因此重新核验或移动；同ID异参数拒绝。提交不明不自动重试。
