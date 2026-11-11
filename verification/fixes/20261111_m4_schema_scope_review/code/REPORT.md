# M4 geometry schema scope：独立复核

结论：**本次新增 geometry 适用域的 schema / runtime 不一致已关闭。未发现新的代码缺陷。** 此结论只验收该最小修复；既有默认 OFF 性能问题未决，没有重测性能或作整版收益结论。

## 固定对象及改动范围

- 实施 Git HEAD：`00b13060a3cbe709b38f6e98ce04a6e5c3dabfb4`；基线 `be2de48bd9656787c4cdfbc5767c2551defcaada` / 产品 `a81e530a03460f93846e3bef4c45ebaa9347531b`。
- 本轮执行的 137 源 canonical SHA-256：`4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c`。
- 唯一运行源差异为 `human_eye_plugin/live_spatial_mcp.py:112–114`，在 `_QUERY_SCHEMA.allOf` 末尾添加条件：有 `geometry` 时必须同时具有 `mode=task`、`target` 和 `candidates`。原有 task 条件继续要求事实集合。净增 188 字节，其他 136 源未变。
- 独立从 Git 读取旧模块；从已固定 r1/e 快照读取新模块。逐文件复算 137 源身份、与工作树逐字节比对；删除新条件后，整个 MCP 模块 AST 与基线完全相同。运行时校验、转换和处理函数均未改动。
- 新 MCP 文件 SHA-256：`0bb0733babb117a6ef6b0afc20bd451a700c347f047f867c4b10434d9222f326`。旧文件：`b52f6468e6b71eb10b065a89b3417c1ee025e464b9be84d32b0b5625cd1b6275`。

## 本轮实际独立执行

运行 `review_schema_scope.py`，退出码 0。脚本只读取作者已有快照，没有另拷 137 源，没有运行作者 runner / 测试类或服务 dispatch。实际产品校验函数通过 verified source loader 执行上述同一份核验字节。

| 独立检查 | 实际结果 |
|---|---|
| 审核后独立重述的 20 个 generic query 案例：旧 schema、新 schema、`validate_query`、generic `_validate_arguments` | 20/20 与预定结果一致 |
| 原 `overview + geometry`、旧 `task objects/aabb + geometry`、仅 `geometry` | 旧 schema 接受；新 schema 拒绝；真实运行时均拒绝 |
| 正常 task geometry 顶点 / 顶点与三角形及可选 AABB | schema 与运行时均接受 |
| 缺 mode / target / candidates / facts、缺必要事实、混用 objects、非法事实、空 geometry、非布尔 include_triangles | schema 与运行时均拒绝 |
| 无 geometry 的正常 task、overview、默认 query、旧 AABB、surface_nearest | 原有接受结果保留 |
| compact OFF / vertices / full schema、真实参数校验及 query 转换 | 3/3 通过；compact 整个公开 schema 与旧版相同 |
| 137 源身份、整模块 AST 差异、运行前后工作树与快照字节 | 全部通过；工作树 tracked 状态前后均干净 |
| guard.verify_loaded、外部进程 / 网络 / signal 调用拦截 | 通过；外部调用尝试 0 |

20 是明确查询案例数，3 是 compact 参数控制数；不能记作 23 个独立场景或模型消费样本。schema 检查复用先前审核的 `accepts` 函数 AST，执行本次访问到的显式 JSON Schema 规则，对未知关键字报错；**不是完整 JSON Schema 库或宿主协议兼容性认证**。没有重新执行旧版运行时；已独立证明旧、新运行时相关代码相同，实际执行新版。

## 作者记录与本轮证据分开

作者 r1 记录：4 个 unittest 方法、20 个 generic 案例、3 个 compact 参数控制，以及 3 次有限内存 host 的真实产品 dispatch；均通过。已阅读其测试定义、RESULTS/EVIDENCE、来源摘要与 runner。作者三次 dispatch 覆盖 OFF / vertices / full、同核心结果及相应几何内容，本轮没有重跑该服务路径，不能作为本轮独立运行成绩。

本轮实际执行：上述 20 + 3 参数级检查及源码身份检查。机器记录在 `RESULTS.json`，Git / manifest / 脚本 / 作者证据固定摘要在 `SOURCE_PINS.json`。零 Blender、零服务实例/dispatch、零模型、零安装、零性能测试、零新增运行源副本。

## 后续边界

这个新字段导致的公开参数误导已由一条条件修复，可以关闭这一项。未扩修历史通用 schema，也未改变几何能力或默认输出。先前 a81 默认 warm 增加约 1.341 ms / 3.57% 是已有作者记录，本轮未独立复测，继续单独归因；不得用这次 schema 通过替代性能验收。

复现命令：

```powershell
& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -X utf8 'D:/hefe/verification/fixes/20261111_m4_schema_scope_review/code/review_schema_scope.py'
```

输出采用独占创建；已有 `RESULTS.json` / `SOURCE_PINS.json` 时重跑应换一个新审查输出目录，不覆盖历史结果。
