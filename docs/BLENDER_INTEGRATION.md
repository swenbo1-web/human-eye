# Blender 宿主接入

实时服务通过 BlenderMCP 回环连接读取已打开的 Blender 场景。项目连接配置指定宿主地址、受信引擎根和状态路径。桌面常用地址为 `127.0.0.1:9876`。Blender 中需要先启用对应的连接器。[宿主实现](../human_eye_plugin/blender_mcp_host.py)

## 核对一次真实读数

1. 核对 MCP 的 `human_eye_connection_status` 与预期发行身份。
2. 在已打开的场景中选两个已知对象，用 `human_eye_scene_observe` 请求 `task`、有序的 `objects`、`surface_proximity` 及 `include_image=false`。
3. 核对回包的有效性、对象顺序、米制距离和世界方向。有图任务还应核对返回的原帧、源三角和像素归属。

连接到用户窗口时，读取使用当前求值几何和有效显示范围。独立实验可启动自有后台 Blender，并在退出时核对初末场景和进程关闭。编辑、回读和状态恢复使用各自的动作合同。[架构](ARCHITECTURE_ANALYSIS.md) · [安装入口](INSTALLED_RELEASE_ACTIVATION.md)
