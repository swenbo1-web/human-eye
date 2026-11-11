# M4-RELATION-SELECTED-EVIDENCE-001 独立代码与功能复核

固定证据提交：`be2de48bd9656787c4cdfbc5767c2551defcaada`。
固定产品提交：`a81e530a03460f93846e3bef4c45ebaa9347531b`，137 源，canonical SHA-256 `9f287f28a9be9ad0a06c0689b1fda3b15e9181efae0e280c0f2bcfed2d3ef504`。
对照产品：`e077fce38b5951efff8166b3b688d05ffa2ebf04` / `53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732`。
日期：2026-11-11。复核子任务：`/root/v21_algorithm_audit`。

## 结论

**几何附件的主路径和有限离线功能验收通过；公开接口还有一项应做的最小 schema 修复。** 未发现几何错绑、集合外公开、原 unknown 被放行、额外求解或缓存污染；无需新增防御层或第二套缓存。

已确认本次新引入的协议不一致：通用 `human_eye_scene_observe.query` schema 接受 `overview+geometry` 和旧 `task objects/aabb+geometry`，实际工具校验却拒绝。合法 `task target/candidates+geometry` 控制通过。精简关系工具不受影响，且无几何事实错误；但不能把公开声明允许、实际拒单留成“无需修”的注记。只收紧新 geometry 的适用域即可，独立于默认性能结论，详见第8节。

## 实际验证及身份

读取时实施 HEAD 是固定证据提交、tracked working tree clean。与基线相比只改三个产品文件：

| 文件 | diff |
|---|---:|
| `human_eye_plugin/task_query.py` | +50 / -3 |
| `human_eye_plugin/live_service.py` | +7 / -0 |
| `human_eye_plugin/live_spatial_mcp.py` | +19 / -3 |
| 总计 | **+76 / -6** |

已静态阅读 `CONTRACT.md`、三产品 diff、`read_context.py`、新定向测试、offline runner 及其选用的 fixture/旧测试范围，确认定向执行不需 Blender、网络、安装或外部服务。未调用 entry/installation runner。

本轮实际执行：

1. 将审核过的 offline runner 按原字节复制到本目录，重定向其输出和临时目录。runner 创建新的137源物理副本，用原 verified loader 加载，核对上述 canonical hash，禁用外部进程/网络/信号；执行 **22/22 方法通过，0 skip、0 failure、0 error**。
2. 在同一隔离、已核源码包补 **14 项检查全部通过**，涵盖全场 fallback 中集合外对象不公开、name/id 不混用、重复数组独立、原 unknown 优先、可选 triangles 不转换、关系不被修改、UTF-8 selector 合同与 legacy/nearest 拒绝等。14含重放和身份确认，不把它们称作14个新场景。
3. 保存基线 b2 的 `default_cold/default_warm` 与本轮实际重跑 candidate 对比。先核对双方完整源码 hash，仅把 hash 替换成相同身份占位并去瞬态 trace；其余结果、counts、residency_delta 都相同，geometry 均缺省。**基线本轮未重跑**。

证据文件：`SOURCE_PINS.json`、`candidate_replay/RESULTS.json`、`candidate_replay/EXECUTION_IDENTITY.json`、`candidate_replay/EVIDENCE.json`、`ADDITIONAL_CHECKS.json`、`DEFAULT_COMPARISON.json`，复现入口 `replay_code_review.py`。

4. 对精确复制的 query schema 使用下述明确静态规则，并调用真实 `validate_query` 和通用工具 `_validate_arguments`，实际确认两个错误允许案例与一个合法控制，见 `SCHEMA_SCOPE_REPRO.json`、`CANDIDATE_QUERY_SCHEMA.json`、`check_geometry_schema_scope.py`。未安装依赖；该补核不跑宿主、求解或消费者。

无真实 Blender、模型消费者、网络、安装、默认修改或性能测量。原 checkout/source/test/sealed evidence 字节未变检查通过。AL 子 assignment 仍归旧阶段，本轮不借父句柄、不代更新父任务、不将新证据伪归旧 assignment。

以下行号针对固定产品提交。

## 1. 输入只扩展既有 task-set，未扩大选择集合

`task_query.py:57–89` 在既有 target/candidates 或已归一化 task-set 形状中允许 geometry：必须是 dict、只有 objects/include_triangles、objects 为1..4 selectors，include_triangles 严格 bool。每个 selector 继续走 `49–54` 的单独 id/name、非空、256 UTF-8 bytes 规则；返回新字典，不保留调用者 selector 的可变引用。

旧 pair/AABB `90–102` 不接受 geometry；nearest 也继续拒绝。null、空列表、五项、混合 id/name、额外字段、非 boolean 在公共入口捕获之前拒绝，当前定向测试均覆盖。新增候选没有自行增加第五对象或以全场采集补足 geometry 请求。

`live_service.py:1350–1365` 把 geometry 从求关系的 query 中分离；宿主仍只收原 `query['objects']`，context.activate 的 selection 也没有显示选项。主关系集合最多4对象、geometry列表最多4项，重复请求按冻结合同保留。

