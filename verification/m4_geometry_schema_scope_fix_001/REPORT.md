# M4-GEOMETRY-SCHEMA-SCOPE-FIX-001

通用 `human_eye_scene_observe.query` 的 geometry 适用域已修正。出现 geometry 时，公开 schema 要求 `mode=task`，并要求 target 和 candidates。原有 task 分支继续负责必需事实与 objects 的约束。

## 固定来源与最小改动

基线证据提交为 `be2de48bd9656787c4cdfbc5767c2551defcaada`，基线运行源为 `a81e530a03460f93846e3bef4c45ebaa9347531b`，137 源摘要 `9f287f28a9be9ad0a06c0689b1fda3b15e9181efae0e280c0f2bcfed2d3ef504`。

本次只向 `live_spatial_mcp.py` 的 `_QUERY_SCHEMA.allOf` 追加一个 if/then 条件，Git 差异为 4 行增加、1 行替换，文件增加 188 字节。新运行来源仍有 137 个文件，规范摘要为 `4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c`。

AST 比对在移除这一附加条件后，整个模块与基线严格相等。字节比对通过一次精确替换还原整个文件，其他 136 个运行源逐文件摘要相等。精简工具定义、运行时校验、几何、绑定、缓存与求解逻辑的保留均有上述比对支持。SOURCE_DIFF.json 保存完整来源及差异证明。一次简化复核选择保留单条件并复用既有分支。

第一次受保护的编辑使用了 CRLF 锚点，锚点断言在写入前停止。按实际 LF 锚点执行后完成唯一产品修改，记录见 EDIT_RECORD.json。

## 定向验证

4 个测试方法通过，包含 20 个固定通用查询案例、3 组精简工具 schema 与实际参数校验控制，以及 OFF、vertices、full 的 3 次内存宿主实际派发。失败、错误及跳过均为零。

| 固定输入 | 基线 schema | 本次 schema | 实际运行时 |
|---|---|---|---|
| overview 附带 geometry | 接受 | 拒绝 | 保留原理由拒绝 |
| 旧 task objects/aabb 附带 geometry | 接受 | 拒绝 | 保留原理由拒绝 |
| 合法 target/candidates task 附带 geometry | 接受 | 接受 | 接受 |
| 无 geometry 的 overview、旧 task/aabb | 接受 | 接受 | 接受 |
| surface_nearest 附带 geometry | 拒绝 | 拒绝 | 拒绝 |

其余固定案例核对 geometry 出现但 mode、target 或 candidates 缺失、objects 冲突、缺少必需关系事实，以及既有字段拒绝条件。精简工具三组控制的定义和返回事实比较通过。单候选源码隔离副本的 137 源摘要、加载 guard、测试及参考脚本在执行前后检查通过。

schema 检查采用根复审脚本中已明确范围的静态规则求值器，未知的已访问关键词会报错。完整两版 schema、求值器与来源摘要保存在 r1。该求值器覆盖本批固定输入经过的规则。实际 validate_query 和两类工具参数校验使用当前受 guard 保护的源码。

基线 schema 从精确 Git 源码的 AST 提取，基线校验函数通过源码及 AST 等价核对。旧运行时没有重新执行。当前执行身份为源码隔离副本的 `unregistered_runtime`，本批验证范围为离线协议及有限内存宿主。

## 未运行与准入边界

本批新增 Blender 会话、产品业务会话、安装、模型消费者、图片、付费调用及性能重采样均为零。新来源的隔离安装、真实 Blender 入口、模型消费与性能尚未验证。

上一候选 a81 的默认暖请求曾观察到 +1.341 毫秒、约 +3.57% 的回退，其完整准入仍未通过。本次协议修复只解决新字段适用域误宣告，先前未决结果继续保留。新来源没有获得性能保持或完整发布准入。

结果入口为 r1/RESULTS.json、r1/EVIDENCE.json、SOURCE_DIFF.json、REVIEW.md 与本批工作单。Agent Learning 自身绑定仍缺失，本批依照管理员允许的本地工作单记录。提交后交管理员独立复核，本批结束。
