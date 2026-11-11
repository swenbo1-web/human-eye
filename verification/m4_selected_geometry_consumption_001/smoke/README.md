# G 隔离入口烟测准备

本批 G 固定为 00b13060、137 源 canonical 4ebc3910…5c76c，独立外部版本为 9.7.2+sg.r1。P 沿用 e077 的 lr.r1 安装。两者源、封存 wheel、入口、绑定及共同依赖的只读核对保存在 installation/VERIFIED_P_G.json。

烟测直接使用 m4_local_relation_consumption_001/runtime/actor.py 的原 Peer，配合 native_plugin_complex_003/reused/accepted_native.py 的原 NativeSession。该 backend 源摘要为 13887e30…59b8。它保存原指纹、文件保护、期限、代码和输出日志及拥有进程的关闭记录。源码中没有 QA profiler。

```text
python -I -B -X utf8 smoke/run_smoke.py --output run_01
```

root 记录合同并授权后，最多启动一个拥有生命周期的后台 Blender。元数据固定为 initialize、initialized notification、tools/list、ping，要求宿主 RPC 为零。随后 OFF、vertices、full 各一个相同关系请求，geometry 选择固定 fixture 中的两个对象。三个业务 RPC 与一个 close 原件均保留。实际失败会结束本轮烟测。

几何来源核对读取每次实际宿主代码和 stdout，绑定内部请求 ID、完整 selector 集合与捕获代。首次实际回包中的资源包含局部顶点、实际矩阵、米制比例及捕获三角连接。期望世界坐标由这些值前向计算，三角索引逐值对应其捕获数组。后两次须保持同代并复用首次资源。该解析是 QA 来源核对，原始捕获与三个 stdio 响应各自完整保存。

三个响应的核心事实连同 context 逐值一致，仅 trace 和显式 geometry 外层单独检查。OFF 省略 geometry，vertices 返回所选世界顶点，full 同时返回对应三角索引。后两次关系结果须命中已有缓存且内核计数为零。既有同次工作与 schema 离线记录作为来源依据。本烟测范围为这三个公开请求及其附件。

原 Windows helper 在元数据后持有实际产品 PID 的句柄，产品关闭后核对该 PID 的退出和 exit0。Blender 则核对 closed 回执、拥有的 Popen、未 poison 的终态、原指纹与文件摘要。实际工具目录、加载身份和源摘要在本会话记录。

STATIC_PRECHECK.json 仅记录对旧 53db 冻结捕获的解析与前向计算检查。新 G 的实际 smoke 在 root 授权后单独记录。本准备阶段模型消费者为零，正式九格由本批后续唯一 GO 控制。