集合外 selector 的拒绝发生在取得关系结果后（`task_query.py:232–233`），因此无效请求可能已有一次原关系捕获/计算；这不是额外扩捕获，也不能把其成本记成0。作者已说明该时序。本轮不要求再造预绑定层来把它前移。

## 2. unknown、别名、同名与身份

`task_query.py:216–248` 只从 `result.binding.objects` 获取可公开身份：

- `224–228` 首先找到与请求 selector **完全相同**的原 unresolved row，保留原 reason，优先于任何成功对象的 name alias。
- `219` 仅按成功 object ID 合并重复身份用于歧义判断。重复绑定同一对象不会伪造同名歧义；不同 ID 同名仍有多个 match，输出 `object_name_ambiguous`。
- `229–233` 按 selector 声明的键查 literal 值，没有 name→ID 猜测、大小写折叠、trim 绑定或“取第一个”。没有原绑定匹配就拒绝。
- 输出顺序和重复按用户 geometry 请求保留；每个成功 row 生成独立普通数组。

本轮定向补查使用“object ID=a、name=b，full-capture meshes 另含 ID=b 的未绑定对象”：geometry name=b 正确取 ID=a；geometry id=b 被拒绝，未绑定对象数组没有被转换。该测试验证即使 legacy host fallback 返回全场 mesh，新增投影也不会漏出关系范围外的几何。

原始同名 unresolved 与单独成功 ID 的组合、重复候选、缺失对象、开放壳关系 unknown 均通过。几何存在只说明该对象数组可显示，**不会改写 unknown 的固体事实、same-object/duplicate-candidate reason、summary 或 nearest**。

## 3. 同次捕获、单位与拓扑

`live_service.py:1367–1379` 将同次 context.normalized 的 meshes 同时供关系与显示；新增 helper 直接 `mesh.vertices.tolist()`，可选 `mesh.faces.tolist()`。它没有矩阵变换、再次缩放、to_mesh、三角剖分或求解器调用。

`task_query.py:245–247` 明确顶点是当前求值 world metres、捕获顺序；triangles 是同一顶点数组的零基 triplets，保留捕获顺序。没有误称原始 polygon IDs、孔识别、流形证明或损伤诊断。

几何在 observation lock 内附加，之后 `live_service.py:1380` 执行原 `_bind_read_result`，共享既有 scene revision/fingerprint、source、host身份、unit/frame。没有创建另一套 snapshot hash 或“可忽略旧代次”的缓存。

离线 RNA 测试以可精确表示的置换旋转、dyadic平移/scale，用独立 Fraction 前向表达式核世界点；triangles 取 fake RNA 的实际 loop-triangle 顺序。姿态变化触发1次世界准备、不重建mesh；局部几何变化触发该对象mesh/triangulation/world准备，并使关系和显示一起更新。**这些是有限宿主替身测试，不是本轮实测真实 Blender 变换误差**。

## 4. 默认路径与结果缓存

geometry 在 `ReadContext.query_key` 前被剥离，显示开关、顺序、别名、是否 triangles 都不产生新的关系 cache key。`read_context.py:67–79` 的 result 在 miss 和 hit 都返回 deepcopy；新增字段附加在该 detached copy 上，关系缓存没有 geometry。

新增数组通过 tolist 与原 mesh 分离。本轮额外实际修改同响应的第一个重复 row 的 vertices/triangles，第二个 row 和源 mesh 不变；已有测试还修改返回字段再查，后续 default 及 geometry 都未受污染。输入 selector 和原关系 result 也未被 helper 改动。

缺省 geometry 时 `live_service.py:1376` 不进 helper，不做新增别名匹配、tolist、triangle转换或geometry contract。候选默认测试将 helper 替换成一调用即抛错仍通过；冷/暖 relation工作与保存基线一致。确实存在几次轻量 key/形状判断，故“默认没有新增投影工作”准确，“默认绝对零 CPU 增量”不应声称。

`result_cache_hit=true` 与 `engine_invoked=false` 只表示关系结果命中、几何内核未重跑；显式 geometry 仍发生tolist和编码。源码没有新增 geometry 计数器，实际成本必须看入口采样/输出字节，而不能把这两个字段等同于显示免费。

## 5. 公共输出不会改变事实

`live_spatial_mcp.py:304–312` 把显式选项传到既有 normalizer；`353–372` 不接受非合同参数。公共 compact projection `658–661` 只在原结果存在 geometry 时带出附件，不另算或改写关系。

JSON结果只得到本次 detached投影，不会持有缓存数组。geometry 成功行不附加“关系已验证”状态；unknown 行没有几何数组。旧 wholly-unknown 工具回包仍 `isError=true`，与几何存在与否无关；该行为是原合同，不是新增误拒。

从固定源码看，没有将原无向/有向关系混淆、把未知转换成功或把显示选项变成执行许可的路径。

## 6. 原 QA 失败纠正是否削弱验收

