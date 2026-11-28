# Human Eye · 人类之眼

Human Eye 把 Blender 当前场景里的空间问题转成可核查的答案。它可以量两个对象或指定面区之间的最短距离，给出世界坐标中的最近点和源三角，也可以选择观察方向，返回带像素归属的原图。

`main` 对应桌面发行版 **9.7.2+k049final**。安装版包含五个公开 MCP 工具、桌面 Hook 和带 032 回退的表面距离求解器。发行身份、复现步骤和历史验收入口分别见[版本记录](docs/PROGRESS.md)和[开发与测试](docs/DEVELOPMENT.md)。

| 要做的事 | 从这里开始 |
| --- | --- |
| 连接正在使用的 Blender | [Blender 接入](docs/BLENDER_INTEGRATION.md) |
| 配置 MCP、Hook 或检查已有桌面安装 | [Agent 接入](docs/AGENT_SETUP.md) · [安装版核对](docs/INSTALLED_RELEASE_ACTIVATION.md) |
| 了解选区、几何传输、精确量测与取景之间的关系 | [产品架构](docs/ARCHITECTURE_ANALYSIS.md) |
| 运行回归、构建可复现的 wheel | [开发与测试](docs/DEVELOPMENT.md) |
| 查下一步方向、定位专项实验 | [研发路线](docs/PRODUCT_ROADMAP.md) · [本机目录约定](docs/HUMAN_EYE_WORKSPACE.md) |

公开查询从 `human_eye_scene_observe` 进入。例如，对名字已知的两个对象求整件距离，可以提交下列工具参数。用当前场景的对象名替换示例值。回包给出距离是否有效、单位、点对及方向。

```json
{
  "include_image": false,
  "query": {
    "mode": "task",
    "objects": [{"name": "Part"}, {"name": "Reference"}],
    "requested_facts": ["surface_proximity"]
  }
}
```

`human_eye_connection_status` 可核对当前加载版本。`human_eye_arm_twist_observe` 提供手臂扭转观察。涉及实际动作时，`human_eye_transform` 和 `human_eye_clearance_segment` 使用各自的验证与执行协议。