独立比较初版 `tests/history/test_selected_geometry_01.py` 与当前测试：唯一逻辑调整是从“一律 isError=false”改成 `isError == status not in {'observed','partial'}`。c1三项失败都停在旧一律False断言；几何、身份、ambiguity、unknown 等后续断言未删除。

c1与c2都是相同 `9f287f28…ef504` 产品。该修正与原 MCP 的 wholly unknown 语义一致，没有为了让候选通过而削弱业务判定。本轮重新实际跑到这些后续断言并通过，旧失败记录继续保留。

实际 source-check 曾把注册修改的 binary64 literal 与 Blender binary32 存储直接比较的失败属于另一条入口数据核对；本子任务仅阅读其保留说明，未重跑或替其验收，交父任务对应来源审查。

## 7. 一次简化与是否还需继续优化

冻结实现直接复用原绑定和 detached结果，省去了第二次 bind、额外选定快照和几何缓存，已经满足本批“薄附件”的设计目的。别名查询最多4×4匹配，额外 memo/cache 不会自然带来值得付出的收益；重复用户请求还需要保持输出彼此独立。

没有证据支持为了“再优化一次”重写几何投影。当前简化评审选择保持单 helper、无新增层是合理结果。第8节仅要求修新字段的公开适用域，不改变几何实现。后续收益归因应关注是否减少真实补读、增加多少schema/几何字节以及模型是否消费，不应再刷这个小循环。

## 8. [P2] 新 geometry 公开适用域过宽：唯一最小修复

`live_spatial_mcp.py:79` 将 geometry 放入通用 `_QUERY_SCHEMA.properties`，但现有条件只限制 surface_nearest 和部分 task 形状。overview 不触发 task 条件；`105–106` 的 legacy objects 分支也没有排除 geometry。因此以下两个实际通用工具参数在 schema 上被允许，运行时却在捕获前拒绝：

```json
{"query":{"mode":"overview","geometry":{"objects":[{"id":"a"}]}},"include_image":false}
```

```json
{"query":{"mode":"task","objects":[{"id":"a"}],"requested_facts":["aabb"],"geometry":{"objects":[{"id":"a"}]}},"include_image":false}
```

合法控制使用 `mode=task`、`target={id:a}`、`candidates=[{id:b}]`、两项 required facts 及相同 geometry，schema 和真实工具校验均接受。

本环境没有第三方 jsonschema 包，不安装新依赖。复现器读取受核源生成的真实 `_QUERY_SCHEMA`，明确求值这三个输入实际经过的规则：type/properties/required/additionalProperties、allOf/anyOf/oneOf、if/then、enum/const、items/contains、数量/长度/uniqueItems；遇未知关键词就失败，不静默忽略。另保存完整 schema 便于标准验证器复核。runtime 侧实际调用产品原 `validate_query` 和 `_validate_arguments('human_eye_scene_observe',...)`，没有服务对象或宿主请求。

**introduced 确认**：保存的基线137源文件通过其 manifest SHA 核对，旧 `_QUERY_SCHEMA` 没有 geometry property，顶层 `additionalProperties=false` 会拒绝两个输入。候选新增全局 property 后放宽了 schema，runtime 仍按既有分支拒绝，所以这是本次新选项造成的协议误宣告，而不是泛指旧 schema 所有不精确之处。

最小修正：在通用 `_QUERY_SCHEMA.allOf` 增加“若包含 geometry，则必须有 mode/target/candidates 且 mode=task”的条件，利用现有 target/candidates 分支继续核对事实和不允许 objects。示意：

```json
{"if":{"required":["geometry"]},"then":{"required":["mode","target","candidates"],"properties":{"mode":{"const":"task"}}}}
```

仅限制新 geometry 适用域。保持 compact 工具、runtime校验、legacy拒绝、选择集合和几何实现不变，不扩修其他历史宽 schema，不增加业务层。这一修复及三个协议控制应作为唯一小修，不需要因此重跑几何性能优化。源码版本/源码身份变化后的必要同版检查由父任务安排。

影响是模型依据通用公开 schema 构造参数后遭到拒单，影响可用性；不是几何泄漏/错误判定。它与默认路径性能问题完全独立，不能被正常 compact 测试通过或微秒耗时覆盖。

## 9. 最终状态

**通过**：固定137源守护加载；22项原定向/回归方法；14项补查；默认冷热结果与保存基线一致；原unknown优先；别名与重复身份；最多4项；只公开原绑定；同代显示开关不增加关系求解；输出与缓存隔离；默认无新增数组投影。

**没有发现**：需要修复的绑定、数值、关系结论、缓存污染或实际捕获范围扩大缺陷。

**确认待修**：新 geometry 的通用 query schema 适用域比runtime宽，两个真实参数案例误宣告允许、合法控制正常。最小修复只限该新字段适用域；无需改变正常compact几何路径。

**本轮未测**：真实Blender/stdin/隔离安装、实际RPC和整链成本、性能回归、模型消费与净收益。这些必须按父任务的独立证据审查处理，不能从22项离线通过自动推导。
